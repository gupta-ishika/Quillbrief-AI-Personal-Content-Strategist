"""Integration tests for Writer to Critic loop and best-draft selection (GRAPH-05, IT-03, UT-06).

Validates:
- Graph topology: writer -> critic, critic -> writer | approval
- Iterative revision: Writer -> Critic (fail) -> Writer -> Critic (pass) -> Approval
- Review exhaustion: Fail 3 times -> stops revision -> selects highest scoring draft version -> Approval
"""

import pytest

from app.agents.critic import critic_node
from app.agents.writer import writer_node
from app.db.base import generate_uuid
from app.db.repositories.plans import (
    create_draft_version,
    create_plan_version,
    get_draft_by_id,
)
from app.db.repositories.runs import create_run
from app.db.session import SessionLocal
from app.graph.builder import create_content_graph, route_from_critic, route_from_supervisor


def test_graph_topology_contains_writer_and_critic():
    """Verifies compiled StateGraph includes writer, critic, and correct routing branches."""
    graph = create_content_graph()
    assert "writer" in graph.nodes
    assert "critic" in graph.nodes
    assert "supervisor" in graph.nodes
    assert "approval" in graph.nodes

    # Test route_from_supervisor allows writer
    assert route_from_supervisor({"next_action": "writer"}) == "writer"
    assert route_from_supervisor({"next_action": "strategist"}) == "strategist"

    # Test route_from_critic branches
    assert route_from_critic({"next_action": "writer"}) == "writer"
    assert route_from_critic({"next_action": "approval"}) == "approval"
    assert route_from_critic({"next_action": "unknown"}) == "approval"


