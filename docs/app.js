"use strict";
/* Flood Safe Route - routing on AI-estimated flood tiles, drawn on a real map.

   The routing rules here are the project's own, from config.py and the README:
   block above 50% new floodwater, caution 25-50% and unscored, caution costs
   six times its length, and an edge takes the worst class of the tiles touching
   either end or its midpoint. */

/* ============================================================ constants
   Mirrors the "Safe route" settings in config.py. */
const BBOX = { n: 29.8597, s: 29.7262, e: -95.5811, w: -95.7349 };
const BLOCK_ABOVE_PCT    = 50;
const CAUTION_PCT        = 25;
const CAUTION_MULTIPLIER = 5;
const AVG_SPEED_KMH      = 40;

/* Taken verbatim from flood_heatmap.py so this page, the Folium map and any
   future app shade a tile identically. Note flood_heatmap.FLOOD_BINS is the six
   bin EDGES [0,10,25,50,75,100]; FLOOD_BINS here is the four interior
   thresholds between them. Same boundaries, one representation apart - convert
   with EDGES.slice(1, -1), never paste the edges in. */
const FLOOD_BINS     = [10, 25, 50, 75];
const FLOOD_COLORS   = ["#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const UNSCORED_COLOR = "#bdbdb9";

const M_PER_DEG_LAT = 111320;
const COS_LAT = Math.cos(29.79 * Math.PI / 180);

/* ============================================================ helpers */
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function metres(aLat, aLon, bLat, bLon) {
  const dy = (aLat - bLat) * M_PER_DEG_LAT;
  const dx = (aLon - bLon) * M_PER_DEG_LAT * COS_LAT;
  return Math.hypot(dx, dy);
}
const miles = m => m / 1609.344;
const fmtLatLon = p => p.lat.toFixed(4) + ", " + p.lon.toFixed(4);
const inBox = p => p.lat <= BBOX.n && p.lat >= BBOX.s && p.lon >= BBOX.w && p.lon <= BBOX.e;

/* Tile ids and localities come out of a GeoJSON file the viewer picks, and they
   end up in innerHTML, so escape them rather than trusting the file. */
function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g,
    ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

/* The rule from the README: null (never scored) is caution, not clear. */
function classify(pct) {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return "caution";
  if (pct > BLOCK_ABOVE_PCT) return "blocked";
  if (pct >= CAUTION_PCT) return "caution";
  return "clear";
}
const CLASS_RANK = { blocked: 3, caution: 2, clear: 1, none: 0 };

function fillFor(pct) {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return UNSCORED_COLOR;
  for (let i = 0; i < FLOOD_BINS.length; i++) if (pct < FLOOD_BINS[i]) return FLOOD_COLORS[i];
  return FLOOD_COLORS[FLOOD_COLORS.length - 1];
}

/* ============================================================ sample tiles
   Generated, NOT model output, and the banner says so. Shaped exactly like
   results/flood_tiles.geojson so the real file is a drop-in replacement. */
const TILE_ROWS = 15, TILE_COLS = 18;
const D_LAT = (BBOX.n - BBOX.s) / TILE_ROWS;
const D_LON = (BBOX.e - BBOX.w) / TILE_COLS;

function buildSampleTiles() {
  const rnd = mulberry32(20170829);
  const centres = [
    { lat: 29.8210, lon: -95.6450, peak: 96, scale: 0.0260 },
    { lat: 29.7560, lon: -95.6560, peak: 94, scale: 0.0280 },
    { lat: 29.7650, lon: -95.6000, peak: 72, scale: 0.0180 },
    { lat: 29.8430, lon: -95.6900, peak: 66, scale: 0.0150 },
  ];
  const locality = (lat, lon) => {
    if (lat > 29.832) return lon < -95.665 ? "Bear Creek" : "Jersey Village";
    if (lat > 29.795) return lon < -95.660 ? "Addicks Reservoir" : "Eldridge";
    if (lat > 29.762) return lon < -95.655 ? "Barker Reservoir" : "Buffalo Bayou";
    return lon < -95.655 ? "Cinco Ranch" : "Briar Forest";
  };
  const tiles = [];
  let seq = 27200;
  for (let r = 0; r < TILE_ROWS; r++) {
    for (let c = 0; c < TILE_COLS; c++) {
      const north = BBOX.n - r * D_LAT, south = north - D_LAT;
      const west = BBOX.w + c * D_LON, east = west + D_LON;
      const lat = (north + south) / 2, lon = (west + east) / 2;
      seq += 1;
      if (rnd() < 0.07) continue;                       /* never photographed */
      let field = 0;
      for (const ce of centres) {
        const d = Math.hypot(lat - ce.lat, (lon - ce.lon) * COS_LAT);
        field = Math.max(field, ce.peak * Math.exp(-Math.pow(d / ce.scale, 2)));
      }
      field = Math.max(0, Math.min(100, field + (rnd() - 0.5) * 16));
      let pct = Math.round(field);
      if (rnd() < 0.035) pct = null;                    /* photographed, never scored */
      const before = pct === null ? null : Math.round(rnd() * 8);
      tiles.push({
        after_id: "SAMPLE_" + seq, locality: locality(lat, lon),
        new_flood_pct: pct, before_water_pct: before,
        after_water_pct: pct === null ? null : Math.min(100, before + pct),
        rechecked: false,
        lat: +lat.toFixed(6), lon: +lon.toFixed(6),
        north, south, east, west,
      });
    }
  }
  /* The recheck rescored 39 tiles in the real run; mirror that here so the
     toggle has something to move. Only 0% tiles were ever rechecked, which is
     why shownPct() can reconstruct the first pass by zeroing them. */
  const rnd2 = mulberry32(39390);
  const pool = tiles.filter(t => t.new_flood_pct !== null && t.new_flood_pct < 18)
                    .sort((a, b) => (a.after_id < b.after_id ? -1 : 1));
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rnd2() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  for (let k = 0; k < 39 && k < pool.length; k++) {
    const t = pool[k];
    t.rechecked = true;
    t.new_flood_pct = rnd2() < 0.6 ? 55 + Math.round(rnd2() * 40) : 28 + Math.round(rnd2() * 20);
    t.after_water_pct = Math.min(100, (t.before_water_pct || 0) + t.new_flood_pct);
  }
  return tiles;
}

/* ============================================================ state */
let TILES = buildSampleTiles();
let REAL_TILES = false, REAL_ROADS = false;
let recheckOn = true, showBaseline = false;
let start = null, end = null, result = null;
let clickTurn = 0;
let showcaseCache = null;

/* With the recheck off, every rechecked tile falls back to the 0% the first
   pass gave it - only 0% tiles were ever rechecked. */
const shownPct = t => (recheckOn ? t.new_flood_pct : (t.rechecked ? 0 : t.new_flood_pct));

/* ============================================================ tile index */
let tileGrid = new Map();
function indexTiles() {
  tileGrid = new Map();
  for (const t of TILES) {
    const r = Math.floor((BBOX.n - t.lat) / D_LAT), c = Math.floor((t.lon - BBOX.w) / D_LON);
    const k = r + "," + c;
    if (!tileGrid.has(k)) tileGrid.set(k, []);
    tileGrid.get(k).push(t);
  }
}
/* Bounds are inclusive, so a point on a shared edge is inside both tiles and
   takes the worse of the two. */
function tilesAt(lat, lon) {
  const rf = Math.floor((BBOX.n - lat) / D_LAT), cf = Math.floor((lon - BBOX.w) / D_LON);
  const out = [];
  for (let r = rf - 1; r <= rf + 1; r++) {
    for (let c = cf - 1; c <= cf + 1; c++) {
      const cell = tileGrid.get(r + "," + c);
      if (!cell) continue;
      for (const t of cell) {
        if (lat >= t.south && lat <= t.north && lon >= t.west && lon <= t.east) out.push(t);
      }
    }
  }
  return out;
}
function classAt(lat, lon) {
  const hits = tilesAt(lat, lon);
  if (!hits.length) return { cls: "none", tile: null };
  let cls = "clear", tile = hits[0];
  for (const t of hits) {
    const c = classify(shownPct(t));
    if (CLASS_RANK[c] >= CLASS_RANK[cls]) { cls = c; tile = t; }
  }
  return { cls, tile };
}

/* ============================================================ street network
   Two sources, same shape: nodes with lat/lon, and undirected edges between
   them. The simulated grid is the fallback; scripts/fetch_roads.py produces the
   real one from OpenStreetMap. */
let nodes = [], rawEdges = [], edges = [], adj = [], allEdgeIndex = null;
let nodeIndex = new Map();            /* spatial hash for nearestNode */
const NODE_CELL = 0.005;              /* degrees */

function buildSimulatedGrid() {
  const NR = TILE_ROWS * 2, NC = TILE_COLS * 2;
  const dLat = D_LAT / 2, dLon = D_LON / 2;
  const ns = [], es = [];
  const id = (i, j) => i * NC + j;
  for (let i = 0; i < NR; i++) {
    for (let j = 0; j < NC; j++) {
      /* Offset by half a step so junctions sit inside tiles, not on their
         shared edges, which keeps "which tile blocked this road" unambiguous. */
      ns.push({ id: id(i, j), lat: BBOX.n - (i + 0.5) * dLat, lon: BBOX.w + (j + 0.5) * dLon });
    }
  }
  const rnd = mulberry32(7717);
  for (let i = 0; i < NR; i++) {
    for (let j = 0; j < NC; j++) {
      if (j + 1 < NC && rnd() > 0.08) es.push([id(i, j), id(i, j + 1)]);
      if (i + 1 < NR && rnd() > 0.08) es.push([id(i, j), id(i + 1, j)]);
    }
  }
  return { ns, es };
}

/* A LineString FeatureCollection from scripts/fetch_roads.py. Coordinates are
   snapped to 6 dp so ways that meet at a junction share one node. */
function buildRoadNetwork(gj) {
  const ns = [], es = [], byKey = new Map();
  const nodeAt = (lon, lat) => {
    const key = lat.toFixed(6) + "," + lon.toFixed(6);
    let idx = byKey.get(key);
    if (idx === undefined) { idx = ns.length; ns.push({ id: idx, lat, lon }); byKey.set(key, idx); }
    return idx;
  };
  let skipped = 0;
  for (const f of gj.features || []) {
    const g = f && f.geometry;
    if (!g) continue;
    const lines = g.type === "LineString" ? [g.coordinates]
                : g.type === "MultiLineString" ? g.coordinates : null;
    if (!lines) { skipped++; continue; }
    for (const line of lines) {
      let prev = null;
      for (const c of line) {
        const lon = c[0], lat = c[1];
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) { prev = null; continue; }
        if (!inBox({ lat, lon })) { prev = null; continue; }   /* clip to the routing area */
        const cur = nodeAt(lon, lat);
        if (prev !== null && prev !== cur) es.push([prev, cur]);
        prev = cur;
      }
    }
  }
  return { ns, es, skipped };
}

