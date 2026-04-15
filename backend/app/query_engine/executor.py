from typing import Any, Dict, List

import duckdb
import pandas as pd
from sqlalchemy import text

from app.models.query import ChartSpec, ResultBlock, SqlSubQuery, SubQuestion
from app.query_engine.chart_recommender import recommend_chart, recommend_chart_from_rows, validated_planned_chart_from_rows
from app.query_engine.intent_layer import detect_intent
from app.query_engine.safe_sql_builder import build_select_sql, format_sql_preview, prepare_raw_select_sql
from app.services.workspace import SourceRuntime

SYNTHETIC_CHART_LABEL = "chart_item"


def rows_from_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    clean = df.where(pd.notnull(df), None)
    return clean.to_dict(orient="records")


def execute_sub_question(sub_question: SubQuestion, runtime: SourceRuntime) -> ResultBlock:
    metadata = runtime.metadata
    if runtime.dataframe is not None:
        sql, params = build_select_sql(metadata.table_name, metadata, sub_question.operation)
        sql_preview = format_sql_preview(sql, params)
        connection = duckdb.connect(database=":memory:")
        connection.register(metadata.table_name, runtime.dataframe)
        result_df = connection.execute(sql, params).df()
        rows = rows_from_dataframe(result_df)
        columns = list(result_df.columns)
    elif runtime.engine is not None:
        dialect = runtime.engine.dialect.name
        sql, params = build_select_sql(metadata.table_name, metadata, sub_question.operation, dialect=dialect, named_params=True)
        sql_preview = format_sql_preview(sql, params)
        with runtime.engine.connect() as connection:
            result = connection.execute(text(sql), params)
            rows = [dict(row._mapping) for row in result.fetchall()]
            columns = list(result.keys())
    else:
        raise ValueError("Source is not executable.")

    chart = validated_planned_chart_from_rows(sub_question.question, columns, rows, sub_question.chart, forced_chart_intent=sub_question.chart_intent)
    if not chart.enabled:
        chart = recommend_chart(sub_question.question, sub_question.operation, columns, forced_chart_intent=sub_question.chart_intent)
    if not chart.enabled:
        chart = fallback_chart_from_rows(sub_question.question, columns, rows, sub_question.chart_intent)
    return ResultBlock(
        id=sub_question.id,
        label=sub_question.label,
        source_name=metadata.name,
        question=sub_question.question,
        rows=rows,
        columns=columns,
        sql=sql_preview,
        chart=chart,
    )


def execute_sql_sub_query(sub_query: SqlSubQuery, runtime: SourceRuntime, allow_joins: bool = False) -> ResultBlock:
    metadata = runtime.metadata
    if runtime.dataframe is not None:
        sql = prepare_raw_select_sql(sub_query.sql, metadata, dialect="duckdb", allow_joins=allow_joins)
        connection = duckdb.connect(database=":memory:")
        connection.register(metadata.table_name, runtime.dataframe)
        result_df = connection.execute(sql).df()
        rows = rows_from_dataframe(result_df)
        columns = list(result_df.columns)
    elif runtime.engine is not None:
        dialect = runtime.engine.dialect.name
        sql = prepare_raw_select_sql(sub_query.sql, metadata, dialect=dialect, allow_joins=allow_joins)
        with runtime.engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = [dict(row._mapping) for row in result.fetchall()]
            columns = list(result.keys())
    else:
        raise ValueError("Source is not executable.")

    chart = validated_planned_chart_from_rows(sub_query.question, columns, rows, sub_query.chart, forced_chart_intent=sub_query.chart_intent)
    if not chart.enabled:
        chart = recommend_chart_from_rows(sub_query.question, columns, rows, forced_chart_intent=sub_query.chart_intent)
    if not chart.enabled:
        chart = fallback_chart_from_rows(sub_query.question, columns, rows, sub_query.chart_intent)
    return ResultBlock(
        id=sub_query.id,
        label=sub_query.label,
        source_name=metadata.name,
        question=sub_query.question,
        rows=rows,
        columns=columns,
        sql=sql,
        chart=chart,
    )


def fallback_chart_from_rows(question: str, columns: list[str], rows: list[dict[str, Any]], forced_chart_intent: bool) -> ChartSpec:
    if not rows or not (forced_chart_intent or detect_intent(question).wants_chart):
        return ChartSpec(enabled=False)
    label_column = ensure_synthetic_label_column(columns, rows)
    chart_columns = [label_column, *columns]
    return recommend_chart_from_rows(question, chart_columns, rows, forced_chart_intent=True)


def ensure_synthetic_label_column(columns: list[str], rows: list[dict[str, Any]]) -> str:
    label_column = SYNTHETIC_CHART_LABEL
    suffix = 2
    while label_column in columns:
        label_column = f"{SYNTHETIC_CHART_LABEL}_{suffix}"
        suffix += 1
    for index, row in enumerate(rows):
        row.setdefault(label_column, f"Item {index + 1}")
    return label_column
