"""Fuel and hydration intake ledger with summary helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ultra_cycling_ai.api.schemas import IntakeEvent


@dataclass
class _LedgerEntry:
    timestamp: datetime
    event_type: str  # "eat" | "drink"
    detail: str


@dataclass
class IntakeLedger:
    """Tracks all eat/drink events for a single ride."""

    ride_id: str
    entries: list[_LedgerEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def record(self, event: IntakeEvent) -> None:
        ts = (
            datetime.fromisoformat(event.timestamp)
            if event.timestamp
            else datetime.now(timezone.utc)
        )
        self.entries.append(
            _LedgerEntry(timestamp=ts, event_type=event.type.value, detail=event.detail)
        )

    def record_many(self, events: list[IntakeEvent]) -> None:
        for e in events:
            self.record(e)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _since(self, minutes: int) -> list[_LedgerEntry]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [e for e in self.entries if e.timestamp >= cutoff]

    def eat_count_last(self, minutes: int = 60) -> int:
        return sum(1 for e in self._since(minutes) if e.event_type == "eat")

    def drink_count_last(self, minutes: int = 60) -> int:
        return sum(1 for e in self._since(minutes) if e.event_type == "drink")

    def time_since_last_eat(self) -> timedelta | None:
        eats = [e for e in self.entries if e.event_type == "eat"]
        if not eats:
            return None
        return datetime.now(timezone.utc) - eats[-1].timestamp

    def time_since_last_drink(self) -> timedelta | None:
        drinks = [e for e in self.entries if e.event_type == "drink"]
        if not drinks:
            return None
        return datetime.now(timezone.utc) - drinks[-1].timestamp

    def summary(self) -> dict[str, Any]:
        """Compact summary for LLM context."""
        tse = self.time_since_last_eat()
        tsd = self.time_since_last_drink()
        return {
            "total_eat_events": sum(1 for e in self.entries if e.event_type == "eat"),
            "total_drink_events": sum(1 for e in self.entries if e.event_type == "drink"),
            "eat_last_60min": self.eat_count_last(60),
            "drink_last_60min": self.drink_count_last(60),
            "minutes_since_last_eat": round(tse.total_seconds() / 60, 1) if tse else None,
            "minutes_since_last_drink": round(tsd.total_seconds() / 60, 1) if tsd else None,
        }


# ---------------------------------------------------------------------------
# In-memory store keyed by ride_id.
# ---------------------------------------------------------------------------

_ledgers: dict[str, IntakeLedger] = {}


def get_intake_ledger(ride_id: str) -> IntakeLedger:
    if ride_id not in _ledgers:
        _ledgers[ride_id] = IntakeLedger(ride_id=ride_id)
    return _ledgers[ride_id]


def clear_intake_ledger(ride_id: str) -> None:
    _ledgers.pop(ride_id, None)