function setNetwork(built) {
  nodes = built.ns; rawEdges = built.es;
  nodeIndex = new Map();
  for (const n of nodes) {
    const k = Math.round(n.lat / NODE_CELL) + "," + Math.round(n.lon / NODE_CELL);
    if (!nodeIndex.has(k)) nodeIndex.set(k, []);
    nodeIndex.get(k).push(n);
  }
  showcaseCache = null;
}

function nearestNode(pt) {
  const ci = Math.round(pt.lat / NODE_CELL), cj = Math.round(pt.lon / NODE_CELL);
  let best = null, bestD = Infinity, bestRing = -1;
  for (let ring = 0; ring < 40; ring++) {
    for (let i = ci - ring; i <= ci + ring; i++) {
      for (let j = cj - ring; j <= cj + ring; j++) {
        /* only the newly added ring */
        if (ring > 0 && i !== ci - ring && i !== ci + ring && j !== cj - ring && j !== cj + ring) continue;
        const cell = nodeIndex.get(i + "," + j);
        if (!cell) continue;
        for (const n of cell) {
          const d = metres(pt.lat, pt.lon, n.lat, n.lon);
          if (d < bestD) { bestD = d; best = n; bestRing = ring; }
        }
      }
    }
    /* Rings are square, so a hit in one ring's corner can be farther than one
       in the next ring's middle. Always look one ring past the best so far. */
    if (best && ring > bestRing) break;
  }
  return best;
}

