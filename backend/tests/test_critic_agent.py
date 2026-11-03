"""Tests for Critic Agent (AGT-05, FR-6, UT-06, IT-03).

Validates:
- Rubric scoring and token limits (under 3,000 tokens)
- Untrusted data directives and declared profile isolation (UT-38)
- Deterministic checks overriding LLM pass (TOOL-05 integration)
- Routing: passed -> approval, failed -> writer
- Review limit enforcement and best-draft selection (UT-06, IT-03)
- Depth-dependent limits (Quick: 2, Standard: 3)
"""

import pytest

from app.agents.critic import (
    CRITIC_TOKEN_LIMIT,
    critic_node,
    format_critic_user_prompt,
    generate_deterministic_fallback_evaluation,
)
from app.db.base import generate_uuid
from app.db.repositories.plans import (
    create_draft_version,
    get_critic_evaluation_for_draft,
    get_draft_by_id,
)
from app.db.session import SessionLocal
from app.tools.draft_checker import check_draft


def test_critic_prompt_token_limit_and_untrusted_data():
    plan_item = {
        "topic": "Microservices with FastAPI and SQLite WAL",
        "format": "script",
        "platform": "youtube",
        "objective": "Teach backend reliability",
    }
    creator_profile = {
        "niche": "Software Engineering",
        "tone_preset": "actionable_educator",
        "tone_instructions": "Focus on clean patterns.",
        "profile_source": "declared",
    }
    draft_content = "# Hook\nLearn how SQLite handles concurrency.\n\n# Body\nWAL mode allows multiple readers.\n\n# CTA\nSubscribe!"
    deterministic_result = check_draft(draft_content, "script", "youtube")

    user_prompt = format_critic_user_prompt(
        plan_item=plan_item,
        creator_profile=creator_profile,
        draft_content=draft_content,
        kind="script",
        platform="youtube",
        deterministic_result=deterministic_result,
        review_number=1,
        max_reviews=3,
    )

    assert "<creator_profile>" in user_prompt
    assert "</creator_profile>" in user_prompt
    assert "<deterministic_checks>" in user_prompt
    assert "<draft_content>" in user_prompt
    assert "actionable_educator" in user_prompt

    estimated_tokens = len(user_prompt.split())
    assert estimated_tokens < CRITIC_TOKEN_LIMIT


def test_deterministic_fallback_evaluation():
    plan_item = {"topic": "Local LLMs", "format": "script"}
    creator_profile = {"tone_preset": "actionable_educator"}

    # Valid draft
    good_content = (
        "# Hook\nFast hook.\n\n# Body\nCore concept explained.\n\n# CTA\nFollow for more!"
    )
    good_check = check_draft(good_content, "script", "youtube")
    eval_good = generate_deterministic_fallback_evaluation(
        draft_content=good_content,
        deterministic_result=good_check,
        plan_item=plan_item,
        creator_profile=creator_profile,
    )
    assert eval_good.passed is True
    assert eval_good.overall_score >= 7.0

    # Bad draft (missing CTA)
    bad_content = "# Hook\nFast hook.\n\n# Body\nCore concept without any outro or conclusion."
    bad_check = check_draft(bad_content, "script", "youtube")
    eval_bad = generate_deterministic_fallback_evaluation(
        draft_content=bad_content,
        deterministic_result=bad_check,
        plan_item=plan_item,
        creator_profile=creator_profile,
    )
    assert eval_bad.passed is False
    assert eval_bad.overall_score < 7.0
    assert any("CTA" in i["issue"] for i in eval_bad.issues)


