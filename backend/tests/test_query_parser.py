from __future__ import annotations

from app.models.query import AggregateFunction, FilterSpec, OperationSpec
from app.models.sources import ColumnProfile, SourceKind, SourceMetadata, SourceType
from app.query_engine.query_parser import deterministic_parse_query, reconcile_operation


def make_source(source_id: str, name: str, columns: list[ColumnProfile], row_count: int | None = None) -> SourceMetadata:
    return SourceMetadata(
        id=source_id,
        name=name,
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name=f"t_{source_id}",
        row_count=row_count,
        columns=columns,
    )


def test_routing_uses_columns_not_dataset_filename():
    misleading_name = make_source(
        "misleading",
        "movies.csv",
        [
            ColumnProfile(name="customer", dtype="object", sample_values=["Ada"]),
            ColumnProfile(name="region", dtype="object", sample_values=["West"]),
            ColumnProfile(name="revenue", dtype="int64", sample_values=[120]),
        ],
    )
    movie_schema = make_source(
        "movie_schema",
        "sample.csv",
        [
            ColumnProfile(name="type", dtype="object", sample_values=["Movie"]),
            ColumnProfile(name="title", dtype="object", sample_values=["A Thriller"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
            ColumnProfile(name="listed_in", dtype="object", sample_values=["Thrillers"]),
            ColumnProfile(name="date_added", dtype="datetime64[ns]", sample_values=["2021-09-01"]),
        ],
    )

    parsed = deterministic_parse_query("most recent movies in 2021 of thrillers category", [misleading_name, movie_schema])

    assert parsed.sub_questions[0].source_id == "movie_schema"
    operation = parsed.sub_questions[0].operation
    assert operation.sort_by == "date_added"
    assert {filter_spec.column for filter_spec in operation.filters} == {"type", "release_year", "listed_in"}


def test_identical_schema_asks_for_source_confirmation():
    columns = [
        ColumnProfile(name="type", dtype="object", sample_values=["Movie"]),
        ColumnProfile(name="title", dtype="object", sample_values=["A Thriller"]),
        ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
        ColumnProfile(name="listed_in", dtype="object", sample_values=["Thrillers"]),
    ]
    first = make_source("first", "one.csv", columns)
    second = make_source("second", "two.csv", columns)

    parsed = deterministic_parse_query("most recent movies in 2021 of thrillers category", [first, second])

    assert parsed.needs_source_confirmation is True
    assert parsed.candidate_source_ids == ["first", "second"]


def test_longest_movies_uses_duration_sort_not_grouped_counts():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="show_id", dtype="object", sample_values=["s1"]),
            ColumnProfile(name="type", dtype="object", sample_values=["Movie"]),
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
            ColumnProfile(name="listed_in", dtype="object", sample_values=["Thrillers"]),
            ColumnProfile(name="duration", dtype="object", sample_values=["90 min"]),
            ColumnProfile(name="duration_value", dtype="int64", sample_values=[90]),
        ],
    )

    parsed = deterministic_parse_query("top 10 longest movies of year 2021", [movies])
    operation = parsed.sub_questions[0].operation

    assert operation.aggregate is None
    assert operation.group_by == []
    assert operation.sort_by == "duration_value"
    assert operation.sort_direction == "desc"
    assert "title" in operation.select_columns
    assert "duration" in operation.select_columns
    assert {filter_spec.column for filter_spec in operation.filters} == {"type", "release_year"}


def test_reconcile_rejects_llm_grouping_by_identifier_for_row_ranking():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="show_id", dtype="object", unique_count=5000, sample_values=["s1"]),
            ColumnProfile(name="type", dtype="object", sample_values=["Movie"]),
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
            ColumnProfile(name="duration", dtype="object", sample_values=["90 min"]),
            ColumnProfile(name="duration_value", dtype="int64", sample_values=[90]),
        ],
        row_count=5000,
    )
    bad_llm_operation = OperationSpec(
        group_by=["show_id"],
        aggregate=AggregateFunction.count,
        sort_by="show_id",
        limit=10,
    )

    operation = reconcile_operation("top 10 longest movies of year 2021", movies, bad_llm_operation)

    assert operation.aggregate is None
    assert operation.group_by == []
    assert operation.sort_by == "duration_value"
    assert "title" in operation.select_columns