/* ============================================================ flood weights */
function applyFloodWeights() {
  edges = []; adj = nodes.map(() => []); allEdgeIndex = null;
  for (const [ai, bi] of rawEdges) {
    const a = nodes[ai], b = nodes[bi];
    if (!a || !b) continue;
    const mid = { lat: (a.lat + b.lat) / 2, lon: (a.lon + b.lon) / 2 };
    let cls = "none", tile = null;
    for (const p of [a, b, mid]) {
      const got = classAt(p.lat, p.lon);
      if (CLASS_RANK[got.cls] > CLASS_RANK[cls]) { cls = got.cls; tile = got.tile; }
      else if (got.cls === cls && tile === null) tile = got.tile;
    }
    const length = metres(a.lat, a.lon, b.lat, b.lon);
    const e = {
      a: ai, b: bi, length, cls, tile,
      cost: cls === "caution" ? length * (1 + CAUTION_MULTIPLIER) : length,
      blocked: cls === "blocked",
    };
    edges.push(e);
    if (!e.blocked) { adj[ai].push(e); adj[bi].push(e); }
  }
}
function reweight() { indexTiles(); applyFloodWeights(); }

function allEdgesAt(u) {
  if (!allEdgeIndex) {
    allEdgeIndex = nodes.map(() => []);
    for (const e of edges) { allEdgeIndex[e.a].push(e); allEdgeIndex[e.b].push(e); }
  }
  return allEdgeIndex[u];
}

/* ============================================================ shortest path
   A real street network runs to tens of thousands of nodes, so the frontier is
   a binary heap rather than a linear scan. */
class MinHeap {
  constructor() { this.h = []; }
  get size() { return this.h.length; }
  push(node, dist) {
    const h = this.h; h.push({ node, dist });
    let i = h.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (h[p].dist <= h[i].dist) break;
      [h[p], h[i]] = [h[i], h[p]]; i = p;
    }
  }
  pop() {
    const h = this.h, top = h[0], last = h.pop();
    if (h.length) {
      h[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < h.length && h[l].dist < h[m].dist) m = l;
        if (r < h.length && h[r].dist < h[m].dist) m = r;
        if (m === i) break;
        [h[m], h[i]] = [h[i], h[m]]; i = m;
      }
    }
    return top;
  }
}

function dijkstra(fromId, toId, weight, useBlocked) {
  const dist = new Float64Array(nodes.length).fill(Infinity);
  const prev = new Int32Array(nodes.length).fill(-1);
  const prevEdge = new Array(nodes.length).fill(null);
  const done = new Uint8Array(nodes.length);
  const heap = new MinHeap();
  dist[fromId] = 0; heap.push(fromId, 0);
  while (heap.size) {
    const { node: u, dist: d } = heap.pop();
    if (done[u]) continue;
    done[u] = 1;
    if (u === toId) break;
    if (d > dist[u]) continue;
    for (const e of (useBlocked ? allEdgesAt(u) : adj[u])) {
      const v = e.a === u ? e.b : e.a;
      if (done[v]) continue;
      const nd = dist[u] + e[weight];
      if (nd < dist[v]) { dist[v] = nd; prev[v] = u; prevEdge[v] = e; heap.push(v, nd); }
    }
  }
  if (!Number.isFinite(dist[toId])) return null;
  const path = [], pathEdges = [];
  for (let v = toId; v !== -1; v = prev[v]) {
    path.push(v);
    if (prevEdge[v]) pathEdges.push(prevEdge[v]);
    if (v === fromId) break;
  }
  path.reverse(); pathEdges.reverse();
  return { path, edges: pathEdges, total: dist[toId] };
}

