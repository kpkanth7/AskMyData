from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Iterable

import pandas as pd

from app.models.query import FilterOperator, FilterSpec, OperationSpec
from app.models.sources import ColumnProfile
from app.services.workspace import SourceRuntime


def ground_operation_values(question: str, runtime: SourceRuntime, operation: OperationSpec) -> OperationSpec:
    candidates_by_column = categorical_value_candidates(runtime)
    if not candidates_by_column:
        return operation

    meaningful_question = remove_command_phrases(question)
    group_columns = set(operation.group_by)
    existing_filter_columns = {filter_spec.column for filter_spec in operation.filters}
    kept_filters = []
    for filter_spec in operation.filters:
        if filter_spec.column in group_columns:
            continue
        if isinstance(filter_spec.value, str) and filter_spec.column in candidates_by_column:
            grounded = best_value_match(str(filter_spec.value), candidates_by_column[filter_spec.column])
            if grounded and grounded != filter_spec.value:
                filter_spec.value = grounded
            if filter_spec.operator == FilterOperator.eq and not best_value_match(meaningful_question, [str(filter_spec.value)]):
                continue
        kept_filters.append(filter_spec)
    operation.filters = kept_filters
    existing_filter_columns = {filter_spec.column for filter_spec in operation.filters}

    for column_name, values in candidates_by_column.items():
        if column_name in group_columns:
            continue
        if column_name in existing_filter_columns:
            continue
        grounded = best_value_match(meaningful_question, values)
        if grounded:
            operation.filters.append(FilterSpec(column=column_name, operator=FilterOperator.eq, value=grounded))

    return operation


def categorical_value_candidates(runtime: SourceRuntime) -> dict[str, list[str]]:
    if runtime.dataframe is not None:
        return dataframe_categorical_values(runtime.dataframe, runtime.metadata.columns)
    return {
        column.name: [str(value) for value in column.sample_values if value is not None]
        for column in runtime.metadata.columns
        if is_categorical_profile(column)
    }


def dataframe_categorical_values(df: pd.DataFrame, columns: list[ColumnProfile]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for profile in columns:
        if not is_categorical_profile(profile):
            continue
        if profile.name not in df.columns:
            continue
        series = df[profile.name].dropna().astype(str)
        unique_values = sorted(series.unique().tolist(), key=lambda value: (len(value), value.lower()))
        values[profile.name] = unique_values[:250]
    return values


def is_categorical_profile(column: ColumnProfile) -> bool:
    dtype = column.dtype.lower()
    if any(kind in dtype for kind in ("datetime", "date", "time", "int", "float", "double", "decimal", "bool")):
        return False
    if column.unique_count == 0:
        return False
    return column.unique_count <= 250


def best_value_match(question: str, values: Iterable[str]) -> str | None:
    best_value = None
    best_score = 0.0
    for value in values:
        score = value_match_score(question, value)
        if score > best_score:
            best_value = value
            best_score = score
    return best_value if best_score >= 0.62 else None


def value_match_score(question: str, value: str) -> float:
    query_phrases = phrase_candidates(question)
    value_tokens = normalized_tokens(value)
    if not value_tokens:
        return 0.0

    best_score = 0.0
    value_text = normalize_text(value)
    for phrase in query_phrases:
        phrase_text = normalize_text(phrase)
        if not phrase_text:
            continue
        phrase_tokens = normalized_tokens(phrase)
        overlap = len(phrase_tokens & value_tokens) / max(len(value_tokens), 1)
        sequence = SequenceMatcher(None, phrase_text, value_text).ratio()
        contains = 1.0 if phrase_text in value_text or value_text in phrase_text else 0.0
        best_score = max(best_score, (0.55 * overlap) + (0.35 * sequence) + (0.10 * contains))
    return best_score


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


def normalized_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        if len(token) >= 2:
            tokens.add(token)
    return tokens


def normalize_text(text: str) -> str:
    return " ".join(sorted(normalized_tokens(text)))
