from typing import Any, Literal, TypedDict


class TaskDict(TypedDict, total=False):
    id: str
    title: str
    agent: str
    position: int
    status: Literal["TODO", "DONE", "SKIPPED", "FAILED"]


class ContentState(TypedDict, total=False):
    # Core identifiers and inputs
    run_id: str
    user_goal: str
    depth_level: Literal["quick", "standard", "deep"]
    task_list: list[TaskDict]
    creator_profile: dict[str, Any]

    # Analysis & research context
    comment_insights: list[dict[str, Any]]
    research_results: dict[str, Any]

    # Plan state
    content_plan: list[dict[str, Any]]
    current_plan_id: str | None
    current_plan_version: int

    # Draft & revision state
    current_draft_id: str | None
    current_draft_version: int
    critic_feedback: list[dict[str, Any]]
    critic_score: float
    critic_retries: int

    # Strategy & post-mortem
    strategy: dict[str, Any]
    performance_insights: dict[str, Any]
    weekly_brief_id: str | None

    # Approval and human feedback
    user_feedback: str | None
    approval_status: Literal["NONE", "PENDING", "APPROVED", "REJECTED", "EDITED", "CANCELLED"]
    approval_item_id: str | None
    approval_item_type: Literal["plan", "draft", "depth_increase"] | None

    # Routing and execution budgets
    next_action: str
    execution_steps: int
    tokens_used: int
    stop_reason: str | None
    degraded: bool
    degraded_reason: str | None
    route_history: list[str]
