from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ApprovalItemType = Literal["plan", "draft", "depth_increase"]
ApprovalStatus = Literal["PENDING", "DECIDED", "CANCELLED"]
ApprovalDecision = Literal["APPROVED", "REJECTED", "EDITED"]


class ApprovalDecisionRequest(BaseModel):
    item_id: str = Field(..., description="Exact version row ID the creator reviewed")
    decision: ApprovalDecision
    feedback_text: str | None = Field(
        default=None, description="Required when decision is REJECTED"
    )
    edited_content: Any | None = Field(default=None, description="Required when decision is EDITED")


class ApprovalResponse(BaseModel):
    id: str
    run_id: str | None = None
    item_type: ApprovalItemType
    item_id: str
    status: ApprovalStatus
    decision: ApprovalDecision | None = None
    feedback_text: str | None = None
    edited_content: Any | None = None
    resulting_item_id: str | None = None
    brief_id: str | None = None
    item_details: dict[str, Any] | None = Field(
        default=None, description="Populated preview of the item to review"
    )
    requested_at: datetime
    decided_at: datetime | None = None


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalResponse
    resulting_item_id: str | None = None
    resumed_run_id: str | None = None