/* ============================================================ routing */
function computeRoute() {
  const sN = nearestNode(start), eN = nearestNode(end);
  if (!sN || !eN) {
    return { status: "no_safe_route", reason: "No street near one of those points.", baselineCoords: null };
  }
  const tileProps = t => ({ after_id: t.after_id, locality: t.locality,
                            new_flood_pct: shownPct(t), lat: t.lat, lon: t.lon });
  if (sN.id === eN.id) {
    return { status: "ok", coords: [[sN.lon, sN.lat]], distance_m: 0, duration_s: 0,
             baseline: null, flooded_tiles_avoided: [], caution_tiles: [], uncovered_m: 0 };
  }
  /* A point inside a flooded tile has no passable road at all, which is a
     different problem from being unable to get there. Say which. */
  const sCls = classAt(sN.lat, sN.lon).cls, eCls = classAt(eN.lat, eN.lon).cls;
  if (sCls === "blocked" || eCls === "blocked") {
    const who = sCls === "blocked" && eCls === "blocked" ? "Both the start and the destination are"
              : sCls === "blocked" ? "The start is" : "The destination is";
    return { status: "no_safe_route", baselineCoords: null,
             reason: who + " inside a tile rated above " + BLOCK_ABOVE_PCT +
                     "% new floodwater, so no road there is passable." };
  }

  const safe = dijkstra(sN.id, eN.id, "cost", false);
  const base = dijkstra(sN.id, eN.id, "length", true);
  if (!safe) {
    return { status: "no_safe_route", baselineCoords: base ? base.path.map(i => [nodes[i].lon, nodes[i].lat]) : null,
             reason: "All paths cross roads in tiles rated above " + BLOCK_ABOVE_PCT + "% new floodwater." };
  }

  let distance = 0, uncovered = 0;
  const caution = new Map(), safeTiles = new Set();
  for (const e of safe.edges) {
    distance += e.length;
    if (e.cls === "none") uncovered += e.length;
    if (e.cls === "caution" && e.tile) caution.set(e.tile.after_id, tileProps(e.tile));
    if (e.tile) safeTiles.add(e.tile.after_id);
  }
  let baseDistance = 0;
  const avoided = new Map();
  if (base) {
    for (const e of base.edges) {
      baseDistance += e.length;
      if (e.cls === "blocked" && e.tile && !safeTiles.has(e.tile.after_id)) avoided.set(e.tile.after_id, tileProps(e.tile));
    }
  }
  const samePath = base && base.path.length === safe.path.length && base.path.every((v, k) => v === safe.path[k]);
  return {
    status: "ok",
    coords: safe.path.map(i => [nodes[i].lon, nodes[i].lat]),
    distance_m: distance,
    duration_s: Math.round(distance / 1000 / AVG_SPEED_KMH * 3600),
    baseline: (base && !samePath) ? { coords: base.path.map(i => [nodes[i].lon, nodes[i].lat]), distance_m: baseDistance } : null,
    flooded_tiles_avoided: [...avoided.values()],
    caution_tiles: [...caution.values()],
    uncovered_m: uncovered,
  };
}

/* ============================================================ the map */
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
const ESRI_ATTR = "Tiles &copy; Esri";
const map = L.map("map", { zoomSnap: 0.25, zoomControl: true })
  .fitBounds([[BBOX.s, BBOX.w], [BBOX.n, BBOX.e]]);

const baseLight = L.tileLayer(ESRI + "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
  { attribution: ESRI_ATTR + " &mdash; Esri, DeLorme, NAVTEQ", maxZoom: 19 });
const baseDark = L.tileLayer(ESRI + "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
  { attribution: ESRI_ATTR + " &mdash; Esri, DeLorme, NAVTEQ", maxZoom: 19 });
const baseSat = L.tileLayer(ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: ESRI_ATTR + " &mdash; Source: Esri, Maxar, Earthstar Geographics", maxZoom: 19 });

const tileLayer = L.layerGroup().addTo(map);
const gridLayer = L.layerGroup();
const routeLayer = L.layerGroup().addTo(map);
const markerLayer = L.layerGroup().addTo(map);

const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";
let activeBase = isDark() ? baseDark : baseLight;
activeBase.addTo(map);

const layerControl = L.control.layers(
  { "Streets (light)": baseLight, "Streets (dark)": baseDark, "Satellite": baseSat },
  { "Flood estimate": tileLayer, "Simulated street grid": gridLayer },
  { collapsed: false }
).addTo(map);
map.on("baselayerchange", ev => { activeBase = ev.layer; });

/* ---------------------------------------------------------- tiles */
function drawTiles() {
  tileLayer.clearLayers();
  const avoided = new Set((result && result.flooded_tiles_avoided || []).map(t => t.after_id));
  for (const t of TILES) {
    const pct = shownPct(t);
    const hit = avoided.has(t.after_id);
    const rect = L.rectangle([[t.south, t.west], [t.north, t.east]], {
      color: hit ? "#e69f00" : "#ffffff",
      weight: hit ? 2.5 : 0.5,
      dashArray: hit ? "5 3" : null,
      fill: true, fillColor: fillFor(pct), fillOpacity: 0.78,
      interactive: true,
    });
    const water = (t.before_water_pct === null || t.before_water_pct === undefined)
      ? "" : "<br>Water before &rarr; after: " + t.before_water_pct + "% &rarr; " + t.after_water_pct + "%";
    const label = { blocked: "impassable", caution: "caution", clear: "passable" }[classify(pct)];
    rect.bindTooltip(
      "<b>" + esc(t.locality) + "</b><br>" +
      (pct === null ? "Not scored" : "New flood: " + pct + "%") + water +
      "<br>Routing treats this as <b>" + label + "</b>" +
      (t.rechecked && recheckOn ? "<br>After-image rechecked for missed floodwater" : "") +
      "<br><small>" + esc(t.after_id) + "</small>",
      { sticky: true });
    tileLayer.addLayer(rect);
  }
  /* Leaflet gives every interactive path a tab stop. With hundreds of tiles that
     turns one Tab press into hundreds, which is worse for a keyboard user than
     losing the hover tooltips - and the route card names every tile that matters
     anyway. Keep them mouse-interactive, out of the tab order. */
  for (const layer of tileLayer.getLayers()) {
    const el = layer.getElement && layer.getElement();
    if (el) el.setAttribute("tabindex", "-1");
  }
}

