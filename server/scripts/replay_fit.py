#!/usr/bin/env python3
"""Replay a FIT file as a stream of tick payloads against the backend.

Usage:
    python replay_fit.py <fit_file> --route-id <id> [--ride-id <id>] \
        [--base-url http://localhost:8000] [--speed-multiplier 10]
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


def parse_fit_records(fit_path: str) -> list[dict]:
    """Parse a FIT file and extract records with lat/lon/etc."""
    from fitparse import FitFile

    fitfile = FitFile(fit_path)
    records: list[dict] = []

    for record in fitfile.get_messages("record"):
        row: dict = {}
        for field in record.fields:
            row[field.name] = field.value
        # Convert semicircles → degrees if present.
        if "position_lat" in row and row["position_lat"] is not None:
            row["lat"] = row["position_lat"] * (180 / 2**31)
        if "position_long" in row and row["position_long"] is not None:
            row["lon"] = row["position_long"] * (180 / 2**31)
        records.append(row)

    return records


def group_into_ticks(records: list[dict], interval_s: int = 120) -> list[dict]:
    """Group FIT records into tick-sized windows.

    Returns a list of tick payload dicts ready to POST.
    """
    if not records:
        return []

    ticks: list[dict] = []
    window: list[dict] = []
    first_ts = records[0].get("timestamp")
    cumulative_distance_m = 0.0
    cumulative_elevation_m = 0.0
    prev = None

    for rec in records:
        window.append(rec)

        # Accumulate distance.
        if rec.get("distance") is not None:
            cumulative_distance_m = rec["distance"]

        # Accumulate elevation gain.
        if prev and rec.get("altitude") is not None and prev.get("altitude") is not None:
            diff = rec["altitude"] - prev["altitude"]
            if diff > 0:
                cumulative_elevation_m += diff

        ts = rec.get("timestamp")
        elapsed_s = 0
        if ts and first_ts:
            elapsed_s = int((ts - first_ts).total_seconds())

        # Emit a tick every interval_s seconds.
        if len(window) > 1 and elapsed_s > 0 and elapsed_s % interval_s < (records[1].get("timestamp", records[0].get("timestamp")) - records[0].get("timestamp")).total_seconds() + 1:
            if elapsed_s >= len(ticks) * interval_s + interval_s:
                tick = _build_tick(window, elapsed_s, cumulative_distance_m, cumulative_elevation_m)
                if tick:
                    ticks.append(tick)
                window = [rec]  # Start new window with current record.

        prev = rec

    # Final window.
    if window:
        ts = window[-1].get("timestamp")
        elapsed_s = int((ts - first_ts).total_seconds()) if ts and first_ts else 0
        tick = _build_tick(window, elapsed_s, cumulative_distance_m, cumulative_elevation_m)
        if tick:
            ticks.append(tick)

    return ticks


def _build_tick(window: list[dict], elapsed_s: int, total_dist_m: float, total_elev_m: float) -> dict | None:
    last = window[-1]
    lat = last.get("lat")
    lon = last.get("lon")
    if lat is None or lon is None:
        return None

    speeds = [r["speed"] for r in window if r.get("speed") is not None]
    hrs = [r["heart_rate"] for r in window if r.get("heart_rate") is not None]
    powers = [r["power"] for r in window if r.get("power") is not None]
    cadences = [r["cadence"] for r in window if r.get("cadence") is not None]

    def avg(vals: list) -> float | None:
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "position": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "elevation_m": last.get("altitude"),
            "distance_km": round(total_dist_m / 1000, 2),
        },
        "recent_window": {
            "avg_speed_kph": round(avg(speeds) * 3.6, 1) if avg(speeds) else None,
            "avg_hr_bpm": avg(hrs),
            "avg_power_w": avg(powers),
            "avg_cadence_rpm": avg(cadences),
        },
        "totals": {
            "elapsed_s": elapsed_s,
            "distance_km": round(total_dist_m / 1000, 2),
            "elevation_gain_m": round(total_elev_m, 1),
        },
        "intake_events_since_last_tick": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a FIT file as ride ticks")
    parser.add_argument("fit_file", help="Path to the FIT file")
    parser.add_argument("--route-id", required=True, help="Route ID (must exist on server)")
    parser.add_argument("--ride-id", default=None, help="Ride ID (auto-generated if omitted)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--speed-multiplier", type=float, default=10, help="Playback speed (1=real-time)")
    parser.add_argument("--tick-interval", type=int, default=120, help="Seconds between ticks")
    args = parser.parse_args()

    if not Path(args.fit_file).exists():
        print(f"FIT file not found: {args.fit_file}", file=sys.stderr)
        sys.exit(1)

    ride_id = args.ride_id or f"replay-{uuid.uuid4().hex[:8]}"
    print(f"Parsing FIT file: {args.fit_file}")
    records = parse_fit_records(args.fit_file)
    print(f"  {len(records)} records found")

    ticks = group_into_ticks(records, interval_s=args.tick_interval)
    print(f"  {len(ticks)} ticks generated (interval={args.tick_interval}s)")
    print(f"  Ride ID: {ride_id}")
    print(f"  Speed: {args.speed_multiplier}x\n")

    delay = args.tick_interval / args.speed_multiplier

    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        for i, tick in enumerate(ticks, 1):
            tick["route_id"] = args.route_id
            tick["ride_id"] = ride_id

            print(f"[Tick {i}/{len(ticks)}] dist={tick['totals']['distance_km']}km "
                  f"elapsed={tick['totals']['elapsed_s']}s")

            resp = client.post(f"/ride/{ride_id}/tick", json=tick)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("advice"):
                    adv = data["advice"]
                    print(f"  → [{adv['priority'].upper()}] ({adv['category']}) {adv['message']}")
                else:
                    print(f"  → no advice")
            else:
                print(f"  ✗ HTTP {resp.status_code}: {resp.text[:200]}")

            if i < len(ticks):
                time.sleep(delay)

    print(f"\nReplay complete. {len(ticks)} ticks sent.")


if __name__ == "__main__":
    main()
