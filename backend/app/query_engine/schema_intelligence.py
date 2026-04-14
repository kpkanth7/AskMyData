from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Iterable

from app.models.sources import ColumnProfile, SourceMetadata
from app.utils.text import query_tokens

MEASURE_NAME_TERMS = {
    "amount",
    "average",
    "avg",
    "balance",
    "cost",
    "count",
    "delay",
    "duration",
    "fare",
    "index",
    "margin",
    "metric",
    "percent",
    "percentage",
    "price",
    "profit",
    "quantity",
    "qty",
    "rate",
    "ratio",
    "revenue",
    "score",
    "sum",
    "total",
    "value",
    "volume",
    "weight",
}

TEMPORAL_NAME_TERMS = {"date", "datetime", "day", "month", "quarter", "time", "timestamp", "week", "year"}
IDENTIFIER_NAME_TERMS = {"id", "identifier", "key", "uuid"}
DESCRIPTIVE_NAME_TERMS = {"category", "class", "description", "group", "label", "name", "segment", "status", "title", "type"}


def normalize_identifier(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.lower()))


def column_tokens(column_name: str) -> set[str]:
    return query_tokens(column_name)


def column_base_tokens(column_name: str) -> set[str]:
    tokens = column_tokens(column_name)
    return {token for token in tokens if token not in IDENTIFIER_NAME_TERMS}


def semantic_for_column(column: ColumnProfile) -> str:
    semantic = (column.semantic_type or "").lower()
    if semantic and semantic != "unknown":
        return semantic

    lower_name = column.name.lower()
    lower_dtype = (column.dtype or "").lower()
    name_tokens = column_tokens(column.name)

    if lower_name in IDENTIFIER_NAME_TERMS or name_tokens & IDENTIFIER_NAME_TERMS or lower_name.endswith("_id"):
        return "identifier"
    if name_tokens & TEMPORAL_NAME_TERMS:
        return "temporal"
    if "bool" in lower_dtype:
        return "boolean"
    if any(term in lower_dtype for term in ("datetime", "date", "time", "timestamp")):
        return "temporal"
    if any(term in lower_dtype for term in ("int", "float", "double", "decimal", "number")):
        return "numeric"
    if name_tokens & MEASURE_NAME_TERMS:
        return "numeric"
    if name_tokens & DESCRIPTIVE_NAME_TERMS:
        return "categorical"
    return "text"


def is_identifier_column(column: ColumnProfile, source: SourceMetadata | None = None) -> bool:
    lower_name = column.name.lower()
    if column.is_identifier or semantic_for_column(column) == "identifier":
        return True
    if lower_name in IDENTIFIER_NAME_TERMS or lower_name.endswith("_id"):
        return True
    tokens = column_tokens(column.name)
    if tokens & {"uuid"}:
        return True
    if source and source.row_count and source.row_count > 20 and column.unique_count >= int(source.row_count * 0.9):
        return True
    return False


def is_numeric_column(column: ColumnProfile, source: SourceMetadata | None = None, include_temporal: bool = False) -> bool:
    if is_identifier_column(column, source):
        return False
    semantic = semantic_for_column(column)
    if semantic == "temporal" and not include_temporal:
        return False
    if semantic == "numeric":
        return True
    lower_dtype = (column.dtype or "").lower()
    return any(term in lower_dtype for term in ("int", "float", "double", "decimal", "number"))


def is_temporal_column(column: ColumnProfile) -> bool:
    semantic = semantic_for_column(column)
    lower_dtype = (column.dtype or "").lower()
    lower_name = column.name.lower()
    return semantic == "temporal" or any(term in lower_dtype for term in ("datetime", "date", "time", "timestamp")) or bool(column_tokens(lower_name) & TEMPORAL_NAME_TERMS)


def is_categorical_column(column: ColumnProfile, source: SourceMetadata | None = None, include_text: bool = True) -> bool:
    if is_identifier_column(column, source):
        return False
    semantic = semantic_for_column(column)
    if semantic == "categorical":
        return True
    if include_text and semantic == "text":
        return True
    if semantic in {"numeric", "temporal", "boolean", "identifier"}:
        return False
    lower_dtype = (column.dtype or "").lower()
    return not any(term in lower_dtype for term in ("int", "float", "double", "decimal", "date", "time", "bool"))


def query_mentions_column(question: str, column_name: str) -> bool:
    lower_question = question.lower()
    tokens = query_tokens(lower_question)
    tokens_for_column = column_tokens(column_name)
    if tokens & tokens_for_column:
        return True
    normalized_column = normalize_identifier(column_name)
    normalized_question = normalize_identifier(lower_question)
    if normalized_column and normalized_column in normalized_question:
        return True
    return any(SequenceMatcher(None, normalized_column, normalize_identifier(phrase)).ratio() >= 0.86 for phrase in phrase_candidates(lower_question))


