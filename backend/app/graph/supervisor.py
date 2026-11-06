import json
import logging
import time
from typing import Any, Literal, cast

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db.repositories.runs import create_routing_log, record_run_event, sync_run_tasks
from app.graph.budgets import (
    detect_routing_repeat,
    is_step_budget_exceeded,
    trim_messages_to_token_limit,
)
from app.graph.decisions import NodeName, SupervisorDecision
from app.graph.state import ContentState, TaskDict

logger = logging.getLogger(__name__)


SUPERVISOR_TOKEN_LIMIT = 1500


def calculate_eligible_nodes(state: ContentState) -> list[NodeName]:
    """Computes the list of eligible next nodes deterministically in code from state (GRAPH-07, PRD AG-7).

    Authoritative eligibility rules (ARCHITECTURE.md Section 3.3, TEST_PLAN.md UT-01, AT-01, AT-02, AT-05, AT-06, AT-07):
    1. If approval is pending on a plan, draft, or depth increase: only ['approval'] is eligible.
    2. If a plan was rejected: ['strategist'] is eligible to incorporate creator feedback (AT-03).
    3. If plan items are approved and at least one item has no draft: ['writer'] is eligible.
    4. Post-Mortem / Analyst skip & repeat rules:
       - For weekly_brief or post_mortem run types:
         - If no performance_insights exist yet:
           - If there are no new posts (has_new_posts is False or new_posts_count == 0):
             Analyst is skipped (AT-07).
           - Otherwise: 'analyst' is eligible.
    5. Data freshness & thinness skip & repeat rules:
       - Listener:
         - If comment insights exist and are fresh (insights_is_stale is False): listener is skipped.
         - If comment insights are missing or stale (insights_is_stale is True): listener is eligible.
       - Research:
         - If research is stale (research_is_stale is True or research_results.get('is_stale') is True)
           or data is thin (data_is_thin is True or research_results.get('is_thin') is True):
           research is repeated and eligible (AT-05, AT-06).
         - If research exists and is fresh: research is skipped (AT-06).
       - Strategist:
         - If fresh comment insights exist (established creator): strategist is eligible directly, skipping research (AT-02).
         - If research is fresh and robust: strategist is eligible.
         - If no plan exists and either insights or research exist: strategist is eligible.
    6. If all tasks are completed and drafts approved: only ['END'] is eligible.
    """
    approval_status = state.get("approval_status", "NONE")
    current_plan_id = state.get("current_plan_id")
    content_plan = state.get("content_plan", [])
    comment_insights = state.get("comment_insights", [])
    research_results = state.get("research_results", {})
    current_draft_id = state.get("current_draft_id")
    task_list = state.get("task_list", [])
    run_type = state.get("run_type", "goal")

    # Rule 1: Approval waiting
    if approval_status == "PENDING":
        return ["approval"]

    # Rule 2: Plan rejected with feedback (AT-03)
    if approval_status == "REJECTED":
        return ["strategist"]

    # Rule 3: Approved plan exists; check if an item needs drafting
    if approval_status == "APPROVED" and content_plan:
        if not current_draft_id:
            return ["writer"]
        if task_list and all(t.get("status") in ("DONE", "SKIPPED") for t in task_list):
            return ["END"]

    # Rule 4: Post-Mortem / Weekly Brief Analyst skip logic (AT-07)
    if run_type in ("weekly_brief", "post_mortem") and not state.get("performance_insights"):
        has_new_posts = state.get("has_new_posts")
        new_posts_count = state.get("new_posts_count")
        if has_new_posts is False or new_posts_count == 0:
            # Skip analyst when there are no new posts (AT-07)
            pass
        elif has_new_posts is True or (new_posts_count is not None and new_posts_count > 0):
            return ["analyst"]

    # Rule 5: Freshness & Thinness checks (AT-01, AT-02, AT-05, AT-06)
    has_insights = bool(comment_insights)
    insights_stale = state.get("insights_is_stale", False)
    insights_fresh = has_insights and not insights_stale

    has_research = bool(research_results)
    research_stale = state.get("research_is_stale", False) or research_results.get("is_stale", False)
    data_thin = state.get("data_is_thin", False) or research_results.get("is_thin", False)
    research_fresh = has_research and not research_stale and not data_thin

    # If research is stale or thin: research must be repeated (AT-05, AT-06)
    if (has_research and (research_stale or data_thin)) or (has_insights and data_thin):
        if not insights_fresh:
            return ["listener", "research"]
        return ["research"]

    # If both insights and research are fresh, and no plan yet: route directly to strategist (skipping listener and research)
    if insights_fresh and research_fresh and not current_plan_id:
        return ["strategist"]

    # If insights are fresh, but no research: established creator can route directly to strategist or research (AT-02)
    if insights_fresh and not has_research and not current_plan_id:
        return ["research", "strategist"]

    # If neither insights nor research exists yet: new creator must gather data (AT-01)
    if not has_insights and not has_research:
        return ["listener", "research"]

    # If research is fresh but no insights: listener and strategist are eligible
    if not has_insights and research_fresh and not current_plan_id:
        return ["listener", "strategist"]

    # If insights exist and research is not stale, but no content plan yet
    if (has_insights or has_research) and not current_plan_id:
        return ["strategist"]

    # Rule 6: Finished all tasks
    if task_list and all(t.get("status") in ("DONE", "SKIPPED") for t in task_list):
        return ["END"]

    # Default safety fallbacks
    if not current_plan_id:
        return ["strategist"]

    return ["END"]


