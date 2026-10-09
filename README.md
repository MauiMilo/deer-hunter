# Deer Scout

A phone app for deciding where and when to hunt deer on public land in northern New Hampshire,
starting with Coos County and Pittsburg. You tell it the day, morning or evening, and how you're
hunting; it tells you which legal, in-season places look best, which spots inside them suit the wind,
and shows the evidence behind every pick.

It is a scouting aid, not a guarantee. Scores are rankings, not the chance of seeing a deer. Always
check the NH Hunting Digest, posted signs and property rules.

## What it does today

- **Finds the land.** Pulls every conservation and public-land parcel in Coos County from NH GRANIT
  (297 properties, 670,000+ acres), measures true acreage, and splits big properties into ~1,000-acre
  blocks so "go here" means a specific area.
- **Checks permission separately from habitat.** Each property is *hunting allowed (with source and
  date)*, *no public access*, or *not verified*. Only cited sources count: state park/forest rules,
  Fish and Game land rules, the Connecticut Lakes Headwaters rules, WMNF, Umbagog refuge, Dartmouth's
  Second College Grant. Places Fish and Game lists as closed (Pondicherry Wildlife Refuge, state
  historic sites) are marked off-limits. Unverified land is hidden unless you ask for research
  candidates.
- **Knows the seasons.** Official WMU map for every block; 2026-27 seasons by method and WMU; legal
  hours from sunrise/sunset; crossbow rules and their exceptions; flags blocks that straddle a WMU line.
- **Scores habitat, pressure, terrain and access** from USGS Annual NLCD 2025 land cover (30 m, with
  forest cut since 2020 counted as fresh browse), DOT and OpenStreetMap roads, state trails, and USGS
  3DEP bare-earth elevation (10 m). Every score shows its parts, what kind of
  evidence each rests on, and what's missing.
- **Finds scouting spots**: about 1,100 saddles and benches from the elevation data across the
  county, scored for nearby food/cover edges, walk-in distance, trails and boundaries, with the winds
  that suit each one and the direction to walk in from.
- **Plans the day** with a 7-day forecast (Open-Meteo): conditions score, safety warnings, wind check
  for each spot and for the walk in, and five seasons of wind history as wind roses.
- **Keeps a field log**: GPS waypoints, sightings by hour, notes, GPX export. Stored only on the phone.
- **Works like an app on iPhone**: add to Home Screen, dark pre-dawn theme, GPS distances, last data
  available without signal.

## What's not done yet

- Regional deer abundance (Fish and Game buck kill per square mile): official report not yet loaded.
- Real drive times (distances are straight-line with a rough drive estimate).
- Season dates match the online digest and the season formula in the rules, but haven't been
  checked against the printed digest.
- Offline map tiles, GPX/KML import, and tuning scores from your own logged sits.
- Other counties.

See `RESEARCH.md` for the evidence and its limits, `DATA_SOURCES.md` for every source,
`ARCHITECTURE.md` for how it fits together.

## Running it

### The app (on your computer)

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

The data files in `web/public/data/` are already built and committed, so the app works immediately.

### Rebuilding the data

The pipeline downloads from state and federal servers. It runs automatically on GitHub every Monday
and whenever the rules or pipeline change (`.github/workflows/data.yml`); you can also start it from
the repo's **Actions → Refresh data → Run workflow**. To run it yourself:

```bash
cd pipeline
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m deerscout.build --region coos            # full run, ~10-30 min
python -m deerscout.build --skip terrain,wind      # quicker partial run
```

### Tests

```bash
cd pipeline && pytest          # acreage, projections, polygon repair, scoring, permission rules,
                               # paging/errors, WMUs, seasons, land cover, terrain, roads, full build
cd web && npm test             # seasons, legal hours, wind math, conditions, spots, ranking
```

### Marking a property as verified

When you confirm a property's rules (town office, posted sign, managing agency), add it to
`pipeline/data/verifications.yaml` with what you were told, where, and the date. It overrides the
automatic rules on the next data build.

### Putting it on your phone (Cloudflare Pages)

1. In Cloudflare: **Workers & Pages → Create → Pages → Connect to Git**, pick `MauiMilo/deer-hunter`.
2. Root directory `web`, build command `npm run build`, output directory `out`.
3. Lock it down so only you can open it: **Zero Trust → Access → Applications → Add**, protect the
   Pages domain, allow your email (one-time code login).
4. On the iPhone, open the site in Safari → Share → **Add to Home Screen**.

## Layout

```
pipeline/   Python data pipeline (deerscout package, rules and settings in data/, tests/)
web/        Next.js app (src/app screens, src/lib logic + tests, public/data built data)
.github/    Tests, weekly data refresh, reference-document fetcher
```