@pytest.mark.asyncio
async def test_writer_to_critic_revision_loop_fail_then_pass(monkeypatch):
    """IT-03: Draft fails initial review, writer revises with feedback, second review passes."""
    session = SessionLocal()
    try:
        run = create_run(session, run_type="goal", depth_level="standard")
        run_id = run.id
        lineage_id = generate_uuid()

        # Seed an approved plan
        plan = create_plan_version(
            db=session,
            lineage_id=lineage_id,
            version=1,
            run_id=run_id,
            items=[
                {
                    "topic": "FastAPI Performance Tuning",
                    "format": "script",
                    "platform": "youtube",
                    "objective": "Deep technical explanation of async benchmarks",
                    "reason": "Top requested topic",
                    "source_type": "comment",
                    "priority": 1,
                }
            ],
            status="APPROVED",
        )

        state = {
            "run_id": run_id,
            "depth_level": "standard",
            "creator_profile": {
                "niche": "Software Engineering",
                "tone_preset": "actionable_educator",
            },
            "content_plan": [
                {
                    "id": plan.items[0].id,
                    "item_key": plan.items[0].item_key,
                    "topic": plan.items[0].topic,
                    "format": plan.items[0].format,
                    "platform": plan.items[0].platform,
                    "objective": plan.items[0].objective,
                }
            ],
            "execution_steps": 1,
            "tokens_used": 100,
            "critic_retries": 0,
        }

        # Step 1: Writer creates draft v1 (lacking strong hook)
        async def mock_writer_v1(*args, **kwargs):
            return {
                "message": {
                    "content": '{"kind": "script", "platform": "youtube", "title": "FastAPI Tuning", "content": "# Hook\\nFastAPI is fast.\\n\\n# Body\\nHere are some benchmark details.\\n\\n# CTA\\nSubscribe for more!", "hook": "FastAPI is fast.", "sections": ["Hook", "Body", "CTA"]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.writer.request_writer_llm", mock_writer_v1)
        res_w1 = await writer_node(state, db_session=session)
        draft1_id = res_w1["current_draft_id"]
        assert res_w1["current_draft_version"] == 1
        assert res_w1["next_action"] == "critic"

        state.update(res_w1)

        # Step 2: Critic reviews v1 -> fails (hook is weak)
        async def mock_critic_v1(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 6.2, "passed": false, "rubric": {"hook": {"score": 1.0, "feedback": "Hook is too plain"}, "tone": {"score": 1.4, "feedback": ""}, "accuracy": {"score": 1.3, "feedback": ""}, "length": {"score": 1.2, "feedback": ""}, "relevance": {"score": 1.3, "feedback": ""}}, "issues": [{"issue": "Hook lacks punch", "suggestion": "Add concrete metric hook"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_critic_v1)
        res_c1 = await critic_node(state, db_session=session)
        assert res_c1["next_action"] == "writer"
        assert res_c1["critic_retries"] == 1
        assert res_c1["critic_score"] == 6.2
        assert len(res_c1["critic_feedback"]) >= 1

        state.update(res_c1)

        # Step 3: Writer revises draft -> produces v2
        async def mock_writer_v2(*args, **kwargs):
            return {
                "message": {
                    "content": '{"kind": "script", "platform": "youtube", "title": "FastAPI 10x Performance", "content": "# Hook\\nDid you know FastAPI can process 50,000 requests per second with three tuning tweaks?\\n\\n# Body\\nFirst, use uvloop.\\nSecond, optimize connection pools.\\nThird, enable gzip compression.\\n\\n# CTA\\nSubscribe and hit the bell for more backend performance deep dives!", "hook": "Did you know FastAPI can process 50,000 req/sec?", "sections": ["Hook", "Body", "CTA"]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.writer.request_writer_llm", mock_writer_v2)
        res_w2 = await writer_node(state, db_session=session)
        draft2_id = res_w2["current_draft_id"]
        assert draft2_id != draft1_id
        assert res_w2["current_draft_version"] == 2
        assert res_w2["next_action"] == "critic"

        state.update(res_w2)

        # Step 4: Critic reviews v2 -> passes!
        async def mock_critic_v2(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 8.8, "passed": true, "rubric": {"hook": {"score": 1.8, "feedback": "Engaging metric hook"}, "tone": {"score": 1.8, "feedback": ""}, "accuracy": {"score": 1.8, "feedback": ""}, "length": {"score": 1.7, "feedback": ""}, "relevance": {"score": 1.7, "feedback": ""}}, "issues": []}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_critic_v2)
        res_c2 = await critic_node(state, db_session=session)
        assert res_c2["next_action"] == "approval"
        assert res_c2["critic_score"] == 8.8
        assert res_c2["current_draft_id"] == draft2_id
        assert res_c2["approval_item_type"] == "draft"

        # Check DB states
        d2 = get_draft_by_id(session, draft2_id)
        assert d2 is not None
        assert d2.status == "PENDING_APPROVAL"
        assert d2.version == 2
        assert d2.previous_version_id == draft1_id

    finally:
        session.close()


@pytest.mark.asyncio
async def test_critic_exhaustion_selects_best_draft_version(monkeypatch):
    """IT-03 / UT-06: 3 failed reviews -> stops loop -> selects best draft in lineage."""
    session = SessionLocal()
    try:
        lineage_id = generate_uuid()

        # Seed 3 draft versions with known content
        d1 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=1,
            kind="script",
            platform="youtube",
            content="# Hook\nDraft 1 hook.\n\n# Body\nDraft 1 body.\n\n# CTA\nSubscribe!",
            status="IN_REVIEW",
        )
        d2 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=2,
            kind="script",
            platform="youtube",
            content="# Hook\nDraft 2 hook.\n\n# Body\nDraft 2 body.\n\n# CTA\nSubscribe!",
            previous_version_id=d1.id,
            status="IN_REVIEW",
        )
        d3 = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=3,
            kind="script",
            platform="youtube",
            content="# Hook\nDraft 3 hook.\n\n# Body\nDraft 3 body.\n\n# CTA\nSubscribe!",
            previous_version_id=d2.id,
            status="IN_REVIEW",
        )

        # Mock review 1 on d1 -> score 6.9
        async def mock_c1(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 6.9, "passed": false, "rubric": {"hook": {"score": 1.3, "feedback": ""}, "tone": {"score": 1.4, "feedback": ""}, "accuracy": {"score": 1.4, "feedback": ""}, "length": {"score": 1.4, "feedback": ""}, "relevance": {"score": 1.4, "feedback": ""}}, "issues": [{"issue": "Nearly passed"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_c1)
        r1 = await critic_node(
            {"current_draft_id": d1.id, "depth_level": "standard", "critic_retries": 0},
            db_session=session,
        )
        assert r1["next_action"] == "writer"
        assert r1["critic_retries"] == 1

        # Mock review 2 on d2 -> score 5.2
        async def mock_c2(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 5.2, "passed": false, "rubric": {"hook": {"score": 1.0, "feedback": ""}, "tone": {"score": 1.0, "feedback": ""}, "accuracy": {"score": 1.1, "feedback": ""}, "length": {"score": 1.0, "feedback": ""}, "relevance": {"score": 1.1, "feedback": ""}}, "issues": [{"issue": "Significant flaws"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_c2)
        r2 = await critic_node(
            {"current_draft_id": d2.id, "depth_level": "standard", "critic_retries": 1},
            db_session=session,
        )
        assert r2["next_action"] == "writer"
        assert r2["critic_retries"] == 2

        # Mock review 3 on d3 -> score 6.1 (3rd review -> limit reached!)
        async def mock_c3(*args, **kwargs):
            return {
                "message": {
                    "content": '{"overall_score": 6.1, "passed": false, "rubric": {"hook": {"score": 1.2, "feedback": ""}, "tone": {"score": 1.2, "feedback": ""}, "accuracy": {"score": 1.2, "feedback": ""}, "length": {"score": 1.2, "feedback": ""}, "relevance": {"score": 1.3, "feedback": ""}}, "issues": [{"issue": "Still slightly weak"}]}'
                }
            }, 0.05

        monkeypatch.setattr("app.agents.critic.request_critic_llm", mock_c3)
        r3 = await critic_node(
            {"current_draft_id": d3.id, "depth_level": "standard", "critic_retries": 2},
            db_session=session,
        )

        # Must route to approval and select best draft d1 (score 6.9 > 6.1 > 5.2)
        assert r3["next_action"] == "approval"
        assert r3["critic_retries"] == 3
        assert r3["current_draft_id"] == d1.id

        best_d = get_draft_by_id(session, d1.id)
        assert best_d is not None
        assert best_d.status == "PENDING_APPROVAL"
        assert any("review limit" in issue["issue"].lower() for issue in r3["critic_feedback"])

    finally:
        session.close()
