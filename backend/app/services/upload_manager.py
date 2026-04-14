from pathlib import Path
from typing import List, Tuple
from uuid import uuid4

import pandas as pd
from fastapi import UploadFile

from app.config.settings import Settings
from app.models.sources import CleaningReport, SourceKind, SourceMetadata, SourceType
from app.services.light_cleaning import lightly_clean_dataframe
from app.services.schema_profiler import profile_dataframe
from app.services.workspace import SourceRuntime, workspace


class UploadLimitError(ValueError):
    pass


async def ingest_uploads(files: List[UploadFile], should_clean: bool, settings: Settings) -> Tuple[List[SourceMetadata], List[CleaningReport]]:
    if len(workspace.sources) + len(files) > settings.max_total_files:
        raise UploadLimitError(
            f"Workspace limit reached. This workspace allows {settings.max_total_files} sources total."
        )

    added: List[SourceMetadata] = []
    reports: List[CleaningReport] = []
    for upload in files:
        content = await upload.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > settings.max_file_size_mb:
            raise UploadLimitError(f"{upload.filename} is larger than {settings.max_file_size_mb} MB.")

        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise UploadLimitError("Only CSV and XLSX uploads are supported in the first version.")

        if suffix == ".csv":
            from io import BytesIO

            df = pd.read_csv(BytesIO(content))
            source_type = SourceType.csv
        else:
            from io import BytesIO

            df = pd.read_excel(BytesIO(content), engine="openpyxl")
            source_type = SourceType.xlsx

        report = CleaningReport(applied=False, notes=["Cleaning skipped for this upload batch."])
        if should_clean:
            df, report = lightly_clean_dataframe(df)
        reports.append(report)

        source_id = f"src_{uuid4().hex[:10]}"
        table_name = f"t_{source_id}"
        metadata = SourceMetadata(
            id=source_id,
            name=upload.filename or source_id,
            kind=SourceKind.file,
            source_type=source_type,
            table_name=table_name,
            row_count=len(df),
            columns=profile_dataframe(df),
            notes=report.notes,
        )
        workspace.add(SourceRuntime(metadata=metadata, dataframe=df))
        workspace.uploaded_file_count += 1
        added.append(metadata)

    return added, reports
