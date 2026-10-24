from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluationRunRequest(BaseModel):
    test_case_ids: list[str] | None = Field(
        default=None, description="Optional list of fixture IDs; defaults to all"
    )


class EvaluationRunResponse(BaseModel):
    evaluation_run_id: str


class EvaluationResultItem(BaseModel):
    test_case_id: str
    completed: bool
    plan_score: float = 0.0
    agent_calls: int = 0
    routing_errors: int = 0
    routing_invalid: int = 0
    routing_suboptimal: int = 0
    duration_seconds: float = 0.0
    tokens_used: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunDetailsResponse(BaseModel):
    id: str
    system_variant: Literal["fixed_pipeline", "supervisor_graph"]
    model_name: str
    model_version: str | None = None
    prompt_version: str | None = None
    tool_versions: dict[str, str] = Field(default_factory=dict)
    fixture_set_version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime | None = None
    results: list[EvaluationResultItem] = Field(default_factory=list)
