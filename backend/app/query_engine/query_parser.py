from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any, List

from app.models.query import AggregateFunction, FilterOperator, FilterSpec, OperationSpec, ParsedQuery, SortDirection, SubQuestion
from app.models.sources import SourceMetadata
from app.query_engine.intent_layer import detect_intent, extract_explicit_limit
from app.query_engine.operation_sufficiency import enforce_operation_sufficiency
from app.query_engine.schema_intelligence import (
    choose_categorical_column,
    choose_numeric_column,
    choose_temporal_column,
    display_columns,
    is_identifier_column as schema_is_identifier_column,
    is_numeric_column as schema_is_numeric_column,
    mentioned_columns as find_mentioned_columns,
    semantic_for_column,
    wants_identifier_for_entity,
)
from app.providers.factory import ProviderRouter
from app.utils.text import query_tokens


JOIN_TERMS = ("join", "combine", "merge", "match", "relationship between", "correlate", "both datasets")
AMBIGUITY_MARGIN = 1


async def parse_query(question: str, sources: List[SourceMetadata], provider: ProviderRouter | None = None) -> ParsedQuery:
    if provider is not None:
        parsed = await try_llm_parse(question, sources, provider)
        if parsed is not None:
            return parsed
    return deterministic_parse_query(question, sources)


async def try_llm_parse(question: str, sources: List[SourceMetadata], provider: ProviderRouter) -> ParsedQuery | None:
    schema_hint: dict[str, Any] = {
        "original_question": question,
        "likely_requires_join": False,
        "wants_explanation": False,
        "sub_questions": [
            {
                "id": "q1",
                "label": "short result label",
                "question": "sub-question text",
                "source_id": "one of the provided source ids",
                "source_hint": "source name",
                "requires_join": False,
                "chart_intent": False,
                "chart": {
                    "enabled": False,
                    "chart_type": "bar | horizontal_bar | line | area | pie | radial_bar | treemap | radar | scatter | histogram | null",
                    "x_key": "selected/grouped/category/time/x column",
                    "y_key": "numeric metric column",
                    "title": "short chart title",
                },
                "operation": {
                    "select_columns": [],
                    "filters": [],
                    "group_by": [],
                    "aggregate": "count | sum | avg | min | max | null",
                    "aggregate_column": None,
                    "sort_by": None,
                    "sort_direction": "desc",
                    "limit": 10,
                },
            }
        ],
    }
    source_context = [
        {
            "id": source.id,
            "columns": [
                {
                    "name": column.name,
                    "dtype": column.dtype,
                    "semantic_type": column.semantic_type,
                    "is_identifier": column.is_identifier,
                }
                for column in source.columns
            ],
            "sample_values": {column.name: column.sample_values[:10] for column in source.columns},
            "head_rows": source_head_rows(source),
        }
        for source in sources
    ]
    system_prompt = (
        "Parse the user's data question into safe query JSON only. "
        "Use only provided source ids and columns. Do not use source filenames or table names as evidence. Do not invent SQL. "
        "If a query appears to require combining datasets, set likely_requires_join true. "
        "Represent user values as filters in JSON. For ranges, use gte and lte filters. "
        "For negated values such as 'not Unknown' or 'excluding cancelled', use operator neq. "
        "For questions like 'X with the most Y', group by X, aggregate count, sort descending, and limit to the requested count. "
        "Fill chart when a chart is explicit or useful. If the user asks for a specific chart type, use that chart_type and pick axes from selected/grouped output columns."
    )
    user_prompt = f"Sources: {source_context}\nQuestion: {question}"
    try:
        payload = await provider.structured_json(system_prompt, user_prompt, schema_hint)
        parsed = ParsedQuery.model_validate(payload)
        sources_by_id = {source.id: source for source in sources}
        for index, sub_question in enumerate(parsed.sub_questions):
            best_source = best_source_for_question(sub_question.question, sources)
            chosen_source = sources_by_id.get(sub_question.source_id or "")
            if sub_question.source_id not in sources_by_id:
                sub_question.source_id = best_source.id if best_source else sources[min(index, len(sources) - 1)].id
                chosen_source = sources_by_id[sub_question.source_id]
            elif best_source and chosen_source and (source_score(best_source, sub_question.question) > source_score(chosen_source, sub_question.question)):
                sub_question.source_id = best_source.id
                chosen_source = sources_by_id[sub_question.source_id]
            if chosen_source is None:
                chosen_source = sources[min(index, len(sources) - 1)]
            sub_question.chart_intent = sub_question.chart_intent or detect_intent(sub_question.question).wants_chart
            sub_question.operation = reconcile_operation(sub_question.question, chosen_source, sub_question.operation)
        return parsed
    except Exception:
        return None


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