/* The simulated grid is drawn only while it is what we are routing on. Over a
   real basemap it would otherwise read as a claim about real streets. */
function drawGrid() {
  gridLayer.clearLayers();
  if (REAL_ROADS) return;
  const segs = rawEdges.map(([ai, bi]) => [[nodes[ai].lat, nodes[ai].lon], [nodes[bi].lat, nodes[bi].lon]]);
  gridLayer.addLayer(L.polyline(segs, {
    color: "#f2f4f7", weight: 1.2, opacity: 0.55, dashArray: "4 4", interactive: false,
  }));
}

/* ---------------------------------------------------------- route */
function drawRoute(fit) {
  routeLayer.clearLayers(); markerLayer.clearLayers();
  if (result && result.status === "ok" && result.coords.length > 1) {
    const line = result.coords.map(([lon, lat]) => [lat, lon]);
    if (showBaseline && result.baseline) {
      routeLayer.addLayer(L.polyline(result.baseline.coords.map(([lon, lat]) => [lat, lon]),
        { color: "#444", weight: 4, dashArray: "10 7", opacity: 0.95, interactive: false }));
    }
    routeLayer.addLayer(L.polyline(line, { color: "#000", weight: 9, opacity: 0.9, lineJoin: "round", interactive: false }));
    routeLayer.addLayer(L.polyline(line, { color: "#e69f00", weight: 6, opacity: 1, lineJoin: "round", interactive: false }));
    if (fit) map.fitBounds(L.latLngBounds(line).pad(0.25));
  } else if (result && result.status === "no_safe_route" && showBaseline && result.baselineCoords) {
    routeLayer.addLayer(L.polyline(result.baselineCoords.map(([lon, lat]) => [lat, lon]),
      { color: "#444", weight: 4, dashArray: "10 7", interactive: false }));
  }
  const pin = (pt, label, bg) => L.marker([pt.lat, pt.lon], {
    icon: L.divIcon({ className: "", iconSize: [26, 26], iconAnchor: [13, 13],
      html: '<div class="marker-pin" style="background:' + bg + '">' + label + "</div>" }),
    keyboard: false, title: label === "A" ? "Start" : "Destination",
  });
  if (start) markerLayer.addLayer(pin(start, "A", "#1a7f37"));
  if (end) markerLayer.addLayer(pin(end, "B", "#8a1c1c"));
}

function redraw(fit) { drawTiles(); drawGrid(); drawRoute(fit); }

/* ============================================================ result card */
function renderResult() {
  const body = document.getElementById("result-body");
  const explain = document.getElementById("explain-body");
  const btnBase = document.getElementById("btn-baseline");

  if (!result) {
    body.innerHTML = '<p class="hint">Set a start and a destination, then press <em>Find safe route</em>.</p>';
    explain.innerHTML = '<p class="hint">No route yet.</p>';
    btnBase.disabled = true; btnBase.setAttribute("aria-pressed", "false");
    btnBase.textContent = "Show normal route"; showBaseline = false;
    return;
  }
  if (result.status === "no_safe_route") {
    body.innerHTML = '<p class="nosafe">No safe route found.</p><p class="hint">' + result.reason + "</p>";
    explain.innerHTML = "<p>Every road out of there runs through tiles the model rated above " +
      BLOCK_ABOVE_PCT + "% new floodwater, so there is nothing to recommend.</p>";
    btnBase.disabled = !result.baselineCoords;
    return;
  }

  const mi = miles(result.distance_m), mins = Math.round(result.duration_s / 60);
  const av = result.flooded_tiles_avoided, locs = [...new Set(av.map(t => t.locality))];
  let html = '<p class="card-head"><span class="stat"><b>' + mi.toFixed(1) + '</b> mi</span>' +
             '<span class="stat"><b>' + mins + "</b> min</span></p>";
  if (av.length) {
    html += "<p><strong>Avoided " + av.length + " heavily flooded area" + (av.length === 1 ? "" : "s") +
            "</strong>" + (locs.length ? " — " + esc(locs.join(", ")) : "") + ".</p><ul>";
    for (const t of av) html += "<li>" + esc(t.locality) + " — " + t.new_flood_pct + "% (" + esc(t.after_id) + ")</li>";
    html += "</ul>";
  } else {
    html += "<p>No heavily flooded areas on the direct route, so this is the normal shortest path.</p>";
  }
  if (result.baseline) {
    const b = miles(result.baseline.distance_m);
    html += "<p>The direct route is " + b.toFixed(1) + " mi. This one adds " + (mi - b).toFixed(1) +
            " mi to stay out of the water.</p>";
  }
  html += '<ul class="cautions">';
  for (const c of buildCautions(result)) html += "<li>⚠ " + esc(c) + "</li>";
  html += "</ul>";
  body.innerHTML = html;

  /* The app's fallback template, used here because no model is reachable. */
  let text;
  if (av.length) {
    text = "This route avoids " + av.length + " heavily flooded area" + (av.length === 1 ? "" : "s") +
      (locs.length ? " (" + esc(locs.join(", ")) + ")" : "") +
      (result.baseline ? " and adds " + (mi - miles(result.baseline.distance_m)).toFixed(1) +
        " mi compared with the direct route." : ".");
  } else {
    text = "Nothing on the direct route was rated above " + BLOCK_ABOVE_PCT +
      "% new floodwater, so this is the shortest path, " + mi.toFixed(1) + " mi and about " + mins + " minutes.";
  }
  explain.innerHTML = "<p>" + text + "</p>";

  btnBase.disabled = !result.baseline;
  if (!result.baseline) {
    showBaseline = false;
    btnBase.setAttribute("aria-pressed", "false"); btnBase.textContent = "Show normal route";
  }
}

