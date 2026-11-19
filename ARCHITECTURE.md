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
| `config.py` | Regions (Coos County; Concord area = towns within 30 miles), coordinate systems, endpoints, block size |
| `regions.py` | Writes `web/public/data/regions.json`, the list of regions the app can show |
| `http.py`, `arcgis.py` | Downloads with retries, paging, size caps, and provenance |
| `granit.py` | GRANIT code tables (agency, protection type, access, accuracy) |
| `tiger.py` | County and town boundaries; towns within a radius for multi-county regions |
| `geo.py` | Geometry repair, acreage in an equal-area projection, block splitting |
| `units.py` | Tracts → properties → rankable blocks (~1,000 acres, labeled like a map grid) |
| `access.py` + `data/access_rules.yaml` + `data/verifications.yaml` | Hunting permission: verified / prohibited / unknown, each with sources |
| `zones.py` + `data/zones/*.geojson` | Areas inside a property where only some methods are allowed (Bear Brook's bow-only refuge); blocks overlapping one by 5%+ get the stricter rule |
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

### Output files (`web/public/data/<region>/`)

Each region has its own folder, e.g. `web/public/data/coos/` and `web/public/data/concord/`.
`web/public/data/regions.json` lists them (name, folder, map center, default starting point); it's
written from `config.py` and never by a data build, so building one region can't affect another.

| File | Contents |
|---|---|
| `catalog.json` | Every property (attributes, permission, sources, towns, WMUs, overlaps), every block (score breakdown, signals), every scouting spot |
| `properties.geojson`, `blocks.geojson`, `spots.geojson` | Map shapes (simplified to ~8 m, coordinates to 5 decimals) |
| `landcover.png` + `landcover.json` | Land cover image for the map, warped to Web Mercator, with its corner coordinates and legend |
| `wind_history.json` | Wind roses by point, month and morning/evening |
| `regulations.json` | Seasons, legal hours and method notes |
| `manifest.json` | When each source was fetched, what worked and failed, counts, warnings, limitations; for a radius region, the towns included |
| `zones.geojson` | Method-limited areas in the region (only written when there are any) |

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
| **Settings** | Region, starting point (per region), score weights, trip blend, data sources and run status |

The app loads `regions.json`, then the chosen region's files (`DataProvider`). Switching region
clears the old data first and starts a fresh map, so no screen mixes two regions. The service
worker's precache list is every file in the build, so every region's folder is saved on the phone.

Logic that matters is in plain TypeScript under `web/src/lib/` with unit tests: seasons, legal hours
(NOAA sun equations), wind math (circular statistics), conditions score, spot wind checks, ranking.

## Automation (`.github/workflows/`)

- `ci.yml`: pipeline tests, app type check, lint, tests, build on every push.
- `data.yml`: weekly (Mondays), when rules or pipeline code change on `main`, or by hand. One job per
  region, run one after another (`max-parallel: 1`), each with its own 150-minute limit; one failing
  doesn't stop the others. Each job runs the tests, builds its region, checks it changed nothing
  outside `web/public/data/<region>/`, commits that folder to the branch the run started on, and
  saves its log to the `run-logs` branch as `<region>.log` (plus `latest.log`). A local Concord
  build takes about 15 minutes and Coos runs take 5-11 minutes on GitHub, so both together are far
  inside the limit; separate jobs keep it that way as regions are added.
- `fetch-docs.yml`: downloads reference documents to the `reference-docs` branch on request.

## Adding a region

1. Add a `Region` in `config.py` and put it in `REGIONS`. A one-county region gives `counties=("33xxx",)`
   and no radius (clipped to the county). A drive-area region gives several counties plus `center`
   and `radius_miles` (clipped to whole towns whose Census internal point is within the radius).
2. `python -m deerscout.regions` rewrites `web/public/data/regions.json` (a test fails until you do).
3. Seasons in `data/regulations/nh-deer-2026.yaml` cover every WMU. Access rules are mostly
   statewide; add property-specific rules to `data/access_rules.yaml` and method-limited areas to
   `data/zones/`.
4. Build it with **Actions → Refresh data → Run workflow** (region = its short name). The weekly run
   picks it up automatically from `regions.json`.
