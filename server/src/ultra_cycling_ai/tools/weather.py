"""Weather forecast tool powered by Open-Meteo (https://open-meteo.com)."""

from __future__ import annotations

from typing import Any

import httpx

from ultra_cycling_ai.tools.registry import Tool

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather interpretation codes → human-readable string
# https://open-meteo.com/en/docs (WMO Weather interpretation codes table)
_WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

_CARDINALS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _wmo_description(code: int) -> str:
    return _WMO_CODES.get(code, f"Unknown (WMO {code})")


def _degrees_to_cardinal(degrees: float) -> str:
    return _CARDINALS[round(degrees / 22.5) % 16]


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
        lat: float = kwargs["lat"]
        lon: float = kwargs["lon"]
        hours_ahead: int = int(kwargs.get("hours_ahead", 6))

        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            # Current snapshot variables
            "current": [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "precipitation",
                "weather_code",
            ],
            # Hourly variables for the forecast window summary
            "hourly": [
                "temperature_2m",
                "wind_speed_10m",
                "precipitation_probability",
                "precipitation",
                "weather_code",
            ],
            "forecast_hours": hours_ahead,
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current", {})
        hourly = data.get("hourly", {})

        # ── Current conditions ────────────────────────────────────────────────
        temperature_c: float | None = current.get("temperature_2m")
        feels_like_c: float | None = current.get("apparent_temperature")
        humidity_pct: float | None = current.get("relative_humidity_2m")
        wind_kph: float | None = current.get("wind_speed_10m")
        wind_dir_deg: float | None = current.get("wind_direction_10m")
        wind_gusts_kph: float | None = current.get("wind_gusts_10m")
        wmo_code: int = current.get("weather_code", 0)

        # ── Hourly forecast summary over the requested window ─────────────────
        def _clean(values: list | None) -> list[float]:
            return [v for v in (values or []) if v is not None]

        precip_probs = _clean(hourly.get("precipitation_probability"))
        precip_totals = _clean(hourly.get("precipitation"))
        hourly_codes = [int(v) for v in _clean(hourly.get("weather_code"))]
        hourly_temps = _clean(hourly.get("temperature_2m"))
        hourly_winds = _clean(hourly.get("wind_speed_10m"))

        avg_precip_chance = (sum(precip_probs) / len(precip_probs)) if precip_probs else 0.0
        total_precip_mm = sum(precip_totals)
        worst_code = max(hourly_codes) if hourly_codes else wmo_code
        forecast_max_temp = max(hourly_temps) if hourly_temps else temperature_c
        forecast_min_temp = min(hourly_temps) if hourly_temps else temperature_c
        forecast_max_wind = max(hourly_winds) if hourly_winds else wind_kph

        return {
            # Current snapshot
            "temperature_c": temperature_c,
            "feels_like_c": feels_like_c,
            "humidity_pct": humidity_pct,
            "wind_kph": wind_kph,
            "wind_gusts_kph": wind_gusts_kph,
            "wind_direction": _degrees_to_cardinal(wind_dir_deg) if wind_dir_deg is not None else None,
            "wind_direction_deg": wind_dir_deg,
            "conditions": _wmo_description(wmo_code),
            "weather_code": wmo_code,
            # Forecast summary over `hours_ahead` window
            "hours_ahead": hours_ahead,
            "forecast_max_temp_c": forecast_max_temp,
            "forecast_min_temp_c": forecast_min_temp,
            "forecast_max_wind_kph": forecast_max_wind,
            "forecast_precipitation_chance": round(avg_precip_chance / 100, 2),
            "forecast_precipitation_mm": round(total_precip_mm, 1),
            "forecast_worst_conditions": _wmo_description(worst_code),
        }
