from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NodeName = Literal[
    "listener",
    "research",
    "strategist",
    "writer",
    "critic",
    "repurposer",
    "analyst",
    "approval",
    "END",
]

TaskStatus = Literal["TODO", "DONE", "SKIPPED", "FAILED"]


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "update", "reorder", "remove"] = Field(
        ..., description="Action to perform on the task list"
    )
    task_id: str | None = Field(default=None, description="Task ID for update/remove")
    title: str | None = Field(default=None, description="Title of the task")
    agent: str | None = Field(default=None, description="Agent assigned to the task")
    position: int | None = Field(default=None, description="Position order in task list")
    status: TaskStatus | None = Field(default=None, description="Updated status")


class SupervisorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_node: NodeName = Field(
        ..., description="The chosen next node from the eligible nodes list"
    )
    reason: str = Field(
        ..., min_length=5, max_length=500, description="Brief rationale for the routing decision"
    )
    task_updates: list[TaskUpdate] = Field(
        default_factory=list, description="Optional task list modifications"
    )


class CriticEvaluationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(..., ge=0.0, le=10.0, description="Rubric score between 0.0 and 10.0")
    passed: bool = Field(..., description="True if draft passes quality bar (score >= 7.0)")
    rubric: dict[str, float] = Field(
        default_factory=dict, description="Component scores (hook, clarity, value, tone)"
    )
    deterministic_checks: dict[str, bool] = Field(
        default_factory=dict, description="Results of deterministic checks (length, sections)"
    )
    feedback: list[str] = Field(
        default_factory=list, description="Specific feedback points for Writer revision"
    )


class DepthIncreaseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_depth: Literal["quick", "standard", "deep"] = Field(
        ..., description="Current run depth level"
    )
    proposed_depth: Literal["standard", "deep"] = Field(
        ..., description="Proposed higher depth level"
    )
    reason: str = Field(
        ..., min_length=10, max_length=500, description="Justification for expanding run budget"
    )
    additional_steps: int = Field(
        ..., ge=1, le=20, description="Number of additional execution steps requested"
    )
