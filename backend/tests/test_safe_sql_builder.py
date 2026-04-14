from app.models.query import AggregateFunction, FilterSpec, OperationSpec
from app.models.sources import ColumnProfile, SourceKind, SourceMetadata, SourceType
from app.query_engine.safe_sql_builder import build_select_sql, format_sql_preview, prepare_raw_select_sql


def test_builds_allowlisted_grouped_query():
    metadata = SourceMetadata(
        id="src_test",
        name="sales.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="sales",
        columns=[
            ColumnProfile(name="region", dtype="object"),
            ColumnProfile(name="revenue", dtype="float64"),
        ],
    )
    sql, params = build_select_sql(
        "sales",
        metadata,
        OperationSpec(group_by=["region"], aggregate=AggregateFunction.sum, aggregate_column="revenue", limit=10),
    )
    assert 'SUM("revenue") AS metric' in sql
    assert 'GROUP BY "region"' in sql
    assert params == []


def test_grouped_aggregate_sorts_by_metric_when_llm_picks_metric_column():
    metadata = SourceMetadata(
        id="src_test",
        name="sales.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="sales",
        columns=[
            ColumnProfile(name="region", dtype="object"),
            ColumnProfile(name="revenue", dtype="float64"),
        ],
    )
    sql, _ = build_select_sql(
        "sales",
        metadata,
        OperationSpec(
            group_by=["region"],
            aggregate=AggregateFunction.sum,
            aggregate_column="revenue",
            sort_by="revenue",
            limit=10,
        ),
    )
    assert 'ORDER BY metric DESC' in sql


def test_builds_not_equal_filter():
    metadata = SourceMetadata(
        id="src_test",
        name="movies.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="movies",
        columns=[
            ColumnProfile(name="director", dtype="object"),
        ],
    )

    sql, params = build_select_sql(
        "movies",
        metadata,
        OperationSpec(filters=[FilterSpec(column="director", operator="neq", value="Unknown")], limit=10),
    )

    assert '"director" != ?' in sql
    assert params == ["Unknown"]


def test_contains_filter_uses_portable_sql_for_sql_sources():
    metadata = SourceMetadata(
        id="src_test",
        name="orders.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="orders",
        columns=[
            ColumnProfile(name="customer_name", dtype="object"),
        ],
    )

    mysql_sql, mysql_params = build_select_sql(
        "orders",
        metadata,
        OperationSpec(filters=[FilterSpec(column="customer_name", operator="contains", value="ada")], limit=10),
        dialect="mysql",
        named_params=True,
    )
    sqlite_sql, sqlite_params = build_select_sql(
        "orders",
        metadata,
        OperationSpec(filters=[FilterSpec(column="customer_name", operator="contains", value="ada")], limit=10),
        dialect="sqlite",
        named_params=True,
    )

    assert "LIKE LOWER(:p0)" in mysql_sql
    assert "ILIKE" not in mysql_sql
    assert "LIKE LOWER(:p0)" in sqlite_sql
    assert "ILIKE" not in sqlite_sql
    assert mysql_params == {"p0": "%ada%"}
    assert sqlite_params == {"p0": "%ada%"}


def test_prepares_valid_raw_select_sql_with_limit():
    metadata = SourceMetadata(
        id="src_test",
        name="movies.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="movies",
        columns=[
            ColumnProfile(name="director", dtype="object"),
            ColumnProfile(name="release_year", dtype="int64"),
        ],
    )

    sql = prepare_raw_select_sql('SELECT "director" FROM "movies" WHERE "release_year" >= 2017', metadata)

    assert sql.endswith("LIMIT 10")


def test_rejects_raw_sql_unknown_column():
    metadata = SourceMetadata(
        id="src_test",
        name="movies.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="movies",
        columns=[ColumnProfile(name="director", dtype="object")],
    )

    try:
        prepare_raw_select_sql('SELECT "made_up" FROM "movies" LIMIT 5', metadata)
    except ValueError as exc:
        assert "unknown column" in str(exc).lower()
    else:
        raise AssertionError("Expected unknown column to be rejected")


def test_rejects_raw_sql_destructive_statement():
    metadata = SourceMetadata(
        id="src_test",
        name="movies.csv",
        kind=SourceKind.file,
        source_type=SourceType.csv,
        table_name="movies",
        columns=[ColumnProfile(name="director", dtype="object")],
    )

    try:
        prepare_raw_select_sql('DELETE FROM "movies"', metadata)
    except ValueError as exc:
        assert "select" in str(exc).lower() or "unsafe" in str(exc).lower()
    else:
        raise AssertionError("Expected destructive statement to be rejected")


def test_format_sql_preview_inlines_display_values_only():
    sql = format_sql_preview('SELECT * FROM "movies" WHERE "release_year" >= ? AND "type" != ?', [2017, "Unknown"])

    assert sql == "SELECT * FROM \"movies\" WHERE \"release_year\" >= 2017 AND \"type\" != 'Unknown'"
