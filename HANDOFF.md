# Flood Safe Route — what's in this repo

Handoff note for planning how to merge the scoring pipeline into this repo.
Written 2026-11-17. Uncommitted scratch file — delete it whenever.

## Repo state

`github.com/3rlandjr7/dell-datahon-flooding-navigation`, branch `main`
(also on `claude/focused-cray-ns36lr`, identical). Four files, ~1500 lines:

| File | What it is |
|---|---|
| `docs/route_demo.html` | Standalone demo page, 52 KB, no dependencies |
| `scripts/export_tiles.py` | CSVs → `results/flood_tiles.geojson` |
| `docs/DEMO_SCRIPT.md` | 3-minute pitch sequence |
| `README.md` | Project overview + "Try the demo" section |

**Nothing from the scoring pipeline is here.** No `config.py`, `flood_heatmap.py`,
`labeling.py`, notebook, `experiments/`, `data/` or `results/`. The repo has never
contained them — `git log --all --name-only` shows only these four files plus the
README. That is the gap this merge has to close.

## 1. `docs/route_demo.html` — the demo page

One self-contained file. Open by double-clicking: no server, no Python, no
internet, no GB10. Inline SVG, no CDN, no external requests at all (verified with
network blocked in a headless browser).

What it does:

- Draws flood tiles over the real `ROAD_BBOX`, sequential blue, 7-entry legend
- Routes between two points on a **simulated street grid** (not OpenStreetMap)
- Toggles first-pass vs recheck scores, which visibly redraws the map and reroutes
- Result card: distance, time, areas avoided, caution warnings, unphotographed share
- Nine-step "How we built it" story
- Dark mode toggle; keyboard-operable throughout; WCAG AA contrast in both themes

**The flood numbers in it are sample data I generated, not Qwen output**, and an
amber banner on the page says so. A **"Load real scores"** file input reads a real
`results/flood_tiles.geojson` via `FileReader` — works from `file://`, no server —
and the banner turns green. That is the designed seam between this page and the
pipeline: the page never needs the dataset, the model, or any Python.

Routing rules implemented in the page, matching the ticket contracts:

```
blocked   pct > 50            → edge removed from the graph
caution   25 <= pct <= 50     → cost = length * (1 + 5)
caution   pct is null         → same (never-scored is treated as risky)
clear     pct < 25            → cost = length
none      no tile covers it   → cost = length, counts toward uncovered_m
```

An edge takes the **worst** class among its two end nodes and its midpoint.
Duration = distance / 40 km/h. Safe route = Dijkstra on `cost`; baseline =
Dijkstra on `length` over the full graph, so the card can show what was avoided.

## 2. `scripts/export_tiles.py` — the integration point

Standalone. Imports only pandas; **imports nothing from the project**, so it runs
whether or not `config.py` and `flood_heatmap.py` exist yet.

```bash
python3 scripts/export_tiles.py
# or: --scores … --metadata … --recheck … --out …
```

Reads `results/water_scores.csv`, `data/image_metadata.csv`,
`results/recheck_scores.csv` → writes `results/flood_tiles.geojson`.

- Column names matched loosely (`after_id`, `After ID`, `tile_id` all work); on a
  miss it prints the columns it found rather than guessing
- Applies the recheck per D13: rows with a score replace `after_water_pct` and set
  `rechecked: true`; blank scores (the yes/no check said no) change nothing
- `new_flood_pct = after - before`, clipped at 0; NaN → JSON `null`; coords to 6 dp

Tested against synthetic fixtures covering scored-yes / no / blank-yes /
clip-at-zero, odd column names, a missing recheck file, and a missing required
column. Output round-trips into the demo page.

**This script is a stopgap.** If the pipeline already has `flood_table()` and a
recheck step, the better end state is ticket E1's `apply_recheck()` /
`export_tiles()` living in `flood_heatmap.py`, with this script deleted or reduced
to a thin CLI over them. Worth deciding during the merge.

### The data contract both sides agree on

`results/flood_tiles.geojson` — a FeatureCollection, one Feature per tile:

- `geometry`: Polygon, closed 5-point ring from `west/south/east/north`, `[lon, lat]`
- `properties`: `after_id`, `locality`, `new_flood_pct` (0–100 or null),
  `before_water_pct`, `after_water_pct`, `rechecked` (bool), `lat`, `lon`

The page filters to `ROAD_BBOX` on load, so a file with all 575 tiles is fine.

## 3. What was never built

The `saferoute/` Flask app from the ticket plan — tickets 0, 5.0–5.5, 6.1–6.3.
No `app.py`, no API endpoints, no `tests/`, no `pyproject.toml`, no
`requirements.txt`. We ran out of clock and chose the standalone page (D16)
instead, because it was the one thing that could be finished and verified.

So there is **no Flask server, no live geocoding, no OSM road graph and no model
call** anywhere in this repo. The demo page fakes the street grid and uses the
ticket 6.1 fallback template instead of asking the model.

## 4. Constraints to plan around

- The cloud session this was built in **cannot reach Nominatim or Overpass**
  (both 403 at the proxy) and cannot reach the GB10 at `10.42.0.52` (LAN address).
  So geocoding and the OSM download can only be mock-tested there; the real
  download has to happen once on a laptop with internet.
- `data/` (1.6 GB) and `road_graph.graphml` must stay out of git — `.gitignore`
  them before the pipeline push, or the push will be enormous.
- `results/flood_tiles.geojson` **should** be committed; it's small and it's what
  the page loads.
- D14 is still open: the pipeline's `config.py` and `README.md` predate the
  recheck, and `flood_map.html` shows pre-recheck scores.
- The page's colour bins are my own 6-bin blue scale with a `TODO` to reconcile
  with `flood_heatmap.FLOOD_COLORS` once that file exists, so the app, the Folium
  map and this page agree.

## 5. Merge questions worth answering

1. Does `apply_recheck` already exist in the pipeline? If so, `export_tiles.py`
   should call it rather than reimplementing it.
2. Do the real column names match what the script expects? Loose matching covers
   a lot, but `water_scores.csv`'s actual schema is unverified.
3. Is the `saferoute/` Flask app still wanted, or is the standalone page the
   product now? That decides whether tickets 0 and 5.x–6.x get built at all.
4. Where does `FLOOD_COLORS` live as the single source of truth?
5. Does the pipeline push go to `main` directly, or through a branch?
