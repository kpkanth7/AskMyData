import pandas as pd

from app.models.query import FilterSpec, OperationSpec
from app.models.sources import ColumnProfile, SourceKind, SourceMetadata, SourceType
from app.query_engine.semantic_grounding import ground_operation_values
from app.services.workspace import SourceRuntime


def make_runtime() -> SourceRuntime:
    df = pd.DataFrame(
        [
            {"type": "Movie", "title": "A"},
            {"type": "TV Show", "title": "B"},
            {"type": "TV Show", "title": "C"},
        ]
    )
    runtime = SourceRuntime(
        metadata=SourceMetadata(
            id="src",
            name="sample.csv",
            kind=SourceKind.file,
            source_type=SourceType.csv,
            table_name="t_src",
            row_count=3,
            columns=[
                ColumnProfile(name="type", dtype="object", unique_count=2, sample_values=["Movie", "TV Show"]),
                ColumnProfile(name="title", dtype="object", unique_count=3, sample_values=["A", "B", "C"]),
            ],
        ),
        dataframe=df,
    )
    return runtime


def test_grounding_maps_natural_phrase_to_actual_categorical_value():
    runtime = make_runtime()

    operation = ground_operation_values("show me shows", runtime, OperationSpec())

    assert [(filter_spec.column, filter_spec.value) for filter_spec in operation.filters] == [("type", "TV Show")]


def test_grounding_does_not_treat_show_me_as_tv_show_filter():
    runtime = make_runtime()

    operation = ground_operation_values("show me 2 most recent records", runtime, OperationSpec())

    assert operation.filters == []


def test_grounding_removes_llm_filter_created_from_command_word():
    runtime = make_runtime()

    operation = ground_operation_values(
        "show me 2 most recent records",
        runtime,
        OperationSpec(filters=[FilterSpec(column="type", operator="eq", value="TV Show")]),
    )

    assert operation.filters == []


def test_grounding_removes_filter_on_grouped_comparison_column():
    runtime = make_runtime()

    operation = ground_operation_values(
        "movies vs tv shows total count",
        runtime,
        OperationSpec(group_by=["type"], filters=[FilterSpec(column="type", operator="eq", value="Movie")]),
    )

    assert operation.group_by == ["type"]
    assert operation.filters == []
