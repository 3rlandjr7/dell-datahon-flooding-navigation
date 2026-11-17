"""Project settings. Change values here; environment variables override a few for one-off runs."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Model server: vLLM's OpenAI-compatible API, running on the Dell GB10 ---
VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "http://10.42.0.52:8000/v1")
VLM_MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "NONE")
VLM_TIMEOUT_S = 180
SCORING_WORKERS = 8  # requests sent to the server at once

# --- Dataset: downloaded into DATA_DIR, never committed ---
DATASET_REPO = "jennifer-fowler/UTSA-flood-images"
DATA_DIR = Path(os.environ.get("FLOOD_DATA_DIR", ROOT / "data" / "Texas_Flood_Student_Data"))

# --- Outputs: committed so results can be viewed without a GB10 ---
RESULTS_DIR = ROOT / "results"
SCORES_CSV = RESULTS_DIR / "water_scores.csv"
RECHECK_CSV = RESULTS_DIR / "recheck_scores.csv"
MAP_HTML = RESULTS_DIR / "flood_map.html"
LABELS_DIR = ROOT / "labels"

# --- Prompt: one image per call, answered with a bare number ---
# Checked by hand on nine pairs: this scored far better than comparing both images
# in one call or forcing JSON output. New floodwater = after-image % minus before-image %.
WATER_PROMPT = """This is an overhead aerial photo of a ~530 m square area in the Houston, Texas region.
Estimate what percent of the image is covered by water of any kind: rivers, ponds, reservoirs, or floodwater.
Floodwater from the air is usually flat, opaque, muddy brown, tan or grey-brown with no texture,
with tree crowns, rooftops and road edges sticking out of it.
Answer with a single integer from 0 to 100 and nothing else."""

# --- Recheck: for tiles where WATER_PROMPT found no new flood ---
# Muddy water filling the frame was being read as bare soil. Ask this yes/no question about
# the after-image; on "yes", ask WATER_PROMPT again with RECHECK_NOTE in front of it.
# Tested on hand labels: held-out flooded/dry agreement rose from 83% to 91%.
CHECK_PROMPT = """Is any of the ground in this overhead aerial photo covered by standing floodwater?
Floodwater can be brown, tan, grey or dark, and can fill the whole frame so that only trees,
roofs and road edges show. Bare soil, dirt fields and shadows are not water. Answer yes or no."""

RECHECK_NOTE = """This photo was taken just after Hurricane Harvey and contains standing floodwater.
Muddy water filling most of the frame is water, not bare soil.
"""

# --- Hand-label sets: one folder per labeller ---
LABEL_SETS = ["A", "B", "C"]
LABEL_TILES_PER_BAND = 12  # per model-score band, dealt evenly across LABEL_SETS
LABEL_SEED = 0
