#!/usr/bin/env python3
"""Ticket E1 - export the final flood scores to results/flood_tiles.geojson.

Run this on the laptop that has data/ and results/. It needs pandas and nothing
else, and it does NOT import the project's own modules, so it works whether or
not config.py / flood_heatmap.py are in place yet.

    python3 scripts/export_tiles.py

It looks for the usual files under results/ and data/, applies the recheck pass
(decision D13), and writes results/flood_tiles.geojson. Then open
docs/route_demo.html, click "Load real scores" and pick that file.

If your files live elsewhere, point at them:

    python3 scripts/export_tiles.py --scores results/water_scores.csv \
        --metadata data/image_metadata.csv \
        --recheck results/recheck_scores.csv \
        --out results/flood_tiles.geojson

Column names are matched loosely (case and separators are ignored), so
"after_id", "afterId" and "AFTER ID" all work. If a required column is missing
the script prints the columns it did find instead of guessing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    sys.exit("pandas is required:  pip install pandas")

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DATA = ROOT / "data"


# --------------------------------------------------------------- column lookup
def _norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def pick(df: pd.DataFrame, *candidates: str, required: bool = True, label: str = "") -> str | None:
    """Return the real column name matching any of `candidates`, loosely."""
    lookup = {_norm(c): c for c in df.columns}
    for cand in candidates:
        hit = lookup.get(_norm(cand))
        if hit is not None:
            return hit
    # substring fallback, e.g. "after_water_pct" inside "mean_after_water_pct"
    for cand in candidates:
        n = _norm(cand)
        for key, real in lookup.items():
            if n and n in key:
                return real
    if required:
        sys.exit(
            f"Could not find a column for {label or candidates[0]!r}.\n"
            f"Tried: {', '.join(candidates)}\n"
            f"Columns present: {', '.join(map(str, df.columns))}"
        )
    return None


def read_csv(path: Path, what: str) -> pd.DataFrame:
    if not path.exists():
        sys.exit(f"{what} not found at {path}\nPass its path with the matching --flag.")
    df = pd.read_csv(path)
    print(f"  {what}: {len(df)} rows from {path.relative_to(ROOT) if ROOT in path.parents else path}")
    return df


# --------------------------------------------------------------- build the table
def build_table(scores_path: Path, meta_path: Path) -> pd.DataFrame:
    """Join the per-tile water percentages onto the tile bounds."""
    print("Reading inputs...")
    scores = read_csv(scores_path, "scores")
    meta = read_csv(meta_path, "metadata")

    s_id = pick(scores, "after_id", "afterid", "tile_id", "id", label="after_id")
    s_after = pick(scores, "after_water_pct", "after_pct", "water_pct_after", "after", label="after_water_pct")
    s_before = pick(scores, "before_water_pct", "before_pct", "water_pct_before", "before",
                    required=False, label="before_water_pct")

    m_id = pick(meta, "after_id", "afterid", "tile_id", "id", label="after_id in metadata")
    m_n = pick(meta, "north", label="north")
    m_s = pick(meta, "south", label="south")
    m_e = pick(meta, "east", label="east")
    m_w = pick(meta, "west", label="west")
    m_lat = pick(meta, "latitude", "lat", required=False)
    m_lon = pick(meta, "longitude", "lon", "lng", required=False)
    m_loc = pick(meta, "locality", "city", "place", "area", required=False)

    # Rename to canonical names in each frame BEFORE merging, so the join does
    # not leave two id columns behind.
    keep_meta = [m_id, m_n, m_s, m_e, m_w] + [c for c in (m_lat, m_lon, m_loc) if c]
    meta_small = meta[keep_meta].drop_duplicates(subset=[m_id]).rename(columns={
        m_id: "after_id", m_n: "north", m_s: "south", m_e: "east", m_w: "west",
        **({m_lat: "lat"} if m_lat else {}),
        **({m_lon: "lon"} if m_lon else {}),
        **({m_loc: "locality"} if m_loc else {}),
    })

    keep_scores = [s_id, s_after] + ([s_before] if s_before else [])
    scores_small = scores[keep_scores].rename(columns={
        s_id: "after_id", s_after: "after_water_pct",
        **({s_before: "before_water_pct"} if s_before else {}),
    })

    table = meta_small.merge(scores_small, on="after_id", how="inner")

    if "before_water_pct" not in table.columns:
        table["before_water_pct"] = 0.0
    if "lat" not in table.columns:
        table["lat"] = (table["north"] + table["south"]) / 2
    if "lon" not in table.columns:
        table["lon"] = (table["east"] + table["west"]) / 2
    table["locality"] = table["locality"].fillna("Unknown") if "locality" in table.columns else "Unknown"

    table["new_flood_pct"] = (
        pd.to_numeric(table["after_water_pct"], errors="coerce")
        - pd.to_numeric(table["before_water_pct"], errors="coerce")
    ).clip(lower=0)
    table["rechecked"] = False
    print(f"  joined: {len(table)} tiles")
    return table


# --------------------------------------------------------------- recheck (D13)
def apply_recheck(table: pd.DataFrame, recheck_path: Path | None) -> pd.DataFrame:
    """Apply results/recheck_scores.csv: rows with a score replace after_water_pct.

    A blank score means the yes/no check said "no flooding here", so that tile
    keeps its original number and rechecked stays False.
    """
    if recheck_path is None or not recheck_path.exists():
        print(f"No recheck file at {recheck_path} - exporting first-pass scores only.")
        return table

    rc = read_csv(recheck_path, "recheck")
    r_id = pick(rc, "after_id", "afterid", "tile_id", "id", label="after_id in recheck")
    r_pct = pick(rc, "water_pct", "after_water_pct", "recheck_pct", "pct", label="water_pct in recheck")

    scores = pd.to_numeric(rc[r_pct], errors="coerce")
    applied = 0
    table = table.set_index("after_id")
    for tile_id, pct in zip(rc[r_id], scores):
        if pd.isna(pct) or tile_id not in table.index:
            continue  # blank score = the check said no
        before = pd.to_numeric(table.at[tile_id, "before_water_pct"], errors="coerce")
        before = 0.0 if pd.isna(before) else float(before)
        table.at[tile_id, "after_water_pct"] = float(pct)
        table.at[tile_id, "new_flood_pct"] = max(0.0, float(pct) - before)
        table.at[tile_id, "rechecked"] = True
        applied += 1
    table = table.reset_index()
    print(f"  recheck applied to {applied} tiles")
    return table


# --------------------------------------------------------------- export
def _num(v):
    """JSON-safe number: NaN becomes null, floats are rounded."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 2)


