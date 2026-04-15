from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config.settings import Settings, get_settings
from app.models.query import CandidateSource, QueryRequest, QueryResponse
from app.models.sources import SqlConnectionRequest, WorkspaceState
from app.query_engine.executor import execute_sql_sub_query, execute_sub_question
from app.query_engine.intent_layer import has_data_question_intent
from app.query_engine.operation_sufficiency import enforce_operation_sufficiency
from app.query_engine.query_parser import deterministic_parse_query, parse_query, source_score
from app.query_engine.raw_sql_planner import plan_raw_sql_query
from app.query_engine.semantic_grounding import ground_operation_values
from app.query_engine.summarizer import summarize_results
from app.query_engine.visual_planner import enrich_charts_with_llm
from app.providers.factory import ProviderRouter
from app.services.sql_connection_manager import connect_sql_source
from app.services.upload_manager import UploadLimitError, ingest_uploads
from app.services.workspace import workspace

router = APIRouter(prefix="/api")


@router.get("/workspace", response_model=WorkspaceState)
def get_workspace(settings: Settings = Depends(get_settings)) -> WorkspaceState:
    return WorkspaceState(
        sources=workspace.list_metadata(),
        uploaded_file_count=workspace.uploaded_file_count,
        max_total_files=settings.max_total_files,
        max_file_size_mb=settings.max_file_size_mb,
    )


@router.post("/uploads")
async def upload_files(
    files: list[UploadFile] = File(...),
    should_clean: bool = Form(False),
    settings: Settings = Depends(get_settings),
):
    try:
        sources, cleaning_reports = await ingest_uploads(files, should_clean, settings)
        return {"sources": sources, "cleaning_reports": cleaning_reports}
    except UploadLimitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/sql")
