from __future__ import annotations

from numbers import Number
from typing import Any

from app.models.query import ChartKind, ChartSpec, OperationSpec
from app.query_engine.intent_layer import detect_intent
from app.query_engine.schema_intelligence import column_tokens


LABEL_NAME_TERMS = {"category", "class", "group", "label", "name", "segment", "status", "title", "type"}


def recommend_chart(question: str, operation: OperationSpec, columns: list[str], forced_chart_intent: bool = False) -> ChartSpec:
    intent = detect_intent(question)
    explicit_chart = intent.explicit_chart
    explicit_pie = wants_pie(question)
    explicit_part_to_whole = explicit_pie or wants_treemap(question) or wants_radial(question) or wants_radar(question)
    explicit_histogram = wants_histogram(question)
    if forced_chart_intent:
        intent.wants_chart = True
        intent.comparison = intent.comparison or bool(operation.group_by)
        intent.ranking = intent.ranking or bool(operation.sort_by and not operation.group_by)
    if operation.group_by:
        x_key = operation.group_by[0]
        y_key = "metric" if "metric" in columns else next((column for column in columns if column != x_key), None)
        if not explicit_chart and not intent.wants_chart and not operation.aggregate and not intent.comparison and not intent.trend:
            return ChartSpec(enabled=False)
    elif operation.sort_by and operation.sort_by in columns:
        if (looks_temporal_axis(operation.sort_by) or looks_like_identifier(operation.sort_by)) and not explicit_chart and not intent.trend:
            return ChartSpec(enabled=False)
        if not looks_numeric_measure(operation.sort_by) and not explicit_chart:
            return ChartSpec(enabled=False)
        if not explicit_chart and not intent.wants_chart and not intent.ranking:
            return ChartSpec(enabled=False)
        x_key = first_display_axis(columns, operation.sort_by, allow_identifiers=explicit_part_to_whole)
        y_key = operation.sort_by
    else:
        if not explicit_chart:
            return ChartSpec(enabled=False)
        if wants_scatter(question):
            numeric_columns = [column for column in columns if looks_numeric_measure(column)]
            if len(numeric_columns) < 2:
                return ChartSpec(enabled=False)
            x_key, y_key = numeric_columns[0], numeric_columns[1]
        elif explicit_histogram:
            numeric_column = first_numeric_like_column(columns)
            if not numeric_column:
                return ChartSpec(enabled=False)
            x_key = numeric_column
            y_key = numeric_column
        else:
            return ChartSpec(enabled=False)

    if not x_key or (looks_like_identifier(x_key) and not explicit_part_to_whole):
        return ChartSpec(enabled=False)
    if not y_key:
        return ChartSpec(enabled=False)

    chart_type = choose_chart_kind(question, x_key, y_key, columns)
    return ChartSpec(enabled=True, chart_type=chart_type, x_key=x_key, y_key=y_key, title="Chart for this result")


def first_display_axis(
    columns: list[str],
    y_key: str,
    allow_identifiers: bool = False,
    rows: list[dict[str, Any]] | None = None,
) -> str | None:
    candidates = [column for column in columns if column != y_key and (allow_identifiers or not looks_like_identifier(column))]
    if not candidates:
        return None

    def score(column: str) -> float:
        value = 0.0
        tokens = column_tokens(column)
        if tokens & LABEL_NAME_TERMS:
            value += 3.0
        if looks_like_identifier(column):
            value += 1.0 if allow_identifiers else -5.0
        if rows:
            sample_values = [row.get(column) for row in rows[:20] if row.get(column) not in (None, "")]
            if sample_values and not all(is_numeric_value(item) for item in sample_values):
                value += 2.0
            unique_values = len({str(item) for item in sample_values})
            if 1 < unique_values <= 30:
                value += 1.0
        return value

    return max(candidates, key=score)


def looks_like_identifier(column: str) -> bool:
    lower = column.lower()
    return lower in {"id", "uuid"} or lower.endswith("_id")


def looks_temporal_axis(column: str) -> bool:
    lower = column.lower()
    return "date" in lower or "time" in lower or lower in {"year", "month"}


def looks_numeric_measure(column: str) -> bool:
    lower = column.lower()
    return any(term in lower for term in ("count", "total", "sum", "avg", "average", "value", "amount", "revenue", "sales", "score", "duration", "delay", "metric", "rate", "percent", "index"))


