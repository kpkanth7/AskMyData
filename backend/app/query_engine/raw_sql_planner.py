from __future__ import annotations

import re
from typing import Any, List

from app.models.query import ChartKind, SqlQueryPlan
from app.models.sources import SourceMetadata
from app.providers.factory import ProviderRouter
from app.query_engine.intent_layer import detect_intent


async def plan_raw_sql_query(question: str, sources: List[SourceMetadata], provider: ProviderRouter | None) -> SqlQueryPlan | None:
    if provider is None:
        return None

    schema_hint: dict[str, Any] = {
        "original_question": question,
        "likely_requires_join": False,
        "wants_explanation": False,
        "needs_source_confirmation": False,
        "candidate_source_ids": [],
        "sub_queries": [
            {
                "id": "q1",
                "label": "short clear result heading",
                "question": "the specific sub-question being answered",
                "source_id": "one provided source id",
                "source_hint": "source name",
                "requires_join": False,
                "chart_intent": False,
                "chart": {
                    "enabled": False,
                    "chart_type": "bar | horizontal_bar | line | area | pie | radial_bar | treemap | radar | scatter | histogram | null",
                    "x_key": "column used for categories, time, or x values",
                    "y_key": "numeric metric column",
                    "title": "short chart title",
                },
                "sql": "SELECT ... FROM exact_table_name ... LIMIT 10",
            }
        ],
    }
    source_context = [source_context_for_prompt(source) for source in sources]
    detected_sub_questions = split_query_parts(question)
    system_prompt = (
        "You are the SQL planning brain for askmydata. Return JSON only. "
        "For each independent part of the user question, choose the best source and write one read-only SQL SELECT query. "
        "Create one sub_query per independent request in detected_sub_questions when more than one is provided. Do not merge independent requests into one SQL query. "
        "Use the exact table_name and exact column names from the source context. "
        "Use head_rows, sample_values, dtypes, semantic_type, and is_identifier to map user wording to fields and values. "
        "Handle spelling mistakes, case differences, natural phrasing, ranges, negation, counts, groupings, and rankings. "
        "Do not invent tables or columns. Do not output INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, or multiple statements. "
        "Use only one source table per sub-query unless a join is required. If a join is required, set likely_requires_join true and requires_join true. "
        "For unconfirmed joins, do not write a join query. "
        "For 'with the most', 'top by count', or similar intent, use GROUP BY, COUNT(*) AS metric, ORDER BY metric DESC. "
        "For top/bottom row rankings and chart requests, include one human-readable label or identifier column in SELECT along with the numeric measure. "
        "For pie, treemap, radial, radar, bar, and comparison charts, SELECT both the slice/category/label column and the numeric metric. "
        "Fill chart when a chart is explicit or useful. If the user names a chart type, use that chart_type. "
        "Choose x_key and y_key from columns that will appear in that sub-query's SELECT output. "
        "For 'not X', 'excluding X', or 'without X', add a not-equal filter. "
        "For year/date ranges such as 2017-2021, use >= and <= filters. "
        "Always include a sensible LIMIT, respecting the user's requested number when provided; otherwise use 10 or 1 for a single winner aggregate. "
        "Set chart_intent true when a chart would help: comparisons, ranked aggregates, distributions, trends, changes over time, or explicit chart requests."
    )
    user_prompt = f"Sources: {source_context}\nDetected independent requests: {detected_sub_questions}\nQuestion: {question}"
    try:
        payload = await provider.structured_json(system_prompt, user_prompt, schema_hint)
        plan = SqlQueryPlan.model_validate(payload)
        cleaned_plan = clean_plan(plan, sources)
        if cleaned_plan is not None:
            preserve_subquery_chart_requests(cleaned_plan)
        return cleaned_plan
    except Exception:
        return None


