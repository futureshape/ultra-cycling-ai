"""API endpoint handlers."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from ultra_cycling_ai.api.schemas import (
    AdviceResponse,
    IntakeLogRequest,
    IntakeLogResponse,
    RouteBootstrapRequest,
    RouteBootstrapResponse,
    TickPayload,
    TickResponse,
)
from ultra_cycling_ai.db.engine import get_db
from ultra_cycling_ai.db.models import (
    ensure_ride,
    get_route,
    insert_intake_event,
    insert_route,
    insert_tick,
)
from ultra_cycling_ai.agent.runner import process_tick

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /route/bootstrap
# ---------------------------------------------------------------------------


@router.post("/route/bootstrap", response_model=RouteBootstrapResponse)
async def route_bootstrap(req: RouteBootstrapRequest):
    """Receive route geometry (GPX or GeoJSON) and store it."""
    if not req.has_geometry():
        raise HTTPException(status_code=422, detail="Provide gpx_data or geojson")

    route_id = req.route_id or str(uuid.uuid4())[:12]

    # Convert GPX → GeoJSON stub (real parsing in a future step)
    geojson = req.geojson or {"type": "FeatureCollection", "features": [], "_raw_gpx": True}

    db = await get_db()
    await insert_route(db, route_id, geojson)

    return RouteBootstrapResponse(route_id=route_id)


# ---------------------------------------------------------------------------
# POST /ride/{ride_id}/tick
# ---------------------------------------------------------------------------


@router.post("/ride/{ride_id}/tick", response_model=TickResponse)
async def ride_tick(ride_id: str, tick: TickPayload):
    """Receive a periodic tick from the Karoo extension (or replay script)."""
    db = await get_db()

    # Make sure the route exists.
    route = await get_route(db, tick.route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Route {tick.route_id} not found")

    # Ensure ride row exists.
    await ensure_ride(db, ride_id, tick.route_id)

    # Persist tick.
    await insert_tick(db, ride_id, tick.model_dump(mode="json"))

    # Persist any inline intake events.
    for evt in tick.intake_events_since_last_tick:
        await insert_intake_event(
            db, ride_id, evt.type.value, evt.detail, evt.timestamp
        )

    # Run the agent.
    advice: AdviceResponse | None = await process_tick(ride_id, tick)

    if advice is None:
        return TickResponse(no_advice=True)
    return TickResponse(advice=advice)


# ---------------------------------------------------------------------------
# POST /ride/{ride_id}/intake
# ---------------------------------------------------------------------------


@router.post("/ride/{ride_id}/intake", response_model=IntakeLogResponse)
async def ride_intake(ride_id: str, req: IntakeLogRequest):
    """Log manual intake events outside the normal tick cycle."""
    db = await get_db()

    for evt in req.events:
        await insert_intake_event(
            db, ride_id, evt.type.value, evt.detail, evt.timestamp
        )

    return IntakeLogResponse(logged=len(req.events))
