from __future__ import annotations

from typing import Any

from app.models.query import ParsedQuery, ResultBlock
from app.providers.factory import ProviderRouter
from app.query_engine.schema_intelligence import column_tokens


async def summarize_results(parsed: ParsedQuery | Any, result_blocks: list[ResultBlock], provider: ProviderRouter | None = None) -> str:
    if provider is not None and result_blocks:
        try:
            system_prompt = (
                "Write exactly one grounded final answer to the user's original question. "
                "Use only the provided rows and aggregates. Do not claim facts that are not present in the retrieved data. "
                "Do not describe the retrieval process, SQL, row counts, result sections, or sample rows unless the row count is itself the answer. "
                "If the result is an aggregate or ranking, name the winning or compared values and their metrics. "
                "If the result is a record listing, briefly describe the listed records using the most meaningful fields. "
                "If there are multiple sub-questions, synthesize them into one final answer."
            )
            retrieved_results = [
                {
                    "source_name": block.source_name,
                    "question": block.question,
                    "columns": block.columns,
                    "all_retrieved_rows": block.rows,
                }
                for block in result_blocks
            ]
            summary = await provider.text(
                system_prompt,
                f"Original question: {getattr(parsed, 'original_question', '')}\nRetrieved results: {retrieved_results}",
                temperature=0.25 if getattr(parsed, "wants_explanation", False) else 0.1,
            )
            if summary and not looks_like_retrieval_process_summary(summary):
                return summary
            retry_prompt = (
                "Rewrite the final answer. Answer the original question directly using only the retrieved rows. "
                "Do not mention row counts, result sections, SQL, retrieval, or samples unless the user's question asks for counts."
            )
            retry_summary = await provider.text(
                system_prompt,
                f"{retry_prompt}\nOriginal question: {getattr(parsed, 'original_question', '')}\nRetrieved results: {retrieved_results}",
                temperature=0.1,
            )
            if retry_summary:
                return retry_summary
        except Exception:
            pass
    return deterministic_summary(parsed, result_blocks)


def deterministic_summary(parsed: ParsedQuery | Any, result_blocks: list[ResultBlock]) -> str:
    if not result_blocks:
        return "No matching records were found for this question."

    aggregate_summary = concise_aggregate_summary(result_blocks)
    if aggregate_summary:
        return aggregate_summary

    parts = []
    for block in result_blocks:
        if not block.rows:
            parts.append(f"{block.source_name}: no matching records were found.")
            continue
        display_column = preferred_display_column(block.columns)
        if display_column:
            values = [stringify_value(row.get(display_column)) for row in block.rows[:5]]
            values = [value for value in values if value]
            if values:
                parts.append(f"{block.source_name}: {', '.join(values)}.")
                continue
        parts.append(f"{block.source_name}: the matching records are shown in the table.")
    return " ".join(parts)


def concise_aggregate_summary(result_blocks: list[ResultBlock]) -> str | None:
    parts: list[str] = []
    for block in result_blocks:
        if "metric" not in block.columns or not block.rows:
            continue
        label_column = next((column for column in block.columns if column != "metric"), None)
        if not label_column:
            continue
        metric_label = infer_metric_label(block.question)
        leading = [
            f"{stringify_value(row.get(label_column))} ({metric_label} {stringify_value(row.get('metric'))})"
            for row in block.rows[:5]
        ]
        leading = [item for item in leading if not item.startswith("(")]
        if not leading:
            continue
        if len(block.rows) == 1:
            parts.append(f"{block.source_name}: {format_column_name(label_column)} is {leading[0]}.")
        else:
            parts.append(f"{block.source_name}: {format_column_name(label_column)} values are {', '.join(leading)}.")
    if not parts:
        return None
    return " ".join(parts)


def infer_metric_label(question: str) -> str:
    lower = question.lower()
    if any(term in lower for term in ("count", "how many", "number of", "most", "least", "total")):
        return "count"
    if "average" in lower or "avg" in lower:
        return "average"
    if "sum" in lower:
        return "sum"
    return "metric"


def preferred_display_column(columns: list[str]) -> str | None:
    candidates = [column for column in columns if column != "metric"]
    if not candidates:
        return None
    label_terms = {"category", "class", "description", "group", "label", "name", "segment", "status", "title", "type"}

    def score(column: str) -> int:
        tokens = column_tokens(column)
        value = 0
        if tokens & label_terms:
            value += 3
        if tokens & {"id", "identifier", "key", "uuid"}:
            value += 1
        return value

    return max(candidates, key=score)


def stringify_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def format_column_name(column: str) -> str:
    return column.replace("_", " ")


def looks_like_retrieval_process_summary(summary: str) -> bool:
    lower = summary.strip().lower()
    process_phrases = (
        "rows across",
        "result section",
        "result sections",
        "row was returned",
        "rows were returned",
        "row returned",
        "rows returned",
        "fetched ",
        "retrieved ",
    )
    return any(phrase in lower for phrase in process_phrases)