def get_deterministic_default_node(
    eligible_nodes: list[NodeName], state: ContentState
) -> tuple[NodeName, str]:
    """Returns a deterministic fallback node and rationale when model output is invalid or fails."""
    priority_order: list[NodeName] = [
        "approval",
        "strategist",
        "writer",
        "listener",
        "research",
        "repurposer",
        "analyst",
        "END",
    ]
    for node in priority_order:
        if node in eligible_nodes:
            return (
                node,
                f"Deterministic code fallback chose highest-priority eligible node '{node}'.",
            )
    return eligible_nodes[
        0
    ], f"Deterministic code fallback chose first eligible node '{eligible_nodes[0]}'."


async def request_supervisor_llm(
    messages: list[dict[str, str]],
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], float]:
    """Calls Ollama chat endpoint with think=False, temperature=0.0, and JSON schema."""
    url = f"{settings.ollama_base_url}/api/chat"
    payload = {
        "model": settings.model_name,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
        },
    }

    start = time.perf_counter()
    if client:
        resp = await client.post(url, json=payload, timeout=45.0)
        resp.raise_for_status()
        return resp.json(), time.perf_counter() - start

    async with httpx.AsyncClient(timeout=45.0) as default_client:
        resp = await default_client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json(), time.perf_counter() - start


