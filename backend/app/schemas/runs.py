from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal[
    "PENDING",
    "RUNNING",
    "WAITING_APPROVAL",
    "COMPLETED",
    "FAILED",
    "STOPPED",
    "INTERRUPTED",
]

RunType = Literal["goal", "weekly_brief", "post_mortem"]
DepthLevel = Literal["quick", "standard", "deep"]
TaskStatus = Literal["TODO", "DONE", "SKIPPED", "FAILED"]


class RunCreateRequest(BaseModel):
    goal_text: str = Field(..., min_length=1, description="Goal in natural language")
    depth_level: DepthLevel | None = Field(default=None, description="Depth level for the run")


class RunCreateResponse(BaseModel):
    run_id: str
    status: RunStatus


class TaskResponse(BaseModel):
    id: str
    run_id: str
    title: str
    agent: str
    position: int
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class RunResponse(BaseModel):
    id: str
    goal_id: str | None = None
    run_type: RunType
    depth_level: DepthLevel
    status: RunStatus
    step_count: int = 0
    tokens_used: int = 0
    stop_reason: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    current_node: str | None = None
    tasks: list[TaskResponse] = Field(default_factory=list)
    pending_approval_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RoutingLogItem(BaseModel):
    step_number: int
    from_node: str
    to_node: str
    reason: str
    decided_by: Literal["model", "code"]
    eligible_nodes: list[str] = Field(default_factory=list)
    output_status: Literal["valid", "retried_valid", "fallback"]
    invalid_category: (
        Literal["bad_json", "schema_violation", "ineligible_node", "timeout"] | None
    ) = None
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: datetime
