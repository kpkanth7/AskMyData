from app.models.query import ChartSpec, ResultBlock
from app.query_engine.summarizer import deterministic_summary


def test_deterministic_summary_includes_aggregate_and_record_blocks():
    summary = deterministic_summary(
        parsed=None,
        result_blocks=[
            ResultBlock(
                id="q1",
                label="Counts",
                source_name="media.csv",
                question="compare movies vs tv shows by count",
                rows=[{"type": "Movie", "metric": 7}, {"type": "TV Show", "metric": 3}],
                columns=["type", "metric"],
                chart=ChartSpec(),
            ),
            ResultBlock(
                id="q2",
                label="Top delays",
                source_name="transport.csv",
                question="show top train trips by delay",
                rows=[{"trip_id": "T1", "actual_delay": 29}, {"trip_id": "T2", "actual_delay": 21}],
                columns=["trip_id", "actual_delay"],
                chart=ChartSpec(),
            ),
        ],
    )

    assert "Movie" in summary
    assert "TV Show" in summary
    assert "T1" in summary