@pytest.mark.asyncio
async def test_critic_deterministic_failure_blocks_passing(monkeypatch):
    """Even if LLM claims draft passed, deterministic failure forces passed=False."""

    # Mock LLM returning 9.0 and passed=True
    async def mock_llm(*args, **kwargs):
        return {
            "message": {
                "content": '{"overall_score": 9.0, "passed": true, "rubric": {"hook": {"score": 1.8, "feedback": ""}, "tone": {"score": 1.8, "feedback": ""}, "accuracy": {"score": 1.8, "feedback": ""}, "length": {"score": 1.8, "feedback": ""}, "relevance": {"score": 1.8, "feedback": ""}}, "issues": []}'
            }
        }, 0.05

    monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_llm)

    session = SessionLocal()
    try:
        # Create draft missing CTA
        bad_draft = create_draft_version(
            db=session,
            lineage_id=generate_uuid(),
            version=1,
            kind="script",
            platform="youtube",
            content="# Hook\nAwesome opening.\n\n# Body\nBody without CTA section.",
            status="IN_REVIEW",
        )

        state = {
            "current_draft_id": bad_draft.id,
            "depth_level": "standard",
            "critic_retries": 0,
        }

        res = await critic_node(state, db_session=session)
        assert res["next_action"] == "writer"
        assert res["critic_score"] < 7.0
        assert any("CTA" in issue["issue"] for issue in res["critic_feedback"])

        # Check DB evaluation
        evaluation = get_critic_evaluation_for_draft(session, bad_draft.id)
        assert evaluation is not None
        assert evaluation.passed is False
    finally:
        session.close()