def export_tiles(table: pd.DataFrame, out_path: Path) -> int:
    features = []
    for row in table.itertuples(index=False):
        d = row._asdict()
        n, s = _num(d.get("north")), _num(d.get("south"))
        e, w = _num(d.get("east")), _num(d.get("west"))
        if None in (n, s, e, w):
            continue
        n, s = round(float(d["north"]), 6), round(float(d["south"]), 6)
        e, w = round(float(d["east"]), 6), round(float(d["west"]), 6)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[
                [w, s], [e, s], [e, n], [w, n], [w, s],   # closed ring, [lon, lat]
            ]]},
            "properties": {
                "after_id": str(d.get("after_id")),
                "locality": str(d.get("locality") or "Unknown"),
                "new_flood_pct": _num(d.get("new_flood_pct")),
                "before_water_pct": _num(d.get("before_water_pct")),
                "after_water_pct": _num(d.get("after_water_pct")),
                "rechecked": bool(d.get("rechecked")),
                "lat": round(float(d["lat"]), 6),
                "lon": round(float(d["lon"]), 6),
            },
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return len(features)


def main() -> None:
    ap = argparse.ArgumentParser(description="Export flood tiles for the app and the demo page.")
    ap.add_argument("--scores", type=Path, default=RESULTS / "water_scores.csv")
    ap.add_argument("--metadata", type=Path, default=DATA / "image_metadata.csv")
    ap.add_argument("--recheck", type=Path, default=RESULTS / "recheck_scores.csv")
    ap.add_argument("--out", type=Path, default=RESULTS / "flood_tiles.geojson")
    args = ap.parse_args()

    table = build_table(args.scores, args.metadata)
    table = apply_recheck(table, args.recheck)
    count = export_tiles(table, args.out)

    size_kb = args.out.stat().st_size / 1024
    scored = table["new_flood_pct"].notna().sum()
    rechecked = int(table["rechecked"].sum())
    blocked = int((pd.to_numeric(table["new_flood_pct"], errors="coerce") > 50).sum())
    print(f"\nWrote {count} tiles to {args.out}  ({size_kb:.0f} KB)")
    print(f"  {scored} scored, {rechecked} rechecked, {blocked} above the 50% block threshold")
    print("\nNow open docs/route_demo.html, click 'Load real scores' and pick that file.")


if __name__ == "__main__":
    main()
