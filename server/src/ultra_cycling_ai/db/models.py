"""Lightweight helpers for DB operations.

We use raw SQL via aiosqlite rather than an ORM to keep things simple
and transparent for this MVP.
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

async def insert_route(
    db: aiosqlite.Connection,
    route_id: str,
    gpx_geojson: dict | str,
    climb_segments: list | str = "[]",
) -> None:
    geojson_str = gpx_geojson if isinstance(gpx_geojson, str) else json.dumps(gpx_geojson)
    climbs_str = climb_segments if isinstance(climb_segments, str) else json.dumps(climb_segments)
    await db.execute(
        "INSERT OR REPLACE INTO routes (route_id, gpx_geojson, climb_segments) VALUES (?, ?, ?)",
        (route_id, geojson_str, climbs_str),
    )
    await db.commit()


async def get_route(db: aiosqlite.Connection, route_id: str) -> dict[str, Any] | None:
    cursor = await db.execute("SELECT * FROM routes WHERE route_id = ?", (route_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Rides
# ---------------------------------------------------------------------------

async def ensure_ride(db: aiosqlite.Connection, ride_id: str, route_id: str) -> None:
    """Create a ride row if it doesn't already exist."""
    await db.execute(
        "INSERT OR IGNORE INTO rides (ride_id, route_id) VALUES (?, ?)",
        (ride_id, route_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Ticks
# ---------------------------------------------------------------------------

async def insert_tick(db: aiosqlite.Connection, ride_id: str, payload: dict) -> int:
    cursor = await db.execute(
        "INSERT INTO ticks (ride_id, payload) VALUES (?, ?)",
        (ride_id, json.dumps(payload)),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Intake events
# ---------------------------------------------------------------------------

async def insert_intake_event(
    db: aiosqlite.Connection,
    ride_id: str,
    event_type: str,
    detail: str = "",
    timestamp: str | None = None,
) -> int:
    if timestamp:
        cursor = await db.execute(
            "INSERT INTO intake_events (ride_id, event_type, detail, timestamp) VALUES (?, ?, ?, ?)",
            (ride_id, event_type, detail, timestamp),
        )
    else:
        cursor = await db.execute(
            "INSERT INTO intake_events (ride_id, event_type, detail) VALUES (?, ?, ?)",
            (ride_id, event_type, detail),
        )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Advice log
# ---------------------------------------------------------------------------

async def insert_advice(
    db: aiosqlite.Connection,
    ride_id: str,
    category: str,
    priority: str,
    message: str,
    cooldown_minutes: int = 15,
) -> int:
    cursor = await db.execute(
        "INSERT INTO advice_log (ride_id, category, priority, message, cooldown_minutes) "
        "VALUES (?, ?, ?, ?, ?)",
        (ride_id, category, priority, message, cooldown_minutes),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]
