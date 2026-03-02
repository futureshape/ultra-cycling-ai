"""Placeholder: Weather forecast tool."""

from __future__ import annotations

from typing import Any

from ultra_cycling_ai.tools.registry import Tool


class WeatherForecastTool(Tool):
    name = "weather_forecast"
    description = (
        "Get a weather forecast for a given location and time horizon. "
        "Returns temperature, wind, precipitation, and conditions summary."
    )
    parameters = {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude."},
            "lon": {"type": "number", "description": "Longitude."},
            "hours_ahead": {
                "type": "integer",
                "description": "Forecast horizon in hours (default 6).",
                "default": 6,
            },
        },
        "required": ["lat", "lon"],
    }

    async def execute(self, **kwargs: Any) -> dict:
        # TODO: Implement real weather API call (e.g. Open-Meteo, OpenWeatherMap).
        return {
            "temperature_c": 18,
            "feels_like_c": 16,
            "wind_kph": 12,
            "wind_direction": "NW",
            "precipitation_chance": 0.1,
            "conditions": "Partly cloudy",
            "hours_ahead": kwargs.get("hours_ahead", 6),
        }