@pytest.mark.asyncio
async def test_critic_passed_routes_to_approval(monkeypatch):
    """When draft passes evaluation, it is set to PENDING_APPROVAL and next_action is approval."""

    async def mock_llm(*args, **kwargs):
        return {
            "message": {
                "content": '{"overall_score": 8.5, "passed": true, "rubric": {"hook": {"score": 1.7, "feedback": "Great hook"}, "tone": {"score": 1.7, "feedback": ""}, "accuracy": {"score": 1.7, "feedback": ""}, "length": {"score": 1.7, "feedback": ""}, "relevance": {"score": 1.7, "feedback": ""}}, "issues": []}'
            }
        }, 0.05

    monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_llm)

    session = SessionLocal()
    try:
        good_draft = create_draft_version(
            db=session,
            lineage_id=generate_uuid(),
            version=1,
            kind="script",
            platform="youtube",
            content="# Hook\nEffective hook.\n\n# Body\nDetailed body explanation.\n\n# CTA\nSubscribe now!",
            status="IN_REVIEW",
        )

        state = {
            "current_draft_id": good_draft.id,
            "depth_level": "standard",
            "critic_retries": 0,
        }

        res = await critic_node(state, db_session=session)
        assert res["next_action"] == "approval"
        assert res["critic_score"] == 8.5
        assert res["current_draft_id"] == good_draft.id

        refreshed = get_draft_by_id(session, good_draft.id)
        assert refreshed is not None
        assert refreshed.status == "PENDING_APPROVAL"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_critic_review_limit_and_best_draft_selection(monkeypatch):
    """UT-06 / IT-03: Revision stops at review limit and selects the highest scoring version."""
    session = SessionLocal()
    try:
        lineage_id = generate_uuid()

        # Version 1: scored 6.8
        v1 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=1,
            kind="script",
            platform="youtube",
            content="# Hook\nHook 1.\n\n# Body\nBody 1.\n\n# CTA\nSubscribe!",
            status="IN_REVIEW",
        )

        # Mock review 1 (score 6.8, fail)
        async def mock_v1(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 6.8, "passed": false, "rubric": {"hook": {"score": 1.2, "feedback": "weak hook"}, "tone": {"score": 1.4, "feedback": ""}, "accuracy": {"score": 1.4, "feedback": ""}, "length": {"score": 1.4, "feedback": ""}, "relevance": {"score": 1.4, "feedback": ""}}, "issues": [{"issue": "Hook needs work"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_v1)
        res1 = await critic_node(
            {"current_draft_id": v1.id, "depth_level": "standard", "critic_retries": 0},
            db_session=session,
        )
        assert res1["next_action"] == "writer"
        assert res1["critic_retries"] == 1

        # Version 2: scored 5.5
        v2 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=2,
            kind="script",
            platform="youtube",
            content="# Hook\nHook 2.\n\n# Body\nBody 2.\n\n# CTA\nSubscribe!",
            previous_version_id=v1.id,
            status="IN_REVIEW",
        )

        async def mock_v2(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 5.5, "passed": false, "rubric": {"hook": {"score": 1.0, "feedback": ""}, "tone": {"score": 1.1, "feedback": ""}, "accuracy": {"score": 1.1, "feedback": ""}, "length": {"score": 1.1, "feedback": ""}, "relevance": {"score": 1.2, "feedback": ""}}, "issues": [{"issue": "Pacing off"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_v2)
        res2 = await critic_node(
            {"current_draft_id": v2.id, "depth_level": "standard", "critic_retries": 1},
            db_session=session,
        )
        assert res2["next_action"] == "writer"
        assert res2["critic_retries"] == 2

        # Version 3: scored 6.2 (Review 3 of 3 -> limit reached!)
        v3 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=3,
            kind="script",
            platform="youtube",
            content="# Hook\nHook 3.\n\n# Body\nBody 3.\n\n# CTA\nSubscribe!",
            previous_version_id=v2.id,
            status="IN_REVIEW",
        )

        async def mock_v3(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 6.2, "passed": false, "rubric": {"hook": {"score": 1.2, "feedback": ""}, "tone": {"score": 1.2, "feedback": ""}, "accuracy": {"score": 1.3, "feedback": ""}, "length": {"score": 1.2, "feedback": ""}, "relevance": {"score": 1.3, "feedback": ""}}, "issues": [{"issue": "Slightly low retention"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_v3)
        res3 = await critic_node(
            {"current_draft_id": v3.id, "depth_level": "standard", "critic_retries": 2},
            db_session=session,
        )

        # Revision loop stops and routes to approval
        assert res3["next_action"] == "approval"
        assert res3["critic_retries"] == 3

        # Best draft was Version 1 (score 6.8 > 6.2 > 5.5)
        assert res3["current_draft_id"] == v1.id
        best_draft = get_draft_by_id(session, v1.id)
        assert best_draft is not None
        assert best_draft.status == "PENDING_APPROVAL"
        assert any("review limit" in issue["issue"].lower() for issue in res3["critic_feedback"])

    finally:
        session.close()


@pytest.mark.asyncio
async def test_critic_quick_depth_limit(monkeypatch):
    """In Quick depth level, review limit is 2."""
    session = SessionLocal()
    try:
        lineage_id = generate_uuid()
        v1 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=1,
            kind="script",
            platform="youtube",
            content="# Hook\nHook.\n\n# Body\nBody.\n\n# CTA\nSubscribe!",
            status="IN_REVIEW",
        )

        async def mock_llm(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 6.0, "passed": false, "rubric": {"hook": {"score": 1.2, "feedback": ""}, "tone": {"score": 1.2, "feedback": ""}, "accuracy": {"score": 1.2, "feedback": ""}, "length": {"score": 1.2, "feedback": ""}, "relevance": {"score": 1.2, "feedback": ""}}, "issues": []}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_llm)

        # Review 1 of 2: retries remaining
        res1 = await critic_node(
            {"current_draft_id": v1.id, "depth_level": "quick", "critic_retries": 0},
            db_session=session,
        )
        assert res1["next_action"] == "writer"

        # Version 2 created by writer
        v2 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=2,
            kind="script",
            platform="youtube",
            content="# Hook\nHook 2.\n\n# Body\nBody 2.\n\n# CTA\nSubscribe!",
            previous_version_id=v1.id,
            status="IN_REVIEW",
        )

        # Review 2 of 2: limit reached -> routes to approval
        res2 = await critic_node(
            {"current_draft_id": v2.id, "depth_level": "quick", "critic_retries": 1},
            db_session=session,
        )
        assert res2["next_action"] == "approval"
        assert res2["critic_retries"] == 2
    finally:
        session.close()