def decompose_goal_to_tasks(
    user_goal: str,
    depth_level: str = "standard",
    creator_profile: dict[str, Any] | None = None,
) -> list[TaskDict]:
    """Decomposes the creator's goal into an initial structured task list (GRAPH-06, PRD AG-2, AT-08).

    Different goals produce distinctly different task lists without hardcoded static workflows.
    """
    goal_lower = (user_goal or "").lower()
    tasks: list[TaskDict] = []

    # Goal Type 1: Content Repurposing focus
    if any(k in goal_lower for k in ("repurpose", "thread", "linkedin", "caption", "short")):
        tasks = [
            {
                "id": "task_1",
                "title": "Analyze and extract key highlights from source content",
                "agent": "repurposer",
                "position": 1,
                "status": "TODO",
            },
            {
                "id": "task_2",
                "title": "Draft repurposed post and multi-format adaptations",
                "agent": "repurposer",
                "position": 2,
                "status": "TODO",
            },
            {
                "id": "task_3",
                "title": "Creator review of repurposed content",
                "agent": "approval",
                "position": 3,
                "status": "TODO",
            },
        ]
    # Goal Type 2: Script / Drafting focus
    elif any(k in goal_lower for k in ("script", "draft", "write", "video tutorial", "record")):
        tasks = [
            {
                "id": "task_1",
                "title": f"Investigate background and competitor videos for '{user_goal[:50]}'",
                "agent": "research",
                "position": 1,
                "status": "TODO",
            },
            {
                "id": "task_2",
                "title": "Structure content outline and strategic rationale",
                "agent": "strategist",
                "position": 2,
                "status": "TODO",
            },
            {
                "id": "task_3",
                "title": "Creator review of outline",
                "agent": "approval",
                "position": 3,
                "status": "TODO",
            },
            {
                "id": "task_4",
                "title": "Draft complete video script",
                "agent": "writer",
                "position": 4,
                "status": "TODO",
            },
            {
                "id": "task_5",
                "title": "Critic rubric evaluation and quality check",
                "agent": "critic",
                "position": 5,
                "status": "TODO",
            },
            {
                "id": "task_6",
                "title": "Creator review of video script",
                "agent": "approval",
                "position": 6,
                "status": "TODO",
            },
        ]
    # Goal Type C: Analytics & Post-Mortem focus
    elif any(
        k in goal_lower for k in ("analytics", "post-mortem", "metrics", "retention", "performance")
    ):
        tasks = [
            {
                "id": "task_1",
                "title": "Analyze recent video performance and viewer retention",
                "agent": "analyst",
                "position": 1,
                "status": "TODO",
            },
            {
                "id": "task_2",
                "title": "Synthesize strategic recommendations and future moves",
                "agent": "strategist",
                "position": 2,
                "status": "TODO",
            },
            {
                "id": "task_3",
                "title": "Review strategic direction",
                "agent": "approval",
                "position": 3,
                "status": "TODO",
            },
        ]
    # Goal Type D: Research & Trends focus
    elif any(k in goal_lower for k in ("research", "competitor", "trending", "explore", "discover")):
        tasks = [
            {
                "id": "task_1",
                "title": "Extract comments and community themes",
                "agent": "listener",
                "position": 1,
                "status": "TODO",
            },
            {
                "id": "task_2",
                "title": "Survey similar creator videos and niche benchmarks",
                "agent": "research",
                "position": 2,
                "status": "TODO",
            },
            {
                "id": "task_3",
                "title": "Formulate targeted content recommendations",
                "agent": "strategist",
                "position": 3,
                "status": "TODO",
            },
            {
                "id": "task_4",
                "title": "Review research-backed content proposals",
                "agent": "approval",
                "position": 4,
                "status": "TODO",
            },
        ]
    # Goal Type E: Comprehensive / Audience Planning (Default)
    else:
        tasks = [
            {
                "id": "task_1",
                "title": "Analyze audience comments and friction points",
                "agent": "listener",
                "position": 1,
                "status": "TODO",
            },
            {
                "id": "task_2",
                "title": "Research trending topics and comparable creators",
                "agent": "research",
                "position": 2,
                "status": "TODO",
            },
            {
                "id": "task_3",
                "title": "Generate comprehensive content plan",
                "agent": "strategist",
                "position": 3,
                "status": "TODO",
            },
            {
                "id": "task_4",
                "title": "Review proposed content plan",
                "agent": "approval",
                "position": 3,
                "status": "TODO",
            },
            {
                "id": "task_5",
                "title": "Draft prioritized content items",
                "agent": "writer",
                "position": 5,
                "status": "TODO",
            },
            {
                "id": "task_6",
                "title": "Critic rubric evaluation",
                "agent": "critic",
                "position": 6,
                "status": "TODO",
            },
            {
                "id": "task_7",
                "title": "Creator review of finished draft",
                "agent": "approval",
                "position": 7,
                "status": "TODO",
            },
        ]

    # Quick depth streamlines tasks
    if depth_level == "quick":
        tasks = [t for t in tasks if t["agent"] in ("research", "strategist", "writer", "approval")]

    for idx, t in enumerate(tasks, start=1):
        t["position"] = idx

    return tasks


