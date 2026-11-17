"""Score Hurricane Harvey before/after image pairs for new floodwater with Qwen, and map the result."""
import base64
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import folium
import matplotlib.pyplot as plt
import pandas as pd
from branca.colormap import StepColormap
from huggingface_hub import snapshot_download
from openai import OpenAI
from PIL import Image

import config

# Map colours: sequential blue, light to dark. The lightest step clears 2:1 contrast
# on the Esri light-gray basemap.
FLOOD_BINS = [0, 10, 25, 50, 75, 100]
FLOOD_COLORS = ["#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
UNSCORED_COLOR = "#bdbdb9"

# Per-tile context carried along from the dataset for later analysis.
CONTEXT_COLUMNS = ["elevation_m", "terrain_slope_mean_degrees", "fema_flood_zones",
                   "preceding_7d_precipitation_mm", "nearest_high_water_mark_distance_km"]


def download_dataset():
    """Download the dataset into config.DATA_DIR: ~1.6 GB the first time, later calls only check for changes."""
    snapshot_download(config.DATASET_REPO, repo_type="dataset", local_dir=config.DATA_DIR)


def load_harvey_pairs():
    """Return one row per Harvey after-image with its before-image, footprint and context."""
    meta = pd.read_csv(config.DATA_DIR / "image_metadata.csv", low_memory=False)
    harvey = meta.loc[(meta["event_name"] == "Hurricane Harvey") & meta["paired_image_id"].notna()]
    after = harvey.loc[harvey["image_role"] == "response"]
    before_paths = harvey.set_index("image_id")["image_path"]
    pairs = after[["image_id", "paired_image_id", "locality", "acquisition_date",
                   "west", "south", "east", "north", "latitude", "longitude", *CONTEXT_COLUMNS]]
    pairs = pairs.rename(columns={"image_id": "after_id", "paired_image_id": "before_id"})
    pairs["after_path"] = [config.DATA_DIR / path for path in after["image_path"]]
    pairs["before_path"] = [config.DATA_DIR / before_paths[image_id] for image_id in pairs["before_id"]]
    return pairs.reset_index(drop=True)


def ask_image(path, client, prompt, max_tokens=5):
    """Send one aerial image and a prompt to Qwen; return its answer text."""
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, "JPEG", quality=90)
    url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    response = client.chat.completions.create(
        model=config.VLM_MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return (response.choices[0].message.content or "").strip()


def water_pct(path, client, prompt=None):
    """Ask Qwen what percent of one aerial image is water; the percent is None if no number comes back."""
    answer = ask_image(path, client, prompt or config.WATER_PROMPT)
    match = re.search(r"\d+", answer)
    return (min(int(match.group()), 100) if match else None), answer


def score_images(pairs, out_csv=None, prompt=None, workers=None):
    """Score every before and after image once, appending to out_csv (default config.SCORES_CSV).

    Rows are saved as they finish, so an interrupted run resumes where it stopped.
    Use a different out_csv when trying a new prompt so the main scores stay intact.
    """
    out_csv = Path(out_csv or config.SCORES_CSV)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    new_file = not out_csv.is_file()
    done = set() if new_file else set(pd.read_csv(out_csv)["image_id"])
    paths = dict(zip(pairs["before_id"], pairs["before_path"])) | dict(zip(pairs["after_id"], pairs["after_path"]))
    todo = {image_id: path for image_id, path in paths.items() if image_id not in done}
    print(f"{len(paths) - len(todo)} images already scored, {len(todo)} to go")
    if todo:
        with OpenAI(base_url=config.VLM_BASE_URL, api_key=config.VLM_API_KEY,
                    timeout=config.VLM_TIMEOUT_S, max_retries=2) as client, \
                open(out_csv, "a", newline="") as file, ThreadPoolExecutor(workers or config.SCORING_WORKERS) as pool:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(["image_id", "water_pct", "answer"])
            futures = {pool.submit(water_pct, path, client, prompt): image_id for image_id, path in todo.items()}
            for count, future in enumerate(as_completed(futures), 1):
                writer.writerow([futures[future], *future.result()])
                file.flush()
                if count % 100 == 0 or count == len(todo):
                    print(f"  {count}/{len(todo)} scored")
    return pd.read_csv(out_csv)


def recheck(path, client):
    """Ask whether an after-image holds standing floodwater; if yes, re-estimate its water percent."""
    check = ask_image(path, client, config.CHECK_PROMPT, max_tokens=3)
    if not check.lower().startswith("yes"):
        return check, None, ""
    return check, *water_pct(path, client, config.RECHECK_NOTE + config.WATER_PROMPT)


def recheck_no_flood(table, out_csv=None, workers=None):
    """Recheck every after-image in table with no new flood, appending to out_csv (default config.RECHECK_CSV).

    Like score_images, rows are saved as they finish and reruns skip tiles already rechecked.
    water_pct is blank where the yes/no check said no.
    """
    out_csv = Path(out_csv or config.RECHECK_CSV)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    new_file = not out_csv.is_file()
    done = set() if new_file else set(pd.read_csv(out_csv)["after_id"])
    todo = table.loc[(table["new_flood_pct"] == 0) & ~table["after_id"].isin(done)]
    print(f"{len(done)} tiles already rechecked, {len(todo)} to go")
    if len(todo):
        with OpenAI(base_url=config.VLM_BASE_URL, api_key=config.VLM_API_KEY,
                    timeout=config.VLM_TIMEOUT_S, max_retries=2) as client, \
                open(out_csv, "a", newline="") as file, ThreadPoolExecutor(workers or config.SCORING_WORKERS) as pool:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(["after_id", "check_answer", "water_pct", "answer"])
            futures = {pool.submit(recheck, path, client): after_id
                       for after_id, path in zip(todo["after_id"], todo["after_path"])}
            for future in as_completed(futures):
                writer.writerow([futures[future], *future.result()])
                file.flush()
    return pd.read_csv(out_csv)


def flood_table(pairs, scores, rechecks=None):
    """Add before/after water percent and new flood percent (after minus before, floored at 0).

    With rechecks (from recheck_no_flood), a re-estimated after-image percent replaces the first one.
    """
    water = scores.drop_duplicates("image_id", keep="last").set_index("image_id")["water_pct"]
    table = pairs.assign(before_water_pct=pairs["before_id"].map(water),
                         after_water_pct=pairs["after_id"].map(water), rechecked=False)
    if rechecks is not None:
        redone = rechecks.dropna(subset=["water_pct"]).drop_duplicates("after_id", keep="last")
        redone = redone.set_index("after_id")["water_pct"].astype(int)
        hit = table["after_id"].isin(redone.index)
        table.loc[hit, "after_water_pct"] = table.loc[hit, "after_id"].map(redone)
        table.loc[hit, "rechecked"] = True
    table["new_flood_pct"] = (table["after_water_pct"] - table["before_water_pct"]).clip(lower=0)
    return table


def flood_map(table):
    """Interactive map with each ~530 m tile coloured by its estimated new-flood percent."""
    colormap = StepColormap(FLOOD_COLORS, index=FLOOD_BINS, vmin=0, vmax=100, tick_labels=FLOOD_BINS,
                            caption="New floodwater after Harvey (% of tile, estimated by Qwen)")
    fmap = folium.Map(tiles=None, control_scale=True, zoom_snap=0.25)  # fractional zoom fits the tiles snugly
    folium.TileLayer("Esri.WorldGrayCanvas", name="Light gray").add_to(fmap)
    folium.TileLayer("Esri.WorldImagery", name="Satellite (current)", show=False).add_to(fmap)
    tiles = folium.FeatureGroup(name="Flood estimate").add_to(fmap)
    for row in table.itertuples():
        if pd.isna(row.new_flood_pct):
            fill, tooltip = UNSCORED_COLOR, f"{row.after_id}<br>Not scored"
        else:
            fill = colormap(row.new_flood_pct)
            tooltip = (f"<b>{row.locality}</b><br>New flood: {row.new_flood_pct:.0f}%<br>"
                       f"Water before → after: {row.before_water_pct:.0f}% → {row.after_water_pct:.0f}%<br>"
                       + ("After-image rechecked for missed floodwater<br>" if row.rechecked else "")
                       + f"{row.after_id}")
        folium.Rectangle(
            bounds=[[row.south, row.west], [row.north, row.east]],
            color="#ffffff", weight=0.5, fill=True, fill_color=fill, fill_opacity=0.9,
            tooltip=tooltip,
        ).add_to(tiles)
    colormap.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.fit_bounds([[table["south"].min(), table["west"].min()], [table["north"].max(), table["east"].max()]],
                    padding_top_left=(10, 150), padding_bottom_right=(10, 10))  # keep tiles clear of legend and layer control
    return fmap


def show_pair(tile):
    """Show one tile's before and after images side by side with Qwen's numbers."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.5))
    for ax, path, title in [(axes[0], tile["before_path"], f"Before · water {tile['before_water_pct']:.0f}%"),
                            (axes[1], tile["after_path"], f"After · water {tile['after_water_pct']:.0f}%")]:
        with Image.open(path) as image:
            ax.imshow(image)
        ax.set_title(title)
        ax.axis("off")
    fig.suptitle(f"{tile['after_id']} · {tile['locality']} · new flood {tile['new_flood_pct']:.0f}%")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    harvey_pairs = load_harvey_pairs()
    recheck_no_flood(flood_table(harvey_pairs, score_images(harvey_pairs)))
