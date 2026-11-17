# Hand labels for the flood map

20 tiles for checking Qwen's flood estimates. Each picture in `images/` shows
one ~530 m tile: BEFORE (2016) on the left, AFTER Hurricane Harvey (2017) on
the right. Fill in that picture's row in `labels.csv` (`label_no` matches the
number at the start of the file name).

## Columns to fill in

| Column | What to enter |
|---|---|
| `flood_visible` | `yes`, `no` or `uncertain`: is there floodwater in AFTER where BEFORE was dry ground? |
| `new_flood_pct` | Rough percent of the tile covered by **new** floodwater, 0–100: water in AFTER minus water in BEFORE. Example: BEFORE is 20% water (a river), AFTER is 45% water, so enter 25. Each grid square is 4%, so you can count water squares in each photo and multiply the difference by 4. Nearest 10 is fine. Leave blank if you can't tell. If `flood_visible` is `no`, enter 0. |
| `notes` | Optional: cloud, haze, shadow, dark image, unsure why, etc. |

Leave `label_no`, `image_file` and `after_id` as they are.

## What counts as new floodwater

- Water in AFTER covering ground that is dry in BEFORE: grass, fields, yards, roads, parking lots, woods.
- Rivers, ponds and reservoirs already in BEFORE don't count. Only the extra area they spread into does.
- **Green before, flat brown after = floodwater.** Ground cover doesn't change that much in a year. Exception: bare plowed fields and construction sites are brown too, but they show texture (furrows, tire tracks, piles of material); floodwater is flat and smooth, with things sticking out of it.
- **Count ground under trees and buildings as flooded when water surrounds them.** If the ground all around a stand of trees or a building is under water, the ground beneath them is too; the water just didn't reach the treetops or roof. Include that area in `new_flood_pct`.
- Floodwater is often flat brown or tan, but can also be grey or dark, and can fill the whole frame with only trees and roofs showing.
- The two cameras render colour differently, so judge by what is covered, not by colour alone.
- Prefer `uncertain` to a guess.

## Keep it blind

The model's scores are deliberately left out of these pictures and this file.
Don't look a tile up on the map until you've labelled it.

## Editing

Open `labels.csv` in LibreOffice Calc or a text editor. Save it as CSV with
the same name, and don't add, remove or reorder columns or rows.