def test_reconcile_preserves_user_top_limit_when_llm_defaults_to_50():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie"]),
            ColumnProfile(name="duration_value", dtype="int64", sample_values=[90]),
        ],
    )

    operation = reconcile_operation("top 10 longest movies", movies, OperationSpec(sort_by="duration_value", limit=50))

    assert operation.limit == 10


def test_reconcile_preserves_show_me_limit_when_llm_defaults_to_50():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie"]),
            ColumnProfile(name="date_added", dtype="datetime64[ns]", sample_values=["2021-09-01"]),
        ],
    )

    operation = reconcile_operation("show me 2 most recent records", movies, OperationSpec(sort_by="date_added", limit=50))

    assert operation.limit == 2


def test_reconcile_maps_misspelled_column_to_real_field():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
        ],
    )

    operation = reconcile_operation("show relase year", movies, OperationSpec(select_columns=["relase year"]))

    assert operation.select_columns == ["release_year"]


def test_compare_movies_and_tv_shows_groups_by_type_without_type_filter():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="show_id", dtype="object", sample_values=["s1"]),
            ColumnProfile(name="type", dtype="object", sample_values=["Movie", "TV Show"]),
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie", "Example Show"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
        ],
    )

    parsed = deterministic_parse_query("compare movies and tv shows by total count in the year 2021", [movies])
    operation = parsed.sub_questions[0].operation

    assert operation.aggregate == AggregateFunction.count
    assert operation.group_by == ["type"]
    assert {filter_spec.column for filter_spec in operation.filters} == {"release_year"}


def test_reconcile_turns_llm_single_type_filter_into_comparison_group():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="type", dtype="object", unique_count=2, sample_values=["Movie", "TV Show", "Movie"]),
            ColumnProfile(name="title", dtype="object", unique_count=3, sample_values=["Short Movie", "Example Show", "Long Movie"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
        ],
        row_count=3,
    )
    bad_llm_operation = OperationSpec(
        filters=[
            FilterSpec(column="release_year", operator="eq", value=2021),
            FilterSpec(column="type", operator="eq", value="Movie"),
        ],
        aggregate=AggregateFunction.count,
        limit=50,
    )

    operation = reconcile_operation("movies vs tv shows total count in 2021", movies, bad_llm_operation)

    assert operation.aggregate == AggregateFunction.count
    assert operation.group_by == ["type"]
    assert {filter_spec.column for filter_spec in operation.filters} == {"release_year"}


def test_trip_ids_routes_to_transport_schema_not_media_recent_date():
    transport = make_source(
        "transport",
        "public_transport_delays.csv",
        [
            ColumnProfile(name="trip_id", dtype="object", sample_values=["T00001"]),
            ColumnProfile(name="date", dtype="datetime64[ns]", sample_values=["2023-01-01"]),
            ColumnProfile(name="time", dtype="datetime64[ns]", sample_values=["05:00:00"]),
            ColumnProfile(name="transport_type", dtype="object", sample_values=["Bus"]),
            ColumnProfile(name="route_id", dtype="object", sample_values=["Route_1"]),
        ],
    )
    media = make_source(
        "media",
        "sample.csv",
        [
            ColumnProfile(name="show_id", dtype="object", sample_values=["s1"]),
            ColumnProfile(name="type", dtype="object", sample_values=["Movie"]),
            ColumnProfile(name="title", dtype="object", sample_values=["Example Movie"]),
            ColumnProfile(name="date_added", dtype="datetime64[ns]", sample_values=["2021-09-01"]),
            ColumnProfile(name="release_year", dtype="int64", sample_values=[2021]),
        ],
    )

    parsed = deterministic_parse_query("top 10 trip ids most recent ones", [transport, media])
    operation = parsed.sub_questions[0].operation

    assert parsed.sub_questions[0].source_id == "transport"
    assert operation.sort_by == "date"
    assert "trip_id" in operation.select_columns


def test_top_train_trip_delay_uses_delay_sort_and_trip_id_display():
    transport = make_source(
        "transport",
        "public_transport_delays.csv",
        [
            ColumnProfile(name="trip_id", dtype="object", sample_values=["T00073"], semantic_type="identifier", is_identifier=True),
            ColumnProfile(name="transport_type", dtype="object", sample_values=["Train"], semantic_type="categorical"),
            ColumnProfile(name="actual_arrival_delay", dtype="int64", sample_values=[29], semantic_type="numeric"),
            ColumnProfile(name="route_id", dtype="object", sample_values=["Route_1"], semantic_type="identifier", is_identifier=True),
        ],
    )

    parsed = deterministic_parse_query(
        "show me top 10 train trips with max actual arival delay time also represent them in pie chart",
        [transport],
    )
    operation = parsed.sub_questions[0].operation

    assert operation.aggregate is None
    assert operation.sort_by == "actual_arrival_delay"
    assert operation.sort_direction == "desc"
    assert operation.limit == 10
    assert "trip_id" in operation.select_columns


