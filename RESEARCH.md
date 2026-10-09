# The evidence behind the model

Deer Scout ranks places and days. It does **not** predict the chance of seeing a deer, and no score
in the app should be read that way. This document explains what each part of the model rests on, and
labels every rule as one of:

- **Fact**: directly mapped or written in a rule (a boundary, a season date, a land cover class).
- **Supported**: the direction of the effect is backed by published research.
- **Heuristic**: a reasonable engineering choice (a threshold, a weight) that hasn't been tested.
- **Assumption**: something we believe but haven't checked.
- **Missing**: data we don't have.

The weights and thresholds are starting guesses, kept in `pipeline/data/scoring.yaml` and adjustable
in the app. They should be tuned against your own field results once you log them.

## 1. Legal access comes first, and it's not a score

Hunting permission is a gate, never a number. A property is shown as "hunting allowed" only when a
cited source says so (`pipeline/data/access_rules.yaml`). Conservation status doesn't count: the
GRANIT `ACCESS` code describes general public access, and the state's largest easement in Pittsburg is
coded "unknown" there even though the state's posted rules allow hunting. Boundaries are approximate;
GRANIT marks the data "not for legal use".

## 2. Property Quality Score (0–100)

Weighted average of five factors (default weights: habitat 35%, pressure 20%, terrain 20%, access 15%,
abundance 10%). A factor without data is left out and the remaining weights are rescaled; the share of
weight that had data is shown as "Based on X% of the model". Below 50% the score is marked provisional.

### Habitat, food and cover — *supported direction, heuristic thresholds*

From 30 m NLCD land cover inside each block:

- **Food: young regrowth, brush and openings.** Deer browse heavily in young forest after cutting
  (Tilghman 1989 documents how strongly deer browse regenerating clearcuts). NLCD's Shrub/Scrub class
  explicitly includes young trees in early succession, which in Coos County is mostly logging regrowth.
  Score rises from 2% to 15% of the block in regrowth/grass/fields, and falls off past 45%, where there's
  little daytime cover.
- **Cover: forest share.** Rises from 40% to 75% forest.
- **Edge: forest next to openings.** Meters of forest/opening boundary per hectare, 5 → 40. Interspersed
  food and cover is a long-standing principle of deer habitat; the state's own forestry guidance for
  deer wintering areas recommends small forage openings within 100 ft of softwood cover and softwood
  travel corridors between them (UNH Cooperative Extension, *Good Forestry in the Granite State*, §6.9).
- **Softwood share of the forest.** In northern New Hampshire, dense softwood (spruce-fir, hemlock, cedar)
  is what deer need to survive deep snow, and deer return to the same wintering areas; northern deer
  travel long distances to reach them (*Good Forestry in the Granite State*, §6.9). It matters most
  late in the season. Rises from 10% to 40% of the forest.
- **Developed land** above 3% cuts the score (homes mean safety zones and disturbance).

What it can't see: tree species (oak and beech mast), understory density, food plots, cuts smaller
than about an acre, or anything newer than the land cover year. NLCD classification has errors.

### Estimated hunting pressure — *supported direction, heuristic index, low confidence*

There is no hunter-count data for these properties, so this is an **estimated pressure index**, not a
measurement. It is built from access:

- In Pennsylvania state forests, about **87% of deer hunters hunted within 0.5 km of a road**, and the
  odds of a hunter being present dropped roughly threefold for each additional 500 m from a road
  (Diefenbach et al. 2005). The index uses the share of each block within 400 m (about a quarter mile) of
  a drivable road (more pressure) and the share more than 800 m away (less pressure).
- Mapped recreation trails near the block add to estimated human traffic.
- Pressure matters to deer: under heavy hunting pressure, GPS-collared bucks reduced movement and used
  smaller areas (Little et al. 2016).

Not captured: parking lots, word of mouth, posted camps, ATV traffic on unmapped roads, guided hunts,
and whether a logging road gate is open this week.

### Terrain and travel features — *heuristic*

From USGS 3DEP bare-earth elevation (lidar-derived where flown), sampled at 6 m:

- **Saddles**: low points along a ridge, found where the ground curves up one way and down the other
  (negative Gaussian curvature) on gentle slope above the surrounding landscape.
- **Benches**: flat shelves (under 8°) partway up steeper slopes (over 16° nearby).
- **Relief** and **steep ground**. More features and moderate relief score higher; a block that is mostly
  over 30° gets a penalty, because the brief asks not to reward hard terrain for its own sake.

These are shapes in the ground, not proof deer use them. Saddles and benches are widely used by
hunters as travel routes, but we found no study quantifying that in northern New Hampshire, so
everything here is labeled "candidate". Bare-earth elevation tells us nothing about vegetation, and we
don't pretend it can model wind swirling in a ravine.

### Access and huntability — *heuristic*

Room to hunt (block size, 20 → 1,500 acres on a log scale), shape (thin strips make it easy to stray over a
line), and distance from the nearest drivable road (easy within 300 m, harder out to 4 km). Remote is
not automatically better: a deer a mile and a half from the truck is a long drag.

### Regional deer abundance — *missing*

Fish and Game's main abundance index is the adult buck kill per square mile by WMU. The official report
couldn't be downloaded, so this factor is currently skipped. When `pipeline/data/abundance.yaml` is filled
from an official source, the factor turns on. It's a regional average and says nothing about a specific
block.

