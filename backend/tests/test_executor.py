import pandas as pd

from app.models.query import OperationSpec, SortDirection, SubQuestion
from app.models.sources import ColumnProfile, SourceKind, SourceMetadata, SourceType
from app.query_engine.executor import execute_sub_question
from app.services.workspace import SourceRuntime


def test_chart_fallback_adds_hidden_axis_when_query_returns_only_measure():
    runtime = SourceRuntime(
        metadata=SourceMetadata(
            id="transport",
            name="transport.csv",
            kind=SourceKind.file,
            source_type=SourceType.csv,
            table_name="t_transport",
            row_count=3,
            columns=[
                ColumnProfile(name="actual_delay_time", dtype="int64", semantic_type="numeric"),
            ],
        ),
        dataframe=pd.DataFrame({"actual_delay_time": [29, 22, 15]}),
    )
    sub_question = SubQuestion(
        id="q1",
        label="Delay chart",
        question="show me top train trips actual delay time in a pie chart",
        source_id="transport",
        chart_intent=True,
        operation=OperationSpec(
            select_columns=["actual_delay_time"],
            sort_by="actual_delay_time",
            sort_direction=SortDirection.desc,
            limit=3,
        ),
    )

    result = execute_sub_question(sub_question, runtime)

    assert result.chart.enabled is True
    assert result.chart.chart_type == "pie"
    assert result.chart.x_key == "chart_item"
    assert result.chart.y_key == "actual_delay_time"
    assert "chart_item" not in result.columns
    assert [row["chart_item"] for row in result.rows] == ["Item 1", "Item 2", "Item 3"]