def test_top_entity_delay_time_in_pie_keeps_identifier_label():
    transport = make_source(
        "transport",
        "public_transport_delays.csv",
        [
            ColumnProfile(name="trip_id", dtype="object", sample_values=["T00073"], semantic_type="identifier", is_identifier=True),
            ColumnProfile(name="transport_type", dtype="object", sample_values=["Train"], semantic_type="categorical"),
            ColumnProfile(name="actual_delay_time", dtype="int64", sample_values=[29], semantic_type="numeric"),
        ],
    )

    parsed = deterministic_parse_query(
        "show me a top 10 train trips actual delay time in a pie chart",
        [transport],
    )
    operation = parsed.sub_questions[0].operation

    assert parsed.sub_questions[0].chart_intent is True
    assert operation.sort_by == "actual_delay_time"
    assert "trip_id" in operation.select_columns
    assert "actual_delay_time" in operation.select_columns


def test_each_trip_id_does_not_force_all_sources():
    transport = make_source(
        "transport",
        "public_transport_delays.csv",
        [
            ColumnProfile(name="trip_id", dtype="object", sample_values=["T00073"], semantic_type="identifier", is_identifier=True),
            ColumnProfile(name="actual_arrival_delay", dtype="int64", sample_values=[29], semantic_type="numeric"),
        ],
    )
    movies = make_source(
        "movies",
        "media.csv",
        [
            ColumnProfile(name="type", dtype="object", sample_values=["Movie", "TV Show"], semantic_type="categorical"),
            ColumnProfile(name="title", dtype="object", sample_values=["Example"], semantic_type="text"),
        ],
    )

    parsed = deterministic_parse_query("top 10 train trips by actual arrival delay where each trip id has its own piece", [transport, movies])

    assert len(parsed.sub_questions) == 1
    assert parsed.sub_questions[0].source_id == "transport"


def test_multi_part_question_routes_each_part_to_its_source():
    transport = make_source(
        "transport",
        "public_transport_delays.csv",
        [
            ColumnProfile(name="trip_id", dtype="object", sample_values=["T00073"], semantic_type="identifier", is_identifier=True),
            ColumnProfile(name="transport_type", dtype="object", sample_values=["Train"], semantic_type="categorical"),
            ColumnProfile(name="actual_arrival_delay", dtype="int64", sample_values=[29], semantic_type="numeric"),
        ],
    )
    movies = make_source(
        "movies",
        "media.csv",
        [
            ColumnProfile(name="type", dtype="object", sample_values=["Movie", "TV Show"], semantic_type="categorical"),
            ColumnProfile(name="title", dtype="object", sample_values=["Example"], semantic_type="text"),
        ],
    )

    parsed = deterministic_parse_query(
        "show top 10 train trips by actual arrival delay as a pie chart where each trip id has its own piece also compare movies vs shows by count",
        [transport, movies],
    )

    assert [sub_question.source_id for sub_question in parsed.sub_questions] == ["transport", "movies"]
    assert parsed.sub_questions[0].chart_intent is True
    assert parsed.sub_questions[1].operation.group_by == ["type"]


def test_aggregate_ranking_supports_negated_categorical_value():
    movies = make_source(
        "movies",
        "sample.csv",
        [
            ColumnProfile(name="type", dtype="object", unique_count=2, sample_values=["Movie", "TV Show"], semantic_type="categorical"),
            ColumnProfile(name="director", dtype="object", unique_count=30, sample_values=["Unknown", "Jane Doe"], semantic_type="categorical"),
            ColumnProfile(name="release_year", dtype="int64", unique_count=10, sample_values=[2017, 2021], semantic_type="numeric"),
        ],
    )

    parsed = deterministic_parse_query("the director with the most movies from 2017-2021 who is not unknown", [movies])
    operation = parsed.sub_questions[0].operation

    assert operation.aggregate == AggregateFunction.count
    assert operation.group_by == ["director"]
    assert any(filter_spec.column == "director" and filter_spec.operator == "neq" and filter_spec.value == "Unknown" for filter_spec in operation.filters)
