"""Agent runner — processes a tick through the LLM tool-call loop."""

from __future__ import annotations

import json
import logging

from ultra_cycling_ai.api.schemas import AdviceResponse, TickPayload
from ultra_cycling_ai.agent.context import build_user_message
from ultra_cycling_ai.agent.cooldown import get_cooldown_tracker
from ultra_cycling_ai.agent.system_prompt import SYSTEM_PROMPT
from ultra_cycling_ai.db.engine import get_db
from ultra_cycling_ai.db.models import insert_advice
from ultra_cycling_ai.llm.openai_client import chat_completion
from ultra_cycling_ai.memory.intake_ledger import get_intake_ledger
from ultra_cycling_ai.memory.ride_state import get_ride_state
from ultra_cycling_ai.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Module-level registry reference (set during app lifespan via set_registry).
_registry: ToolRegistry | None = None


def set_registry(registry: ToolRegistry) -> None:
    global _registry
    _registry = registry


MAX_TOOL_ROUNDS = 3


async def process_tick(ride_id: str, tick: TickPayload) -> AdviceResponse | None:
    """Run the full agent loop for a single tick and return advice (or None)."""

    # 1. Update in-memory state.
    ride_state = get_ride_state(ride_id)
    ride_state.update(tick)

    ledger = get_intake_ledger(ride_id)
    ledger.record_many(tick.intake_events_since_last_tick)

    cooldowns = get_cooldown_tracker(ride_id)

    # 2. Short-circuit if every category is on cooldown.
    if cooldowns.all_cooled_down():
        logger.debug("All categories on cooldown for ride %s — skipping LLM call", ride_id)
        return None

    # 3. Build messages.
    if _registry is None:
        raise RuntimeError("Tool registry not initialised — call set_registry() at startup")

    user_msg = build_user_message(tick, ride_state, ledger, cooldowns)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    tools = _registry.openai_tool_definitions()

    logger.debug(
        "[agent:%s] === NEW TICK === dist=%.1fkm elapsed=%ds",
        ride_id, tick.totals.distance_km, tick.totals.elapsed_s,
    )
    logger.debug("[agent:%s] System prompt: %s", ride_id, SYSTEM_PROMPT[:120] + "…")
    logger.debug("[agent:%s] User message:\n%s", ride_id, user_msg)
    logger.debug("[agent:%s] Tools registered: %s", ride_id, [t["function"]["name"] for t in tools])

    # 4. LLM tool-call loop (up to MAX_TOOL_ROUNDS).
    for _round in range(MAX_TOOL_ROUNDS):
        logger.debug("[agent:%s] LLM call round %d/%d", ride_id, _round + 1, MAX_TOOL_ROUNDS)
        response = await chat_completion(messages, tools=tools)

        # If the model wants to call a tool, dispatch and feed the result back.
        if response.tool_calls:
            logger.debug(
                "[agent:%s] LLM requested %d tool call(s)",
                ride_id, len(response.tool_calls),
            )
            messages.append(response.to_message())
            for tc in response.tool_calls:
                fn_name = tc.function_name
                fn_args = tc.function_args
                logger.debug(
                    "[agent:%s] → tool_call: %s(%s)",
                    ride_id, fn_name, json.dumps(fn_args),
                )
                result = await _registry.dispatch(fn_name, fn_args)
                logger.debug(
                    "[agent:%s] ← tool_result [%s]: %s",
                    ride_id, fn_name, json.dumps(result)[:500],
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )
            continue  # Loop back for the model to process tool results.

        # No tool call — this is the final answer.
        logger.debug("[agent:%s] LLM final response: %s", ride_id, response.text[:500])
        return await _parse_and_record(ride_id, response.text, cooldowns)

    # Exhausted tool rounds — try to parse whatever we have.
    logger.warning("Exhausted %d tool rounds for ride %s", MAX_TOOL_ROUNDS, ride_id)
    return None


async def _parse_and_record(
    ride_id: str,
    raw_text: str,
    cooldowns,
) -> AdviceResponse | None:
    """Parse the LLM's final JSON response and persist if it's advice."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON: %s", raw_text[:200])
        return None

    if data.get("no_advice"):
        logger.debug("[agent:%s] Result: no_advice", ride_id)
        return None

    try:
        advice = AdviceResponse(**data)
    except Exception:
        logger.warning("Could not parse advice from LLM response: %s", data)
        return None

    logger.debug(
        "[agent:%s] Result: [%s] (%s) %s (cooldown=%dm)",
        ride_id, advice.priority.value, advice.category.value,
        advice.message, advice.cooldown_minutes,
    )

    # Record cooldown.
    cooldowns.record(advice.category.value, advice.cooldown_minutes)

    # Persist to DB.
    try:
        db = await get_db()
        await insert_advice(
            db,
            ride_id,
            advice.category.value,
            advice.priority.value,
            advice.message,
            advice.cooldown_minutes,
        )
    except Exception:
        logger.exception("Failed to persist advice to DB")

    return advice
