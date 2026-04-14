from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    file = "file"
    sql = "sql"


class SourceType(str, Enum):
    csv = "csv"
    xlsx = "xlsx"
    sqlite = "sqlite"
    mysql = "mysql"
    postgresql = "postgresql"


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int = 0
    unique_count: int = 0
    sample_values: List[Any] = Field(default_factory=list)
    semantic_type: str = "unknown"
    is_identifier: bool = False


class SourceMetadata(BaseModel):
    id: str
    name: str
    kind: SourceKind
    source_type: SourceType
    table_name: str
    row_count: Optional[int] = None
    columns: List[ColumnProfile] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class WorkspaceState(BaseModel):
    sources: List[SourceMetadata]
    uploaded_file_count: int
    max_total_files: int
    max_file_size_mb: int


class SqlConnectionRequest(BaseModel):
    name: str
    db_type: SourceType
    connection_string: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    sqlite_path: Optional[str] = None


class CleaningReport(BaseModel):
    applied: bool
    notes: List[str] = Field(default_factory=list)
    duplicate_rows_removed: int = 0
    null_counts: Dict[str, int] = Field(default_factory=dict)