def reconcile_operation(question: str, source: SourceMetadata, operation: OperationSpec) -> OperationSpec:
    operation = sanitize_operation(operation, source)
    lower = question.lower()
    intent = detect_intent(question)
    mentioned_columns = find_mentioned_columns(source, lower)
    explicit_limit = intent.explicit_limit
    if explicit_limit is not None:
        operation.limit = explicit_limit

    add_obvious_filters_and_sort(operation, lower, source)
    if apply_aggregate_ranking_intent(operation, lower, source, mentioned_columns):
        return enforce_operation_sufficiency(question, source, operation)
    if apply_row_ranking_intent(operation, lower, source):
        return enforce_operation_sufficiency(question, source, operation)
    comparison_column = comparison_group_column(lower, source)
    if comparison_column:
        operation.group_by = [comparison_column]
        operation.aggregate = operation.aggregate or AggregateFunction.count
        operation.aggregate_column = None
        operation.select_columns = []
        operation.filters = [filter_spec for filter_spec in operation.filters if filter_spec.column != comparison_column]
    if operation.group_by and any(is_identifier_column(column, source) for column in operation.group_by) and not wants_identifier_for_entity(lower, source):
        replacement = best_group_column(source, [], lower)
        operation.group_by = [replacement] if replacement and not is_identifier_column(replacement, source) else []
        if not operation.group_by and operation.aggregate == AggregateFunction.count:
            operation.aggregate = None
            operation.select_columns = preferred_display_columns(source)
    if intent.comparison and operation.group_by:
        grouped = set(operation.group_by)
        operation.filters = [filter_spec for filter_spec in operation.filters if filter_spec.column not in grouped]
    if operation.filters and not operation.group_by and not operation.aggregate and not operation.select_columns:
        operation.select_columns = preferred_display_columns(source)
    return enforce_operation_sufficiency(question, source, operation)


def deterministic_parse_query(question: str, sources: List[SourceMetadata]) -> ParsedQuery:
    # Deterministic parser keeps execution safe even when no LLM credentials are configured.
    intent = detect_intent(question)
    lower = question.lower()
    likely_requires_join = len(sources) > 1 and (intent.mentions_join or any(term in lower for term in JOIN_TERMS))
    wants_explanation = intent.wants_explanation
    parts = split_into_parts(question)

    if len(parts) > 1 and not likely_requires_join:
        routed_pairs: list[tuple[str, SourceMetadata]] = []
        ambiguous_sources: list[SourceMetadata] = []
        for part in parts:
            part_sources, part_ambiguous = resolve_sources(part, sources)
            if part_ambiguous:
                ambiguous_sources.extend(part_ambiguous)
                continue
            for source in part_sources:
                routed_pairs.append((part, source))
        if ambiguous_sources:
            return ParsedQuery(
                original_question=question,
                sub_questions=[],
                needs_source_confirmation=True,
                candidate_source_ids=unique_columns([source.id for source in ambiguous_sources]),
            )
        if routed_pairs:
            return ParsedQuery(
                original_question=question,
                sub_questions=[
                    SubQuestion(
                        id=f"q{index + 1}",
                        label=f"{source.name}: {part[:56]}",
                        question=part,
                        source_id=source.id,
                        source_hint=source.name,
                        requires_join=False,
                        chart_intent=detect_intent(part).wants_chart,
                        operation=infer_operation(part, source),
                    )
                    for index, (part, source) in enumerate(routed_pairs)
                ],
                likely_requires_join=False,
                wants_explanation=wants_explanation,
            )

    routed_sources, ambiguous_candidates = resolve_sources(question, sources)
    if ambiguous_candidates:
        return ParsedQuery(
            original_question=question,
            sub_questions=[],
            needs_source_confirmation=True,
            candidate_source_ids=[source.id for source in ambiguous_candidates],
        )

    sub_questions: List[SubQuestion] = []
    for index, source in enumerate(routed_sources):
        part = parts[index] if index < len(parts) else question
        part_intent = detect_intent(part)
        sub_questions.append(
            SubQuestion(
                id=f"q{index + 1}",
                label=f"{source.name}: {part[:56]}",
                question=part,
                source_id=source.id,
                source_hint=source.name,
                requires_join=likely_requires_join,
                chart_intent=part_intent.wants_chart,
                operation=infer_operation(part, source),
            )
        )

    return ParsedQuery(
        original_question=question,
        sub_questions=sub_questions,
        likely_requires_join=likely_requires_join,
        wants_explanation=wants_explanation,
    )


