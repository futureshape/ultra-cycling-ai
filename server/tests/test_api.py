"""API integration tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ultra_cycling_ai.api.routes import router
from fastapi import FastAPI

# Build a minimal app for testing (lifespan handled by conftest fixtures).
_test_app = FastAPI()
_test_app.include_router(router)


@_test_app.get("/health")
async def health():
    return {"status": "ok"}


@pytest.fixture
async def client():
    """Provide an async test client (DB init handled by conftest)."""
    async with AsyncClient(
        transport=ASGITransport(app=_test_app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_route_bootstrap(client: AsyncClient):
    resp = await client.post(
        "/route/bootstrap",
        json={
            "route_id": "test-route-1",
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0, 0], [1, 1]],
                        },
                        "properties": {},
                    }
                ],
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["route_id"] == "test-route-1"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_route_bootstrap_missing_geometry(client: AsyncClient):
    resp = await client.post("/route/bootstrap", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tick_unknown_route(client: AsyncClient):
    """Tick against a non-existent route should 404."""
    resp = await client.post(
        "/ride/ride-1/tick",
        json={
            "route_id": "nonexistent",
            "position": {"lat": 45.0, "lon": 7.0},
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_intake_logging(client: AsyncClient):
    resp = await client.post(
        "/ride/ride-intake-test/intake",
        json={
            "events": [
                {"type": "eat", "detail": "energy bar"},
                {"type": "drink", "detail": "500ml water"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["logged"] == 2
