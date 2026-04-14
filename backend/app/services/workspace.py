from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import Engine

from app.models.sources import SourceMetadata
from app.utils.text import query_tokens


@dataclass
class SourceRuntime:
    metadata: SourceMetadata
    dataframe: Optional[pd.DataFrame] = None
    engine: Optional[Engine] = None
    sql_table: Optional[str] = None


@dataclass
class WorkspaceRegistry:
    sources: Dict[str, SourceRuntime] = field(default_factory=dict)
    uploaded_file_count: int = 0

    def add(self, runtime: SourceRuntime) -> None:
        self.sources[runtime.metadata.id] = runtime

    def get(self, source_id: str) -> SourceRuntime:
        return self.sources[source_id]

    def remove(self, source_id: str) -> bool:
        runtime = self.sources.pop(source_id, None)
        if runtime is None:
            return False
        if runtime.metadata.kind == "file" and self.uploaded_file_count > 0:
            self.uploaded_file_count -= 1
        return True

    def list_metadata(self) -> list[SourceMetadata]:
        return [runtime.metadata for runtime in self.sources.values()]

    def find_by_hint(self, hint: str | None) -> Optional[SourceRuntime]:
        if not hint:
            return None
        needle = hint.lower()
        for runtime in self.sources.values():
            metadata = runtime.metadata
            haystack = " ".join([metadata.name, metadata.table_name, *[column.name for column in metadata.columns]]).lower()
            if needle in haystack or haystack in needle:
                return runtime
        return None

    def metadata_with_query_value_samples(self, question: str, source_ids: set[str] | None = None) -> list[SourceMetadata]:
        tokens = query_tokens(question)
        if not tokens:
            return self.list_metadata()

        enriched: list[SourceMetadata] = []
        for runtime in self.sources.values():
            metadata = runtime.metadata
            if source_ids is not None and metadata.id not in source_ids:
                continue
            if runtime.dataframe is None:
                enriched.append(metadata)
                continue

            updated_columns = []
            for column in metadata.columns:
                samples = list(column.sample_values)
                if column.name in runtime.dataframe.columns:
                    series = runtime.dataframe[column.name].dropna().astype(str)
                    matched_values = []
                    for token in tokens:
                        pattern = rf"\b{re.escape(token)}\b" if len(token) <= 3 else re.escape(token)
                        matches = series[series.str.lower().str.contains(pattern, regex=True)].head(5).tolist()
                        matched_values.extend(matches)
                    for value in matched_values:
                        if value not in samples:
                            samples.append(value)
                    samples = samples[:25]
                updated_columns.append(column.model_copy(update={"sample_values": samples}))
            enriched.append(metadata.model_copy(update={"columns": updated_columns}))
        return enriched


workspace = WorkspaceRegistry()
