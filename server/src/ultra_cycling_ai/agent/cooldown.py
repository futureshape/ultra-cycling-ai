"""Per-category cooldown tracker to avoid advice repetition."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ultra_cycling_ai.config import settings


class CooldownTracker:
    """Tracks when advice was last given per category."""

    def __init__(self) -> None:
        # {category: (timestamp, cooldown_minutes)}
        self._last: dict[str, tuple[datetime, int]] = {}

    def record(self, category: str, cooldown_minutes: int | None = None) -> None:
        cd = cooldown_minutes if cooldown_minutes is not None else settings.default_cooldown_minutes
        self._last[category] = (datetime.now(timezone.utc), cd)

    def is_cooled_down(self, category: str) -> bool:
        """Return True if the category is still in cooldown (should NOT advise)."""
        entry = self._last.get(category)
        if entry is None:
            return False
        ts, cd_min = entry
        return datetime.now(timezone.utc) - ts < timedelta(minutes=cd_min)

    def all_cooled_down(self) -> bool:
        """Return True if ALL known categories are still cooling down."""
        from ultra_cycling_ai.api.schemas import AdviceCategory

        return all(self.is_cooled_down(c.value) for c in AdviceCategory)

    def categories_on_cooldown(self) -> list[str]:
        """Return list of category names currently in cooldown."""
        from ultra_cycling_ai.api.schemas import AdviceCategory

        return [c.value for c in AdviceCategory if self.is_cooled_down(c.value)]


# ---------------------------------------------------------------------------
# In-memory store keyed by ride_id.
# ---------------------------------------------------------------------------

_trackers: dict[str, CooldownTracker] = {}


def get_cooldown_tracker(ride_id: str) -> CooldownTracker:
    if ride_id not in _trackers:
        _trackers[ride_id] = CooldownTracker()
    return _trackers[ride_id]
