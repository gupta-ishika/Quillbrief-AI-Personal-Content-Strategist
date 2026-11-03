"""Tests for Writer Agent (AGT-04).

Validates:
- Draft generation for scripts, titles, descriptions, captions, and posts
- Incorporation of creator profile (UT-38: declared profile only)
- Token limit adherence (under 4,000 input tokens)
- Draft revision lineage and version incrementing (VER-02, UT-18)
- Deterministic fallback when LLM is unavailable
"""

import pytest

from app.agents.writer import (
    WRITER_TOKEN_LIMIT,
    format_writer_user_prompt,
    generate_deterministic_fallback_draft,
    writer_node,
)
from app.db.repositories.plans import get_draft_by_id
from app.db.session import SessionLocal


def test_writer_prompt_token_limit_and_untrusted_data():
    plan_item = {
        "topic": "Python Async Programming for High-Throughput APIs",
        "format": "script",
        "platform": "youtube",
        "objective": "Teach concurrency concepts with clean diagrams",
        "reason": "Audience asked for backend performance tips",
        "source_type": "comment",
    }
    creator_profile = {
        "niche": "Software Engineering & AI",
        "tone_preset": "actionable_educator",
        "tone_instructions": "Keep explanations practical and concise.",
        "profile_source": "declared",
    }

    user_prompt = format_writer_user_prompt(plan_item, creator_profile)
    assert "<creator_profile>" in user_prompt
    assert "</creator_profile>" in user_prompt
    assert "actionable_educator" in user_prompt

    # Verify token limit cap
    estimated_tokens = len(user_prompt.split())
    assert estimated_tokens < WRITER_TOKEN_LIMIT


def test_deterministic_fallback_drafts_across_formats():
    creator_profile = {
        "niche": "AI Tech",
        "tone_preset": "authentic_storyteller",
    }

    # Test script fallback
    script_draft = generate_deterministic_fallback_draft(
        plan_item={"topic": "Agentic AI", "format": "script", "platform": "youtube"},
        creator_profile=creator_profile,
    )
    assert script_draft.kind == "script"
    assert "# Hook" in script_draft.content
    assert "# CTA" in script_draft.content

    # Test title fallback
    title_draft = generate_deterministic_fallback_draft(
        plan_item={"topic": "Agentic AI", "format": "title", "platform": "youtube"},
        creator_profile=creator_profile,
    )
    assert title_draft.kind == "title"
    assert len(title_draft.content) <= 100

    # Test x_thread fallback
    thread_draft = generate_deterministic_fallback_draft(
        plan_item={"topic": "Agentic AI", "format": "thread", "platform": "x"},
        creator_profile=creator_profile,
    )
    assert thread_draft.kind == "x_thread"
    assert "---" in thread_draft.content
    assert "1/" in thread_draft.content

    # Test linkedin_post fallback
    li_draft = generate_deterministic_fallback_draft(
        plan_item={"topic": "Agentic AI", "format": "post", "platform": "linkedin"},
        creator_profile=creator_profile,
    )
    assert li_draft.kind == "linkedin_post"
    assert "?" in li_draft.content


@pytest.mark.asyncio
async def test_writer_node_execution_and_version_lineage(monkeypatch):
    # Mock LLM to return structured output quickly without timeout
    async def mock_llm(*args, **kwargs):
        return {
            "message": {
                "content": '{"kind": "script", "platform": "youtube", "title": "Mock Title", "content": "# Hook\\nFast mock hook.\\n\\n# Body\\nFast mock body.\\n\\n# CTA\\nSubscribe!", "hook": "Fast mock hook.", "sections": ["Hook", "Body", "CTA"]}'
            }
        }, 0.05

    monkeypatch.setattr("app.agents.writer.request_writer_llm", mock_llm)

    session = SessionLocal()
    try:
        state = {
            "run_id": "test-run-writer",
            "user_goal": "Create a tutorial video on LangGraph checkpoints",
            "creator_profile": {
                "niche": "Developer Tools",
                "tone_preset": "actionable_educator",
            },
            "content_plan": [
                {
                    "topic": "LangGraph SQLite Checkpointers",
                    "format": "script",
                    "platform": "youtube",
                    "objective": "Explain crash recovery in stateful agents",
                    "reason": "Production reliability requirement",
                }
            ],
            "execution_steps": 1,
            "tokens_used": 100,
        }

        # Step 1: Initial draft creation (v1)
        res1 = await writer_node(state, db_session=session)
        draft1_id = res1["current_draft_id"]
        assert res1["current_draft_version"] == 1
        assert res1["next_action"] == "critic"

        draft1 = get_draft_by_id(session, draft1_id)
        assert draft1 is not None
        assert draft1.version == 1
        assert draft1.previous_version_id is None
        lineage_id = draft1.lineage_id

        # Step 2: Revision loop with Critic feedback (v2)
        state_v2 = {
            **state,
            "current_draft_id": draft1_id,
            "current_draft_version": 1,
            "critic_feedback": [
                {"issue": "The hook is too slow. Make the opening more surprising."}
            ],
        }

        res2 = await writer_node(state_v2, db_session=session)
        draft2_id = res2["current_draft_id"]
        assert res2["current_draft_version"] == 2
        assert draft2_id != draft1_id

        draft2 = get_draft_by_id(session, draft2_id)
        assert draft2 is not None
        assert draft2.lineage_id == lineage_id
        assert draft2.version == 2
        assert draft2.previous_version_id == draft1_id

    finally:
        session.close()
