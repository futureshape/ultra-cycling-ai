"""Placeholder: Route analysis / climb lookahead tool."""

from __future__ import annotations

from typing import Any

from ultra_cycling_ai.tools.registry import Tool


class RouteAnalysisTool(Tool):
    name = "route_analysis"
    description = (
        "Analyse the upcoming route segment. Returns climb details, "
        "gradient info, and terrain summary for the next N km."
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
        # TODO: Implement real route analysis against stored route geometry.
        return {
            "upcoming_climbs": [
                {
                    "start_km": kwargs.get("current_distance_km", 0) + 3.2,
                    "end_km": kwargs.get("current_distance_km", 0) + 8.1,
                    "avg_gradient_pct": 5.4,
                    "max_gradient_pct": 9.2,
                    "elevation_gain_m": 320,
                    "category": "Cat 3",
                }
            ],
            "next_descent_km": kwargs.get("current_distance_km", 0) + 8.1,
            "terrain_summary": "Rolling terrain with one categorised climb in the next 20 km.",
        }