/* Built in code, never by a model, so they are always accurate. Grouped by
   locality: one neighbourhood can contribute several caution tiles, and
   repeating the same sentence per tile reads as a bug. */
function buildCautions(res) {
  const out = [], scored = new Map(), unscored = new Map();
  for (const t of res.caution_tiles || []) {
    const bucket = (t.new_flood_pct === null || t.new_flood_pct === undefined) ? unscored : scored;
    if (!bucket.has(t.locality)) bucket.set(t.locality, []);
    bucket.get(t.locality).push(t.new_flood_pct);
  }
  for (const [loc, pcts] of scored) {
    if (pcts.length === 1) out.push("Moderate flooding estimated (" + pcts[0] + "% of the area) near " + loc + ".");
    else {
      const lo = Math.min(...pcts), hi = Math.max(...pcts);
      out.push("Moderate flooding estimated on " + pcts.length + " stretches near " + loc +
               " (" + (lo === hi ? lo + "%" : lo + "–" + hi + "%") + " of the area).");
    }
  }
  for (const [loc, list] of unscored) {
    out.push(list.length === 1 ? "No flood score for an area near " + loc + "."
                               : "No flood score for " + list.length + " areas near " + loc + ".");
  }
  if (res.uncovered_m > 0) out.push(miles(res.uncovered_m).toFixed(1) + " mi of this route has no flood photos.");
  out.push("AI estimates can miss floodwater that looks like bare ground.");
  return out;
}

/* ============================================================ chrome */
function renderLegend() {
  const bounds = [0, ...FLOOD_BINS, 100], rows = [];
  for (let i = 0; i < FLOOD_COLORS.length; i++) {
    const tag = i >= 3 ? " — impassable" : (i === 2 ? " — caution" : "");
    rows.push('<div><i style="background:' + FLOOD_COLORS[i] + '"></i><span>' +
              bounds[i] + "–" + bounds[i + 1] + "%" + tag + "</span></div>");
  }
  rows.push('<div><i style="background:' + UNSCORED_COLOR + '"></i><span>Not scored — caution</span></div>');
  document.getElementById("legend-rows").innerHTML = rows.join("");
  const scored = TILES.filter(t => t.new_flood_pct !== null && t.new_flood_pct !== undefined).length;
  document.getElementById("legend-note").innerHTML =
    (REAL_TILES ? "Real exported scores. " : "Sample scores. ") + TILES.length + " tiles in view, " +
    scored + " scored, " + TILES.filter(t => t.rechecked).length + " rechecked." +
    "<br>Estimated by Qwen3-VL. Tiles shown as 0% can still be flooded (4 of 11 hand checks).";
}

function renderBanners() {
  const tb = document.getElementById("data-banner");
  tb.className = "banner" + (REAL_TILES ? " real" : "");
  tb.innerHTML = REAL_TILES
    ? "<strong>Real flood scores</strong> — " + TILES.length +
      " tiles inside the west Houston routing area, from <code>flood_tiles.geojson</code>."
    : "<strong>Sample flood scores.</strong> These percentages are generated, not Qwen3-VL output. " +
      "Load <code>results/flood_tiles.geojson</code> to see the real ones.";

  const rb = document.getElementById("road-banner");
  rb.className = "banner" + (REAL_ROADS ? " real" : "");
  rb.innerHTML = REAL_ROADS
    ? "<strong>Real streets</strong> — routing on " + nodes.length.toLocaleString() +
      " junctions of the OpenStreetMap network for this area."
    : "<strong>Simulated streets.</strong> The router is running on an evenly spaced grid, not the " +
      "streets under the basemap. Run <code>scripts/fetch_roads.py</code> once, then load " +
      "<code>results/road_network.geojson</code> to route on real streets.";

  document.getElementById("map-note").textContent = REAL_ROADS
    ? "Routing on the real street network. Flood tiles are ~530 m aerial photo footprints."
    : "The grey lattice is the simulated street grid the router uses; it is not the real street layout. "
      + "Flood tiles are ~530 m aerial photo footprints.";
}

/* ============================================================ showcase
   Which trip best shows the recheck off depends entirely on the scores loaded,
   so search for it rather than hard-coding a pair. */
