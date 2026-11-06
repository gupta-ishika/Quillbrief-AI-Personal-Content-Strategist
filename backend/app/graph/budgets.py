from dataclasses import dataclass
from typing import Literal

from app.graph.state import ContentState


@dataclass(frozen=True)
class DepthLimits:
    max_supervisor_steps: int
    max_tool_steps_per_agent: int
    max_critic_reviews: int
    max_videos: int
    max_comments: int
    max_searches: int
    max_pages: int
    max_input_tokens: int = 6000


DEPTH_CONFIG: dict[Literal["quick", "standard", "deep"], DepthLimits] = {
    "quick": DepthLimits(
        max_supervisor_steps=15,
        max_tool_steps_per_agent=4,
        max_critic_reviews=2,
        max_videos=5,
        max_comments=300,
        max_searches=3,
        max_pages=3,
        max_input_tokens=6000,
    ),
    "standard": DepthLimits(
        max_supervisor_steps=30,
        max_tool_steps_per_agent=6,
        max_critic_reviews=3,
        max_videos=10,
        max_comments=1000,
        max_searches=6,
        max_pages=6,
        max_input_tokens=6000,
    ),
    "deep": DepthLimits(
        max_supervisor_steps=50,
        max_tool_steps_per_agent=10,
        max_critic_reviews=3,
        max_videos=25,
        max_comments=3000,
        max_searches=12,
        max_pages=12,
        max_input_tokens=6000,
    ),
}


AGENT_TOKEN_LIMITS: dict[str, int] = {
    "supervisor": 1500,
    "listener": 4000,
    "research": 6000,
    "strategist": 6000,
    "writer": 4000,
    "critic": 3000,
}


def trim_messages_to_token_limit(
    messages: list[dict[str, str]],
    max_tokens: int,
) -> list[dict[str, str]]:
    """Enforces per-call input token limits across agents (ARCHITECTURE.md Section 10).

    Uses a 4 characters/token heuristic. If the total length exceeds max_tokens * 4,
    the user and observation messages are proportionally truncated while preserving the system prompt.
    """
    max_chars = max_tokens * 4
    total_chars = sum(len(m.get("content", "")) for m in messages)
    if total_chars <= max_chars:
        return messages

    result: list[dict[str, str]] = []
    budget_left = max_chars

    # 1. System prompt preserved (up to 50% budget)
    for m in messages:
        if m.get("role") == "system":
            sys_content = m.get("content", "")
            if len(sys_content) > max_chars // 2:
                sys_content = sys_content[: max_chars // 2] + "\n[...system prompt truncated...]"
            result.append({"role": "system", "content": sys_content})
            budget_left -= len(sys_content)

    # 2. Non-system messages
    non_sys = [m for m in messages if m.get("role") != "system"]
    if not non_sys:
        return result

    chars_per_msg = max(200, budget_left // len(non_sys))
    for m in non_sys:
        content = m.get("content", "")
        if len(content) > chars_per_msg:
            content = content[:chars_per_msg] + "\n[...truncated to fit token limit...]"
        result.append({"role": m.get("role", "user"), "content": content})

    return result


def get_depth_limits(depth_level: str) -> DepthLimits:
    if depth_level in ("quick", "standard", "deep"):
        return DEPTH_CONFIG[depth_level]  # type: ignore[index]
    return DEPTH_CONFIG["standard"]


def is_step_budget_exceeded(state: ContentState) -> tuple[bool, str | None]:
    depth_level = state.get("depth_level", "standard")
    limits = get_depth_limits(depth_level)
    current_steps = state.get("execution_steps", 0)

    if current_steps >= limits.max_supervisor_steps:
        return (
            True,
            f"Execution step limit reached ({current_steps}/{limits.max_supervisor_steps}) for depth level '{depth_level}'.",
        )
    return False, None


def detect_routing_repeat(route_history: list[str]) -> tuple[bool, str | None]:
    """Detects infinite loops and ping-pong routing cycles in the route history.

    Rules (UT-05 / ARCHITECTURE.md Section 3.4):
    1. Consecutive repetition: Same node chosen 3 times in a row (e.g. ['A', 'A', 'A']).
    2. 2-node cycle: Alternating pattern repeated at least twice (e.g. ['A', 'B', 'A', 'B']).
    3. 3-node cycle: Pattern of 3 nodes repeated at least twice (e.g. ['A', 'B', 'C', 'A', 'B', 'C']).
    """
    if len(route_history) < 3:
        return False, None

    # Filter out 'supervisor' if recorded in route history, looking at agent nodes
    clean_history = [r for r in route_history if r != "supervisor"]
    if len(clean_history) < 3:
        return False, None

    # 1. 3 consecutive identical nodes
    if len(clean_history) >= 3 and clean_history[-1] == clean_history[-2] == clean_history[-3]:
        node = clean_history[-1]
        return (
            True,
            f"Consecutive routing repeat detected for node '{node}' (called 3 times in succession).",
        )

    # 2. 2-node cycle: e.g. [..., A, B, A, B]
    if len(clean_history) >= 4:
        if clean_history[-4] == clean_history[-2] and clean_history[-3] == clean_history[-1]:
            a, b = clean_history[-2], clean_history[-1]
            return True, f"2-node ping-pong routing cycle detected between '{a}' and '{b}'."

    # 3. 3-node cycle: e.g. [..., A, B, C, A, B, C]
    if len(clean_history) >= 6:
        if (
            clean_history[-6] == clean_history[-3]
            and clean_history[-5] == clean_history[-2]
            and clean_history[-4] == clean_history[-1]
        ):
            cycle = f"{clean_history[-3]} -> {clean_history[-2]} -> {clean_history[-1]}"
            return True, f"3-node routing cycle detected: [{cycle}]."

    return False, None
