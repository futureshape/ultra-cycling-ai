"""Accumulated ride state — sliding window of recent ticks and running totals."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ultra_cycling_ai.api.schemas import TickPayload


@dataclass
class RideState:
    """In-memory state for a single active ride."""

    ride_id: str
    route_id: str | None = None
    recent_ticks: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=10))

    # Running totals (updated from the latest tick).
    elapsed_s: int = 0
    distance_km: float = 0.0
    elevation_gain_m: float = 0.0

    def update(self, tick: TickPayload) -> None:
        """Incorporate a new tick into state."""
        if self.route_id is None:
            self.route_id = tick.route_id

        self.recent_ticks.append(tick.model_dump(mode="json"))

        # Update running totals from the tick's own accumulated values.
        self.elapsed_s = tick.totals.elapsed_s
        self.distance_km = tick.totals.distance_km
        self.elevation_gain_m = tick.totals.elevation_gain_m

    def summary(self) -> dict[str, Any]:
        """Compact summary for LLM context."""
        return {
            "ride_id": self.ride_id,
            "route_id": self.route_id,
            "elapsed_s": self.elapsed_s,
            "distance_km": round(self.distance_km, 2),
            "elevation_gain_m": round(self.elevation_gain_m, 1),
            "recent_tick_count": len(self.recent_ticks),
        }


# ---------------------------------------------------------------------------
# Simple in-memory store keyed by ride_id.
# ---------------------------------------------------------------------------

_states: dict[str, RideState] = {}


def get_ride_state(ride_id: str) -> RideState:
    if ride_id not in _states:
        _states[ride_id] = RideState(ride_id=ride_id)
    return _states[ride_id]


def clear_ride_state(ride_id: str) -> None:
    _states.pop(ride_id, None)
