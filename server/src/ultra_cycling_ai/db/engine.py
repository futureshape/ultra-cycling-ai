"""SQLite async engine and schema migrations."""

from __future__ import annotations

import aiosqlite

# Module-level connection reference (set during app lifespan).
_db: aiosqlite.Connection | None = None


async def init_db(db_path: str = "data/ride.db") -> aiosqlite.Connection:
    """Open (or create) the SQLite database and run migrations."""
    global _db

    # Ensure the parent directory exists.
    import pathlib

    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _run_migrations(_db)
    return _db


async def get_db() -> aiosqlite.Connection:
    """Return the current database connection (call after init_db)."""
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Create tables if they don't already exist."""
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS routes (
            route_id   TEXT PRIMARY KEY,
            gpx_geojson TEXT NOT NULL,
            climb_segments TEXT DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS rides (
            ride_id    TEXT PRIMARY KEY,
            route_id   TEXT NOT NULL REFERENCES routes(route_id),
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            status     TEXT NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS ticks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id    TEXT NOT NULL REFERENCES rides(ride_id),
            timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
            payload    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS intake_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id    TEXT NOT NULL REFERENCES rides(ride_id),
            timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
            event_type TEXT NOT NULL CHECK(event_type IN ('eat', 'drink')),
            detail     TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS advice_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id          TEXT NOT NULL REFERENCES rides(ride_id),
            timestamp        TEXT NOT NULL DEFAULT (datetime('now')),
            category         TEXT NOT NULL,
            priority         TEXT NOT NULL,
            message          TEXT NOT NULL,
            cooldown_minutes INTEGER NOT NULL DEFAULT 15
        );
        """
    )
    await db.commit()
