import asyncio

from app.models.query import ChartKind, ChartSpec, ResultBlock
from app.query_engine.visual_planner import chart_spec_from_payload, enrich_charts_with_llm


class FakeVisualProvider:
    async def structured_json(self, system_prompt, user_prompt, schema_hint):
        return {
            "enabled": True,
            "chart_type": "pie",
            "x_key": "trip_id",
            "y_key": "actual_arrival_delay",
            "title": "Top arrival delays",
        }


def test_chart_spec_from_payload_normalizes_chart_type():
    chart = chart_spec_from_payload(
        {
            "enabled": True,
            "chart_type": "horizontal bar",
            "x_key": "category",
            "y_key": "metric",
        }
    )

    assert chart.enabled is True
    assert chart.chart_type == ChartKind.horizontal_bar


def test_enrich_charts_with_llm_uses_validated_actual_rows():
    block = ResultBlock(
        id="q1",
        label="Arrival delays",
        source_name="trains.csv",
        question="show top 3 train trips actual delay time in a pie chart",
        columns=["trip_id", "actual_arrival_delay"],
        rows=[
            {"trip_id": "T001", "actual_arrival_delay": 29},
            {"trip_id": "T002", "actual_arrival_delay": 24},
            {"trip_id": "T003", "actual_arrival_delay": 18},
        ],
        chart=ChartSpec(enabled=False),
    )

    asyncio.run(enrich_charts_with_llm("show train trips actual delay time in a pie chart", [block], FakeVisualProvider()))

    assert block.chart.enabled is True
    assert block.chart.chart_type == ChartKind.pie
    assert block.chart.x_key == "trip_id"
    assert block.chart.y_key == "actual_arrival_delay"