function findShowcase() {
  if (showcaseCache) return showcaseCache;
  const savedRecheck = recheckOn, savedStart = start, savedEnd = end;

  /* Candidate trips: a start and an end either side of a rechecked tile that
     the recheck pass turned impassable. */
  const pairs = [];
  for (const t of TILES.filter(t => t.rechecked && classify(t.new_flood_pct) === "blocked")
                       .sort((a, b) => (b.new_flood_pct || 0) - (a.new_flood_pct || 0))
                       .slice(0, 14)) {
    const h = t.north - t.south, w = t.east - t.west;
    for (const k of [1.0, 1.6, 2.4]) {
      for (const axis of ["ew", "ns"]) {
        const a = axis === "ew" ? { lat: t.lat, lon: t.west - w * k } : { lat: t.north + h * k, lon: t.lon };
        const c = axis === "ew" ? { lat: t.lat, lon: t.east + w * k } : { lat: t.south - h * k, lon: t.lon };
        if (inBox(a) && inBox(c)) pairs.push({ tile: t, start: a, end: c });
      }
    }
  }

  /* Weight the network twice in all, not twice per candidate. Re-weighting
     touches every edge, and a real street network is tens of thousands of them,
     so doing it per probe would lock the page up for a minute. */
  const route = phase => {
    recheckOn = phase; reweight();
    return pairs.map(p => { start = p.start; end = p.end; return computeRoute(); });
  };
  const withRecheck = route(true);
  const without = route(false);

  let best = { start: null, end: null, tile: null, gain: 0 };
  for (let i = 0; i < pairs.length; i++) {
    const on = withRecheck[i], off = without[i];
    if (on.status !== "ok" || off.status !== "ok") continue;
    if (!(on.flooded_tiles_avoided || []).some(x => x.after_id === pairs[i].tile.after_id)) continue;
    const gain = on.distance_m - off.distance_m;
    if (gain > best.gain) best = { start: pairs[i].start, end: pairs[i].end, tile: pairs[i].tile, gain };
  }

  recheckOn = savedRecheck; reweight();
  start = savedStart; end = savedEnd;      /* probing clobbered these */
  showcaseCache = best;
  return best;
}

/* ============================================================ events */
function setEndpoint(pt, which) {
  if (!inBox(pt)) {
    document.getElementById("map-note").textContent = "Routing covers the west Houston area only.";
    return;
  }
  if (which === "start") start = pt; else end = pt;
  document.getElementById("start-val").textContent = start ? fmtLatLon(start) : "not set";
  document.getElementById("end-val").textContent = end ? fmtLatLon(end) : "not set";
  result = null; renderResult(); redraw(false);
}

map.on("click", ev => setEndpoint({ lat: ev.latlng.lat, lon: ev.latlng.lng },
                                  clickTurn++ % 2 === 0 ? "start" : "end"));

const centrePoint = () => { const c = map.getCenter(); return { lat: c.lat, lon: c.lng }; };
document.getElementById("btn-set-start").addEventListener("click", () => setEndpoint(centrePoint(), "start"));
document.getElementById("btn-set-end").addEventListener("click", () => setEndpoint(centrePoint(), "end"));

document.getElementById("btn-route").addEventListener("click", () => {
  if (!start || !end) {
    document.getElementById("map-note").textContent = "Set a start and a destination first.";
    return;
  }
  result = computeRoute(); renderResult(); redraw(true);
});

document.getElementById("btn-clear").addEventListener("click", () => {
  start = end = result = null; clickTurn = 0; showBaseline = false;
  document.getElementById("start-val").textContent = "not set";
  document.getElementById("end-val").textContent = "not set";
  renderResult(); redraw(false);
  map.fitBounds([[BBOX.s, BBOX.w], [BBOX.n, BBOX.e]]);
});

document.getElementById("btn-recheck").addEventListener("click", ev => {
  recheckOn = !recheckOn;
  ev.currentTarget.setAttribute("aria-pressed", String(recheckOn));
  ev.currentTarget.textContent = "Recheck pass: " + (recheckOn ? "on" : "off");
  reweight();
  if (start && end) result = computeRoute();
  renderLegend(); renderResult();
  /* Refit: the recheck toggle is the moment the route changes shape, and the
     new one is usually much longer than the view fitted to the old one. */
  redraw(!!(result && result.status === "ok"));
});

document.getElementById("btn-baseline").addEventListener("click", ev => {
  showBaseline = !showBaseline;
  ev.currentTarget.setAttribute("aria-pressed", String(showBaseline));
  ev.currentTarget.textContent = showBaseline ? "Hide normal route" : "Show normal route";
  drawRoute(false);
});

document.getElementById("btn-showcase").addEventListener("click", ev => {
  const btn = ev.currentTarget; btn.disabled = true;
  const pick = findShowcase();
  btn.disabled = false;
  const hint = document.getElementById("preset-hint");
  if (!pick.tile) {
    hint.textContent = "No rechecked tile in this data changes a route, so the recheck toggle " +
      "will not move one. Everything else still works.";
    return;
  }
  hint.innerHTML = "The showcase route crosses tile <code>" + esc(pick.tile.after_id) +
    "</code>. The first pass scored it 0%; the recheck scored it " + pick.tile.new_flood_pct +
    "%. Turn the recheck off and the router drives straight through it.";
  start = { ...pick.start }; end = { ...pick.end }; clickTurn = 0;
  document.getElementById("start-val").textContent = fmtLatLon(start);
  document.getElementById("end-val").textContent = fmtLatLon(end);
  result = computeRoute();
  showBaseline = true;
  const b = document.getElementById("btn-baseline");
  b.setAttribute("aria-pressed", "true"); b.textContent = "Hide normal route";
  renderResult(); redraw(true);
});

document.getElementById("btn-nosafe").addEventListener("click", () => {
  /* Any point inside a blocked tile: no road there is passable. */
  const t = TILES.find(x => classify(shownPct(x)) === "blocked");
  if (!t) { document.getElementById("map-note").textContent = "No blocked tile in this data."; return; }
  start = findShowcase().start || { lat: (BBOX.n + BBOX.s) / 2, lon: (BBOX.e + BBOX.w) / 2 };
  end = { lat: t.lat, lon: t.lon };
  clickTurn = 0;
  document.getElementById("start-val").textContent = fmtLatLon(start);
  document.getElementById("end-val").textContent = fmtLatLon(end);
  result = computeRoute(); renderResult(); redraw(true);
});

