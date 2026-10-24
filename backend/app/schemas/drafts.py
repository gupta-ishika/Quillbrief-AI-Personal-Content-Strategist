from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DraftKind = Literal[
    "script",
    "title",
    "description",
    "community_post",
    "caption",
    "linkedin_post",
    "x_thread",
]

DraftStatus = Literal[
    "WRITING",
    "IN_REVIEW",
    "PENDING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "SUPERSEDED",
    "POSTED",
]

RepurposeTarget = Literal[
    "youtube_short",
    "community_post",
    "description",
    "instagram_caption",
    "linkedin_post",
    "x_thread",
]


class CriticEvaluationResponse(BaseModel):
    id: str
    draft_id: str
    review_number: int = Field(..., ge=1, le=3)
    score: float
    passed: bool
    rubric: dict[str, Any] = Field(default_factory=dict)
    deterministic: dict[str, Any] = Field(default_factory=dict)
    feedback: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DraftResponse(BaseModel):
    id: str
    lineage_id: str
    version: int
    previous_version_id: str | None = None
    plan_item_id: str | None = None
    item_key: str | None = None
    parent_draft_id: str | None = None
    kind: DraftKind
    platform: str
    content: str
    created_by: Literal["model", "creator"]
    status: DraftStatus
    is_latest: bool = True
    critic_evaluation: CriticEvaluationResponse | None = None
    posted_at: datetime | None = None
    posted_ref: Literal["url", "platform_id", "none"] | None = None
    posted_url: str | None = None
    posted_platform_id: str | None = None
    child_draft_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DraftVersionSummary(BaseModel):
    version: int
    status: DraftStatus
    created_by: str
    created_at: datetime
    is_approved: bool
    is_posted: bool


class DraftEditRequest(BaseModel):
    content: str = Field(..., min_length=1)
    expected_version: int = Field(..., description="Optimistic locking check")


class DraftEditResponse(BaseModel):
    draft_id: str
    approval_id: str


class MarkPostedRequest(BaseModel):
    posted_url: str | None = None
    platform_content_id: str | None = None
    posted_at: datetime | None = None


class MarkPostedResponse(BaseModel):
    draft_id: str
    status: Literal["POSTED"]
    posted_ref: Literal["url", "platform_id", "none"]
    analytics_eligible: bool


class LinkPostedRequest(BaseModel):
    posted_url: str | None = None
    platform_content_id: str | None = None


class RepurposeRequest(BaseModel):
    targets: list[RepurposeTarget] = Field(..., min_length=1)


class RepurposeResponse(BaseModel):
    run_id: str