def apply_task_updates(
    current_tasks: list[TaskDict],
    task_updates: list[dict[str, Any]],
    from_node: str | None = None,
    approval_status: str = "NONE",
    state: ContentState | None = None,
) -> list[TaskDict]:
    """Applies task list modifications (add, update, remove, reorder) and dynamic status transitions (GRAPH-06, GRAPH-07).

    Ensures sequential positions 1..N and respects the rule that a resumed run never repeats or deletes a DONE task.
    Supports skip and repeat logic based on data freshness and thinness (PRD AG-7).
    """
    tasks = [dict(t) for t in current_tasks]

    # 1. Automatic task completion progression:
    # If control just returned from an agent node, mark that agent's first TODO task as DONE
    if from_node and from_node not in ("supervisor", "START", "END"):
        for t in tasks:
            if t.get("agent") == from_node and t.get("status") == "TODO":
                t["status"] = "DONE"
                break

    # 2. Dynamic replanning if plan was rejected (AT-03)
    if approval_status == "REJECTED":
        has_revision_task = any(
            t.get("agent") == "strategist" and t.get("status") == "TODO" for t in tasks
        )
        if not has_revision_task:
            tasks.append({
                "id": f"task_{len(tasks) + 1}",
                "title": "Revise content plan incorporating creator feedback",
                "agent": "strategist",
                "position": len(tasks) + 1,
                "status": "TODO",
            })

    # 3. Skip and repeat logic based on data freshness & thinness (GRAPH-07, PRD AG-7, AT-05, AT-06, AT-07)
    if state:
        comment_insights = state.get("comment_insights", [])
        research_results = state.get("research_results", {})
        insights_fresh = bool(comment_insights) and not state.get("insights_is_stale", False)
        research_stale = state.get("research_is_stale", False) or research_results.get("is_stale", False)
        data_thin = state.get("data_is_thin", False) or research_results.get("is_thin", False)
        has_new_posts = state.get("has_new_posts")
        new_posts_count = state.get("new_posts_count")

        # Skip listener if comments are already fresh
        if insights_fresh:
            for t in tasks:
                if t.get("agent") == "listener" and t.get("status") == "TODO":
                    t["status"] = "SKIPPED"

        # Skip analyst if there are no new posts (AT-07)
        if has_new_posts is False or new_posts_count == 0:
            for t in tasks:
                if t.get("agent") == "analyst" and t.get("status") == "TODO":
                    t["status"] = "SKIPPED"

        # Repeat research if research is stale or data is thin (AT-05, AT-06)
        if (research_stale or data_thin) and (research_results or comment_insights):
            has_todo_research = any(
                t.get("agent") == "research" and t.get("status") == "TODO" for t in tasks
            )
            if not has_todo_research:
                tasks.append({
                    "id": f"task_{len(tasks) + 1}",
                    "title": "Repeat research: data is stale or thin",
                    "agent": "research",
                    "position": len(tasks) + 1,
                    "status": "TODO",
                })

        # Repeat listener if insights are explicitly marked stale
        if state.get("insights_is_stale", False) and comment_insights:
            has_todo_listener = any(
                t.get("agent") == "listener" and t.get("status") == "TODO" for t in tasks
            )
            if not has_todo_listener:
                tasks.append({
                    "id": f"task_{len(tasks) + 1}",
                    "title": "Refresh audience comments: insights are stale",
                    "agent": "listener",
                    "position": len(tasks) + 1,
                    "status": "TODO",
                })

    # 3. Apply model-directed task updates (add, update, remove, reorder)
    for update in task_updates:
        action = update.get("action")
        task_id = update.get("task_id")

        if action == "add":
            tasks.append({
                "id": f"task_{len(tasks) + 1}",
                "title": str(update.get("title") or "New Task"),
                "agent": str(update.get("agent") or "supervisor"),
                "position": int(update.get("position") or (len(tasks) + 1)),
                "status": "TODO",
            })
        elif action == "update" and task_id:
            for t in tasks:
                if t.get("id") == task_id:
                    if update.get("status"):
                        t["status"] = update["status"]
                    if update.get("title"):
                        t["title"] = update["title"]
                    if update.get("agent"):
                        t["agent"] = update["agent"]
                    if update.get("position"):
                        t["position"] = int(update["position"])
        elif action == "remove" and task_id:
            # Resumed run never deletes a DONE task (DATABASE.md 3.3)
            tasks = [t for t in tasks if not (t.get("id") == task_id and t.get("status") != "DONE")]
        elif action == "reorder":
            if task_id and update.get("position") is not None:
                for t in tasks:
                    if t.get("id") == task_id:
                        t["position"] = int(update["position"])

    # 4. Normalize sequential positions 1..N
    tasks.sort(key=lambda t: (int(str(t.get("position") or 0)), str(t.get("id") or "")))
    normalized: list[TaskDict] = []
    for idx, t in enumerate(tasks, start=1):
        t["position"] = idx
        normalized.append(cast(TaskDict, t))

    return normalized


def build_supervisor_prompt(
    state: ContentState, eligible_nodes: list[NodeName]
) -> list[dict[str, str]]:
    profile = state.get("creator_profile", {})
    raw_messages = [
        {
            "role": "system",
            "content": (
                "You are the Supervisor agent in a multi-agent content strategist workflow.\n"
                "Your role is to choose the BEST next node strictly from the provided allowed eligible nodes list.\n"
                "Rules:\n"
                f"1. You MUST choose 'next_node' from: {json.dumps(eligible_nodes)}.\n"
                "2. Provide a concise reason (5-500 chars).\n"
                "3. You may optionally output task updates.\n"
                "Output strictly valid JSON matching schema:\n"
                '{"next_node": "<chosen_node>", "reason": "<explanation>", "task_updates": []}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Goal: {state.get('user_goal', 'Content planning')}\n"
                f"Niche: {profile.get('niche', 'General')}\n"
                f"Depth Level: {state.get('depth_level', 'standard')}\n"
                f"Current Step: {state.get('execution_steps', 0)}\n"
                f"Eligible Nodes: {json.dumps(eligible_nodes)}\n"
                "Pick the next node."
            ),
        },
    ]
    return trim_messages_to_token_limit(raw_messages, SUPERVISOR_TOKEN_LIMIT)


