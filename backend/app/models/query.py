from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AggregateFunction(str, Enum):
    count = "count"
    sum = "sum"
    avg = "avg"
    min = "min"
    max = "max"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class FilterOperator(str, Enum):
    eq = "eq"
    neq = "neq"
    contains = "contains"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"


class FilterSpec(BaseModel):
    column: str
    operator: FilterOperator
    value: Any


class OperationSpec(BaseModel):
    select_columns: List[str] = Field(default_factory=list)
    filters: List[FilterSpec] = Field(default_factory=list)
    group_by: List[str] = Field(default_factory=list)
    aggregate: Optional[AggregateFunction] = None
    aggregate_column: Optional[str] = None
    sort_by: Optional[str] = None
    sort_direction: SortDirection = SortDirection.desc
    limit: int = Field(default=10, ge=1, le=500)


class SubQuestion(BaseModel):
    id: str
    label: str
    question: str
    source_id: Optional[str] = None
    source_hint: Optional[str] = None
    requires_join: bool = False
    chart_intent: bool = False
    operation: OperationSpec = Field(default_factory=OperationSpec)


class SqlSubQuery(BaseModel):
    id: str
    label: str
    question: str
    source_id: Optional[str] = None
    source_hint: Optional[str] = None
    requires_join: bool = False
    chart_intent: bool = False
    sql: str


class ParsedQuery(BaseModel):
    original_question: str
    sub_questions: List[SubQuestion]
    likely_requires_join: bool = False
    wants_explanation: bool = False
    needs_source_confirmation: bool = False
    candidate_source_ids: List[str] = Field(default_factory=list)


class SqlQueryPlan(BaseModel):
    original_question: str
    sub_queries: List[SqlSubQuery]
    likely_requires_join: bool = False
    wants_explanation: bool = False
    needs_source_confirmation: bool = False
    candidate_source_ids: List[str] = Field(default_factory=list)


class ChartKind(str, Enum):
    bar = "bar"
    horizontal_bar = "horizontal_bar"
    line = "line"
    area = "area"
    pie = "pie"
    radial_bar = "radial_bar"
    treemap = "treemap"
    radar = "radar"
    scatter = "scatter"
    histogram = "histogram"


class ChartSpec(BaseModel):
    enabled: bool = False
    chart_type: Optional[ChartKind] = None
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    title: Optional[str] = None


class ResultBlock(BaseModel):
    id: str
    label: str
    source_name: str
    question: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    sql: Optional[str] = None
    chart: ChartSpec = Field(default_factory=ChartSpec)


class QueryRequest(BaseModel):
    question: str
    allow_joins: bool = False
    preferred_source_id: Optional[str] = None


class CandidateSource(BaseModel):
    id: str
    name: str
    columns: List[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    needs_join_confirmation: bool = False
    join_confirmation_message: Optional[str] = None
    needs_source_confirmation: bool = False
    source_confirmation_message: Optional[str] = None
    candidate_sources: List[CandidateSource] = Field(default_factory=list)
    result_blocks: List[ResultBlock] = Field(default_factory=list)
    final_summary: Optional[str] = None
    debug: Optional[Dict[str, Any]] = None