/* ---------------------------------------------------------- file loading */
function readJSON(input, onOk) {
  const file = input.files && input.files[0];
  if (!file) return;
  const hint = document.getElementById("file-hint");
  const reader = new FileReader();
  reader.onload = () => {
    let parsed;
    try { parsed = JSON.parse(reader.result); }
    catch (err) {
      hint.textContent = "That file is not valid JSON."; hint.style.color = "var(--danger)"; return;
    }
    /* A well-formed file of the wrong shape is a different problem, and saying
       "not valid JSON" sends you hunting for a syntax error that isn't there. */
    try { onOk(parsed, file.name); hint.style.color = ""; }
    catch (err) {
      hint.textContent = "That file is JSON, but not what was expected: " + err.message + ".";
      hint.style.color = "var(--danger)";
    }
  };
  reader.onerror = () => { hint.textContent = "The file could not be read."; hint.style.color = "var(--danger)"; };
  reader.readAsText(file);
}

function applyTiles(gj, name) {
  const hint = document.getElementById("file-hint");
  if (!gj || gj.type !== "FeatureCollection" || !Array.isArray(gj.features)) throw new Error("not a FeatureCollection");
  const out = [];
  for (const f of gj.features) {
    const p = f && f.properties, g = f && f.geometry;
    if (!p || !g || g.type !== "Polygon" || !g.coordinates || !g.coordinates[0]) continue;
    const ring = g.coordinates[0];
    const lons = ring.map(c => c[0]), lats = ring.map(c => c[1]);
    const north = Math.max(...lats), south = Math.min(...lats);
    const east = Math.max(...lons), west = Math.min(...lons);
    const lat = p.lat != null ? p.lat : (north + south) / 2;
    const lon = p.lon != null ? p.lon : (east + west) / 2;
    if (!inBox({ lat, lon })) continue;                    /* other clusters */
    const pct = p.new_flood_pct == null ? null : Number(p.new_flood_pct);
    out.push({
      after_id: p.after_id || "tile", locality: p.locality || "Unknown",
      new_flood_pct: pct === null || Number.isNaN(pct) ? null : pct,
      before_water_pct: p.before_water_pct ?? null, after_water_pct: p.after_water_pct ?? null,
      rechecked: !!p.rechecked, lat, lon, north, south, east, west,
    });
  }
  if (!out.length) {
    hint.textContent = "No tiles in that file fall inside the west Houston routing area.";
    hint.style.color = "var(--danger)"; return;
  }
  TILES = out; REAL_TILES = true; showcaseCache = null; result = null;
  hint.textContent = "Loaded " + out.length + " tiles from " + name + ".";
  reweight(); renderBanners(); renderLegend(); renderResult(); redraw(false);
}

function applyRoads(gj, name) {
  const hint = document.getElementById("file-hint");
  if (!gj || !Array.isArray(gj.features)) throw new Error("not a FeatureCollection");
  const built = buildRoadNetwork(gj);
  if (built.ns.length < 2 || !built.es.length) {
    hint.textContent = "No street segments in that file fall inside the routing area.";
    hint.style.color = "var(--danger)"; return;
  }
  setNetwork(built); REAL_ROADS = true; result = null;
  hint.textContent = "Loaded " + built.es.length.toLocaleString() + " street segments from " + name + ".";
  layerControl.removeLayer(gridLayer); map.removeLayer(gridLayer);
  reweight(); renderBanners(); renderResult(); redraw(false);
}

document.getElementById("file-tiles").addEventListener("change", ev => readJSON(ev.target, applyTiles));
document.getElementById("file-roads").addEventListener("change", ev => readJSON(ev.target, applyRoads));

/* Served over http (a local server, or GitHub Pages) the data files are just
   there, so load them without making anyone pick a file. Opened straight off
   disk, fetch() cannot read them and this quietly does nothing - that is what
   the two file pickers are for. */
async function autoLoad() {
  const tryOne = async (url, apply) => {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return false;
      apply(await res.json(), url.split("/").pop());
      return true;
    } catch (e) { return false; }
  };
  await tryOne("../results/flood_tiles.geojson", applyTiles);
  await tryOne("../results/road_network.geojson", applyRoads);
}
if (location.protocol !== "file:") autoLoad();

/* ---------------------------------------------------------- theme */
(function () {
  const btn = document.getElementById("btn-theme");
  const paint = () => {
    const dark = isDark();
    btn.textContent = dark ? "Light mode" : "Dark mode";
    btn.setAttribute("aria-pressed", String(dark));
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  };
  btn.addEventListener("click", () => {
    const dark = !isDark();
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    try { localStorage.setItem("fsr-theme", dark ? "dark" : "light"); } catch (e) { /* blocked */ }
    /* Follow the theme only if the viewer is on a canvas basemap; if they chose
       satellite, leave it alone. */
    if (activeBase === baseLight || activeBase === baseDark) {
      map.removeLayer(activeBase);
      activeBase = dark ? baseDark : baseLight;
      activeBase.addTo(map);
    }
    paint();
  });
  paint();
})();

/* ============================================================ go */
setNetwork(buildSimulatedGrid());
gridLayer.addTo(map);
reweight();
renderBanners(); renderLegend(); renderResult(); redraw(false);
