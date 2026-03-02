"""Route analysis / climb lookahead tool."""

from __future__ import annotations

import json
import math
from typing import Any

from ultra_cycling_ai.db.engine import get_db
from ultra_cycling_ai.db.models import get_route
from ultra_cycling_ai.tools.registry import Tool

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

_EARTH_R_KM = 6371.0


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km between two lon/lat points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return _EARTH_R_KM * 2 * math.asin(math.sqrt(a))


def _bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Forward azimuth (bearing) in degrees 0–360 from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


_COMPASS_LABELS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _bearing_label(deg: float) -> str:
    return _COMPASS_LABELS[round(deg / 22.5) % 16]


# ---------------------------------------------------------------------------
# Climb categorisation (simplified Fiets index)
# ---------------------------------------------------------------------------

def _categorise_climb(elevation_gain_m: float, length_km: float) -> str:
    """Classify a climb using a Fiets-index approximation.

    Fiets ≈ gain_m² / (length_m × 10).  Calibrated thresholds:
    HC ≥ 10, Cat 1 ≥ 6, Cat 2 ≥ 3, Cat 3 ≥ 1.5, Cat 4 ≥ 0.5.
    """
    if length_km < 0.1:
        return "uncategorised"
    fiets = (elevation_gain_m**2) / (length_km * 10_000)
    if fiets >= 10:
        return "HC"
    if fiets >= 6:
        return "Cat 1"
    if fiets >= 3:
        return "Cat 2"
    if fiets >= 1.5:
        return "Cat 3"
    if fiets >= 0.5:
        return "Cat 4"
    return "uncategorised"


# ---------------------------------------------------------------------------
# Route geometry helpers
# ---------------------------------------------------------------------------

def _extract_track_points(geojson: dict) -> list[tuple[float, float, float]]:
    """Return (lon, lat, ele_m) tuples from the first LineString feature."""
    for feature in geojson.get("features", []):
        if feature.get("geometry", {}).get("type") == "LineString":
            coords = feature["geometry"]["coordinates"]
            return [(c[0], c[1], float(c[2]) if len(c) > 2 else 0.0) for c in coords]
    return []


def _cumulative_distances(points: list[tuple[float, float, float]]) -> list[float]:
    """Cumulative distance in km for each point."""
    cum = [0.0]
    for i in range(1, len(points)):
        lon1, lat1, _ = points[i - 1]
        lon2, lat2, _ = points[i]
        cum.append(cum[-1] + _haversine_km(lon1, lat1, lon2, lat2))
    return cum


def _weighted_avg_bearing(
    points: list[tuple[float, float, float]],
    cum_km: list[float],
    from_km: float,
    to_km: float,
) -> float | None:
    """Distance-weighted average bearing over [from_km, to_km]."""
    total_w = 0.0
    sin_sum = 0.0
    cos_sum = 0.0
    for i in range(1, len(points)):
        if cum_km[i] <= from_km:
            continue
        if cum_km[i - 1] >= to_km:
            break
        lon1, lat1, _ = points[i - 1]
        lon2, lat2, _ = points[i]
        seg_len = cum_km[i] - cum_km[i - 1]
        if seg_len < 1e-9:
            continue
        b = math.radians(_bearing_deg(lon1, lat1, lon2, lat2))
        sin_sum += math.sin(b) * seg_len
        cos_sum += math.cos(b) * seg_len
        total_w += seg_len
    if total_w < 1e-9:
        return None
    return (math.degrees(math.atan2(sin_sum / total_w, cos_sum / total_w)) + 360) % 360


# ---------------------------------------------------------------------------
# Climb detection
# ---------------------------------------------------------------------------

def _detect_climbs(
    points: list[tuple[float, float, float]],
    cum_km: list[float],
    window_start_km: float,
    window_end_km: float,
    min_gradient_pct: float = 2.0,
    min_gain_m: float = 20.0,
) -> list[dict]:
    in_climb = False
    climb_start_i = 0
    climbs: list[dict] = []

    for i in range(1, len(points)):
        if cum_km[i] <= window_start_km:
            continue
        if cum_km[i - 1] >= window_end_km:
            break

        seg_km = cum_km[i] - cum_km[i - 1]
        if seg_km < 1e-9:
            continue

        ele_diff = points[i][2] - points[i - 1][2]
        gradient_pct = (ele_diff / (seg_km * 1000)) * 100

        if gradient_pct >= min_gradient_pct:
            if not in_climb:
                in_climb = True
                climb_start_i = i - 1
        else:
            if in_climb:
                in_climb = False
                climb = _build_climb_dict(points, cum_km, climb_start_i, i - 1)
                if climb and climb["elevation_gain_m"] >= min_gain_m:
                    climbs.append(climb)

    if in_climb:
        climb = _build_climb_dict(points, cum_km, climb_start_i, len(points) - 1)
        if climb and climb["elevation_gain_m"] >= min_gain_m:
            climbs.append(climb)

    return climbs