def first_numeric_like_column(columns: list[str], exclude: set[str] | None = None) -> str | None:
    exclude = exclude or set()
    return next((column for column in columns if column not in exclude and looks_numeric_measure(column)), None)


def explicitly_requests_chart(lower: str) -> bool:
    # Kept for backward compatibility in older tests.
    return detect_intent(lower).explicit_chart


def recommend_chart_from_rows(question: str, columns: list[str], rows: list[dict[str, Any]], forced_chart_intent: bool = False) -> ChartSpec:
    intent = detect_intent(question)
    explicit_pie = wants_pie(question)
    explicit_part_to_whole = explicit_pie or wants_treemap(question) or wants_radial(question) or wants_radar(question)
    if not rows or not columns:
        return ChartSpec(enabled=False)
    if not forced_chart_intent and not intent.wants_chart and "metric" not in columns:
        return ChartSpec(enabled=False)

    requested_scatter = wants_scatter(question)
    requested_histogram = wants_histogram(question)
    if requested_histogram:
        y_key = first_numeric_result_column(columns, rows)
        x_key = y_key
        if not y_key:
            return ChartSpec(enabled=False)
        return ChartSpec(enabled=True, chart_type=ChartKind.histogram, x_key=x_key, y_key=y_key, title="Chart for this result")

    y_key = "metric" if "metric" in columns and not requested_scatter else first_numeric_result_column(columns, rows)
    if not y_key:
        return ChartSpec(enabled=False)
    x_key = first_numeric_result_column(columns, rows, exclude={y_key}) if requested_scatter else first_display_axis(columns, y_key, allow_identifiers=explicit_part_to_whole, rows=rows)
    if not x_key or (looks_like_identifier(x_key) and not explicit_part_to_whole):
        return ChartSpec(enabled=False)

    chart_type = choose_chart_kind(question, x_key, y_key, columns, rows)
    return ChartSpec(enabled=True, chart_type=chart_type, x_key=x_key, y_key=y_key, title="Chart for this result")


def validated_planned_chart_from_rows(
    question: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    planned_chart: ChartSpec | None,
    forced_chart_intent: bool = False,
) -> ChartSpec:
    if not rows or not columns or planned_chart is None or not planned_chart.enabled:
        return ChartSpec(enabled=False)

    chart_type = planned_chart.chart_type
    x_key = planned_chart.x_key if planned_chart.x_key in columns else None
    y_key = planned_chart.y_key if planned_chart.y_key in columns else None

    if not x_key or not y_key:
        fallback = recommend_chart_from_rows(question, columns, rows, forced_chart_intent=True)
        if fallback.enabled and chart_type and chart_type_is_compatible(chart_type, fallback.x_key, fallback.y_key, rows):
            fallback.chart_type = chart_type
        if planned_chart.title:
            fallback.title = planned_chart.title
        return fallback

    if not column_has_numeric_values(y_key, rows):
        return ChartSpec(enabled=False)
    if chart_type in {ChartKind.scatter, ChartKind.histogram} and not column_has_numeric_values(x_key, rows):
        return ChartSpec(enabled=False)

    final_type = chart_type or choose_chart_kind(question, x_key, y_key, columns, rows)
    if not chart_type_is_compatible(final_type, x_key, y_key, rows):
        fallback = recommend_chart_from_rows(question, columns, rows, forced_chart_intent=forced_chart_intent or detect_intent(question).wants_chart)
        if fallback.enabled:
            return fallback
        return ChartSpec(enabled=False)

    return ChartSpec(
        enabled=True,
        chart_type=final_type,
        x_key=x_key,
        y_key=y_key,
        title=planned_chart.title or "Chart for this result",
    )


def first_numeric_result_column(columns: list[str], rows: list[dict[str, Any]], exclude: set[str] | None = None) -> str | None:
    exclude = exclude or set()
    for column in columns:
        if column in exclude:
            continue
        values = [row.get(column) for row in rows[:10] if row.get(column) is not None]
        if values and all(is_numeric_value(value) for value in values):
            return column
    return None


