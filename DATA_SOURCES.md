# Data sources

Every number in the app comes from one of these sources. The pipeline records what it actually
fetched, when, and whether it worked in `web/public/data/manifest.json` (shown in the app under
**Settings → Data and sources**). If a source fails, the feature that needs it is switched off for
that run and the failure is listed there. Nothing is filled in with made-up values.

Checked: 2026-10-08; hunting-permission and crossbow sources rechecked 2026-10-09.

## Land and boundaries

| Source | What we use | Access | Data date | Updates | License | Resolution / accuracy | Notes |
|---|---|---|---|---|---|---|---|
| **GRANIT Conservation/Public Lands** (UNH) | Property polygons, owner/agency, protection type, public-access code, boundary accuracy | ArcGIS REST, `nhgeodata.unh.edu/.../EC/Conservation/MapServer/1`, GeoJSON, paged | Published 2026-06-30 | Twice a year | Public; metadata says **"Not for legal use"** | Tract-level; each tract carries its own accuracy code (survey → poor) | 930 records intersect the Coos search rectangle; 719 tracts after clipping to the county. Code tables come from the July 2022 coding standard (`ftp.granit.unh.edu/d-cons/ConservationLandsStandard.pdf`). The `ACCESS` field is general public access, **not** hunting permission (the Connecticut Lakes Headwaters is coded "unknown"). |
| **Census TIGERweb** counties and county subdivisions | Coos County outline (GEOID 33007) and town boundaries | ArcGIS REST, `tigerweb.geo.census.gov` | Current TIGER vintage | Yearly | Public domain | Census cartographic accuracy | Used to clip properties to the county and name towns. |
| **NH Fish and Game Wildlife Management Units** | Deer WMU for each block | ArcGIS Feature Service `services8.arcgis.com/hg1B9Egwk1I5p300/.../WMU/FeatureServer/0` | Last edited 2026-08-26 | As rules change | NH Fish and Game (©2016 on layer) | Unit boundaries follow roads and rivers | WMU A is drawn as A1/A2; per the layer's description, rules for "A" cover both. Blocks crossing a line are flagged "split" and the app uses the stricter season. Fallback if the layer fails: a town table built from the digest's written boundaries. |

## Hunting rules

| Source | Used for | Date |
|---|---|---|
| 2026-27 NH Hunting Digest (eRegulations) — deer seasons, regulations, WMUs | Season dates by method and WMU, legal hours, crossbow and bag rules | Last updated 2026-08-27. The online season table had a broken layout and was reconstructed. On 2026-10-09 a separate check matched every Coos date against the online table and the season formula in rule Fis 301.03. Crossbow exceptions (age 68+, Disabled Crossbow Permit, Youth Deer Weekend, firearms and muzzleloader seasons) come from the digest PDF (`eregulations.com/assets/docs/guides/26NHHD_LR2.pdf`, pp. 7-8). **Not yet checked against the printed digest** (the app says so). The Justia copy of Fis 301.03 is out of date on crossbows; don't use it. |
| NH Admin. Rules **Res 7301.10** (DNCR parks and forests) | Hunting allowed on state parks/forests except a named list (none in Coos); 300 ft rule near occupied developed areas; tree stands | Retrieved 2026-10-08 (via Justia) |
| NH Admin. Rules **Chapter Fis 900** (Fish and Game lands), **Fis 902.02**, **Fis 903.07** | Fish and Game lands in Table 900.01 open to hunting; Connecticut Lakes Natural Area limits (no baiting, no camping, vehicles) | Chapter last amended 2017-02-24; retrieved 2026-10-08. Fish and Game proposed re-adopting Fis 900 (public hearing Dec 1, 2025). The proposal replaces Table 900.01 with an online list and renumbers some sections; whether it was adopted **couldn't be confirmed**, so the section numbers cited here may be out of date. |
| NH Parks — Connecticut Lakes Headwaters forest rules sign | Hunting permitted with restrictions on the Headwaters easement land | No date on sign; retrieved 2026-10-08 |
| NH Parks — Connecticut Lakes Headwaters road management plan | Road system open to registered road vehicles about mid-May to Dec 15, some roads gated, most gates open in moose season | Draft dated 2024-04-02, not adopted; retrieved 2026-10-10 |
| USDA Forest Service — WMNF Hunting & Shooting | Hunting allowed on all WMNF land under state rules; 150-yard and road rules | Page updated 2026-03-24 |
| USFWS — Lake Umbagog NWR Hunting | Deer hunting allowed; stand, baiting and vehicle rules | No date; retrieved 2026-10-08 |
| Dartmouth — Second College Grant hunting brochure | Public hunting allowed; no baiting; shooting distances; report deer at the gate | **Printed 2012**; the app tells you to call the College Forester |
| Dartmouth — Second College Grant web page | Vehicle passes only for Dartmouth-affiliated visitors, none Oct 1 - Nov 28; walk-in welcome any time | Retrieved 2026-10-09; doesn't mention hunting |
| NH Fish and Game — Hunting on State Lands FAQs, Where to Hunt | State lands closed to hunting (all DNCR state historic sites, Pondicherry Wildlife Refuge in Jefferson, and sites outside Coos); compact-zone rule; LCIP easements | No date; FAQ retrieved 2026-10-09 |
| NH State Parks — Weeks State Park page | The park includes the John Wingate Weeks Historic Site, so it's left "unknown" instead of verified | Retrieved 2026-10-09 |
| USFWS — Silvio O. Conte NFWR Hunting | Pondicherry Division "supports hunting for white-tailed deer", but not all parts are open; closed areas not found, so it stays "unknown" | Retrieved 2026-10-09. The refuge's NH information sheet couldn't be fetched. |

