# Demo run-sheet — Flood Safe Route

Target: 4:30 PM. Everything below runs from `docs/route_demo.html` with no server,
no GB10 and no internet. Rehearse it once.

## Before you start (2 minutes)

If the pipeline files are on this laptop, turn the sample data into your real scores:

```bash
python3 scripts/export_tiles.py
```

It writes `results/flood_tiles.geojson` and prints how many tiles were rechecked.
Then in the page: **Load real scores** → pick that file. The amber banner turns
green and the whole map redraws from Qwen's actual output.

If it doesn't run, **demo anyway**. The page works as-is; the banner tells the
truth about the numbers and nobody has to pretend otherwise.

Open the page and leave it open:

```bash
xdg-open docs/route_demo.html
```

## The demo (about 3 minutes)

**1. The problem.** *"During Harvey, navigation apps kept routing people into
water. Most flood deaths happen in vehicles."* Point at the map — the dark blue
is where our model found new floodwater.

**2. The data.** *"NOAA aerial photos, before and after, 575 tiles. Qwen3-VL-8B
running on the Dell GB10 estimated how much of each tile is under water."*

**3. The route.** Click **Showcase route**.
Expect: an orange route bending around a dark tile, with the dashed gray direct
route going straight through it. Read the card out loud: distance, time,
*"Avoided 1 heavily flooded area — Eldridge, 95%."*

**4. The failure, and the fix — this is the moment.** Click **Recheck pass: on**
to turn it **off**.
The route snaps back to the short line straight through the tile.
*"That's what our first pass would have told you to drive through. The model
scored this tile 0% — muddy brown floodwater over a field doesn't look like
water to it. So we added a second pass: ask yes/no 'is there water here' on
every 0% tile, then re-score the ones that say yes. That tile went from 0% to
95%. Held-out agreement went from 83% to 91%."*
Click it back **on**. The route bends around again.

**5. Honesty.** Point at the caution lines on the card: *"It still tells you how
much of your trip has no flood photos at all, and it says on the page that 4 of
11 tiles we hand-checked at 0% were actually flooded. We route on thresholds,
not on the exact percentages, because the percentages are still about 19 points
off."*

**6. No safe route.** Click **No safe route**.
*"And when every road out is underwater, it says so instead of inventing a path."*

**7. Close.** Scroll to **How we built it** — nine steps, the failure in red at
step 5. *"All of it runs locally on the GB10. No cloud, which matters when the
network is down."*

## If something goes wrong

| Problem | Do this |
|---|---|
| Page won't open | `cd` into the repo first — `xdg-open docs/route_demo.html` from home fails |
| Route doesn't appear | Press **Clear**, then **Showcase route** |
| Judge asks if the numbers are real | Say yes if the banner is green, no if it's amber. Don't hedge. |
| Judge asks about the live app | *"The routing rules on this page are the app's; it reads the same export and real OpenStreetMap roads."* |
| Asked why not Google Maps | *"It has no idea which roads are flooded. Nobody is driving these streets to report it."* |

## Questions worth pre-loading

- **"How accurate is it?"** 91% flooded-vs-dry agreement on held-out tiles, up
  from 83%. Percentages are loose, which is why 50% is a threshold not a number.
- **"Why a vision model and not a flood sensor?"** Sensors are sparse and go
  down. Aerial imagery exists for every disaster, and this runs offline.
- **"Could it run live?"** Yes — scoring a tile takes seconds on the GB10, so a
  fresh flight could be scored and routed on as it lands.
- **"What's the simulated street grid?"** Be straight: this page uses a grid so
  it runs with no network. The app uses real OpenStreetMap roads; the routing
  rules are identical.
