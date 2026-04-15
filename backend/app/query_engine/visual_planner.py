from __future__ import annotations

import asyncio
from typing import Any

from app.models.query import ChartSpec, ResultBlock
from app.providers.factory import ProviderRouter
from app.query_engine.chart_recommender import recommend_chart_from_rows, validated_planned_chart_from_rows
from app.query_engine.intent_layer import detect_intent

MAX_ROWS_FOR_VISUAL_PROMPT = 30
MAX_TEXT_VALUE_LENGTH = 120


async def enrich_charts_with_llm(original_question: str, result_blocks: list[ResultBlock], provider: ProviderRouter | None) -> list[ResultBlock]:
    if provider is None or not result_blocks:
        return result_blocks

    await asyncio.gather(
        *(
            apply_llm_chart_plan(original_question, block, provider)
            for block in result_blocks
            if block.rows and block.columns
        )
    )
    return result_blocks


async def apply_llm_chart_plan(original_question: str, block: ResultBlock, provider: ProviderRouter) -> None:
    try:
        planned_chart = await plan_chart_with_llm(original_question, block, provider)
        force_chart = detect_intent(block.question).wants_chart or detect_intent(original_question).wants_chart or block.chart.enabled
        chart = validated_planned_chart_from_rows(
            block.question,
            block.columns,
            block.rows,
            planned_chart,
            forced_chart_intent=force_chart,
        )
        if not chart.enabled and force_chart:
            chart = recommend_chart_from_rows(block.question, block.columns, block.rows, forced_chart_intent=True)
        if chart.enabled:
            block.chart = chart
    except Exception:
        return


async def plan_chart_with_llm(original_question: str, block: ResultBlock, provider: ProviderRouter) -> ChartSpec:
    schema_hint = {
        "enabled": True,
        "chart_type": "bar | horizontal_bar | line | area | pie | radial_bar | treemap | radar | scatter | histogram | null",
        "x_key": "exact column name from the provided columns, or null",
        "y_key": "exact numeric column name from the provided columns, or null",
        "title": "short human title, or null",
    }
    system_prompt = (
        "You are a visualization planner for a data analysis app. "
        "Choose one chart specification using only the retrieved rows and exact column names provided. "
        "Honor an explicit chart type in the user's question when it is compatible with the rows. "
        "If no chart is explicitly requested, choose a useful chart for comparisons, rankings, trends, distributions, composition, or relationships. "
        "Use bar or horizontal_bar for comparisons and rankings, line or area for time trends, pie or treemap for part-to-whole data, scatter for relationships between numeric fields, histogram for numeric distributions, radar only for a small comparable set, and radial_bar only for positive comparable values. "
        "The y_key must contain numeric values. The x_key should usually be a readable label column; for scatter and histogram it may be numeric. "
        "Return disabled if the rows cannot be visualized honestly. Return JSON only."
    )
    user_prompt = (
        f"Original question: {original_question}\n"
        f"Subquery: {block.question}\n"
        f"Source: {block.source_name}\n"
        f"Columns: {block.columns}\n"
        f"Retrieved rows: {compact_rows(block.rows)}\n"
        f"Current deterministic chart: {block.chart.model_dump()}"
    )
    payload = await provider.structured_json(system_prompt, user_prompt, schema_hint)
    return chart_spec_from_payload(payload)


def chart_spec_from_payload(payload: dict[str, Any]) -> ChartSpec:
    if "chart" in payload and isinstance(payload["chart"], dict):
        payload = payload["chart"]
    chart_type = payload.get("chart_type")
    if isinstance(chart_type, str):
        normalized = chart_type.strip().lower().replace("-", "_").replace(" ", "_")
        payload["chart_type"] = None if normalized in {"", "none", "null", "false", "no_chart"} else normalized
    if "enabled" not in payload:
        payload["enabled"] = bool(payload.get("chart_type") and payload.get("x_key") and payload.get("y_key"))
    if isinstance(payload.get("title"), str):
        payload["title"] = payload["title"].strip()[:90] or None
    try:
        return ChartSpec.model_validate(payload)
    except Exception:
        return ChartSpec(enabled=False)


def compact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: compact_value(value) for key, value in row.items()} for row in rows[:MAX_ROWS_FOR_VISUAL_PROMPT]]


def compact_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_TEXT_VALUE_LENGTH:
        return f"{value[:MAX_TEXT_VALUE_LENGTH]}..."
    return value