def _build_climb_dict(
    points: list[tuple[float, float, float]],
    cum_km: list[float],
    start_i: int,
    end_i: int,
) -> dict | None:
    if start_i >= end_i:
        return None

    gain_m = 0.0
    max_gradient_pct = 0.0

    for j in range(start_i + 1, end_i + 1):
        seg_km = cum_km[j] - cum_km[j - 1]
        if seg_km < 1e-9:
            continue
        ele_diff = points[j][2] - points[j - 1][2]
        if ele_diff > 0:
            gain_m += ele_diff
        grad = (ele_diff / (seg_km * 1000)) * 100
        if grad > max_gradient_pct:
            max_gradient_pct = grad

    length_km = cum_km[end_i] - cum_km[start_i]
    net_gain = points[end_i][2] - points[start_i][2]
    avg_gradient_pct = (net_gain / (length_km * 1000)) * 100 if length_km > 0 else 0.0

    return {
        "start_km": round(cum_km[start_i], 2),
        "end_km": round(cum_km[end_i], 2),
        "length_km": round(length_km, 2),
        "avg_gradient_pct": round(avg_gradient_pct, 1),
        "max_gradient_pct": round(max_gradient_pct, 1),
        "elevation_gain_m": round(gain_m),
        "category": _categorise_climb(gain_m, length_km),
    }


def _find_next_descent_km(
    points: list[tuple[float, float, float]],
    cum_km: list[float],
    window_start_km: float,
    window_end_km: float,
    min_gradient_pct: float = -2.0,
) -> float | None:
    for i in range(1, len(points)):
        if cum_km[i] <= window_start_km:
            continue
        if cum_km[i - 1] >= window_end_km:
            break
        seg_km = cum_km[i] - cum_km[i - 1]
        if seg_km < 1e-9:
            continue
        gradient = ((points[i][2] - points[i - 1][2]) / (seg_km * 1000)) * 100
        if gradient <= min_gradient_pct:
            return round(cum_km[i - 1], 2)
    return None


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class RouteAnalysisTool(Tool):
    name = "route_analysis"
    description = (
        "Analyse the upcoming route segment. Returns climb details, "
        "gradient info, terrain summary, and route bearing for the next N km. "
        "Route bearing can be compared against wind direction to assess "
        "headwind, tailwind, or crosswind exposure."
    )
    parameters = {
        "type": "object",
        "properties": {
            "route_id": {
                "type": "string",
                "description": "The route identifier.",
            },
            "current_distance_km": {
                "type": "number",
                "description": "Rider's current distance along the route in km.",
            },
            "lookahead_km": {
                "type": "number",
                "description": "How far ahead to analyse (default 20 km).",
                "default": 20,
            },
        },
        "required": ["route_id", "current_distance_km"],
    }

    async def execute(self, **kwargs: Any) -> dict:
        route_id: str = kwargs["route_id"]
        current_km: float = float(kwargs["current_distance_km"])
        lookahead_km: float = float(kwargs.get("lookahead_km", 20))
        window_end_km = current_km + lookahead_km

        # Load route from database.
        db = await get_db()
        row = await get_route(db, route_id)
        if row is None:
            return {"error": f"Route '{route_id}' not found in database."}

        geojson = json.loads(row["gpx_geojson"]) if isinstance(row["gpx_geojson"], str) else row["gpx_geojson"]
        points = _extract_track_points(geojson)
        if not points:
            return {"error": "Route has no LineString track geometry."}

        cum_km = _cumulative_distances(points)
        total_route_km = round(cum_km[-1], 2)

        # Clamp window to route length.
        window_end_km = min(window_end_km, total_route_km)

        # --- Bearing at current position (immediate direction of travel) ---
        bearing_deg: float | None = None
        for i in range(1, len(points)):
            if cum_km[i] > current_km:
                lon1, lat1, _ = points[i - 1]
                lon2, lat2, _ = points[i]
                bearing_deg = _bearing_deg(lon1, lat1, lon2, lat2)
                break

        # --- Average bearing over the lookahead window ---
        avg_bearing_deg = _weighted_avg_bearing(points, cum_km, current_km, window_end_km)

        # --- Climbs ---
        climbs = _detect_climbs(points, cum_km, current_km, window_end_km)

        # --- Next descent ---
        next_descent_km = _find_next_descent_km(points, cum_km, current_km, window_end_km)

        # --- Elevation summary for the window ---
        window_points = [
            p for p, d in zip(points, cum_km) if current_km <= d <= window_end_km
        ]
        total_elevation_gain_m = sum(
            max(0.0, window_points[j][2] - window_points[j - 1][2])
            for j in range(1, len(window_points))
        )
        total_elevation_loss_m = sum(
            max(0.0, window_points[j - 1][2] - window_points[j][2])
            for j in range(1, len(window_points))
        )

        result: dict[str, Any] = {
            "lookahead_km": round(window_end_km - current_km, 2),
            "total_route_km": total_route_km,
            "bearing": {
                "current_deg": round(bearing_deg, 1) if bearing_deg is not None else None,
                "current_compass": _bearing_label(bearing_deg) if bearing_deg is not None else None,
                "avg_lookahead_deg": round(avg_bearing_deg, 1) if avg_bearing_deg is not None else None,
                "avg_lookahead_compass": _bearing_label(avg_bearing_deg) if avg_bearing_deg is not None else None,
                "note": (
                    "Compare avg_lookahead_compass against wind_direction from weather_forecast. "
                    "Wind FROM the same compass quadrant as rider travel = headwind; "
                    "opposite = tailwind; perpendicular = crosswind."
                ),
            },
            "elevation_summary": {
                "gain_m": round(total_elevation_gain_m),
                "loss_m": round(total_elevation_loss_m),
            },
            "upcoming_climbs": climbs,
            "next_descent_km": next_descent_km,
        }
        return result
