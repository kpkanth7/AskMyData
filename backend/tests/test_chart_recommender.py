from app.models.query import AggregateFunction, ChartKind, ChartSpec, OperationSpec, SortDirection
from app.models.query import SqlQueryPlan, SqlSubQuery
from app.query_engine.chart_recommender import recommend_chart, recommend_chart_from_rows, validated_planned_chart_from_rows
from app.query_engine.raw_sql_planner import preserve_subquery_chart_requests


def test_row_ranking_chart_uses_bar_for_title_vs_measure():
    operation = OperationSpec(
        select_columns=["title", "duration_value"],
        sort_by="duration_value",
        sort_direction=SortDirection.desc,
        limit=10,
    )

    chart = recommend_chart("top 10 longest movies of year 2021", operation, ["title", "duration_value"])

    assert chart.enabled is True
    assert chart.chart_type == "bar"
    assert chart.x_key == "title"
    assert chart.y_key == "duration_value"


def test_recent_row_lookup_does_not_chart_temporal_sort_without_chart_request():
    operation = OperationSpec(
        select_columns=["trip_id", "date", "transport_type"],
        sort_by="date",
        sort_direction=SortDirection.desc,
        limit=10,
    )

    chart = recommend_chart("top 10 trip ids most recent ones", operation, ["trip_id", "date", "transport_type"])

    assert chart.enabled is False


def test_text_sorted_lookup_does_not_chart_without_chart_request():
    operation = OperationSpec(
        select_columns=["title", "rating"],
        sort_by="rating",
        sort_direction=SortDirection.desc,
        limit=10,
    )

    chart = recommend_chart("top 10 movies by rating", operation, ["title", "rating"])

    assert chart.enabled is False


def test_grouped_comparison_charts_without_literal_chart_word():
    operation = OperationSpec(group_by=["type"], aggregate=AggregateFunction.count, limit=50)

    chart = recommend_chart("movies vs tv shows total count in 2021", operation, ["type", "metric"])

    assert chart.enabled is True
    assert chart.chart_type == "bar"
    assert chart.x_key == "type"
    assert chart.y_key == "metric"


def test_temporal_grouped_change_uses_line_chart():
    operation = OperationSpec(group_by=["date"], aggregate=AggregateFunction.count, limit=50)

    chart = recommend_chart("change in delays wrt date", operation, ["date", "metric"])

    assert chart.enabled is True
    assert chart.chart_type == "line"


