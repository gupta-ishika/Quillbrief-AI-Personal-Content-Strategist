import pytest
from pydantic import ValidationError

from app.graph import (
    ContentState,
    CriticEvaluationDecision,
    DepthIncreaseDecision,
    SupervisorDecision,
)


def test_content_state_structure() -> None:
    state: ContentState = {
        "run_id": "run_001",
        "user_goal": "Grow subscriber base",
        "depth_level": "standard",
        "task_list": [
            {"id": "t1", "title": "Analyze", "agent": "listener", "position": 1, "status": "TODO"}
        ],
        "creator_profile": {"niche": "FastAPI", "tone_preset": "educational"},
        "comment_insights": [],
        "research_results": {},
        "content_plan": [],
        "current_plan_id": None,
        "current_plan_version": 1,
        "current_draft_id": None,
        "current_draft_version": 1,
        "critic_feedback": [],
        "critic_score": 0.0,
        "critic_retries": 0,
        "strategy": {},
        "performance_insights": {},
        "weekly_brief_id": None,
        "user_feedback": None,
        "approval_status": "NONE",
        "approval_item_id": None,
        "approval_item_type": None,
        "next_action": "supervisor",
        "execution_steps": 0,
        "tokens_used": 0,
        "stop_reason": None,
        "degraded": False,
        "degraded_reason": None,
        "route_history": [],
    }
    assert state["run_id"] == "run_001"
    assert state["depth_level"] == "standard"
    assert len(state["task_list"]) == 1


def test_supervisor_decision_valid() -> None:
    data = {
        "next_node": "listener",
        "reason": "Need to check audience comments before planning content",
        "task_updates": [
            {
                "action": "add",
                "title": "Fetch audience questions",
                "agent": "listener",
                "position": 1,
                "status": "TODO",
            }
        ],
    }
    decision = SupervisorDecision.model_validate(data)
    assert decision.next_node == "listener"
    assert len(decision.task_updates) == 1
    assert decision.task_updates[0].action == "add"


def test_supervisor_decision_extra_field_forbidden() -> None:
    data = {
        "next_node": "listener",
        "reason": "Valid reason text",
        "unexpected_extra_field": 123,
    }
    with pytest.raises(ValidationError):
        SupervisorDecision.model_validate(data)


def test_supervisor_decision_invalid_node() -> None:
    data = {
        "next_node": "unauthorized_node",
        "reason": "Some reason here",
    }
    with pytest.raises(ValidationError):
        SupervisorDecision.model_validate(data)


def test_critic_evaluation_decision() -> None:
    data = {
        "score": 8.5,
        "passed": True,
        "rubric": {"hook": 8.0, "clarity": 9.0, "value": 8.5},
        "deterministic_checks": {"length": True, "sections": True},
        "feedback": ["Strong practical tutorial approach."],
    }
    eval_dec = CriticEvaluationDecision.model_validate(data)
    assert eval_dec.score == 8.5
    assert eval_dec.passed is True

    # Test score limits [0, 10]
    with pytest.raises(ValidationError):
        CriticEvaluationDecision.model_validate({**data, "score": 11.0})
    with pytest.raises(ValidationError):
        CriticEvaluationDecision.model_validate({**data, "score": -1.0})


def test_depth_increase_decision() -> None:
    data = {
        "current_depth": "quick",
        "proposed_depth": "standard",
        "reason": "More audience comments found than expected; extra research required.",
        "additional_steps": 5,
    }
    decision = DepthIncreaseDecision.model_validate(data)
    assert decision.additional_steps == 5

    with pytest.raises(ValidationError):
        DepthIncreaseDecision.model_validate({**data, "additional_steps": 25})  # > 20 max
