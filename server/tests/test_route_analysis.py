"""Tests for the route analysis tool."""

from __future__ import annotations

import json
import math

import pytest

from ultra_cycling_ai.db.engine import get_db
from ultra_cycling_ai.db.models import insert_route
from ultra_cycling_ai.tools.route_analysis import (
    RouteAnalysisTool,
    _bearing_deg,
    _bearing_label,
    _categorise_climb,
    _cumulative_distances,
    _extract_track_points,
    _haversine_km,
    _weighted_avg_bearing,
)

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def test_haversine_same_point():
    assert _haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)


def test_haversine_known_distance():
    # London to Paris is ~340 km.
    d = _haversine_km(-0.1278, 51.5074, 2.3522, 48.8566)
    assert 330 < d < 350


def test_bearing_north():
    b = _bearing_deg(0.0, 0.0, 0.0, 1.0)
    assert b == pytest.approx(0.0, abs=0.1)


def test_bearing_east():
    b = _bearing_deg(0.0, 0.0, 1.0, 0.0)
    assert b == pytest.approx(90.0, abs=0.5)


def test_bearing_south():
    b = _bearing_deg(0.0, 1.0, 0.0, 0.0)
    assert b == pytest.approx(180.0, abs=0.1)


def test_bearing_label_north():
    assert _bearing_label(0.0) == "N"
    assert _bearing_label(358.0) == "N"


def test_bearing_label_east():
    assert _bearing_label(90.0) == "E"


def test_bearing_label_southwest():
    assert _bearing_label(225.0) == "SW"


def test_categorise_climb_hc():
    # Very large gain, short distance → HC
    assert _categorise_climb(1200, 5) == "HC"


def test_categorise_climb_cat3():
    assert _categorise_climb(300, 6) == "Cat 3"


def test_categorise_climb_uncat():
    assert _categorise_climb(50, 1) == "uncategorised"


# ---------------------------------------------------------------------------
# Minimal route – a flat 3-point line heading north with a climb in the middle
# ---------------------------------------------------------------------------

def _make_geojson_with_climb() -> dict:
    """
    Simple 4-point route with ~0.018° spacing (≈2 km per segment):
      pt0: (0.0, 0.000,   0m) → 0 km
      pt1: (0.0, 0.018, 100m) → ~2 km – 5% gradient climb
      pt2: (0.0, 0.036, 200m) → ~2 km – 5% gradient climb
      pt3: (0.0, 0.054, 100m) → ~2 km – descent
    """
    coords = [
        [0.0, 0.000,   0.0],
        [0.0, 0.018, 100.0],
        [0.0, 0.036, 200.0],
        [0.0, 0.054, 100.0],
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"name": "test-track", "type": "track"},
            }
        ],
    }


def test_extract_track_points():
    geojson = _make_geojson_with_climb()
    pts = _extract_track_points(geojson)
    assert len(pts) == 4
    assert pts[0] == (0.0, 0.0, 0.0)
    assert pts[2][2] == 200.0


def test_cumulative_distances_monotonic():
    geojson = _make_geojson_with_climb()
    pts = _extract_track_points(geojson)
    cum = _cumulative_distances(pts)
    assert cum[0] == 0.0
    for i in range(1, len(cum)):
        assert cum[i] > cum[i - 1]


def test_weighted_avg_bearing_northward():
    geojson = _make_geojson_with_climb()
    pts = _extract_track_points(geojson)
    cum = _cumulative_distances(pts)
    avg = _weighted_avg_bearing(pts, cum, 0.0, cum[-1])
    # All points are heading north.
    assert avg == pytest.approx(0.0, abs=1.0)


# ---------------------------------------------------------------------------
# Full tool execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_returns_structure():
    """RouteAnalysisTool.execute should return bearing, climbs, and elevation summary."""
    db = await get_db()
    geojson = _make_geojson_with_climb()
    await insert_route(db, "test-route-ra", geojson)

    tool = RouteAnalysisTool()
    result = await tool.execute(
        route_id="test-route-ra",
        current_distance_km=0.0,
        lookahead_km=25.0,
    )

    assert "error" not in result
    assert "bearing" in result
    assert result["bearing"]["current_compass"] is not None
    assert result["bearing"]["avg_lookahead_compass"] is not None
    assert "upcoming_climbs" in result
    assert "elevation_summary" in result
    assert result["elevation_summary"]["gain_m"] > 0


@pytest.mark.asyncio
async def test_execute_detects_climb():
    db = await get_db()
    geojson = _make_geojson_with_climb()
    await insert_route(db, "test-route-climb", geojson)

    tool = RouteAnalysisTool()
    result = await tool.execute(
        route_id="test-route-climb",
        current_distance_km=0.0,
        lookahead_km=50.0,
    )

    assert len(result["upcoming_climbs"]) >= 1
    climb = result["upcoming_climbs"][0]
    assert climb["elevation_gain_m"] > 50
    assert climb["avg_gradient_pct"] > 0
    assert "category" in climb


@pytest.mark.asyncio
async def test_execute_detects_descent():
    db = await get_db()
    geojson = _make_geojson_with_climb()
    await insert_route(db, "test-route-descent", geojson)

    tool = RouteAnalysisTool()
    result = await tool.execute(
        route_id="test-route-descent",
        current_distance_km=0.0,
        lookahead_km=50.0,
    )

    # There is a descent after the climb.
    assert result["next_descent_km"] is not None


@pytest.mark.asyncio
async def test_execute_missing_route():
    tool = RouteAnalysisTool()
    result = await tool.execute(
        route_id="does-not-exist",
        current_distance_km=0.0,
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_lookahead_clamped_to_route_length():
    db = await get_db()
    geojson = _make_geojson_with_climb()
    await insert_route(db, "test-route-clamp", geojson)

    tool = RouteAnalysisTool()
    result = await tool.execute(
        route_id="test-route-clamp",
        current_distance_km=0.0,
        lookahead_km=9999.0,
    )

    assert result["lookahead_km"] == pytest.approx(result["total_route_km"], abs=0.1)
