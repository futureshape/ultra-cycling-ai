"""Shared fixtures for the test suite."""

from __future__ import annotations

import pytest

from ultra_cycling_ai.db.engine import close_db, init_db
from ultra_cycling_ai.tools.registry import build_default_registry
from ultra_cycling_ai.agent.runner import set_registry


@pytest.fixture(autouse=True, scope="session")
def _event_loop():
    """Ensure a single event loop for the test session (pytest-asyncio compat)."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def _init_test_db(tmp_path):
    """Initialise an in-memory SQLite DB and tool registry before each test."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    registry = build_default_registry()
    set_registry(registry)
    yield
    await close_db()
