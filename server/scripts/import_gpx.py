#!/usr/bin/env python3
"""Import a GPX file as a route via the /route/bootstrap endpoint.

Usage:
    python import_gpx.py <gpx_file> [--route-id <id>] [--base-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import gpxpy
import httpx


def gpx_to_geojson(gpx_path: str) -> dict:
    """Parse a GPX file and convert the first track to GeoJSON + extract waypoints."""
    with open(gpx_path) as f:
        gpx = gpxpy.parse(f)

    features: list[dict] = []

    # Convert tracks → LineString features.
    for track in gpx.tracks:
        for segment in track.segments:
            coordinates = [
                [p.longitude, p.latitude, p.elevation or 0]
                for p in segment.points
            ]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coordinates,
                    },
                    "properties": {
                        "name": track.name or "track",
                        "type": "track",
                    },
                }
            )

    # Convert waypoints → Point features (POIs).
    for wpt in gpx.waypoints:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [wpt.longitude, wpt.latitude, wpt.elevation or 0],
                },
                "properties": {
                    "name": wpt.name or "waypoint",
                    "description": wpt.description or "",
                    "type": "poi",
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a GPX route to the backend")
    parser.add_argument("gpx_file", help="Path to the GPX file")
    parser.add_argument("--route-id", default=None, help="Route ID (auto-generated if omitted)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()

    if not Path(args.gpx_file).exists():
        print(f"GPX file not found: {args.gpx_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing GPX: {args.gpx_file}")
    geojson = gpx_to_geojson(args.gpx_file)
    tracks = sum(1 for f in geojson["features"] if f["properties"].get("type") == "track")
    pois = sum(1 for f in geojson["features"] if f["properties"].get("type") == "poi")
    print(f"  {tracks} track(s), {pois} waypoint(s)/POI(s)")

    payload: dict = {"geojson": geojson}
    if args.route_id:
        payload["route_id"] = args.route_id

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        resp = client.post("/route/bootstrap", json=payload)

    if resp.status_code == 200:
        data = resp.json()
        print(f"  Route created: {data['route_id']}")
    else:
        print(f"  ✗ HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
