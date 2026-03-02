"""Pydantic models for API request / response contracts."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IntakeType(str, Enum):
    eat = "eat"
    drink = "drink"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AdviceCategory(str, Enum):
    fuel = "fuel"
    pacing = "pacing"
    fatigue = "fatigue"
    terrain = "terrain"
    environment = "environment"
    morale = "morale"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class Position(BaseModel):
    lat: float
    lon: float
    elevation_m: float | None = None
    distance_km: float | None = None


class RecentWindow(BaseModel):
    """Averages over the most recent sampling window (e.g. last 2-5 min)."""

    avg_speed_kph: float | None = None
    avg_hr_bpm: float | None = None
    avg_power_w: float | None = None
    avg_cadence_rpm: float | None = None


class RideTotals(BaseModel):
    elapsed_s: int = 0
    distance_km: float = 0.0
    elevation_gain_m: float = 0.0
    tss: float | None = None


class IntakeEvent(BaseModel):
    timestamp: str | None = None  # ISO-8601; backend uses server time if absent
    type: IntakeType
    detail: str = ""


# ---------------------------------------------------------------------------
# Route bootstrap
# ---------------------------------------------------------------------------


class RouteBootstrapRequest(BaseModel):
    route_id: str | None = None  # auto-generated if omitted
    gpx_data: str | None = None  # raw GPX XML string
    geojson: dict | None = None  # alternative: pass GeoJSON directly

    def has_geometry(self) -> bool:
        return self.gpx_data is not None or self.geojson is not None


class RouteBootstrapResponse(BaseModel):
    route_id: str
    status: str = "ok"


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------


class TickPayload(BaseModel):
    route_id: str
    ride_id: str | None = None  # auto-generated from route_id if omitted
    position: Position
    recent_window: RecentWindow = Field(default_factory=RecentWindow)
    totals: RideTotals = Field(default_factory=RideTotals)
    intake_events_since_last_tick: list[IntakeEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Intake (standalone endpoint)
# ---------------------------------------------------------------------------


class IntakeLogRequest(BaseModel):
    events: list[IntakeEvent]


class IntakeLogResponse(BaseModel):
    logged: int
    status: str = "ok"


# ---------------------------------------------------------------------------
# Advice response
# ---------------------------------------------------------------------------


class AdviceResponse(BaseModel):
    priority: Priority
    category: AdviceCategory
    message: str
    cooldown_minutes: int = 15


class NoAdviceResponse(BaseModel):
    no_advice: Literal[True] = True


class TickResponse(BaseModel):
    advice: AdviceResponse | None = None
    no_advice: bool = False
