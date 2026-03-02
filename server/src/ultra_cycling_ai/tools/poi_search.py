"""Placeholder: Nearby POI search tool."""

from __future__ import annotations

from typing import Any

from ultra_cycling_ai.tools.registry import Tool


class POISearchTool(Tool):
    name = "poi_search"
    description = (
        "Search for nearby points of interest such as food stops, water sources, "
        "shelters, and bike shops within a given radius."
    )
    parameters = {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude of the search centre."},
            "lon": {"type": "number", "description": "Longitude of the search centre."},
            "radius_km": {
                "type": "number",
                "description": "Search radius in km (default 10).",
                "default": 10,
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by category: food, water, shelter, bike_shop.",
                "default": ["food", "water"],
            },
        },
        "required": ["lat", "lon"],
    }

    async def execute(self, **kwargs: Any) -> dict:
        # TODO: Implement real POI search (e.g. Overpass / Google Places).
        return {
            "pois": [
                {
                    "name": "Mountain Café",
                    "type": "food",
                    "distance_km": 2.3,
                    "lat": kwargs.get("lat", 0) + 0.01,
                    "lon": kwargs.get("lon", 0) + 0.005,
                },
                {
                    "name": "Village Fountain",
                    "type": "water",
                    "distance_km": 4.7,
                    "lat": kwargs.get("lat", 0) + 0.02,
                    "lon": kwargs.get("lon", 0) - 0.01,
                },
            ]
        }
