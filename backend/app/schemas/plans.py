from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PlanStatus = Literal["DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "SUPERSEDED"]
PlanItemStatus = Literal["PLANNED", "DRAFTING", "DONE", "DROPPED"]
SourceType = Literal["comment", "similar_creator", "own_idea"]


class PlanItemResponse(BaseModel):
    id: str
    plan_id: str
    item_key: str
    topic: str
    format: str
    platform: str
    objective: str
    reason: str
    source_type: SourceType
    source_ref: str | None = None
    priority: int = 1
    scheduled_day: str | None = None
    status: PlanItemStatus


class PlanResponse(BaseModel):
    id: str
    lineage_id: str
    version: int
    previous_version_id: str | None = None
    run_id: str | None = None
    created_by: Literal["strategist", "creator"]
    status: PlanStatus
    feedback_text: str | None = None
    is_latest: bool = True
    brief_id: str | None = None
    items: list[PlanItemResponse] = Field(default_factory=list)
    created_at: datetime
    approved_at: datetime | None = None


class PlanEditItem(BaseModel):
    item_key: str | None = Field(default=None, description="Stable item key; omitted for new items")
    topic: str = Field(..., min_length=1)
    format: str = Field(...)
    platform: str = Field(...)
    objective: str = Field(...)
    reason: str = Field(...)
    source_type: SourceType = Field(default="own_idea")
    source_ref: str | None = None
    priority: int = 1
    scheduled_day: str | None = None
    status: PlanItemStatus = "PLANNED"


class PlanEditRequest(BaseModel):
    items: list[PlanEditItem] = Field(..., min_length=1)
    expected_version: int = Field(..., description="Optimistic locking check")


class PlanEditResponse(BaseModel):
    plan_id: str
    approval_id: str
