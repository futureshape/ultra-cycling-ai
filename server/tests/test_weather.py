"""Tests for the WeatherForecastTool (Open-Meteo integration)."""

from __future__ import annotations

import pytest

from ultra_cycling_ai.tools.weather import WeatherForecastTool, _degrees_to_cardinal, _wmo_description

# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


def test_wmo_description_known_code():
    assert _wmo_description(0) == "Clear sky"
    assert _wmo_description(61) == "Slight rain"
    assert _wmo_description(95) == "Thunderstorm"


def test_wmo_description_unknown_code():
    desc = _wmo_description(999)
    assert "999" in desc


def test_degrees_to_cardinal():
    assert _degrees_to_cardinal(0) == "N"
    assert _degrees_to_cardinal(90) == "E"
    assert _degrees_to_cardinal(180) == "S"
    assert _degrees_to_cardinal(270) == "W"
    assert _degrees_to_cardinal(315) == "NW"


# ---------------------------------------------------------------------------
# Integration — live Open-Meteo API
# ---------------------------------------------------------------------------

# London as a stable, well-covered coordinate for the forecast API.
_LAT, _LON = 51.5074, -0.1278

EXPECTED_KEYS = {
    "temperature_c",
    "feels_like_c",
    "humidity_pct",
    "wind_kph",
    "wind_gusts_kph",
    "wind_direction",
    "wind_direction_deg",
    "conditions",
    "weather_code",
    "hours_ahead",
    "forecast_max_temp_c",
    "forecast_min_temp_c",
    "forecast_max_wind_kph",
    "forecast_precipitation_chance",
    "forecast_precipitation_mm",
    "forecast_worst_conditions",
}


@pytest.mark.asyncio
async def test_execute_returns_all_keys():
    """Response must contain every documented key."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON, hours_ahead=6)
    assert EXPECTED_KEYS == result.keys()


@pytest.mark.asyncio
async def test_execute_numeric_types():
    """All numeric fields must be int or float."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON, hours_ahead=6)

    numeric_keys = [
        "temperature_c", "feels_like_c", "humidity_pct",
        "wind_kph", "wind_gusts_kph", "wind_direction_deg",
        "weather_code", "hours_ahead",
        "forecast_max_temp_c", "forecast_min_temp_c", "forecast_max_wind_kph",
        "forecast_precipitation_chance", "forecast_precipitation_mm",
    ]
    for key in numeric_keys:
        assert isinstance(result[key], (int, float)), f"{key!r} is not numeric: {result[key]!r}"


@pytest.mark.asyncio
async def test_execute_string_fields():
    """Cardinal direction and conditions must be non-empty strings."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON, hours_ahead=6)

    assert isinstance(result["wind_direction"], str) and result["wind_direction"]
    assert isinstance(result["conditions"], str) and result["conditions"]
    assert isinstance(result["forecast_worst_conditions"], str) and result["forecast_worst_conditions"]


@pytest.mark.asyncio
async def test_execute_value_ranges():
    """Sanity-check that values fall within physically plausible ranges."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON, hours_ahead=6)

    assert -60 <= result["temperature_c"] <= 60
    assert -60 <= result["feels_like_c"] <= 60
    assert 0 <= result["humidity_pct"] <= 100
    assert result["wind_kph"] >= 0
    assert result["wind_gusts_kph"] >= 0
    assert 0 <= result["wind_direction_deg"] <= 360
    assert result["forecast_precipitation_chance"] >= 0
    assert result["forecast_precipitation_mm"] >= 0


@pytest.mark.asyncio
async def test_execute_hours_ahead_reflected():
    """The returned hours_ahead must echo the requested value."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON, hours_ahead=12)
    assert result["hours_ahead"] == 12


@pytest.mark.asyncio
async def test_execute_default_hours_ahead():
    """hours_ahead defaults to 6 when omitted."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON)
    assert result["hours_ahead"] == 6


@pytest.mark.asyncio
async def test_execute_forecast_temp_ordering():
    """Forecast max temperature must be >= min temperature."""
    tool = WeatherForecastTool()
    result = await tool.execute(lat=_LAT, lon=_LON, hours_ahead=6)
    assert result["forecast_max_temp_c"] >= result["forecast_min_temp_c"]