def sanitize_operation(operation: OperationSpec, source: SourceMetadata) -> OperationSpec:
    valid_columns = {column.name for column in source.columns}
    operation.select_columns = unique_columns([column for column in (resolve_column_name(column, source) for column in operation.select_columns) if column in valid_columns])
    operation.group_by = unique_columns([column for column in (resolve_column_name(column, source) for column in operation.group_by) if column in valid_columns])
    if operation.aggregate_column:
        operation.aggregate_column = resolve_column_name(operation.aggregate_column, source)
    if operation.aggregate_column not in valid_columns:
        operation.aggregate_column = None
    if operation.sort_by:
        operation.sort_by = resolve_column_name(operation.sort_by, source)
    if operation.sort_by not in valid_columns:
        operation.sort_by = None
    for filter_spec in operation.filters:
        filter_spec.column = resolve_column_name(filter_spec.column, source) or filter_spec.column
    operation.filters = [filter_spec for filter_spec in operation.filters if filter_spec.column in valid_columns]
    operation.group_by = [column for column in operation.group_by if not is_identifier_column(column, source)]
    return operation


def split_into_parts(question: str) -> List[str]:
    split_pattern = (
        r"\b(?:and\s+also|also|then)\b"
        r"|;"
        r"|[,?]\s*(?=(?:show|compare|plot|visualize|list|count|give|get|display|fetch|what|which|who|how\s+many)\b)"
        r"|\s+and\s+(?=(?:show|compare|plot|visualize|list|count|give|get|display|fetch)\b)"
    )
    pieces = [piece.strip(" ?") for piece in re.split(split_pattern, question, flags=re.I) if piece.strip()]
    return pieces or [question]


def infer_operation(question: str, source: SourceMetadata) -> OperationSpec:
    lower = question.lower()
    columns = [column.name for column in source.columns]
    operation = OperationSpec(limit=extract_limit(lower))
    mentioned_columns = find_mentioned_columns(source, lower)
    add_obvious_filters_and_sort(operation, lower, source)

    if apply_aggregate_ranking_intent(operation, lower, source, mentioned_columns):
        return enforce_operation_sufficiency(question, source, operation)

    if apply_row_ranking_intent(operation, lower, source):
        return enforce_operation_sufficiency(question, source, operation)

    if "count" in lower or "how many" in lower:
        operation.aggregate = AggregateFunction.count
    elif "average" in lower or "avg" in lower or "mean" in lower:
        operation.aggregate = AggregateFunction.avg
        operation.aggregate_column = first_numeric_column(source, mentioned_columns)
    elif "sum" in lower or "total" in lower:
        operation.aggregate = AggregateFunction.sum
        operation.aggregate_column = first_numeric_column(source, mentioned_columns)
    elif "minimum" in lower or "lowest" in lower:
        operation.aggregate = AggregateFunction.min
        operation.aggregate_column = first_numeric_column(source, mentioned_columns)
    elif "maximum" in lower or "highest" in lower or "top" in lower:
        operation.aggregate = AggregateFunction.max if "maximum" in lower else None
        operation.aggregate_column = first_numeric_column(source, mentioned_columns)

    group_column = best_group_column(source, mentioned_columns, lower)
    if should_group_results(lower) and group_column:
        operation.group_by = [group_column]
        if operation.aggregate is None:
            operation.aggregate = AggregateFunction.count

    date_column = first_date_column(source)
    if any(term in lower for term in ("over time", "trend", "by date", "by month", "change")) and date_column:
        operation.group_by = [date_column]
        operation.aggregate = operation.aggregate or AggregateFunction.count
        operation.sort_by = date_column
        operation.sort_direction = SortDirection.asc

    if mentioned_columns and not operation.group_by and not operation.aggregate:
        operation.select_columns = mentioned_columns[:8]
    if operation.filters and not operation.group_by and not operation.aggregate and not operation.select_columns:
        operation.select_columns = preferred_display_columns(source)
    return enforce_operation_sufficiency(question, source, operation)