async def supervisor_node(
    state: ContentState,
    db_session: Session | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Supervisor node implementation:

    1. Computes eligible next nodes in code.
    2. If single node is eligible, model is NOT called (UT-03).
    3. If multiple eligible nodes, calls Ollama structured output with think=False.
    4. Validates decision against eligible list. Retries once if invalid.
    5. Falls back to deterministic default if retry fails, marking run degraded.
    6. Logs routing decision to database if session provided.
    7. Returns state updates.
    """
    step_number = state.get("execution_steps", 0) + 1
    run_id = state.get("run_id", "")
    from_node = state.get("next_action", "supervisor")

    # Check 1: Step budget enforcement (UT-04, IT-05 / ARCHITECTURE.md Section 10)
    budget_exceeded, budget_reason = is_step_budget_exceeded(state)
    if budget_exceeded:
        budget_tasks = state.get("task_list", [])
        unfinished = [
            str(t.get("title") or t.get("agent", "task"))
            for t in budget_tasks
            if t.get("status") not in ("DONE", "SKIPPED")
        ]
        unfinished_info = f" Unfinished tasks: {', '.join(unfinished)}." if unfinished else ""
        full_reason = f"{budget_reason}{unfinished_info}"

        if db_session and run_id:
            try:
                create_routing_log(
                    db=db_session,
                    run_id=run_id,
                    step_number=step_number,
                    from_node=from_node,
                    to_node="END",
                    reason=full_reason,
                    decided_by="code",
                    eligible_nodes=["END"],
                    output_status="valid",
                )
                record_run_event(
                    db=db_session,
                    run_id=run_id,
                    event_type="limit_reached",
                    payload={
                        "limit": "step_budget",
                        "depth_level": state.get("depth_level", "standard"),
                        "steps": step_number,
                        "reason": full_reason,
                        "unfinished_tasks": unfinished,
                    },
                )
            except Exception as e:
                logger.warning("Failed to record routing log or limit event: %s", e)
        return {
            "next_action": "END",
            "stop_reason": "step_budget_exceeded",
            "degraded": True,
            "degraded_reason": full_reason,
            "execution_steps": step_number,
        }

    # Check 2: Repeat cycle detection (UT-05 / ARCHITECTURE.md Section 3.4)
    route_history = state.get("route_history", [])
    repeat_detected, repeat_reason = detect_routing_repeat(route_history)
    if repeat_detected:
        if db_session and run_id:
            try:
                create_routing_log(
                    db=db_session,
                    run_id=run_id,
                    step_number=step_number,
                    from_node=from_node,
                    to_node="END",
                    reason=repeat_reason or "Repeat cycle detected",
                    decided_by="code",
                    eligible_nodes=["END"],
                    output_status="valid",
                )
            except Exception as e:
                logger.warning("Failed to record routing log: %s", e)
        return {
            "next_action": "END",
            "stop_reason": "repeat_detected",
            "degraded": True,
            "degraded_reason": repeat_reason,
            "execution_steps": step_number,
        }

    eligible_nodes = calculate_eligible_nodes(state)

    # Case 1: Exactly 1 eligible node -> No LLM call needed (UT-03)
    if len(eligible_nodes) == 1:
        chosen_node = eligible_nodes[0]
        reason = f"Only one node '{chosen_node}' is eligible for current state; selected directly in code."
        decided_by = "code"
        output_status = "valid"
        invalid_category = None
        tokens_in = 0
        tokens_out = 0
        degraded = state.get("degraded", False)
        degraded_reason = state.get("degraded_reason")
        task_updates: list[dict[str, Any]] = []
    else:
        # Case 2: Multiple eligible nodes -> Query LLM with structured output
        prompt = build_supervisor_prompt(state, eligible_nodes)
        chosen_node = None
        reason = ""
        decided_by = "model"
        output_status = "valid"
        invalid_category = None
        tokens_in = 0
        tokens_out = 0
        degraded = state.get("degraded", False)
        degraded_reason = state.get("degraded_reason")
        task_updates = []

        # Attempt 1
        try:
            raw_res, _ = await request_supervisor_llm(prompt, client=http_client)
            tokens_in += raw_res.get("prompt_eval_count", 0)
            tokens_out += raw_res.get("eval_count", 0)
            content_str = raw_res.get("message", {}).get("content", "")
            parsed = json.loads(content_str)
            decision = SupervisorDecision.model_validate(parsed)

            if decision.next_node in eligible_nodes:
                chosen_node = decision.next_node
                reason = decision.reason
                task_updates = [u.model_dump() for u in decision.task_updates]
                output_status = "valid"
            else:
                invalid_category = "ineligible_node"
        except json.JSONDecodeError:
            invalid_category = "bad_json"
        except Exception:
            invalid_category = "schema_violation"

        # Attempt 2: Bounded retry once if Attempt 1 failed (ARCHITECTURE.md 12)
        if chosen_node is None:
            try:
                raw_res2, _ = await request_supervisor_llm(prompt, client=http_client)
                tokens_in += raw_res2.get("prompt_eval_count", 0)
                tokens_out += raw_res2.get("eval_count", 0)
                content_str2 = raw_res2.get("message", {}).get("content", "")
                parsed2 = json.loads(content_str2)
                decision2 = SupervisorDecision.model_validate(parsed2)

                if decision2.next_node in eligible_nodes:
                    chosen_node = decision2.next_node
                    reason = f"[Retry Valid] {decision2.reason}"
                    task_updates = [u.model_dump() for u in decision2.task_updates]
                    output_status = "retried_valid"
                    invalid_category = None
                else:
                    invalid_category = "ineligible_node"
            except Exception:
                pass

        # Attempt 3: If retry still failed, fallback to deterministic code default
        if chosen_node is None:
            chosen_node, fallback_reason = get_deterministic_default_node(eligible_nodes, state)
            reason = f"[Fallback: {invalid_category}] {fallback_reason}"
            output_status = "fallback"
            decided_by = "code"
            degraded = True
            degraded_reason = f"Supervisor model output invalid ({invalid_category}); used deterministic fallback '{chosen_node}'."

    final_chosen_node: str = chosen_node or "END"

    # 1. Goal decomposition: initialize task list if empty and model did not supply updates (GRAPH-06, PRD AG-2, AT-08)
    current_tasks: list[TaskDict] = list(state.get("task_list", []))
    if not current_tasks and not task_updates:
        user_goal = state.get("user_goal", "")
        depth_level = state.get("depth_level", "standard")
        profile = state.get("creator_profile", {})
        current_tasks = decompose_goal_to_tasks(user_goal, depth_level, profile)

    # 2. Dynamic replanning and automatic step completion (GRAPH-06)
    approval_status = state.get("approval_status", "NONE")
    current_tasks = apply_task_updates(
        current_tasks=current_tasks,
        task_updates=task_updates,
        from_node=from_node,
        approval_status=approval_status,
        state=state,
    )

    # 3. Synchronize task list to database if session and run_id available
    if db_session and run_id:
        try:
            persisted_tasks = sync_run_tasks(db=db_session, run_id=run_id, tasks_data=current_tasks)
            current_tasks = [
                TaskDict(
                    id=pt.id,
                    title=pt.title,
                    agent=pt.agent,
                    position=pt.position,
                    status=cast(Literal["TODO", "DONE", "SKIPPED", "FAILED"], pt.status),
                )
                for pt in persisted_tasks
            ]
        except Exception as e:
            logger.warning("Failed to sync run tasks to database: %s", e)

    # Record routing log in SQLite if DB session and run_id available
    if db_session and run_id:
        try:
            create_routing_log(
                db=db_session,
                run_id=run_id,
                step_number=step_number,
                from_node=from_node,
                to_node=final_chosen_node,
                reason=reason,
                decided_by=decided_by,
                eligible_nodes=list(eligible_nodes),
                output_status=output_status,
                invalid_category=invalid_category,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        except Exception as e:
            logger.warning("Failed to record routing log to database: %s", e)

    return {
        "next_action": chosen_node,
        "task_list": current_tasks,
        "route_history": state.get("route_history", []) + [chosen_node],
        "execution_steps": step_number,
        "tokens_used": state.get("tokens_used", 0) + tokens_in + tokens_out,
        "degraded": degraded,
        "degraded_reason": degraded_reason,
    }
