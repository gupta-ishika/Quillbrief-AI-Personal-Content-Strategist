from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommentInsightExample(BaseModel):
    comment_id: str
    text: str | None = None
    like_count: int = 0
    published_at: datetime
    available: bool = True


class CommentInsightResponse(BaseModel):
    id: str
    creator_id: str
    run_id: str
    theme_label: str
    comment_count: int
    examples: list[CommentInsightExample] = Field(default_factory=list)
    coverage_analyzed: int
    coverage_total: int
    status: Literal["current", "superseded"]
    created_at: datetime


class AnalystFindingResponse(BaseModel):
    id: str
    run_id: str
    draft_id: str | None = None
    finding: str
    recommendation: str
    confidence: Literal["low", "moderate", "high"]
    sample_size: int
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class StrategyEntryResponse(BaseModel):
    id: str
    creator_id: str
    key: str
    value: Any
    reason: str
    supporting_finding_ids: list[str] = Field(default_factory=list)
    status: Literal["active", "superseded"]
    created_at: datetime
