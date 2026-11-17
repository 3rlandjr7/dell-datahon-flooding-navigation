"""Compare prompt versions against the hand labels.

Run from the repository root:

    python -m experiments.prompt_experiments set_A,set_D           # development sets
    python -m experiments.prompt_experiments set_B,set_C Baseline  # chosen versions only

Every Qwen answer is cached in experiments/answers.json, so reruns reproduce the comparison
without calling the model. "Baseline" reads results/water_scores.csv. The adopted prompts
live in config.py; the alternatives below were tried and not adopted.
"""
import base64
import io
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from openai import OpenAI
from PIL import Image

import config
from flood_heatmap import flood_table, load_harvey_pairs
from labeling import compare_with_model, load_labels

CACHE_FILE = Path(__file__).resolve().parent / "answers.json"

# Rule 2 added to the one-photo prompt.
PROMPT_RULE2 = """This is an overhead aerial photo of a ~530 m square area in the Houston, Texas region.
Estimate what percent of the image is covered by water of any kind: rivers, ponds, reservoirs, or floodwater.
Floodwater from the air is usually flat, opaque, muddy brown, tan or grey-brown with no texture,
with tree crowns, rooftops and road edges sticking out of it.
Where floodwater surrounds trees or buildings, count the ground under them as water too:
the water just doesn't reach the treetops or roofs.
Answer with a single integer from 0 to 100 and nothing else."""

# A gentler note for the re-estimate step.
RECHECK_NOTE_SOFT = """This photo was taken just after Hurricane Harvey, and some of the ground in it is covered by
standing floodwater. Muddy brown or tan floodwater can look like bare soil; count it as water.
Estimate only the area that is actually covered.
"""

# Both photos in one call, with the team's rules 1 and 2.
TWO_PHOTO_INTRO = """Image A is an overhead aerial photo of a ~530 m square area near Houston, Texas, on a normal day in 2016.
Image B is the same area photographed from the air just after Hurricane Harvey in 2017.
The cameras differ, so overall colour and brightness differ between the two; ignore that.
"""
TWO_PHOTO_RULES = """Follow these rules:
1. Ground that is green in A (grass, fields, lawns, clearings) but flat, smooth brown, tan or grey
   in B is floodwater, not dirt. Land cover does not change that much in a year. Plowed fields and
   construction sites are brown too, but they show texture such as furrows, tire tracks or piles.
2. Where floodwater surrounds trees or buildings in B, count the ground under them as flooded too:
   the water just doesn't reach the treetops or roofs.
3. Rivers, ponds and lakes already visible in A are not new floodwater. Only the extra area they
   spread into counts.
"""
TWO_PHOTO_PCT = (TWO_PHOTO_INTRO + "\nEstimate what percent of the area is covered by NEW floodwater in image B, "
                 "meaning water in B where A shows dry ground. " + TWO_PHOTO_RULES
                 + "\nAnswer with a single integer from 0 to 100 and nothing else.")
TWO_PHOTO_YES_NO = (TWO_PHOTO_INTRO + "\nIs there any NEW floodwater in image B, meaning water in B where A "
                    "shows dry ground? " + TWO_PHOTO_RULES + "\nAnswer yes or no.")

cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.is_file() else {}
cache_lock = threading.Lock()
client = OpenAI(base_url=config.VLM_BASE_URL, api_key=config.VLM_API_KEY, timeout=config.VLM_TIMEOUT_S)


def data_url(path):
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def ask(key, content, max_tokens=5):
    """One Qwen call, cached under key (question kind | image id)."""
    with cache_lock:
        if key in cache:
            return cache[key]
    response = client.chat.completions.create(model=config.VLM_MODEL, temperature=0, max_tokens=max_tokens,
                                              messages=[{"role": "user", "content": content}])
    answer = (response.choices[0].message.content or "").strip()
    with cache_lock:
        cache[key] = answer
    return answer


def ask_one_photo(kind, image_id, path, prompt):
    return ask(f"{kind}|{image_id}", [{"type": "image_url", "image_url": {"url": data_url(path)}},
                                      {"type": "text", "text": prompt}])


def ask_two_photo(kind, row, prompt):
    return ask(f"{kind}|{row['after_id']}", [
        {"type": "text", "text": "Image A (2016, before):"},
        {"type": "image_url", "image_url": {"url": data_url(row["before_path"])}},
        {"type": "text", "text": "Image B (2017, just after Hurricane Harvey):"},
        {"type": "image_url", "image_url": {"url": data_url(row["after_path"])}},
        {"type": "text", "text": prompt}])


