#!/usr/bin/env python3
"""Fetch the real street network for the routing area and save it as GeoJSON.

The demo page routes on an evenly spaced simulated grid until this has been run.
It is a stand-in, not the street layout under the basemap, and the page says so.
This script replaces it with the real thing.

    python3 scripts/fetch_roads.py

Writes results/road_network.geojson. Then open docs/index.html, click
"Load street network" and pick that file.

Needs internet and nothing else: no API key, no OSMnx, no GDAL. It asks a public
Overpass API server for the drivable roads inside ROAD_BBOX and writes one
LineString per way. Overpass is a shared free service, so be a good citizen: run
this once and keep the output, rather than calling it from anything automated.

ROAD_BBOX is the west Houston / Addicks-Barker area the flood tiles cover:
north 29.8597, south 29.7262, east -95.5811, west -95.7349.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same bounds as the demo page and the ticket contracts.
BBOX = {"north": 29.8597, "south": 29.7262, "east": -95.5811, "west": -95.7349}

# Public Overpass instances, tried in order. They rate-limit and go down; the
# second and third are mirrors that accept the same query language.
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Drivable public roads. Service roads, driveways and tracks are left out: they
# add a lot of geometry and are not what a car evacuating would use.
HIGHWAYS = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential"
            "|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|living_street")

USER_AGENT = "flood-safe-route/1.0 (portfolio project; one-off road export)"


def build_query(bbox: dict) -> str:
    box = f'{bbox["south"]},{bbox["west"]},{bbox["north"]},{bbox["east"]}'
    return f"""
[out:json][timeout:180];
way["highway"~"^({HIGHWAYS})$"]["area"!~"yes"]({box});
out geom;
""".strip()


def fetch(query: str, endpoints: list[str]) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for i, url in enumerate(endpoints):
        try:
            print(f"Asking {urllib.parse.urlparse(url).netloc} ...", flush=True)
            req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
            started = time.time()
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.load(resp)
            print(f"  got {len(payload.get('elements', []))} ways in {time.time() - started:.0f}s")
            return payload
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
            last = err
            print(f"  failed: {err}")
            if i + 1 < len(endpoints):
                print("  trying the next server in 5s")
                time.sleep(5)
    sys.exit(
        f"Could not reach any Overpass server ({last}).\n"
        "They rate-limit and go down for maintenance; wait a few minutes and try again.\n"
        "The demo page still works without this file - it falls back to the simulated grid."
    )


def to_geojson(payload: dict) -> dict:
    features = []
    for el in payload.get("elements", []):
        geom = el.get("geometry")
        if el.get("type") != "way" or not geom or len(geom) < 2:
            continue
        tags = el.get("tags", {}) or {}
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                # [lon, lat], rounded to ~1 cm: plenty, and it keeps the file small
                "coordinates": [[round(p["lon"], 7), round(p["lat"], 7)] for p in geom],
            },
            "properties": {
                "osm_id": el.get("id"),
                "highway": tags.get("highway"),
                "name": tags.get("name"),
                "oneway": tags.get("oneway"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", type=Path, default=ROOT / "results" / "road_network.geojson")
    ap.add_argument("--endpoint", action="append", dest="endpoints",
                    help="Overpass server to try first; repeatable.")
    args = ap.parse_args()

    endpoints = (args.endpoints or []) + ENDPOINTS
    print(f"Routing area: {BBOX['south']},{BBOX['west']} to {BBOX['north']},{BBOX['east']}")
    gj = to_geojson(fetch(build_query(BBOX), endpoints))
    if not gj["features"]:
        sys.exit("Overpass answered, but with no roads. Check the bounding box.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gj))
    points = sum(len(f["geometry"]["coordinates"]) for f in gj["features"])
    named = sum(1 for f in gj["features"] if f["properties"]["name"])
    print(f"\nWrote {len(gj['features'])} ways ({points} points, {named} named) "
          f"to {args.out} ({args.out.stat().st_size / 1_048_576:.1f} MB)")
    print('\nNow open docs/index.html, click "Load street network" and pick that file.')


if __name__ == "__main__":
    main()
