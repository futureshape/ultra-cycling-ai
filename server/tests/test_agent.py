"""Agent unit tests with mocked LLM."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from ultra_cycling_ai.agent.cooldown import CooldownTracker
from ultra_cycling_ai.agent.runner import process_tick, set_registry
from ultra_cycling_ai.api.schemas import AdviceCategory, Position, TickPayload
from ultra_cycling_ai.llm.openai_client import LLMResponse
from ultra_cycling_ai.tools.registry import build_default_registry



def _make_tick(**overrides) -> TickPayload:
    defaults = {
        "route_id": "test-route",
        "ride_id": "test-ride",
        "position": {"lat": 45.5, "lon": 7.2, "elevation_m": 500, "distance_km": 42.0},
        "totals": {"elapsed_s": 7200, "distance_km": 42.0, "elevation_gain_m": 800},
    }
    defaults.update(overrides)
    return TickPayload(**defaults)


@pytest.mark.asyncio
@patch("ultra_cycling_ai.agent.runner.chat_completion")
@patch("ultra_cycling_ai.db.engine.get_db")
async def test_process_tick_returns_advice(mock_db, mock_llm):
    """When the LLM returns valid advice JSON, process_tick should return AdviceResponse."""
    advice_json = {
        "priority": "medium",
        "category": "fuel",
        "message": "Consider eating something — it's been over an hour since your last intake.",
        "cooldown_minutes": 20,
    }
    mock_llm.return_value = LLMResponse(text=json.dumps(advice_json))

    # Mock DB to avoid needing a real connection.
    mock_conn = AsyncMock()
    mock_db.return_value = mock_conn

    tick = _make_tick()
    result = await process_tick("test-ride", tick)

    assert result is not None
    assert result.category.value == "fuel"
    assert result.priority.value == "medium"
    assert result.cooldown_minutes == 20


@pytest.mark.asyncio
@patch("ultra_cycling_ai.agent.runner.chat_completion")
@patch("ultra_cycling_ai.db.engine.get_db")
async def test_process_tick_no_advice(mock_db, mock_llm):
    """When the LLM returns no_advice, process_tick should return None."""
    mock_llm.return_value = LLMResponse(text=json.dumps({"no_advice": True}))
    mock_conn = AsyncMock()
    mock_db.return_value = mock_conn

    tick = _make_tick()
    result = await process_tick("test-ride-noadvice", tick)

    assert result is None


def test_cooldown_tracker():
    """Verify basic cooldown behaviour."""
    tracker = CooldownTracker()

    # Initially nothing is on cooldown.
    assert not tracker.is_cooled_down("fuel")
    assert tracker.categories_on_cooldown() == []

    # Record advice for fuel with a 15-minute cooldown.
    tracker.record("fuel", 15)
    assert tracker.is_cooled_down("fuel")
    assert "fuel" in tracker.categories_on_cooldown()

    # Other categories are still available.
    assert not tracker.is_cooled_down("pacing")