def apply_aggregate_ranking_intent(operation: OperationSpec, lower: str, source: SourceMetadata, mentioned_columns: List[str]) -> bool:
    intent = detect_intent(lower)
    if not intent.aggregate_superlative:
        return False
    group_column = best_group_column(source, mentioned_columns, lower)
    if not group_column:
        return False
    operation.select_columns = []
    operation.group_by = [group_column]
    operation.aggregate = AggregateFunction.count
    operation.aggregate_column = None
    operation.sort_by = None
    operation.sort_direction = SortDirection.asc if any(term in lower for term in ("fewest", "least", "lowest", "smallest")) else SortDirection.desc
    if intent.explicit_limit is None and asks_for_single_winner(lower):
        operation.limit = 1
    return True


def asks_for_single_winner(lower: str) -> bool:
    return bool(re.search(r"\b(?:the|which|what|who)\b.+\b(?:with|having|has)\s+(?:the\s+)?(?:most|fewest|least|highest|lowest|largest|smallest)\b", lower))


def apply_row_ranking_intent(operation: OperationSpec, lower: str, source: SourceMetadata) -> bool:
    sort_column = ranking_sort_column(lower, source)
    if not sort_column:
        return False
    operation.aggregate = None
    operation.aggregate_column = None
    operation.group_by = []
    operation.sort_by = sort_column
    operation.sort_direction = SortDirection.asc if any(term in lower for term in ("shortest", "smallest", "lowest")) else SortDirection.desc
    include_ids = should_include_identifier_for_ranking(lower, source)
    operation.select_columns = preferred_display_columns(source, include_sort_column=sort_column, include_identifiers=include_ids)
    return True


def ranking_sort_column(lower: str, source: SourceMetadata) -> str | None:
    if any(term in lower for term in ("longest", "duration", "runtime")):
        preferred = [
            column.name
            for column in source.columns
            if schema_is_numeric_column(column, source) and (query_tokens(column.name) & {"duration", "runtime", "elapsed", "length", "time"})
        ]
        return choose_numeric_column(source, lower, preferred) or choose_numeric_column(source, lower)
    if any(term in lower for term in ("most recent", "latest", "newest", "recent")):
        return choose_temporal_column(source, lower)
    mentioned_numeric_columns = [column for column in find_mentioned_columns(source, lower) if is_numeric_column(column, source) and not is_year_or_date_column(column)]
    if mentioned_numeric_columns and any(term in lower for term in ("top", "max", "maximum", "highest", "largest", "biggest", "most")):
        return choose_numeric_column(source, lower, mentioned_numeric_columns)
    if any(term in lower for term in ("max", "maximum", "highest", "largest", "biggest")):
        return choose_numeric_column(source, lower)
    if any(term in lower for term in ("lowest", "smallest", "shortest")):
        return choose_numeric_column(source, lower)
    return None


def should_include_identifier_for_ranking(lower: str, source: SourceMetadata) -> bool:
    return wants_identifier_for_entity(lower, source)


