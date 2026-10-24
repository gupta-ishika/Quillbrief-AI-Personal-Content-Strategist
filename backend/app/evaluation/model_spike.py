import asyncio
import json
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import settings


class SupervisorDecision(BaseModel):
    next_node: str = Field(..., description="Selected next node from eligible list")
    reason: str = Field(..., description="Reason for selection")
    task_updates: list[str] = Field(default_factory=list, description="Any task list updates")


class ToolTestCase(BaseModel):
    instruction: str
    expected_tool: str | None
    should_call_tool: bool


async def run_ollama_chat(
    messages: list[dict[str, str]],
    schema: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], float]:
    url = f"{settings.ollama_base_url}/api/chat"
    payload: dict[str, Any] = {
        "model": settings.model_name,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.0,
        },
    }
    if schema:
        payload["format"] = "json"
    if tools:
        payload["tools"] = tools

    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        duration = time.perf_counter() - start
        return resp.json(), duration


async def test_routing_and_structured_output() -> dict[str, Any]:
    test_cases = [
        {
            "scenario": "New creator, no audience comments or research exists yet",
            "eligible_nodes": ["listener", "research"],
            "expected_one_of": ["listener", "research"],
        },
        {
            "scenario": "Plan items have been drafted and reviewed by Critic, now waiting for human sign-off",
            "eligible_nodes": ["approval"],
            "expected_one_of": ["approval"],
        },
        {
            "scenario": "Creator rejected the content plan with feedback asking for practical coding tutorials",
            "eligible_nodes": ["strategist"],
            "expected_one_of": ["strategist"],
        },
        {
            "scenario": "Fresh comments analyzed and content plan approved; plan item #1 has no draft yet",
            "eligible_nodes": ["writer"],
            "expected_one_of": ["writer"],
        },
    ]

    results = []
    schema_valid_count = 0
    routing_correct_count = 0
    total_tokens_in = 0
    total_tokens_out = 0
    durations = []

    for case in test_cases:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Supervisor agent. Select the best next node from the eligible nodes list.\n"
                    'Output strictly valid JSON: {"next_node": "<chosen_node>", "reason": "<explanation>", "task_updates": []}.\n'
                    f"Allowed eligible nodes: {json.dumps(case['eligible_nodes'])}"
                ),
            },
            {
                "role": "user",
                "content": f"Scenario: {case['scenario']}. Pick the next node from: {json.dumps(case['eligible_nodes'])}.",
            },
        ]

        try:
            raw_result, duration = await run_ollama_chat(
                messages, schema=SupervisorDecision.model_json_schema()
            )
            durations.append(duration)
            message = raw_result.get("message", {})
            content = message.get("content", "")
            prompt_tokens = raw_result.get("prompt_eval_count", 0)
            eval_tokens = raw_result.get("eval_count", 0)
            total_tokens_in += prompt_tokens
            total_tokens_out += eval_tokens

            # Validate against schema
            parsed_data = json.loads(content)
            decision = SupervisorDecision.model_validate(parsed_data)
            schema_valid_count += 1

            # Validate routing choice
            is_valid_choice = decision.next_node in case["eligible_nodes"]
            is_expected = decision.next_node in case["expected_one_of"]
            if is_valid_choice and is_expected:
                routing_correct_count += 1

            results.append(
                {
                    "scenario": case["scenario"],
                    "decision": decision.model_dump(),
                    "duration_seconds": round(duration, 2),
                    "tokens_in": prompt_tokens,
                    "tokens_out": eval_tokens,
                    "schema_valid": True,
                    "routing_correct": is_valid_choice and is_expected,
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": case["scenario"],
                    "error": str(e),
                    "schema_valid": False,
                    "routing_correct": False,
                }
            )

    total = len(test_cases)
    return {
        "total_cases": total,
        "schema_valid_rate": schema_valid_count / total,
        "routing_accuracy": routing_correct_count / total,
        "avg_duration_seconds": round(sum(durations) / len(durations), 2) if durations else 0,
        "avg_tokens_in": round(total_tokens_in / total, 1),
        "avg_tokens_out": round(total_tokens_out / total, 1),
        "cases": results,
    }


async def test_tool_selection() -> dict[str, Any]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "fetch_channel_comments",
                "description": "Fetch audience comments and top questions for a YouTube channel",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string"},
                        "max_comments": {"type": "integer"},
                    },
                    "required": ["channel_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_niche_trends",
                "description": "Search web for trending topics and content gaps in a specific niche",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        },
    ]

    tool_cases: list[ToolTestCase] = [
        ToolTestCase(
            instruction="Find out what my audience is asking about in the comments of my channel UC12345.",
            expected_tool="fetch_channel_comments",
            should_call_tool=True,
        ),
        ToolTestCase(
            instruction="Look up recent trends and popular libraries in the FastAPI Python niche.",
            expected_tool="search_niche_trends",
            should_call_tool=True,
        ),
        ToolTestCase(
            instruction="What is 2 + 2? Answer directly without using any external tools.",
            expected_tool=None,
            should_call_tool=False,
        ),
    ]

    tool_results = []
    tool_correct_count = 0
    no_tool_correct_count = 0

    for case in tool_cases:
        messages = [{"role": "user", "content": case.instruction}]
        raw_result, duration = await run_ollama_chat(messages, tools=tools)

        called_tools: list[str] = []
        message = raw_result.get("message", {})
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                name = tc.get("function", {}).get("name")
                if name:
                    called_tools.append(name)

        if case.should_call_tool:
            correct = case.expected_tool in called_tools if case.expected_tool else False
            if correct:
                tool_correct_count += 1
        else:
            correct = len(called_tools) == 0
            if correct:
                no_tool_correct_count += 1

        tool_results.append(
            {
                "instruction": case.instruction,
                "called_tools": called_tools,
                "duration_seconds": round(duration, 2),
                "correct": correct,
            }
        )

    tool_cases_count = sum(1 for c in tool_cases if c.should_call_tool)
    no_tool_cases_count = sum(1 for c in tool_cases if not c.should_call_tool)

    return {
        "tool_selection_accuracy": tool_correct_count / tool_cases_count if tool_cases_count else 0,
        "no_tool_precision": (
            no_tool_correct_count / no_tool_cases_count if no_tool_cases_count else 0
        ),
        "cases": tool_results,
    }


async def main() -> None:
    print("Testing qwen3.5:4b routing & structured output (think=False)...")
    routing_metrics = await test_routing_and_structured_output()
    print("Routing metrics:", json.dumps(routing_metrics, indent=2))

    print("\nTesting qwen3.5:4b tool calling & precision (think=False)...")
    tool_metrics = await test_tool_selection()
    print("Tool metrics:", json.dumps(tool_metrics, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
