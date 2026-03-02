"""Daylight / sunrise-sunset tool using astral library."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from astral import LocationInfo
from astral.sun import sun

from ultra_cycling_ai.tools.registry import Tool


class DaylightTool(Tool):
    name = "daylight"
    description = (
        "Get sunrise and sunset times for a location and date. "
        "Also returns hours of daylight remaining from the current time."
    )
    parameters = {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude."},
            "lon": {"type": "number", "description": "Longitude."},
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format (default: today).",
            },
        },
        "required": ["lat", "lon"],
    }

    async def execute(self, **kwargs: Any) -> dict:
        lat = float(kwargs["lat"])
        lon = float(kwargs["lon"])

        if not (-90.0 <= lat <= 90.0):
            raise ValueError("lat must be between -90 and 90")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError("lon must be between -180 and 180")

        raw_date = kwargs.get("date")
        if raw_date:
            target_date = date.fromisoformat(raw_date)
        else:
            target_date = datetime.now(timezone.utc).date()

        # Create a location and calculate sun events
        location = LocationInfo(latitude=lat, longitude=lon)
        sun_events = sun(observer=location.observer, date=target_date, tzinfo=timezone.utc)

        sunrise_dt = sun_events["sunrise"]
        sunset_dt = sun_events["sunset"]

        daylight_hours = (sunset_dt - sunrise_dt).total_seconds() / 3600.0

        now_utc = datetime.now(timezone.utc)
        today_utc = now_utc.date()

        if target_date > today_utc:
            hours_remaining = daylight_hours
        elif target_date < today_utc:
            hours_remaining = 0.0
        else:
            if now_utc <= sunrise_dt:
                hours_remaining = daylight_hours
            elif now_utc >= sunset_dt:
                hours_remaining = 0.0
            else:
                hours_remaining = (sunset_dt - now_utc).total_seconds() / 3600.0

        return {
            "sunrise": sunrise_dt.strftime("%H:%M"),
            "sunset": sunset_dt.strftime("%H:%M"),
            "daylight_hours": round(daylight_hours, 2),
            "hours_remaining": round(max(0.0, hours_remaining), 2),
            "date": target_date.isoformat(),
            "latitude": lat,
            "longitude": lon,
            "timezone": "UTC",
            "sunrise_iso": sunrise_dt.isoformat(),
            "sunset_iso": sunset_dt.isoformat(),
        }