def test_share_question_uses_pie_chart_for_small_categorical_aggregate():
    chart = recommend_chart_from_rows(
        "show the share of movies and tv shows",
        ["type", "metric"],
        [{"type": "Movie", "metric": 277}, {"type": "TV Show", "metric": 38}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "pie"


def test_explicit_top_10_trip_id_pie_chart_uses_identifier_slices():
    rows = [{"trip_id": f"T{i:05d}", "actual_arrival_delay": 29} for i in range(1, 11)]

    chart = recommend_chart_from_rows(
        "show top 10 train trips with max actual arrival delay time as a pie chart where each trip id has its own piece",
        ["trip_id", "actual_arrival_delay"],
        rows,
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "pie"
    assert chart.x_key == "trip_id"
    assert chart.y_key == "actual_arrival_delay"


def test_explicit_sorted_identifier_pie_chart_is_allowed_for_safe_operation_results():
    operation = OperationSpec(
        select_columns=["trip_id", "actual_arrival_delay"],
        sort_by="actual_arrival_delay",
        sort_direction=SortDirection.desc,
        limit=10,
    )

    chart = recommend_chart(
        "represent top 10 trip ids by actual arrival delay in a pie chart",
        operation,
        ["trip_id", "actual_arrival_delay"],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "pie"
    assert chart.x_key == "trip_id"
    assert chart.y_key == "actual_arrival_delay"


def test_correlation_question_uses_scatter_for_two_numeric_columns():
    chart = recommend_chart_from_rows(
        "show the relationship between fare and trip duration",
        ["fare", "trip_duration"],
        [{"fare": 10.5, "trip_duration": 16}, {"fare": 20.0, "trip_duration": 30}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "scatter"
    assert chart.x_key == "trip_duration"
    assert chart.y_key == "fare"


def test_cumulative_temporal_question_uses_area_chart():
    chart = recommend_chart_from_rows(
        "cumulative revenue over time",
        ["date", "metric"],
        [{"date": "2021-01-01", "metric": 10}, {"date": "2021-02-01", "metric": 30}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "area"


def test_histogram_request_uses_histogram_for_numeric_distribution():
    chart = recommend_chart_from_rows(
        "show a histogram of actual arrival delay",
        ["trip_id", "actual_arrival_delay"],
        [{"trip_id": "T1", "actual_arrival_delay": 3}, {"trip_id": "T2", "actual_arrival_delay": 29}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "histogram"
    assert chart.x_key == "actual_arrival_delay"
    assert chart.y_key == "actual_arrival_delay"


def test_treemap_request_uses_treemap_for_part_to_whole_rows():
    chart = recommend_chart_from_rows(
        "show a treemap of delay by route",
        ["route_id", "metric"],
        [{"route_id": "R1", "metric": 44}, {"route_id": "R2", "metric": 12}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "treemap"


def test_radial_request_uses_radial_bar_for_part_to_whole_rows():
    chart = recommend_chart_from_rows(
        "show a radial bar chart of delay by route",
        ["route_id", "metric"],
        [{"route_id": "R1", "metric": 44}, {"route_id": "R2", "metric": 12}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "radial_bar"


def test_ranked_many_category_rows_use_horizontal_bar_by_default():
    rows = [{"route": f"Route {index}", "metric": index} for index in range(1, 7)]

    chart = recommend_chart_from_rows(
        "top routes by delay",
        ["route", "metric"],
        rows,
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "horizontal_bar"


def test_raw_sql_plan_preserves_chart_language_per_subquery():
    plan = SqlQueryPlan(
        original_question=(
            "show top 10 train trips by actual arrival delay as a pie chart where each trip id has its own piece "
            "also compare movies vs shows by count"
        ),
        sub_queries=[
            SqlSubQuery(id="q1", label="Delays", question="top 10 train trips by actual arrival delay", source_id="transport", sql="SELECT 1"),
            SqlSubQuery(id="q2", label="Media count", question="compare movies vs shows by count", source_id="media", sql="SELECT 1"),
        ],
    )

    preserve_subquery_chart_requests(plan)

    assert plan.sub_queries[0].chart_intent is True
    assert "pie chart" in plan.sub_queries[0].question
    assert plan.sub_queries[0].chart.enabled is True
    assert plan.sub_queries[0].chart.chart_type == ChartKind.pie
    assert plan.sub_queries[1].chart_intent is True


def test_raw_sql_comparison_rows_chart_without_metric_alias():
    chart = recommend_chart_from_rows(
        "compare online vs store orders by count",
        ["channel", "order_count"],
        [{"channel": "Online", "order_count": "17"}, {"channel": "Store", "order_count": "9"}],
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == "bar"
    assert chart.x_key == "channel"
    assert chart.y_key == "order_count"


def test_validated_planned_chart_uses_llm_chart_axes_when_safe():
    chart = validated_planned_chart_from_rows(
        "show top 10 delays in a pie chart",
        ["trip_id", "actual_delay_time"],
        [{"trip_id": "T1", "actual_delay_time": 29}, {"trip_id": "T2", "actual_delay_time": 12}],
        ChartSpec(enabled=True, chart_type=ChartKind.pie, x_key="trip_id", y_key="actual_delay_time", title="Delay share"),
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == ChartKind.pie
    assert chart.x_key == "trip_id"
    assert chart.y_key == "actual_delay_time"
    assert chart.title == "Delay share"


def test_invalid_planned_chart_falls_back_to_safe_axes():
    chart = validated_planned_chart_from_rows(
        "compare online vs store orders by count",
        ["channel", "order_count"],
        [{"channel": "Online", "order_count": 17}, {"channel": "Store", "order_count": 9}],
        ChartSpec(enabled=True, chart_type=ChartKind.bar, x_key="missing", y_key="also_missing"),
        forced_chart_intent=True,
    )

    assert chart.enabled is True
    assert chart.chart_type == ChartKind.bar
    assert chart.x_key == "channel"
    assert chart.y_key == "order_count"
