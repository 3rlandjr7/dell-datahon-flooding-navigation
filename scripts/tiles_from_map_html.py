#!/usr/bin/env python3
"""Build results/flood_tiles.geojson from results/flood_map.html.

This is the fallback path for ticket E1. The normal route is
`scripts/export_tiles.py`, which goes through `flood_heatmap.flood_table()` and
needs `data/image_metadata.csv` for the tile footprints -- i.e. the 1.6 GB
dataset. Use this script instead when the dataset is not available but the
Folium map is, since the map already carries every footprint and score.

It reads the real, final numbers: `flood_map.html` is rendered from the same
table the app would export, recheck pass included.

Two things are lost by going through the map rather than the table, both
harmless for routing, which compares against thresholds of 25% and 50%:

  * percentages are whole numbers, because the tooltip formats them with `:.0f`
  * `lat`/`lon` are the centre of the tile's bounds rather than the dataset's
    own `latitude`/`longitude`, which can differ by a few metres

Usage:
    python3 scripts/tiles_from_map_html.py path/to/flood_map.html [-o out.geojson]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# var rectangle_<id> = L.rectangle(  [[south, west], [north, east]],
RECT_RE = re.compile(
    r"var (rectangle_\w+) = L\.rectangle\(\s*"
    r"\[\[(-?[\d.]+), (-?[\d.]+)\], \[(-?[\d.]+), (-?[\d.]+)\]\]",
)
# rectangle_<id>.bindTooltip( `...`
TOOLTIP_RE = re.compile(r"(rectangle_\w+)\.bindTooltip\(\s*`(.*?)`", re.DOTALL)

NEW_FLOOD_RE = re.compile(r"New flood: (\d+)%")
WATER_RE = re.compile(r"Water before → after: (\d+)% → (\d+)%")
LOCALITY_RE = re.compile(r"<b>(.*?)</b>")
RECHECK_MARK = "rechecked for missed floodwater"


def parse_map(html: str) -> list[dict]:
    """Return one FloodTile-shaped dict per rectangle in the map."""
    tooltips = {m.group(1): m.group(2) for m in TOOLTIP_RE.finditer(html)}
    tiles = []
    for m in RECT_RE.finditer(html):
        name, south, west, north, east = m.group(1), *map(float, m.groups()[1:])
        tip = tooltips.get(name, "")
        # The after_id is the last line of the tooltip, after the final <br>.
        text = re.sub(r"<br\s*/?>", "\n", tip)
        lines = [ln.strip() for ln in re.sub(r"<[^>]+>", "\n", text).split("\n") if ln.strip()]
        after_id = lines[-1] if lines else ""

        flood = NEW_FLOOD_RE.search(tip)
        water = WATER_RE.search(tip)
        locality = LOCALITY_RE.search(tip)

        tiles.append({
            "after_id": after_id,
            "locality": locality.group(1).strip() if locality else "Unknown",
            "new_flood_pct": int(flood.group(1)) if flood else None,
            "before_water_pct": int(water.group(1)) if water else None,
            "after_water_pct": int(water.group(2)) if water else None,
            "rechecked": RECHECK_MARK in tip,
            "north": north, "south": south, "east": east, "west": west,
        })
    return tiles


def to_geojson(tiles: list[dict]) -> dict:
    features = []
    for t in tiles:
        n, s = round(t["north"], 6), round(t["south"], 6)
        e, w = round(t["east"], 6), round(t["west"], 6)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[
                [w, s], [e, s], [e, n], [w, n], [w, s],   # closed ring, [lon, lat]
            ]]},
            "properties": {
                "after_id": t["after_id"],
                "locality": t["locality"],
                "new_flood_pct": t["new_flood_pct"],
                "before_water_pct": t["before_water_pct"],
                "after_water_pct": t["after_water_pct"],
                "rechecked": t["rechecked"],
                "lat": round((n + s) / 2, 6),
                "lon": round((e + w) / 2, 6),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map_html", type=Path, help="results/flood_map.html")
    ap.add_argument("-o", "--out", type=Path, default=Path("results/flood_tiles.geojson"))
    args = ap.parse_args()

    if not args.map_html.is_file():
        sys.exit(f"No such file: {args.map_html}")

    tiles = parse_map(args.map_html.read_text(encoding="utf-8", errors="replace"))
    if not tiles:
        sys.exit("No rectangles found. Is this a Folium map from flood_map()?")

    missing = [t for t in tiles if not t["after_id"] or t["new_flood_pct"] is None]
    gj = to_geojson(tiles)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gj))

    rechecked = sum(t["rechecked"] for t in tiles)
    blocked = sum(1 for t in tiles if (t["new_flood_pct"] or 0) > 50)
    print(f"Wrote {len(tiles)} tiles to {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    print(f"  {rechecked} rechecked, {blocked} above the 50% block threshold")
    if missing:
        print(f"  WARNING: {len(missing)} tiles had no id or no score "
              f"(exported with null): {[t['after_id'] for t in missing[:5]]}")


if __name__ == "__main__":
    main()