def phrase_candidates(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    phrases = set(tokens)
    for size in (2, 3):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            phrases.add(" ".join(tokens[index : index + size]))
    return list(phrases)


def column_query_score(column: ColumnProfile, question: str, source: SourceMetadata | None = None) -> float:
    tokens = query_tokens(question.lower())
    score = float(len(tokens & column_tokens(column.name)) * 3)
    normalized_column = normalize_identifier(column.name)
    normalized_question = normalize_identifier(question)
    if normalized_column and normalized_column in normalized_question:
        score += 5.0
    for phrase in phrase_candidates(question):
        score = max(score, SequenceMatcher(None, normalized_column, normalize_identifier(phrase)).ratio() * 4)
    for value in column.sample_values[:15]:
        if tokens & query_tokens(str(value)):
            score += 2.0
    if is_identifier_column(column, source):
        score -= 0.5
    return score


def mentioned_columns(source: SourceMetadata, question: str) -> list[str]:
    return [column.name for column in source.columns if query_mentions_column(question, column.name)]


def choose_numeric_column(
    source: SourceMetadata,
    question: str = "",
    preferred: Iterable[str] = (),
    exclude_temporal: bool = True,
) -> str | None:
    preferred_names = list(preferred)
    preferred_set = set(preferred_names)
    candidates = [
        column
        for column in source.columns
        if is_numeric_column(column, source, include_temporal=not exclude_temporal) and (not exclude_temporal or not is_temporal_column(column))
    ]
    if not candidates:
        return None

    def score(column: ColumnProfile) -> float:
        base = column_query_score(column, question, source) if question else 0.0
        if column.name in preferred_set:
            base += 8.0 - min(preferred_names.index(column.name), 5)
        lower_dtype = (column.dtype or "").lower()
        if any(term in lower_dtype for term in ("int", "float", "double", "decimal", "number")):
            base += 2.0
        if column_tokens(column.name) & MEASURE_NAME_TERMS:
            base += 1.0
        return base

    return max(candidates, key=score).name


def choose_temporal_column(source: SourceMetadata, question: str = "") -> str | None:
    candidates = [column for column in source.columns if is_temporal_column(column)]
    if not candidates:
        return None

    def score(column: ColumnProfile) -> float:
        base = column_query_score(column, question, source) if question else 0.0
        tokens = column_tokens(column.name)
        lower_dtype = (column.dtype or "").lower()
        if tokens & {"date", "datetime", "timestamp"} or any(term in lower_dtype for term in ("datetime", "date", "timestamp")):
            base += 3.0
        if tokens == {"year"} or "year" in tokens:
            base -= 1.0
        if tokens == {"time"}:
            base -= 2.0
        return base

    return max(candidates, key=score).name


def choose_categorical_column(source: SourceMetadata, question: str = "", preferred: Iterable[str] = ()) -> str | None:
    preferred_names = list(preferred)
    preferred_set = set(preferred_names)
    candidates = [column for column in source.columns if is_categorical_column(column, source)]
    if not candidates:
        return None

    def score(column: ColumnProfile) -> float:
        base = column_query_score(column, question, source) if question else 0.0
        if column.name in preferred_set:
            base += 8.0 - min(preferred_names.index(column.name), 5)
        semantic = semantic_for_column(column)
        if semantic == "categorical":
            base += 2.0
        elif semantic == "text":
            base -= 0.5
        if column_tokens(column.name) & DESCRIPTIVE_NAME_TERMS:
            base += 1.0
        distinct_count = column.unique_count or len({str(value) for value in column.sample_values if value not in (None, "")})
        if distinct_count:
            base += max(0.0, 2.0 - (distinct_count / 50.0))
        return base

    return max(candidates, key=score).name


def choose_identifier_column(source: SourceMetadata, question: str = "") -> str | None:
    candidates = [column for column in source.columns if is_identifier_column(column, source)]
    if not candidates:
        return None
    return max(candidates, key=lambda column: column_query_score(column, question, source) if question else 0.0).name


def wants_identifier_for_entity(question: str, source: SourceMetadata) -> bool:
    lower = question.lower()
    tokens = query_tokens(lower)
    if tokens & {"id", "ids", "identifier", "identifiers", "uuid", "key"}:
        return True
    for column in source.columns:
        if not is_identifier_column(column, source):
            continue
        base_tokens = column_base_tokens(column.name)
        if tokens & base_tokens:
            return True
        if any(f"{token}s" in tokens for token in base_tokens):
            return True
    return False


def display_columns(
    source: SourceMetadata,
    question: str = "",
    include_sort_column: str | None = None,
    include_identifiers: bool = False,
    limit: int = 8,
) -> list[str]:
    selected: list[str] = []
    identifier = choose_identifier_column(source, question) if include_identifiers else None
    if identifier:
        selected.append(identifier)
    if include_sort_column:
        selected.append(include_sort_column)
    mentioned = mentioned_columns(source, question) if question else []
    selected.extend(mentioned)

    ranked_columns = sorted(
        source.columns,
        key=lambda column: column_query_score(column, question, source) if question else 0.0,
        reverse=True,
    )
    for column in ranked_columns:
        semantic = semantic_for_column(column)
        if is_identifier_column(column, source) and not include_identifiers:
            continue
        if semantic in {"text", "categorical", "numeric", "temporal", "identifier"}:
            selected.append(column.name)

    deduped: list[str] = []
    for name in selected:
        if name and name not in deduped:
            deduped.append(name)
    if deduped:
        return deduped[:limit]
    return [column.name for column in source.columns[:limit]]