## 3. Daily Hunting Conditions Score (0–100)

Starts at 100 and only goes down for conditions that clearly make a sit worse or unsafe. It's
deliberately conservative because the evidence for weather effects on deer movement is weak.

- **Why so cautious**: in a GPS-collar study, short-term weather had an inconsistent effect on movement
  and moon phase had **no** effect; routine dawn/dusk movement dominated (Webb et al. 2010). In a
  Michigan study, activity peaked around sunset and just after sunrise, varied by season, fell as snow
  got deeper, and was highest between about 43 and 61°F, dropping at warmer and colder temperatures
  (Beier & McCullough 1990). So the app gives **no** moon-phase or barometric-pressure bonuses.
- **Wind** (heuristic): sustained over 10 mph −5, over 15 mph −15, over 20 mph −30. Strong wind makes it
  hard to hear and see movement and to manage scent.
- **Gusts** 28+ mph: tree-stand caution; 35+ mph: −20 and a safety warning about falling limbs.
- **Rain** (heuristic): 0.2+ inch in the window −15; 0.5+ inch −30. Light drizzle doesn't count.
- **Thunderstorms**: −40 and a lightning warning. Freezing rain: icy roads and stands warning.
- **Temperature** (supported direction, heuristic thresholds): over 65°F −5, over 72°F −10 (activity
  drops above about 61°F per Beier & McCullough 1990). Under 0°F −10 plus a frostbite warning.
- **Breeding season** (fact): NH Fish and Game says about 80% of breeding happens in roughly three weeks
  starting mid-November. The app notes this on those dates but doesn't add points; it mostly changes
  buck behavior, and the goal here is any legal deer.
- **Spot wind**: if a block has scouting spots and none of them suit the day's wind, the day's conditions
  for that block drop by 15.

Morning = first three legal hours; evening = last three; all day = sunrise−30 min to sunset+30 min (NH
legal hours). Sunrise/sunset use the NOAA solar equations.

## 4. Scouting spots (0–100)

Each saddle or bench inside a legal block is scored: base 55 (saddle) or 50 (bench), plus points for
being within 150 m of a forest/opening edge, being in forest, and a 300 m–1.5 km walk from a road; minus
points within 150 m of a road, within 100 m of a trail, within 100 m of the mapped boundary, or on very
steep ground. Confidence is low or medium; these are places to check for sign, not promises.

**Wind at a spot**: deer cross a ridge through a saddle and travel along the contour on a bench, so each
spot has a likely travel direction. A wind that blows **across** that route carries your scent off it;
one that blows **along** it carries your scent down the route to approaching deer. The app flags winds
within 45° of perpendicular as good, near that as so-so, and along the route as wrong. It also checks the
walk in from the nearest road: wind in your face is good, wind at your back is flagged.

Limits: forecast wind is regional (about 3 km grid cells at 10 m height). Thermals flow downhill in the
morning and uphill in the evening, and hollows swirl. The app says so on every forecast.

## 5. Historical wind

Five hunting seasons (Sept–Dec) of hourly reanalysis wind from Open-Meteo, at a handful of points
across the county. Directions are summarized with circular statistics (a mean of 350° and 10° is 0°, not
180°), weighted by speed, with near-calm hours counted separately. Morning = 5–9 AM, evening = 2–6 PM.

## References

- Beier, P., & McCullough, D. R. (1990). Factors influencing white-tailed deer activity patterns and
  habitat use. *Wildlife Monographs*, 109.
- Diefenbach, D. R., Finley, J. C., Luloff, A. E., Stedman, R., Swope, C. B., Zinn, H. C., & San Julian,
  G. J. (2005). Bear and deer hunter density and distribution on public land in Pennsylvania. *Human
  Dimensions of Wildlife*, 10(3), 201–212. https://doi.org/10.1080/10871200591003445
- Little, A. R., Webb, S. L., Demarais, S., Gee, K. L., Riffell, S. K., & Gaskamp, J. A. (2016). Hunting
  intensity alters movement behaviour of white-tailed deer. *Basic and Applied Ecology*, 17(4), 360–369.
  https://doi.org/10.1016/j.baae.2015.12.003
- Tilghman, N. G. (1989). Impacts of white-tailed deer on forest regeneration in northwestern
  Pennsylvania. *Journal of Wildlife Management*, 53(3), 524–532.
- Webb, S. L., Gee, K. L., Strickland, B. K., Demarais, S., & DeYoung, R. W. (2010). Measuring fine-scale
  white-tailed deer movements and environmental influences using GPS collars. *International Journal of
  Ecology*, 2010, 459610. https://doi.org/10.1155/2010/459610
- New Hampshire Fish and Game Department. White-tailed Deer (species page): breeding timing.
  https://www.wildlife.nh.gov/wildlife-and-habitat/species-occurring-nh/white-tailed-deer
- UNH Cooperative Extension et al. *Good Forestry in the Granite State*, §6.9 Deer Wintering Areas.
  https://extension.unh.edu/goodforestry/html/6-9.htm
- USGS/MRLC. National Land Cover Database class definitions (Annual NLCD Collection 1 user guide v1.2,
  2026). https://www.mrlc.gov/