All hunting-permission rules and their sources live in `pipeline/data/access_rules.yaml`. Your own
checks go in `pipeline/data/verifications.yaml` (needs a source and a date to count as verified).
Parking areas you've confirmed on the ground go in `pipeline/data/parking.yaml`; spots within about
a mile get walk-in directions from them. On the phone, a waypoint saved as "Parking" does the same.

## Habitat, terrain and access

| Source | What we use | Access | Data date | License | Resolution | Limits |
|---|---|---|---|---|---|---|
| **USGS Annual NLCD** land cover | Forest types, regrowth/brush, openings, wetlands, developed land, edge density; forest that turned to brush/open ground over 5 years (recent logging) | MRLC GeoServer for the multi-year layer `mrlc_Land-Cover-Native_conus_year_data`: years listed by WCS DescribeCoverage (1985–2025); a chosen year is fetched through WMS `GetMap` with `TIME=` as a GeoTIFF in the official NLCD colors and decoded back to classes (each class has a unique color; checked on a real Coos sample with every pixel decoding). The coverage interface fails on year requests ("startTime is null"). NLCD 2021 via WCS (`mrlc.gov/.../NLCD_2021_Land_Cover_L48/wcs`) is the fallback. | 2025 (and 2020 for change) | Public domain | 30 m pixels | Can't see tree species, mast, understory density, or small cuts/food plots. Class 52 (Shrub/Scrub) officially includes young trees in early succession, which here is mostly logging regrowth. The year actually used is in the manifest. The USGS S3 copy is requester-pays, so it isn't used. |
| **USGS 3DEP** 1/3 arc-second seamless DEM | Bare-earth elevation for slope, aspect, landform position, saddles, benches | Cloud-optimized GeoTIFFs on USGS's public S3 bucket, `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/{n46w072}/USGS_13_{n46w072}.tif`, read in pieces with HTTP range requests. Coos needs n45w072, n46w071, n46w072 (files dated 2026-05 to 2026-08). | 2026 | Public domain | ~10 m, resampled from lidar where flown | Bare earth only: no vegetation height or understory. Doesn't model wind. |
| **USGS 3DEP 1 m lidar DEM** (standard one-meter DEM tiles) | Re-checks every candidate spot: is the bench really flat (or is there a shelf within 30 m to move it to), does the saddle really rise and fall, is the spot beside a water surface | Tiles listed through The National Map product API (`tnmaccess.nationalmap.gov/api/v1/products`, dataset "Digital Elevation Model (DEM) 1 meter"); a 240 m window around each spot read from the cloud-optimized GeoTIFFs on `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/...` | Coos is covered by `NH_CT_RiverNorthL6_2015` (and its P2 reprocessing) and `NH_Umbagog_LiDAR_2016`; newest tile with data wins | Public domain | 1 m | Spots with no 1 m coverage are labeled "not checked at 1 m". Bare earth only. First run (Oct 10, 2026): 1,069 candidates checked, 963 confirmed, 42 moved, 62 not confirmed, 2 dropped as water. |
| **USGS 3DEP** ImageServer | The map's "LiDAR relief" layer (`Hillshade Multidirectional`, full lidar detail), and a fallback elevation source for the pipeline | `elevation.nationalmap.gov/.../3DEPElevation/ImageServer/exportImage` | Service data through 2026-09-28 | Public domain | Best available, 1 m lidar where flown | Often answered 502 errors or stalled under load during testing, so it isn't the pipeline's default. |
| **NH DOT road inventory** (GRANIT `TN/RoadsForDOTViewer/MapServer/5`) | Public roads with legislative class | ArcGIS REST | Current | Public | Road centerlines | Class VI (unmaintained) roads aren't counted as drivable or used for parking. Privately owned (class 0) roads count only where at least half their length runs through land with confirmed hunting access: the Connecticut Lakes Headwaters main roads (Indian Stream, Perry Stream, Comstock Hill) are privately owned but open to registered vehicles most of the year under the easement; camp drives elsewhere aren't. A DOT segment that mostly runs along a way OpenStreetMap marks closed to vehicles is treated as closed too. Private logging roads are mostly missing. |
| **OpenStreetMap** via Overpass API | Logging/forest roads and tracks the DOT layer lacks; any way tagged `access` or `motor_vehicle` = `no`/`private` is treated as closed to vehicles | `overpass-api.de` (mirror fallback) | Live | ODbL, © OpenStreetMap contributors | Varies by mapper | Gate status and current condition are often unknown. |
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

Map tiles can be saved on the phone for use with no signal (Settings → Offline maps, or **Save map** under a property's map). USGS says its map services and data are free and in the public domain with no restrictions ([USGS FAQ](https://usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map)); saves are capped at 4,000 tiles per area to stay light on their servers.
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
