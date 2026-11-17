# Demo run-sheet — Flood Safe Route

Everything below runs from `docs/index.html`. No GB10, and no internet except for
the basemap imagery. Rehearse it once.

## Before you start (1 minute)

Serve the repo and the page loads the real scores by itself:

```bash
python3 -m http.server 8000     # then open http://localhost:8000/docs/
```

Check the top banner reads **Real flood scores** in green before anyone is
watching. Opening `docs/index.html` straight off disk works too, but then you
have to click **Load flood scores** and pick `results/flood_tiles.geojson`
yourself. Either way the banner tells the truth about the numbers.

If you have run `scripts/fetch_roads.py`, the second banner turns green too and
the router is on real streets. If not, it says the streets are simulated —
which is the honest answer to give if anyone asks.

## The demo (about 3 minutes)

**1. The problem.** *"During Harvey, navigation apps kept routing people into
water. Most flood deaths happen in vehicles."* Point at the map — the dark blue
is where our model found new floodwater.

**2. The data.** *"NOAA aerial photos, before and after, 575 tiles. Qwen3-VL-8B
running on the Dell GB10 estimated how much of each tile is under water."*

**3. The route.** Click **Showcase route**.
Expect: an orange route bending around a dark tile, with the dashed gray direct
route going straight through it. Read the card out loud — distance, time, and the
*"Avoided N heavily flooded areas"* line with the locality and percentage.

The button picks the trip that best shows the recheck off in whatever scores are
loaded, so the exact distances and tile differ between the sample and the real
data. Click it once beforehand and note the numbers you'll be saying.

**4. The failure, and the fix — this is the moment.** Click **Recheck pass: on**
to turn it **off**.
The route snaps back to the short line straight through the tile. On the real
scores that's about a mile instead of six and a half.
*"That's what our first pass would have told you to drive through. The model
scored this tile 0% — muddy brown floodwater over a field doesn't look like
water to it. So we added a second pass: ask yes/no 'is there water here' on
every 0% tile, then re-score the ones that say yes. That tile went from 0% to
95%. Held-out agreement went from 83% to 91%."*
The tile it names is printed under the preset buttons, so you can read the id
and its percentage straight off the page.
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
| Page won't open | `cd` into the repo first — `xdg-open docs/index.html` from home fails |
| Basemap is blank | No internet. Everything else still works; say the basemap is the only thing that needs the network |
| Route doesn't appear | Press **Clear**, then **Showcase route** |
| Recheck toggle doesn't move the route | The hint under the presets says so outright when no rechecked tile changes a route in the loaded scores. Skip step 4 and talk through step 5 instead. |
| Judge asks if the numbers are real | Say yes if the banner is green, no if it's amber. Don't hedge. |
| Judge asks about the streets | Read the second banner. Green means real OpenStreetMap streets; amber means a simulated grid, and say so plainly. |
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
