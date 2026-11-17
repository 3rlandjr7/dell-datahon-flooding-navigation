"""Make blind hand-labelling sheets, and compare the filled-in labels with Qwen's scores."""
import shutil
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

import config

# Bands of the model's new-flood score that label tiles are drawn from.
SCORE_BANDS = [-1, 0, 25, 50, 75, 100]
BAND_LABELS = ["0", "1-25", "26-50", "51-75", "76-100"]
GRID = 5  # grid squares per side on label pictures, so each square is 4% of a tile
TILE_PX = 1024


def side_by_side(before_path, after_path, number):
    """Before and after images side by side, each under a light grid for estimating area."""
    gap, header = 16, 44
    sheet = Image.new("RGB", (2 * TILE_PX + gap, TILE_PX + header), "white")
    draw = ImageDraw.Draw(sheet)
    for column, (path, title) in enumerate([(before_path, "BEFORE (2016)"), (after_path, "AFTER (2017)")]):
        x = column * (TILE_PX + gap)
        tile = Image.open(path).convert("RGBA").resize((TILE_PX, TILE_PX))
        lines = Image.new("RGBA", tile.size)
        line_draw = ImageDraw.Draw(lines)
        for k in range(1, GRID):
            offset = k * TILE_PX // GRID
            line_draw.line([(offset, 0), (offset, TILE_PX)], fill=(255, 255, 255, 150), width=2)
            line_draw.line([(0, offset), (TILE_PX, offset)], fill=(255, 255, 255, 150), width=2)
        sheet.paste(Image.alpha_composite(tile, lines).convert("RGB"), (x, header))
        draw.text((x + 8, 8), f"#{number}  {title}", fill="black", font_size=26)
    return sheet


def make_labeling_sets(table, folder=None):
    """Save blind before/after pictures and blank labels.csv files, one folder per labeller.

    Picks config.LABEL_TILES_PER_BAND tiles from each SCORE_BANDS band and deals them evenly
    into set_A, set_B, ... (config.LABEL_SETS). Each set is shuffled, numbered uniquely across
    sets, and given a copy of folder/README.md. No model scores appear in the pictures or CSVs.
    Refuses to overwrite existing labels.
    """
    folder = Path(folder or config.LABELS_DIR)
    if any(folder.glob("set_*/labels.csv")):
        raise FileExistsError(f"Labels already exist under {folder}; move them aside to make new sets.")
    sets, seed = config.LABEL_SETS, config.LABEL_SEED
    bands = pd.cut(table["new_flood_pct"], SCORE_BANDS)
    picks = []
    for _, band in table.groupby(bands, observed=True):
        band = band.sample(min(config.LABEL_TILES_PER_BAND, len(band)), random_state=seed)
        picks.append(band.assign(label_set=[sets[k % len(sets)] for k in range(len(band))]))
    picks = pd.concat(picks).sample(frac=1, random_state=seed).sort_values("label_set", kind="stable")
    number = 0
    for label_set, members in picks.groupby("label_set"):
        _write_set(folder, label_set, members, first_number=number + 1)
        number += len(members)
    return picks


def make_extra_set(table, name, tiles_per_band, folder=None):
    """Add one more blind label set, e.g. a development set aimed at the model's weak spots.

    tiles_per_band maps BAND_LABELS to counts, e.g. {"0": 10, "1-25": 5}. Tiles already in
    another set are skipped, and numbering continues after the highest existing label_no.
    """
    folder = Path(folder or config.LABELS_DIR)
    if (folder / f"set_{name}" / "labels.csv").exists():
        raise FileExistsError(f"set_{name} already has labels; pick another name.")
    existing = pd.concat([pd.read_csv(path, usecols=["label_no", "after_id"])
                          for path in folder.glob("set_*/labels.csv")])
    bands = pd.cut(table["new_flood_pct"], SCORE_BANDS, labels=BAND_LABELS)
    unused = table.loc[~table["after_id"].isin(existing["after_id"])]
    picks = pd.concat([unused.loc[bands[unused.index] == band].sample(count, random_state=config.LABEL_SEED)
                       for band, count in tiles_per_band.items()])
    picks = picks.sample(frac=1, random_state=config.LABEL_SEED)
    _write_set(folder, name, picks, first_number=existing["label_no"].max() + 1)
    return picks


def _write_set(folder, name, members, first_number):
    """Write one set_<name> folder: numbered pictures, a blank labels.csv and a README copy."""
    set_folder = folder / f"set_{name}"
    (set_folder / "images").mkdir(parents=True, exist_ok=True)
    if (folder / "README.md").is_file():
        shutil.copy(folder / "README.md", set_folder / "README.md")
    rows = []
    for number, tile in enumerate(members.itertuples(), first_number):
        image_file = f"{number:02d}_{tile.after_id}.jpg"
        side_by_side(tile.before_path, tile.after_path, number).save(set_folder / "images" / image_file, quality=90)
        rows.append({"label_no": number, "image_file": image_file, "after_id": tile.after_id,
                     "flood_visible": "", "new_flood_pct": "", "notes": ""})
    pd.DataFrame(rows).to_csv(set_folder / "labels.csv", index=False)


def load_labels(folder=None):
    """Read every set_*/labels.csv and keep the rows someone has filled in."""
    folder = Path(folder or config.LABELS_DIR)
    paths = sorted(folder.glob("set_*/labels.csv"))
    if not paths:
        raise FileNotFoundError(f"No set_*/labels.csv files under {folder}")
    labels = pd.concat([pd.read_csv(path, dtype=str, keep_default_na=False).assign(label_set=path.parent.name)
                        for path in paths], ignore_index=True)
    labels["flood_visible"] = labels["flood_visible"].str.strip().str.lower()
    labels["new_flood_pct"] = pd.to_numeric(labels["new_flood_pct"], errors="coerce")
    return labels.loc[(labels["flood_visible"] != "") | labels["new_flood_pct"].notna()].reset_index(drop=True)


def compare_with_model(labels, table, flooded_above=0):
    """Join hand labels to Qwen's scores and summarise how well they agree.

    Qwen counts a tile as flooded when its new_flood_pct is above flooded_above.
    error = Qwen minus human, in percentage points, so a positive mean means Qwen reads high.
    """
    model = table[["after_id", "locality", "before_water_pct", "after_water_pct", "new_flood_pct"]]
    both = labels.merge(model.rename(columns={"new_flood_pct": "model_new_flood_pct"}), on="after_id", how="left")
    both["error"] = both["model_new_flood_pct"] - both["new_flood_pct"]
    decided = both.loc[both["flood_visible"].isin(["yes", "no"])]
    agree = (decided["flood_visible"].eq("yes") == decided["model_new_flood_pct"].gt(flooded_above)).mean()
    numeric = both.dropna(subset=["new_flood_pct", "model_new_flood_pct"])
    summary = pd.Series({
        "tiles labelled": len(both),
        "flooded/dry agreement": f"{agree:.0%} of {len(decided)} tiles",
        "mean absolute error (points)": round(numeric["error"].abs().mean(), 1),
        "mean error (points, + = Qwen reads high)": round(numeric["error"].mean(), 1),
    })
    return both, summary
