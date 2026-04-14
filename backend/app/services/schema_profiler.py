from __future__ import annotations

from typing import Any, Dict, Iterable, List

import pandas as pd

from app.models.sources import ColumnProfile


def profile_dataframe(df: pd.DataFrame) -> List[ColumnProfile]:
    profiles: List[ColumnProfile] = []
    for column in df.columns:
        series = df[column]
        sample_values = [coerce_sample_value(value) for value in series.dropna().head(10).tolist()]
        semantic_type = infer_semantic_type(str(column), str(series.dtype), series)
        is_identifier = infer_identifier(str(column), series)
        profiles.append(
            ColumnProfile(
                name=str(column),
                dtype=str(series.dtype),
                null_count=int(series.isna().sum()),
                unique_count=int(series.nunique(dropna=True)),
                sample_values=sample_values,
                semantic_type=semantic_type,
                is_identifier=is_identifier,
            )
        )
    return profiles


def coerce_sample_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def profile_sql_columns(columns: Iterable[Dict[str, Any]]) -> List[ColumnProfile]:
    profiles: List[ColumnProfile] = []
    for column in columns:
        name = str(column["name"])
        dtype = str(column.get("type", "unknown"))
        profiles.append(
            ColumnProfile(
                name=name,
                dtype=dtype,
                null_count=0,
                unique_count=0,
                sample_values=[],
                semantic_type=infer_semantic_type(name, dtype, None),
                is_identifier=infer_identifier(name, None),
            )
        )
    return profiles


def infer_semantic_type(name: str, dtype: str, series: pd.Series | None) -> str:
    lower_name = name.lower()
    lower_dtype = dtype.lower()

    if "bool" in lower_dtype:
        return "boolean"
    if any(term in lower_dtype for term in ("datetime", "timestamp", "date", "time")):
        return "temporal"
    if any(term in lower_dtype for term in ("int", "float", "double", "decimal", "number")):
        return "numeric"
    if infer_identifier(name, series):
        return "identifier"
    if any(term in lower_name for term in ("date", "time", "month", "year")):
        return "temporal"
    if any(term in lower_name for term in ("count", "total", "amount", "price", "revenue", "score", "duration", "delay", "cost", "qty")):
        return "numeric"
    if any(term in lower_name for term in ("id", "uuid", "key")):
        return "identifier"

    if series is not None:
        non_null = series.dropna()
        if non_null.empty:
            return "unknown"
        row_count = max(len(non_null), 1)
        unique_count = int(non_null.nunique(dropna=True))
        unique_ratio = unique_count / row_count
        if unique_count <= 80 or unique_ratio <= 0.25:
            return "categorical"
        return "text"
    return "unknown"


def infer_identifier(name: str, series: pd.Series | None) -> bool:
    lower_name = name.lower()
    if lower_name == "id" or lower_name.endswith("_id") or "uuid" in lower_name:
        return True
    if series is None:
        return False
    non_null = series.dropna()
    if non_null.empty or len(non_null) < 20:
        return False
    unique_ratio = float(non_null.nunique(dropna=True)) / float(len(non_null))
    return unique_ratio >= 0.95
