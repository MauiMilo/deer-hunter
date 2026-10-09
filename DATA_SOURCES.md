# Data sources

Every number in the app comes from one of these sources. The pipeline records what it actually
fetched, when, and whether it worked in `web/public/data/manifest.json` (shown in the app under
**Settings → Data and sources**). If a source fails, the feature that needs it is switched off for
that run and the failure is listed there. Nothing is filled in with made-up values.

Checked: 2026-10-08.

## Land and boundaries

| Source | What we use | Access | Data date | Updates | License | Resolution / accuracy | Notes |
|---|---|---|---|---|---|---|---|
| **GRANIT Conservation/Public Lands** (UNH) | Property polygons, owner/agency, protection type, public-access code, boundary accuracy | ArcGIS REST, `nhgeodata.unh.edu/.../EC/Conservation/MapServer/1`, GeoJSON, paged | Published 2026-06-30 | Twice a year | Public; metadata says **"Not for legal use"** | Tract-level; each tract carries its own accuracy code (survey → poor) | 930 records intersect the Coos search rectangle; 719 tracts after clipping to the county. Code tables come from the July 2022 coding standard (`ftp.granit.unh.edu/d-cons/ConservationLandsStandard.pdf`). The `ACCESS` field is general public access, **not** hunting permission (the Connecticut Lakes Headwaters is coded "unknown"). |
| **Census TIGERweb** counties and county subdivisions | Coos County outline (GEOID 33007) and town boundaries | ArcGIS REST, `tigerweb.geo.census.gov` | Current TIGER vintage | Yearly | Public domain | Census cartographic accuracy | Used to clip properties to the county and name towns. |
| **NH Fish and Game Wildlife Management Units** | Deer WMU for each block | ArcGIS Feature Service `services8.arcgis.com/hg1B9Egwk1I5p300/.../WMU/FeatureServer/0` | Last edited 2026-08-26 | As rules change | NH Fish and Game (©2016 on layer) | Unit boundaries follow roads and rivers | WMU A is drawn as A1/A2; per the layer's description, rules for "A" cover both. Blocks crossing a line are flagged "split" and the app uses the stricter season. Fallback if the layer fails: a town table built from the digest's written boundaries. |

## Hunting rules

| Source | Used for | Date |
|---|---|---|
| 2026-27 NH Hunting Digest (eRegulations) — deer seasons, regulations, WMUs | Season dates by method and WMU, legal hours, crossbow and bag rules | Last updated 2026-08-27. The online season table had a broken layout and was reconstructed; **not yet checked against the printed digest** (the app says so). |
| NH Admin. Rules **Res 7301.10** (DNCR parks and forests) | Hunting allowed on state parks/forests except a named list (none in Coos); 300 ft rule near occupied developed areas; tree stands | Retrieved 2026-10-08 (via Justia) |
| NH Admin. Rules **Chapter Fis 900** (Fish and Game lands), **Fis 902.02**, **Fis 903.07** | Fish and Game lands in Table 900.01 open to hunting; Connecticut Lakes Natural Area limits (no baiting, no camping, vehicles) | Chapter last amended 2017-02-24; retrieved 2026-10-08. Fish and Game held a hearing in Oct 2025 on re-adopting Fis 900, so watch for changes. |
| NH Parks — Connecticut Lakes Headwaters forest rules sign | Hunting permitted with restrictions on the Headwaters easement land | No date on sign; retrieved 2026-10-08 |
| USDA Forest Service — WMNF Hunting & Shooting | Hunting allowed on all WMNF land under state rules; 150-yard and road rules | Page updated 2026-03-24 |
| USFWS — Lake Umbagog NWR Hunting | Deer hunting allowed; stand, baiting and vehicle rules | No date; retrieved 2026-10-08 |
| Dartmouth — Second College Grant hunting brochure | Public hunting allowed; walk-in only during deer season unless renting a cabin | **Printed 2012**; the app tells you to confirm with Dartmouth |
| NH Fish and Game — Hunting on State Lands FAQs, Where to Hunt | Compact-zone rule; LCIP easements; general guidance | No date; retrieved 2026-10-08 |

All hunting-permission rules and their sources live in `pipeline/data/access_rules.yaml`. Your own
checks go in `pipeline/data/verifications.yaml` (needs a source and a date to count as verified).

## Habitat, terrain and access

