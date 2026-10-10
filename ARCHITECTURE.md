# How Deer Scout is put together

```
 GitHub Actions (weekly, or on demand)                    Your iPhone
 ┌──────────────────────────────────────────┐            ┌──────────────────────────────┐
 │ Python pipeline (pipeline/)              │            │ Static web app (web/)        │
 │  1. download public data                 │  commits   │  reads /data/*.json          │
 │  2. clean, measure, check permission     │ ─────────▶ │  asks Open-Meteo for the     │
 │  3. analyze land cover, roads, terrain   │  data      │  7-day forecast directly     │
 │  4. score blocks and spots               │  files     │  keeps saved places on the   │
 │  5. write web/public/data/*              │            │  phone only                  │
 └──────────────────────────────────────────┘            └──────────────────────────────┘
```

## Why no server or database (yet)

The original plan had FastAPI and PostGIS. For a single user, everything heavy (boundaries, land
cover, terrain, scoring) only changes when the source data changes, so it's computed ahead of time and
saved as files. The phone gets the forecast straight from Open-Meteo. That means:

- nothing to keep running or pay for; any static host works (Cloudflare Pages planned);
- the app keeps working with no signal: a service worker (`web/public/sw.js`) saves every app and data
  file on install (list written at build time to `precache.json`), serves map tiles from the phone
  first (areas you save, plus recently viewed tiles), and app files are tried on the network for 4
  seconds before falling back to the saved copy;
- personal notes and saved places never leave the phone.

A server becomes worth it when notes need to sync between devices or when the data outgrows static
files (statewide LiDAR, vector tiles). The pipeline's outputs would load straight into PostGIS then.

## Pipeline (`pipeline/deerscout/`)

| Module | Job |
|---|---|
| `config.py` | Region (Coos County), coordinate systems, endpoints, block size |
| `http.py`, `arcgis.py` | Downloads with retries, paging, size caps, and provenance |
| `granit.py` | GRANIT code tables (agency, protection type, access, accuracy) |
| `tiger.py` | County and town boundaries |
| `geo.py` | Geometry repair, acreage in an equal-area projection, block splitting |
| `units.py` | Tracts → properties → rankable blocks (~1,000 acres, labeled like a map grid) |
| `access.py` + `data/access_rules.yaml` + `data/verifications.yaml` | Hunting permission: verified / prohibited / unknown, each with sources |
| `wmu.py` | Deer WMU per block from the official WMU map (town table as fallback) |
| `landcover.py` | NLCD land cover download and per-block habitat stats |
| `roads.py` | DOT roads, OpenStreetMap logging roads, trails; distances and road-zone shares |
| `terrain.py` | 3DEP elevation tiles; slope, aspect, landform position, saddles, benches |
| `spots.py` | Scores candidate spots, drops ones on pond shores, and works out which winds suit them |
| `lidar1m.py` | Re-checks each candidate against the 1 m lidar DEM (flat shelf, real saddle, water) and moves or marks it |
| `windhistory.py` | Five seasons of hourly wind → wind roses with circular statistics |
| `scoring.py` + `factors.py` + `data/scoring.yaml` | Explainable Property Quality Score with coverage and confidence |
| `analyses.py` | Runs the optional analyses; any failure is logged and that factor is skipped |
| `build.py` | Orchestrates a full run and writes the data files |

Acreage is always measured in NAD83 / Conus Albers (EPSG:5070, equal-area), never in degrees.

### Output files (`web/public/data/`)

| File | Contents |
|---|---|
| `catalog.json` | Every property (attributes, permission, sources, towns, WMUs, overlaps), every block (score breakdown, signals), every scouting spot |
| `properties.geojson`, `blocks.geojson`, `spots.geojson` | Map shapes (simplified to ~8 m, coordinates to 5 decimals) |
| `landcover.png` + `landcover.json` | Land cover image for the map, warped to Web Mercator, with its corner coordinates and legend |
| `wind_history.json` | Wind roses by point, month and morning/evening |
| `regulations.json` | Seasons, legal hours and method notes |
| `manifest.json` | When each source was fetched, what worked and failed, counts, warnings, limitations |

These files are the "database". Their shapes are defined in `web/src/lib/types.ts`; when a shape
changes, the pipeline and the TypeScript types change in the same commit and the tests cover both.

## App (`web/`)

Next.js 16 (static export), React 19, Tailwind 4, MapLibre GL 5.

| Screen | What it does |
|---|---|
| **Hunt** (`/`) | Pick a day, morning/evening, method; ranks legal, in-season blocks by property quality, the day's conditions (including whether any spot suits the wind) and distance from you |
| **Map** (`/map/`) | Topo, satellite and LiDAR relief base maps; land cover layer; properties colored by permission; blocks; scouting spots; your imported files; save the view for offline |
| **Property** (`/property/?id=…`) | Permission with sources and rules, season and legal hours, 7-day outlook, scouting spots ranked for the day's wind, usual winds for the month, score breakdown, GRANIT records, your notes |
| **Saved** | Favorites and notes (phone only) |
| **Settings** | Starting point, score weights, trip blend, data sources and run status |

Logic that matters is in plain TypeScript under `web/src/lib/` with unit tests: seasons, legal hours
(NOAA sun equations), wind math (circular statistics), conditions score, spot wind checks, ranking.

## Automation (`.github/workflows/`)

- `ci.yml`: pipeline tests, app type check, lint, tests, build on every push.
- `data.yml`: weekly (Mondays) and when rules or pipeline code change: runs the tests, builds the data,
  commits it to `main`, and saves the run log to the `run-logs` branch.
- `fetch-docs.yml`: downloads reference documents to the `reference-docs` branch on request.

## Adding a region

Add a `Region` in `config.py` (county GEOID, search rectangle) and the WMU seasons for it in
`data/regulations/`. Access rules are statewide already.
