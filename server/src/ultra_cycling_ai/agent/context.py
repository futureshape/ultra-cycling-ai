"""Build compact LLM context from the current tick, ride state, and intake ledger."""

from __future__ import annotations

import json
from typing import Any

from ultra_cycling_ai.api.schemas import TickPayload
from ultra_cycling_ai.memory.ride_state import RideState
from ultra_cycling_ai.memory.intake_ledger import IntakeLedger
from ultra_cycling_ai.agent.cooldown import CooldownTracker


def build_user_message(
    tick: TickPayload,
    ride_state: RideState,
    ledger: IntakeLedger,
    cooldowns: CooldownTracker,
) -> str:
    """Assemble the user-role message sent to the LLM on each tick."""
    ctx: dict[str, Any] = {
        "position": {
            "lat": tick.position.lat,
            "lon": tick.position.lon,
            "elevation_m": tick.position.elevation_m,
            "distance_km": tick.position.distance_km,
        },
        "recent_window": tick.recent_window.model_dump(exclude_none=True),
        "ride_summary": ride_state.summary(),
        "intake_summary": ledger.summary(),
        "categories_on_cooldown": cooldowns.categories_on_cooldown(),
    }
    return (
        "Current tick data — use your tools if you need more context "
        "before deciding whether to advise.\n\n"
        + json.dumps(ctx, indent=2)
    )