def source_context_for_prompt(source: SourceMetadata) -> dict[str, Any]:
    return {
        "id": source.id,
        "name": source.name,
        "table_name": source.table_name,
        "kind": source.kind.value,
        "source_type": source.source_type.value,
        "row_count": source.row_count,
        "columns": [
            {
                "name": column.name,
                "dtype": column.dtype,
                "semantic_type": column.semantic_type,
                "is_identifier": column.is_identifier,
                "unique_count": column.unique_count,
                "sample_values": column.sample_values[:15],
            }
            for column in source.columns
        ],
        "head_rows": source_head_rows(source),
    }


def source_head_rows(source: SourceMetadata, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    columns = source.columns[:20]
    max_rows = min(limit, max((len(column.sample_values) for column in columns), default=0))
    for row_index in range(max_rows):
        row: dict[str, Any] = {}
        for column in columns:
            if row_index < len(column.sample_values):
                row[column.name] = column.sample_values[row_index]
        rows.append(row)
    return rows


def clean_plan(plan: SqlQueryPlan, sources: List[SourceMetadata]) -> SqlQueryPlan | None:
    sources_by_id = {source.id: source for source in sources}
    cleaned_sub_queries = []
    for index, sub_query in enumerate(plan.sub_queries):
        if sub_query.source_id not in sources_by_id:
            continue
        if not sub_query.id:
            sub_query.id = f"q{index + 1}"
        if not sub_query.label:
            sub_query.label = sub_query.question[:64] or f"Result {index + 1}"
        cleaned_sub_queries.append(sub_query)
    if not cleaned_sub_queries:
        return None
    plan.sub_queries = cleaned_sub_queries
    return plan


def preserve_subquery_chart_requests(plan: SqlQueryPlan) -> None:
    parts = split_query_parts(plan.original_question)
    if not parts:
        return
    for index, sub_query in enumerate(plan.sub_queries):
        part = parts[index] if index < len(parts) else ""
        if not part or not has_visual_intent(part):
            continue
        sub_query.chart_intent = True
        chart_type = explicit_chart_kind(part)
        if chart_type and not sub_query.chart.chart_type:
            sub_query.chart.enabled = True
            sub_query.chart.chart_type = chart_type
        if has_chart_language(part) and not has_specific_chart_language(sub_query.question):
            sub_query.question = f"{sub_query.question} Visualization request: {part}"


def split_query_parts(question: str) -> list[str]:
    split_pattern = (
        r"\b(?:and\s+also|also|then)\b"
        r"|;"
        r"|[,?]\s*(?=(?:show|compare|plot|visualize|list|count|give|get|display|fetch|what|which|who|how\s+many)\b)"
        r"|\s+and\s+(?=(?:show|compare|plot|visualize|list|count|give|get|display|fetch)\b)"
    )
    return [piece.strip(" .?") for piece in re.split(split_pattern, question, flags=re.I) if piece.strip()]


def has_chart_language(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ("chart", "plot", "graph", "visualize", "pie", "donut", "treemap", "radial", "radar", "scatter", "histogram"))


def has_visual_intent(text: str) -> bool:
    intent = detect_intent(text)
    return intent.wants_chart or has_chart_language(text)


def has_specific_chart_language(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ("pie", "donut", "treemap", "radial", "radar", "scatter", "histogram", "line", "area", "bar"))


def explicit_chart_kind(text: str) -> ChartKind | None:
    lower = text.lower()
    if any(term in lower for term in ("pie", "donut", "doughnut")):
        return ChartKind.pie
    if "treemap" in lower or "tree map" in lower:
        return ChartKind.treemap
    if "radial" in lower:
        return ChartKind.radial_bar
    if "radar" in lower or "spider chart" in lower or "spider graph" in lower:
        return ChartKind.radar
    if "scatter" in lower:
        return ChartKind.scatter
    if "histogram" in lower:
        return ChartKind.histogram
    if "area" in lower:
        return ChartKind.area
    if "line" in lower:
        return ChartKind.line
    if "horizontal bar" in lower:
        return ChartKind.horizontal_bar
    if "bar" in lower:
        return ChartKind.bar
    return None