def column_has_numeric_values(column: str, rows: list[dict[str, Any]]) -> bool:
    values = [row.get(column) for row in rows[:20] if row.get(column) is not None]
    return bool(values) and all(is_numeric_value(value) for value in values)


def chart_type_is_compatible(chart_type: ChartKind | None, x_key: str | None, y_key: str | None, rows: list[dict[str, Any]]) -> bool:
    if not chart_type or not x_key or not y_key:
        return False
    if not column_has_numeric_values(y_key, rows):
        return False
    if chart_type == ChartKind.scatter:
        return column_has_numeric_values(x_key, rows)
    if chart_type == ChartKind.histogram:
        return column_has_numeric_values(x_key, rows)
    if chart_type == ChartKind.pie:
        return can_use_pie(x_key, y_key, rows) and has_positive_measure(y_key, rows)
    if chart_type in {ChartKind.treemap, ChartKind.radial_bar, ChartKind.radar}:
        return can_use_part_to_whole(x_key, y_key, rows) and has_positive_measure(y_key, rows)
    if chart_type in {ChartKind.line, ChartKind.area, ChartKind.bar, ChartKind.horizontal_bar}:
        return True
    return False


def has_positive_measure(y_key: str, rows: list[dict[str, Any]]) -> bool:
    return any((numeric_value(row.get(y_key)) or 0) > 0 for row in rows)


def numeric_value(value: Any) -> float | None:
    if not is_numeric_value(value):
        return None
    return float(value)


def is_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Number):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def choose_chart_kind(
    question: str,
    x_key: str,
    y_key: str,
    columns: list[str],
    rows: list[dict[str, Any]] | None = None,
) -> ChartKind:
    lower = question.lower()
    if wants_scatter(lower):
        return ChartKind.scatter
    if wants_histogram(lower):
        return ChartKind.histogram
    if wants_area(lower):
        return ChartKind.area
    if looks_temporal_axis(x_key) and any(term in lower for term in ("trend", "over time", "change", "wrt", "with respect to")):
        return ChartKind.line
    if wants_radar(lower):
        return ChartKind.radar
    if wants_treemap(lower) and can_use_part_to_whole(x_key, y_key, rows):
        return ChartKind.treemap
    if wants_radial(lower) and can_use_part_to_whole(x_key, y_key, rows):
        return ChartKind.radial_bar
    if wants_pie(lower) and can_use_pie(x_key, y_key, rows):
        return ChartKind.pie
    if looks_distribution(lower) and can_use_pie(x_key, y_key, rows) and not any(term in lower for term in ("compare", " vs ", " versus ")):
        return ChartKind.pie
    if rows and len(rows) >= 6 and not looks_temporal_axis(x_key):
        return ChartKind.horizontal_bar
    return ChartKind.bar


def wants_pie(lower: str) -> bool:
    return any(term in lower for term in ("pie", "donut", "doughnut", "share", "proportion", "percentage", "percent of", "breakdown of"))


def wants_area(lower: str) -> bool:
    return any(term in lower for term in ("area chart", "area graph", "cumulative", "volume over time"))


def wants_scatter(lower: str) -> bool:
    return any(term in lower for term in ("scatter", "correlation", "relationship", "relate ", "related to"))


def wants_histogram(lower: str) -> bool:
    return any(term in lower for term in ("histogram", "frequency", "distribution of values", "numeric distribution"))


def wants_treemap(lower: str) -> bool:
    return any(term in lower for term in ("treemap", "tree map"))


def wants_radial(lower: str) -> bool:
    return any(term in lower for term in ("radial", "radial bar", "circular bar"))


def wants_radar(lower: str) -> bool:
    return any(term in lower for term in ("radar", "spider chart", "spider graph"))


def looks_distribution(lower: str) -> bool:
    return any(term in lower for term in ("distribution", "composition", "mix of"))


def can_use_pie(x_key: str, y_key: str, rows: list[dict[str, Any]] | None) -> bool:
    if not x_key or not y_key or looks_temporal_axis(x_key):
        return False
    if rows is None:
        return True
    return 1 < len(rows) <= 12


def can_use_part_to_whole(x_key: str, y_key: str, rows: list[dict[str, Any]] | None) -> bool:
    if not x_key or not y_key or looks_temporal_axis(x_key):
        return False
    if rows is None:
        return True
    return 1 < len(rows) <= 30
