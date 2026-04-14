from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class QueryIntent:
    comparison: bool = False
    trend: bool = False
    ranking: bool = False
    explicit_chart: bool = False
    wants_chart: bool = False
    wants_explanation: bool = False
    mentions_join: bool = False
    mentions_identifier: bool = False
    explicit_limit: int | None = None
    top_without_number: bool = False
    fetch_only: bool = False
    aggregate_superlative: bool = False


def detect_intent(question: str) -> QueryIntent:
    lower = question.lower()
    explicit_limit = extract_explicit_limit(lower)
    explicit_chart = any(term in lower for term in ("chart", "plot", "graph", "visualize"))
    comparison = any(term in lower for term in ("compare", "comparison", " vs ", " versus ", "against", "breakdown", "split by"))
    trend = any(term in lower for term in ("trend", "over time", "change", "month over month", "year over year", "wrt", "with respect to"))
    aggregate_superlative = bool(
        re.search(r"\b(?:with|having|has|have)\s+(?:the\s+)?(?:most|fewest|least|highest|lowest|largest|smallest)\b", lower)
    )
    ranking = aggregate_superlative or any(
        term in lower for term in ("top", "bottom", "highest", "lowest", "largest", "smallest", "longest", "shortest", "rank", "most", "fewest", "least")
    )
    mentions_join = any(term in lower for term in ("join", "combine", "merge", "match across", "correlate", "relationship between"))
    wants_explanation = any(term in lower for term in ("why", "explain", "insight", "analysis", "analyze", "reason", "because"))
    mentions_identifier = bool(re.search(r"\b(?:id|ids|identifier|uuid)\b", lower))
    top_without_number = bool(re.search(r"\btop\b", lower)) and explicit_limit is None
    fetch_only = (
        any(term in lower for term in ("show", "list", "fetch", "retrieve", "give me", "display"))
        and not wants_explanation
        and not comparison
        and not trend
    )
    wants_chart = explicit_chart or comparison or trend or ranking

    return QueryIntent(
        comparison=comparison,
        trend=trend,
        ranking=ranking,
        explicit_chart=explicit_chart,
        wants_chart=wants_chart,
        wants_explanation=wants_explanation,
        mentions_join=mentions_join,
        mentions_identifier=mentions_identifier,
        explicit_limit=explicit_limit,
        top_without_number=top_without_number,
        fetch_only=fetch_only,
        aggregate_superlative=aggregate_superlative,
    )


def has_data_question_intent(question: str) -> bool:
    lower = question.lower()
    intent = detect_intent(lower)
    if intent.wants_chart or intent.fetch_only or intent.wants_explanation or intent.mentions_join:
        return True
    if intent.explicit_limit is not None:
        return True
    return any(
        term in lower
        for term in (
            "average",
            "avg",
            "count",
            "data",
            "dataset",
            "distribution",
            "filter",
            "group",
            "how many",
            "maximum",
            "minimum",
            "records",
            "rows",
            "source",
            "sum",
            "table",
            "total",
        )
    )


def extract_explicit_limit(question: str) -> int | None:
    match = re.search(r"\b(?:top|first|show|limit|latest|newest|recent)\s+(\d{1,3})\b", question)
    if not match:
        match = re.search(r"\b(?:show|give|get|list|fetch|display)\s+(?:me\s+|us\s+|the\s+)?(\d{1,3})\b", question)
    if not match:
        match = re.search(r"\b(\d{1,3})\s+(?:records|rows|entries|results)\b", question)
    if match:
        return max(1, min(500, int(match.group(1))))
    return None