| Source | What we use | Access | Data date | License | Resolution | Limits |
|---|---|---|---|---|---|---|
| **USGS Annual NLCD** land cover | Forest types, regrowth/brush, openings, wetlands, developed land, edge density; forest that turned to brush/open ground over 5 years (recent logging) | MRLC GeoServer for the multi-year layer `mrlc_Land-Cover-Native_conus_year_data`: years listed by WCS DescribeCoverage (1985–2025); a chosen year is fetched through WMS `GetMap` with `TIME=` as a GeoTIFF in the official NLCD colors and decoded back to classes (each class has a unique color; checked on a real Coos sample with every pixel decoding). The coverage interface fails on year requests ("startTime is null"). NLCD 2021 via WCS (`mrlc.gov/.../NLCD_2021_Land_Cover_L48/wcs`) is the fallback. | 2025 (and 2020 for change) | Public domain | 30 m pixels | Can't see tree species, mast, understory density, or small cuts/food plots. Class 52 (Shrub/Scrub) officially includes young trees in early succession, which here is mostly logging regrowth. The year actually used is in the manifest. The USGS S3 copy is requester-pays, so it isn't used. |
| **USGS 3DEP** 1/3 arc-second seamless DEM | Bare-earth elevation for slope, aspect, landform position, saddles, benches | Cloud-optimized GeoTIFFs on USGS's public S3 bucket, `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/{n46w072}/USGS_13_{n46w072}.tif`, read in pieces with HTTP range requests. Coos needs n45w072, n46w071, n46w072 (files dated 2026-05 to 2026-08). | 2026 | Public domain | ~10 m, resampled from lidar where flown | Bare earth only: no vegetation height or understory. Doesn't model wind. 1 m lidar DEMs also exist on S3 for northern NH (`1m/Projects/NH_CT_RiverNorthL6_2015`, `NH_Umbagog_LiDAR_2016`); not used yet. |
| **USGS 3DEP** ImageServer | The map's "LiDAR relief" layer (`Hillshade Multidirectional`, full lidar detail), and a fallback elevation source for the pipeline | `elevation.nationalmap.gov/.../3DEPElevation/ImageServer/exportImage` | Service data through 2026-09-28 | Public domain | Best available, 1 m lidar where flown | Often answered 502 errors or stalled under load during testing, so it isn't the pipeline's default. |
| **NH DOT road inventory** (GRANIT `TN/RoadsForDOTViewer/MapServer/5`) | Public roads with legislative class | ArcGIS REST | Current | Public | Road centerlines | Public roads only; private logging roads are mostly missing. |
| **OpenStreetMap** via Overpass API | Logging/forest roads and tracks the DOT layer lacks; `access=private/no` treated as gated | `overpass-api.de` (mirror fallback) | Live | ODbL, © OpenStreetMap contributors | Varies by mapper | Gate status and current condition are often unknown. |
| **NH Recreational Trails** | Trail density near each block (human traffic proxy) | ArcGIS Feature Service (NH state org) | Current | Public | Line data | Snowmobile/ATV/hiking mix; not all trails mapped. |

## Weather

| Source | Used for | License | Notes |
|---|---|---|---|
| **Open-Meteo forecast** (`api.open-meteo.com/v1/forecast`) | 7-day hourly wind, gusts, temperature, precipitation, weather code, called straight from the phone | CC BY 4.0; free for non-commercial use | Units: mph, °F, inches. Unix timestamps avoid time-zone mistakes. Cached on the phone for an hour. |
| **Open-Meteo historical archive** (`archive-api.open-meteo.com/v1/archive`) | Wind roses by month, mornings vs evenings, 5 seasons (Sept–Dec) | CC BY 4.0 | Reanalysis model winds at 10 m, not measured at the stand. |

## Map display

| Source | Layer | License |
|---|---|---|
| USGS The National Map `USGSTopo`, `USGSImageryOnly` tile services | Topo and satellite base maps | Public domain |
| USGS 3DEP ImageServer hillshade | "LiDAR relief" base map | Public domain |
| MapLibre demo glyphs (`demotiles.maplibre.org`) | Fonts for map labels | Open fonts; third-party server (could be self-hosted later) |

## Not used (yet)

- **Deer harvest per square mile by WMU** (Fish and Game deer assessment / harvest summary): the
  official PDF couldn't be downloaded from here or from GitHub. The "regional deer abundance"
  factor is skipped until `pipeline/data/abundance.yaml` is filled in from an official source.
- **USDA Cropland Data Layer, USFS forest type maps, NH Wildlife Action Plan habitat map**: candidates
  for better forest-type and mast detail; not wired in.
- **OnX or other proprietary maps**: not used. User-owned GPX/KML/GeoJSON import is a later phase.
- **Routing service for real drive times**: drive times are a labeled rough estimate from
  straight-line distance.