def pct(answer):
    match = re.search(r"\d+", answer)
    return min(int(match.group()), 100) if match else None


def run_all(jobs):
    with ThreadPoolExecutor(config.SCORING_WORKERS) as pool:
        return list(pool.map(lambda job: job(), jobs))


def one_photo_version(pairs, kind, prompt):
    """Score both images of every pair with prompt; new flood = after minus before."""
    images = list(zip(pairs["before_id"], pairs["before_path"])) + list(zip(pairs["after_id"], pairs["after_path"]))
    answers = run_all([lambda i=i, p=p: ask_one_photo(kind, i, p, prompt) for i, p in images])
    return flood_table(pairs, pd.DataFrame({"image_id": [i for i, _ in images], "water_pct": list(map(pct, answers))}))


def two_photo_version(pairs):
    """Ask for the new-flood percent directly, showing both images."""
    answers = run_all([lambda r=r: ask_two_photo("2p_pct", r, TWO_PHOTO_PCT) for _, r in pairs.iterrows()])
    return pairs.assign(before_water_pct=float("nan"), after_water_pct=float("nan"), new_flood_pct=list(map(pct, answers)))


def recheck_version(table, base_prompt, note=config.RECHECK_NOTE, two_photo_check=False):
    """Where no new flood was found, ask yes/no; on yes, re-estimate the after-image with note in front."""
    table = table.copy()
    rows = [row for _, row in table.loc[table["new_flood_pct"] == 0].iterrows()]
    if two_photo_check:
        answers = run_all([lambda r=r: ask_two_photo("2p_yesno", r, TWO_PHOTO_YES_NO) for r in rows])
    else:
        answers = run_all([lambda r=r: ask_one_photo("check", r["after_id"], r["after_path"], config.CHECK_PROMPT)
                           for r in rows])
    flagged = [r for r, answer in zip(rows, answers) if answer.lower().startswith("yes")]
    kind = "present_" + ("rule2" if base_prompt == PROMPT_RULE2 else "base") + ("_soft" if note != config.RECHECK_NOTE else "")
    redone = run_all([lambda r=r: pct(ask_one_photo(kind, r["after_id"], r["after_path"], note + base_prompt))
                      for r in flagged])
    for row, value in zip(flagged, redone):
        table.loc[table["after_id"] == row["after_id"], "after_water_pct"] = value
    table["new_flood_pct"] = (table["after_water_pct"] - table["before_water_pct"]).clip(lower=0)
    return table


def versions(pairs):
    """Every version tried, by name. Built lazily so only the requested ones call the model."""
    baseline = flood_table(pairs, pd.read_csv(config.SCORES_CSV))
    rule2 = lambda: one_photo_version(pairs, "rule2", PROMPT_RULE2)
    return {
        "Baseline": lambda: baseline,
        "Check": lambda: recheck_version(baseline, config.WATER_PROMPT),
        "Check (soft note)": lambda: recheck_version(baseline, config.WATER_PROMPT, RECHECK_NOTE_SOFT),
        "Rule 2": rule2,
        "Rule 2 + check": lambda: recheck_version(rule2(), PROMPT_RULE2),
        "Two photo": lambda: two_photo_version(pairs),
        "Two-photo tiebreak": lambda: recheck_version(baseline, config.WATER_PROMPT, two_photo_check=True),
    }


def main(sets, names=None):
    labels = load_labels()
    labels = labels.loc[labels["label_set"].isin(sets)]
    pairs = load_harvey_pairs()
    pairs = pairs.loc[pairs["after_id"].isin(labels["after_id"])].reset_index(drop=True)
    tables = {name: build() for name, build in versions(pairs).items() if names is None or name in names}
    CACHE_FILE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    for group in [sets] + ([[s] for s in sets] if len(sets) > 1 else []):
        subset = labels.loc[labels["label_set"].isin(group)]
        summary = pd.DataFrame({name: compare_with_model(subset, table)[1] for name, table in tables.items()})
        print(f"\n=== {' + '.join(group)}")
        print(summary.to_string())


if __name__ == "__main__":
    main(sys.argv[1].split(","), sys.argv[2].split(",") if len(sys.argv) > 2 else None)
