from __future__ import annotations

from app.models.query import AggregateFunction, OperationSpec, SortDirection
from app.models.sources import SourceMetadata
from app.query_engine.intent_layer import detect_intent
from app.query_engine.schema_intelligence import (
    choose_categorical_column,
    choose_identifier_column,
    choose_numeric_column,
    choose_temporal_column,
    display_columns,
    is_identifier_column,
    wants_identifier_for_entity,
)


def enforce_operation_sufficiency(question: str, source: SourceMetadata, operation: OperationSpec) -> OperationSpec:
    intent = detect_intent(question)
    valid_columns = {column.name for column in source.columns}

    if intent.explicit_limit is not None:
        operation.limit = intent.explicit_limit
    elif intent.top_without_number:
        operation.limit = 10
    operation.limit = max(1, min(500, operation.limit))

    operation.select_columns = [column for column in operation.select_columns if column in valid_columns]
    operation.group_by = [column for column in operation.group_by if column in valid_columns]
    if operation.sort_by not in valid_columns:
        operation.sort_by = None
    if operation.aggregate_column not in valid_columns:
        operation.aggregate_column = None
    operation.filters = [filter_spec for filter_spec in operation.filters if filter_spec.column in valid_columns]

    if intent.comparison:
        if not operation.group_by:
            group_column = choose_categorical_column(source, question)
            if group_column:
                operation.group_by = [group_column]
        if operation.group_by:
            grouped = set(operation.group_by)
            operation.filters = [filter_spec for filter_spec in operation.filters if filter_spec.column not in grouped]
        operation.aggregate = operation.aggregate or AggregateFunction.count
        operation.aggregate_column = None
        operation.select_columns = []

    if intent.trend:
        temporal_column = choose_temporal_column(source, question)
        if temporal_column and not operation.group_by:
            operation.group_by = [temporal_column]
        if operation.group_by and operation.group_by[0] == temporal_column:
            operation.aggregate = operation.aggregate or AggregateFunction.count
            operation.sort_by = temporal_column
            operation.sort_direction = SortDirection.asc

    if operation.aggregate in {AggregateFunction.sum, AggregateFunction.avg, AggregateFunction.min, AggregateFunction.max}:
        if not operation.aggregate_column:
            operation.aggregate_column = choose_numeric_column(source, question)
        if not operation.aggregate_column:
            operation.aggregate = AggregateFunction.count

    if intent.ranking and not operation.aggregate and not operation.sort_by:
        operation.sort_by = choose_numeric_column(source, question) or choose_temporal_column(source, question)
        operation.sort_direction = SortDirection.desc
    if intent.ranking and not operation.aggregate and operation.sort_by and column_is_identifier(operation.sort_by, source):
        alternative = choose_numeric_column(source, question) or choose_temporal_column(source, question)
        if alternative:
            operation.sort_by = alternative
    if intent.ranking and not operation.aggregate and operation.sort_by:
        include_identifiers = wants_identifier_for_entity(question, source)
        if not operation.select_columns or operation.select_columns == [operation.sort_by] or include_identifiers:
            operation.select_columns = display_columns(
                source,
                question,
                include_sort_column=operation.sort_by,
                include_identifiers=include_identifiers,
            )

    if operation.filters and not operation.aggregate and not operation.group_by and not operation.select_columns:
        operation.select_columns = display_columns(source, question, include_sort_column=operation.sort_by)

    if not operation.select_columns and not operation.group_by and not operation.aggregate:
        operation.select_columns = display_columns(source, question, include_sort_column=operation.sort_by)
    if intent.mentions_identifier:
        identifier_column = choose_identifier_column(source, question)
        if identifier_column and identifier_column not in operation.select_columns:
            operation.select_columns = [identifier_column, *operation.select_columns][:8]

    return operation


def column_is_identifier(column_name: str, source: SourceMetadata) -> bool:
    column = next((column for column in source.columns if column.name == column_name), None)
    return is_identifier_column(column, source) if column else False
