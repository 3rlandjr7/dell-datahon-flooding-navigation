# Flood grading rules

The team's rules for judging new floodwater in a before/after pair. They define what
the hand labels mean, and each rule is added to Qwen's prompt (`WATER_PROMPT` in
`config.py`) once it has been tested.

## Definitions

- **New floodwater:** water in the AFTER image covering ground that is dry in the BEFORE
  image: grass, fields, yards, roads, parking lots, woods.
- **Existing water doesn't count:** rivers, ponds and reservoirs already in BEFORE are
  excluded. Only the extra area they spread into counts.
- **`new_flood_pct`:** percent of the tile that is new floodwater, which is water in AFTER
  minus water in BEFORE. Example: BEFORE 20% water, AFTER 45%, so 25.
- **`flood_visible`:** `yes`, `no` or `uncertain`. If `no`, `new_flood_pct` is 0.

## Rules

| # | Rule | Hand labels | Qwen prompt |
|---|---|---|---|
| 1 | **Green before, flat brown after = floodwater, not dirt.** Ground cover doesn't change that much in a year. Exception: plowed fields and construction sites are brown too, but show texture (furrows, tire tracks, piles); floodwater is flat and smooth, with things sticking out of it. | In use | Tested, not adopted: needs both photos in one call, and Qwen then read the camera colour change as "green turned brown" (mean error +19.8 points on sets A + D) |
| 2 | **Ground under trees and buildings counts as flooded when water surrounds them.** The water just didn't reach the treetops or roof. | In use | Tested, not adopted: no gain over the recheck alone (mean absolute error 12.6 vs 11.5 on sets A + D) |

What did go into the prompt is a recheck for missed floodwater; see `CHECK_PROMPT` and
`RECHECK_NOTE` in `config.py`. Full results are in the README.

## Adding a rule

1. Agree on the wording and add it to the table above.
2. If it changes what a label means, update `labels/README.md` and recheck affected labels.
3. Add it as a version in `experiments/prompt_experiments.py` and compare on the
   development sets: `python -m experiments.prompt_experiments set_A,set_D`.
4. If it helps there, measure it once on sets B and C (held out), then move the prompt
   into `config.py`, rescore the whole dataset and rebuild the map.
