from typing import Tuple

import pandas as pd

from app.models.sources import CleaningReport


def normalize_column_name(column: str) -> str:
    normalized = column.strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(char for char in normalized if char.isalnum() or char == "_").strip("_") or "column"


def lightly_clean_dataframe(df: pd.DataFrame, remove_duplicates: bool = False) -> Tuple[pd.DataFrame, CleaningReport]:
    cleaned = df.copy()
    notes = ["Light cleaning only: headers, likely dates, obvious numeric strings, nulls, and duplicates."]

    original_columns = list(cleaned.columns)
    cleaned.columns = [normalize_column_name(str(column)) for column in cleaned.columns]
    if list(cleaned.columns) != original_columns:
        notes.append("Trimmed and safely normalized column names.")

    for column in cleaned.columns:
        if cleaned[column].dtype == object:
            cleaned[column] = cleaned[column].map(lambda value: value.strip() if isinstance(value, str) else value)
            try:
                numeric = pd.to_numeric(cleaned[column])
                cleaned[column] = numeric
                notes.append(f"Converted numeric-looking values in {column}.")
                continue
            except (TypeError, ValueError):
                pass
            lower = column.lower()
            if "date" in lower or "time" in lower or lower.endswith("_at"):
                parsed = pd.to_datetime(cleaned[column], errors="coerce")
                if parsed.notna().sum() > 0:
                    cleaned[column] = parsed
                    notes.append(f"Parsed likely date values in {column}.")

    duplicate_count = int(cleaned.duplicated().sum())
    if remove_duplicates and duplicate_count:
        cleaned = cleaned.drop_duplicates()
        notes.append(f"Removed {duplicate_count} exact duplicate rows.")
    elif duplicate_count:
        notes.append(f"Surfaced {duplicate_count} exact duplicate rows; none removed.")

    null_counts = {str(key): int(value) for key, value in cleaned.isna().sum().items() if int(value) > 0}
    if null_counts:
        notes.append("Surfaced null counts for columns with missing values.")

    return cleaned, CleaningReport(
        applied=True,
        notes=notes,
        duplicate_rows_removed=duplicate_count if remove_duplicates else 0,
        null_counts=null_counts,
    )