def should_group_results(lower: str) -> bool:
    return any(term in lower for term in (" by ", " per ", "compare", "distribution", "breakdown", "group", " vs ", " versus "))


def best_group_column(source: SourceMetadata, mentioned_columns: List[str], lower: str) -> str | None:
    comparison_column = comparison_group_column(lower, source)
    if comparison_column:
        return comparison_column
    for column in mentioned_columns:
        if not is_identifier_column(column, source):
            return column
    return choose_categorical_column(source, lower, mentioned_columns)


def best_source_for_question(question: str, sources: List[SourceMetadata]) -> SourceMetadata | None:
    scored = sorted(((source_score(source, question), source) for source in sources), key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        return None
    return scored[0][1]


def resolve_sources(question: str, sources: List[SourceMetadata]) -> tuple[List[SourceMetadata], List[SourceMetadata]]:
    lower = question.lower()
    if len(sources) <= 1:
        return sources, []
    if any(term in lower for term in ("each dataset", "each source", "each file", "each table", "all datasets", "all sources")):
        return sources, []

    scored = sorted(((source_score(source, question), source) for source in sources), key=lambda item: item[0], reverse=True)
    top_score = scored[0][0]
    if top_score <= 0:
        return [], [source for _, source in scored[: min(3, len(scored))]]

    candidates = [source for score, source in scored if score >= top_score - AMBIGUITY_MARGIN]
    if len(candidates) > 1:
        return [], candidates
    return [scored[0][1]], []


def source_score(source: SourceMetadata, question: str) -> int:
    intent = detect_intent(question)
    tokens = query_tokens(question.lower())
    score = 0.0

    for column in source.columns:
        name_tokens = query_tokens(column.name)
        overlap = len(tokens & name_tokens)
        score += overlap * 3.0

        semantic = semantic_for_column(column)

        if intent.trend and semantic == "temporal":
            score += 2.0
        if intent.ranking and semantic in {"numeric", "temporal"} and not column.is_identifier:
            score += 1.5
        if intent.comparison and semantic in {"categorical", "text"} and not column.is_identifier:
            score += 1.5
        if intent.mentions_identifier and (column.is_identifier or is_identifier_column(column.name, source)):
            score += 2.0

        for value in column.sample_values[:15]:
            if tokens & query_tokens(str(value)):
                score += 1.0

    return int(score)


def is_identifier_column(column_name: str, source: SourceMetadata) -> bool:
    column = next((column for column in source.columns if column.name == column_name), None)
    return schema_is_identifier_column(column, source) if column else False


def is_numeric_column(column_name: str, source: SourceMetadata) -> bool:
    column = next((column for column in source.columns if column.name == column_name), None)
    return schema_is_numeric_column(column, source) if column else False


def is_year_or_date_column(column_name: str) -> bool:
    lower = column_name.lower()
    tokens = query_tokens(lower)
    if tokens & {"delay", "duration", "elapsed", "runtime", "latency", "wait"}:
        return False
    return lower == "year" or lower.endswith("_year") or "date" in tokens or "datetime" in tokens or "timestamp" in tokens or tokens == {"time"}


def add_obvious_filters_and_sort(operation: OperationSpec, lower: str, source: SourceMetadata) -> None:
    filters: list[FilterSpec] = []

    year_range = extract_year_range(lower)
    if year_range:
        year_column = year_like_column(source)
        if year_column:
            start_year, end_year = year_range
            filters.append(FilterSpec(column=year_column, operator=FilterOperator.gte, value=start_year))
            filters.append(FilterSpec(column=year_column, operator=FilterOperator.lte, value=end_year))
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", lower)
    if year_match and not year_range:
        year_column = year_like_column(source)
        if year_column:
            filters.append(FilterSpec(column=year_column, operator=FilterOperator.eq, value=int(year_match.group(1))))
    for filter_spec in infer_value_filters(lower, source):
        filters.append(filter_spec)

    existing = {(filter_spec.column, filter_spec.operator, str(filter_spec.value).lower()) for filter_spec in operation.filters}
    for filter_spec in filters:
        key = (filter_spec.column, filter_spec.operator, str(filter_spec.value).lower())
        if key not in existing:
            operation.filters.append(filter_spec)

    if any(term in lower for term in ("most recent", "latest", "newest", "recent")):
        operation.sort_by = choose_temporal_column(source, lower) or year_like_column(source)
        operation.sort_direction = SortDirection.desc


def extract_year_range(lower: str) -> tuple[int, int] | None:
    patterns = (
        r"\b(?:from\s+)?(19\d{2}|20\d{2})\s*(?:-|to|through|until)\s*(19\d{2}|20\d{2})\b",
        r"\bbetween\s+(19\d{2}|20\d{2})\s+and\s+(19\d{2}|20\d{2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            start_year = int(match.group(1))
            end_year = int(match.group(2))
            return (min(start_year, end_year), max(start_year, end_year))
    return None


def comparison_group_column(lower: str, source: SourceMetadata) -> str | None:
    if not comparison_intent(lower):
        return None
    best_column: str | None = None
    best_score = 0.0
    for column in source.columns:
        if is_identifier_column(column.name, source) or not is_categorical_profile(column):
            continue
        matched_values = matched_sample_values(lower, column.sample_values)
        distinct_count = column.unique_count or len({str(value) for value in column.sample_values if value not in (None, "")})
        if distinct_count <= 0:
            continue
        match_count = len(matched_values)
        score = (match_count / distinct_count) - (0.01 * distinct_count)
        if match_count >= 2 and score > best_score:
            best_column = column.name
            best_score = score
    return best_column


def comparison_intent(lower: str) -> bool:
    return detect_intent(lower).comparison


def infer_value_filters(lower: str, source: SourceMetadata) -> list[FilterSpec]:
    lowered = remove_command_phrases(lower)
    filters: list[FilterSpec] = []
    for column in source.columns:
        if is_identifier_column(column.name, source):
            continue
        if not is_categorical_profile(column):
            continue
        if is_free_text_column(column.name):
            continue
        if is_year_or_date_column(column.name):
            continue
        value = best_matching_sample_value(lowered, [str(sample) for sample in column.sample_values if sample is not None])
        if not value:
            continue
        if is_negated_value(lowered, value):
            operator = FilterOperator.neq
        else:
            operator = FilterOperator.eq if looks_exact_label(value) else FilterOperator.contains
        filters.append(FilterSpec(column=column.name, operator=operator, value=value))
    return filters


def is_negated_value(lower: str, value: str) -> bool:
    value_pattern = re.escape(value.lower())
    normalized_value = normalize_identifier(value)
    negation_patterns = (
        rf"\b(?:not|isn't|isnt|is\s+not|are\s+not|without|excluding|exclude|except)\s+{value_pattern}\b",
        rf"\b{value_pattern}\s+(?:is\s+not|isn't|isnt)\b",
    )
    if any(re.search(pattern, lower) for pattern in negation_patterns):
        return True

    normalized_lower = normalize_identifier(lower)
    negated_markers = ("not", "isnot", "isnt", "without", "excluding", "exclude", "except")
    return any(f"{marker}{normalized_value}" in normalized_lower for marker in negated_markers)


def best_matching_sample_value(lower: str, sample_values: list[str]) -> str | None:
    if not sample_values:
        return None
    best_value: str | None = None
    best_score = 0.0
    phrases = phrase_candidates(lower)
    for value in sample_values[:25]:
        normalized_value = normalize_identifier(value)
        if not normalized_value:
            continue
        score = 0.0
        if normalized_value in normalize_identifier(lower):
            score += 0.8
        for phrase in phrases:
            similarity = SequenceMatcher(None, normalized_value, normalize_identifier(phrase)).ratio()
            if similarity > score:
                score = similarity
        if score > best_score:
            best_score = score
            best_value = value
    return best_value if best_score >= 0.84 else None


def looks_exact_label(value: str) -> bool:
    token_count = len(re.findall(r"[a-z0-9]+", value.lower()))
    return token_count <= 3


def is_free_text_column(column_name: str) -> bool:
    lower = column_name.lower()
    return any(term in lower for term in ("title", "name", "description", "summary", "comment", "notes", "text"))


def is_categorical_profile(column: Any) -> bool:
    semantic = str(getattr(column, "semantic_type", "")).lower()
    if semantic in {"categorical", "text"}:
        return True
    if semantic in {"numeric", "temporal", "boolean", "identifier"}:
        return False
    dtype = str(getattr(column, "dtype", "")).lower()
    if any(term in dtype for term in ("int", "float", "double", "decimal", "date", "time", "bool")):
        return False
    sample_values = [value for value in getattr(column, "sample_values", []) if value not in (None, "")]
    return bool(sample_values)


def matched_sample_values(lower: str, sample_values: list[Any]) -> set[str]:
    query_phrases = phrase_candidates(lower)
    query_tokens = set(re.findall(r"[a-z0-9]+", lower))
    matches: set[str] = set()
    for value in sample_values[:25]:
        normalized_value = normalize_identifier(str(value))
        value_tokens = set(re.findall(r"[a-z0-9]+", str(value).lower()))
        if not normalized_value or not value_tokens:
            continue
        phrase_match = any(SequenceMatcher(None, normalized_value, normalize_identifier(phrase)).ratio() >= 0.84 for phrase in query_phrases)
        token_match = any(
            value_token in query_tokens
            or any(SequenceMatcher(None, value_token, query_token).ratio() >= 0.88 for query_token in query_tokens)
            for value_token in value_tokens
        )
        if len(value_tokens) > 1 and not phrase_match:
            token_match = False
        if phrase_match or token_match:
            matches.add(normalized_value)
    return matches


def preferred_display_columns(source: SourceMetadata, include_sort_column: str | None = None, include_identifiers: bool = False) -> list[str]:
    return display_columns(source, include_sort_column=include_sort_column, include_identifiers=include_identifiers)


def extract_limit(question: str) -> int:
    explicit_limit = extract_explicit_limit(question)
    if explicit_limit is not None:
        return explicit_limit
    return 10

def resolve_column_name(candidate: str, source: SourceMetadata) -> str | None:
    if not candidate:
        return None
    valid = {column.name for column in source.columns}
    if candidate in valid:
        return candidate
    normalized_candidate = normalize_identifier(candidate)
    for column in source.columns:
        if normalize_identifier(column.name) == normalized_candidate:
            return column.name

    best_name = None
    best_score = 0.0
    for column in source.columns:
        score = SequenceMatcher(None, normalized_candidate, normalize_identifier(column.name)).ratio()
        if score > best_score:
            best_name = column.name
            best_score = score
    return best_name if best_score >= 0.84 else None


def phrase_candidates(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    phrases = set(tokens)
    for size in (2, 3):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            phrases.add(" ".join(tokens[index : index + size]))
    return list(phrases)


def remove_command_phrases(text: str) -> str:
    cleaned = text.lower()
    cleaned = re.sub(r"\b(?:show|give|get|list|fetch|display)\s+(?:me|us|the|all)?\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:records|rows|entries|results)\b", " ", cleaned)
    return cleaned


def normalize_identifier(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.lower()))


def unique_columns(columns: list[str]) -> list[str]:
    seen = set()
    unique = []
    for column in columns:
        if column not in seen:
            seen.add(column)
            unique.append(column)
    return unique


def first_numeric_column(source: SourceMetadata, preferred: List[str]) -> str | None:
    return choose_numeric_column(source, preferred=preferred)


def year_like_column(source: SourceMetadata) -> str | None:
    for column in source.columns:
        lower = column.name.lower()
        if lower == "year" or lower.endswith("_year") or lower.startswith("year_"):
            return column.name
    return None


def first_categorical_column(source: SourceMetadata, preferred: List[str]) -> str | None:
    return choose_categorical_column(source, preferred=preferred)


def first_date_column(source: SourceMetadata) -> str | None:
    return choose_temporal_column(source)
