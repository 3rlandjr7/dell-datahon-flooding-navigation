# 🛡️ Flood Safe Route

**Find a safe path around flooded areas, powered by a vision LLM running locally on the Dell Pro Max GB10.**

During a flood, standard navigation apps still send drivers down streets that are underwater. Flood Safe Route looks at post-disaster aerial and satellite imagery, finds which roads are flooded, and plans a route that avoids them.

## How it works
1. **Ingest imagery:** Aerial and satellite tiles of the affected area (e.g., Houston, Hurricane Harvey 2017).
2. **Detect flooding:** Qwen3-VL (served with vLLM on the GB10) labels each tile and road segment as flooded or passable, with a confidence score.
3. **Build a hazard map:** Flooded segments are marked as blocked or heavily penalized in the road network.
4. **Route safely:** A shortest-path search finds a route from start to destination that avoids flooded roads, with distance and estimated time.
5. **Explain the route:** The LLM gives a plain-language summary of why the route was chosen and which areas to avoid.

## Why it matters
Most flood deaths happen in vehicles. Flood Safe Route gives residents, first responders and evacuation planners a fast, visual way to see which roads are still passable. It runs fully on local hardware, with no cloud connection needed when networks are down.

## Tech stack
- **Model:** Qwen3-VL-Instruct via vLLM (OpenAI-compatible API)
- **Hardware:** Dell Pro Max GB10 (NVIDIA DGX Spark)
- **Routing:** Python, OSMnx / NetworkX on OpenStreetMap road data
- **Interface:** Web map showing flood overlay, start/destination input and the safe route

## Built for
UTSA × Dell GB10 Datathon, November 2026