def add_sql_source(request: SqlConnectionRequest, settings: Settings = Depends(get_settings)):
    if len(workspace.sources) >= settings.max_total_files:
        raise HTTPException(status_code=400, detail=f"Workspace limit reached. This workspace allows {settings.max_total_files} sources total.")
    try:
        return connect_sql_source(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/sources/{source_id}")
def remove_source(source_id: str):
    if not workspace.remove(source_id):
        raise HTTPException(status_code=404, detail="Source not found.")
    return {"removed": True, "source_id": source_id}


@router.post("/query", response_model=QueryResponse)
async def run_query(request: QueryRequest, settings: Settings = Depends(get_settings)) -> QueryResponse:
    sources = workspace.list_metadata()
    if not sources:
        raise HTTPException(status_code=400, detail="Add a CSV, XLSX, SQLite, MySQL, or PostgreSQL source first.")
    if request.preferred_source_id:
        selected_source = next((source for source in sources if source.id == request.preferred_source_id), None)
        if selected_source is None:
            raise HTTPException(status_code=400, detail="Selected source was not found.")
        sources = [selected_source]
    source_ids = {source.id for source in sources}
    sources = workspace.metadata_with_query_value_samples(request.question, source_ids)
    if not has_data_question_intent(request.question) and not any(source_score(source, request.question) > 0 for source in sources):
        raise HTTPException(
            status_code=400,
            detail="I could not match that question to the available sources. Mention a source, column, value, or ask for a data operation like count, top rows, trends, or a chart.",
        )
    routing_hint = deterministic_parse_query(request.question, sources)
    if routing_hint.needs_source_confirmation:
        candidate_sources = [
            CandidateSource(id=source.id, name=source.name, columns=[column.name for column in source.columns[:10]])
            for source in workspace.list_metadata()
            if source.id in routing_hint.candidate_source_ids
        ]
        return QueryResponse(
            needs_source_confirmation=True,
            source_confirmation_message="I found multiple datasets that could answer this. Which source should I use for this query?",
            candidate_sources=candidate_sources,
            debug=routing_hint.model_dump() if settings.is_dev_mode else None,
        )
    if (
        len(sources) > 1
        and not routing_hint.likely_requires_join
        and len(routing_hint.sub_questions) == 1
        and routing_hint.sub_questions[0].source_id
    ):
        routed_source_id = routing_hint.sub_questions[0].source_id
        sources = [source for source in sources if source.id == routed_source_id]

    provider_router = ProviderRouter(settings)
    provider = provider_router if provider_router.available else None
    raw_sql_error = None
    sql_plan = await plan_raw_sql_query(request.question, sources, provider)
    if sql_plan is not None:
        if sql_plan.needs_source_confirmation:
            candidate_sources = [
                CandidateSource(id=source.id, name=source.name, columns=[column.name for column in source.columns[:10]])
                for source in workspace.list_metadata()
                if source.id in sql_plan.candidate_source_ids
            ]
            return QueryResponse(
                needs_source_confirmation=True,
                source_confirmation_message="I found multiple datasets that could answer this. Which source should I use for this query?",
                candidate_sources=candidate_sources,
                debug=sql_plan.model_dump() if settings.is_dev_mode else None,
            )

        if settings.enable_join_confirmation and sql_plan.likely_requires_join and not request.allow_joins:
            return QueryResponse(
                needs_join_confirmation=True,
                join_confirmation_message="This question may require combining two datasets. Should joins be permitted for this query?",
                debug=sql_plan.model_dump() if settings.is_dev_mode else None,
            )

        try:
            result_blocks = []
            for sub_query in sql_plan.sub_queries:
                if not sub_query.source_id:
                    continue
                runtime = workspace.get(sub_query.source_id)
                result_blocks.append(execute_sql_sub_query(sub_query, runtime, allow_joins=request.allow_joins))
            if not result_blocks:
                raise ValueError("The generated plan did not produce an executable source query.")
            await enrich_charts_with_llm(request.question, result_blocks, provider)
            return QueryResponse(
                result_blocks=result_blocks,
                final_summary=await summarize_results(sql_plan, result_blocks, provider),
                debug=sql_plan.model_dump() if settings.is_dev_mode else None,
            )
        except Exception as exc:
            raw_sql_error = str(exc)

    parsed = await parse_query(request.question, sources, provider)
    if parsed.needs_source_confirmation:
        candidate_sources = [
            CandidateSource(id=source.id, name=source.name, columns=[column.name for column in source.columns[:10]])
            for source in workspace.list_metadata()
            if source.id in parsed.candidate_source_ids
        ]
        return QueryResponse(
            needs_source_confirmation=True,
            source_confirmation_message="I found multiple datasets that could answer this. Which source should I use for this query?",
            candidate_sources=candidate_sources,
            debug=parsed.model_dump() if settings.is_dev_mode else None,
        )

    if settings.enable_join_confirmation and parsed.likely_requires_join and not request.allow_joins:
        return QueryResponse(
            needs_join_confirmation=True,
            join_confirmation_message="This question may require combining two datasets. Should joins be permitted for this query?",
            debug=parsed.model_dump() if settings.is_dev_mode else None,
        )

    result_blocks = []
    for sub_question in parsed.sub_questions:
        if not sub_question.source_id:
            continue
        runtime = workspace.get(sub_question.source_id)
        sub_question.operation = ground_operation_values(sub_question.question, runtime, sub_question.operation)
        sub_question.operation = enforce_operation_sufficiency(sub_question.question, runtime.metadata, sub_question.operation)
        result_blocks.append(execute_sub_question(sub_question, runtime))

    if not result_blocks:
        raise HTTPException(
            status_code=400,
            detail="I could not turn that request into a safe read-only query for the selected sources.",
        )

    await enrich_charts_with_llm(request.question, result_blocks, provider)
    return QueryResponse(
        result_blocks=result_blocks,
        final_summary=await summarize_results(parsed, result_blocks, provider),
        debug={"raw_sql_error": raw_sql_error, "fallback_plan": parsed.model_dump()} if settings.is_dev_mode else None,
    )
