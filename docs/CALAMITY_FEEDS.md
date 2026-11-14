# Recent calamity feeds and NISAR coverage

Tested 2026-11-15 (all calls made live from this machine). Tool: `backend/scripts/recent_events.py`.
Anything not called is marked UNVERIFIED.

## 1. Source table

| Source | URL tested | Auth | Rate limit | Result | Key fields |
|---|---|---|---|---|---|
| NASA EONET v3 | `https://eonet.gsfc.nasa.gov/api/v3/events?days=45&status=all&category=floods,severeStorms,landslides` | none | response header `X-RateLimit-Limit: 60` (window not stated, UNVERIFIED) | WORKS, 200, ~6 s unfiltered (4 MB, mostly wildfires), small when category-filtered | `id`, `title`, `categories[].id`, `closed`, `sources[]` (GDACS/JTWC/NOAA_NHC), `geometry[]` (`date`, `type` Point or Polygon, `coordinates`). No alert level. Quirk: some polygons have vertices as [lat, lon] (Thailand, Mexico), so validate and swap. Landslides category exists but had 0 events in 45 d. |
| GDACS event list | `https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=FL;TC;LS&fromdate=...&todate=...&alertlevel=green;orange;red` | none | none observed (UNVERIFIED) | WORKS, 200, ~2 s, GeoJSON. Default page 100. Paging via `pagenumber` repeated rows, so de-dupe by id. Empty result is a non-JSON body (LS returned that: 0 landslides). | `eventtype` (EQ/TC/FL/WF/LS...), `eventid`, `name`, `alertlevel` (Green/Orange/Red), `alertscore`, `fromdate`/`todate`, `country`, `severitydata`, feature `bbox` and Point/Polygon geometry, `url.report` |
| GDACS RSS | `https://www.gdacs.org/xml/rss.xml` (and `rss_7d.xml`) | none | none observed | WORKS, 200, 273 items / 835 KB (rss.xml); rss_7d.xml also 200 (item count not checked) | `gdacs:eventtype`, `gdacs:alertlevel`, `gdacs:fromdate`, `geo:Point`, `gdacs:bbox` (lonmin lonmax latmin latmax), `link`, `gdacs:cap`. Same data as the API; the API is easier. |
| USGS earthquakes (FDSN) | `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=...&minmagnitude=5` | none | none observed; response `cache-control: public, max-age=60`; per-query result cap not tested (UNVERIFIED) | WORKS, 200, ~1.8 s, 278 M5+ events in 45 d | `id`, `properties.mag`, `place`, `time` (epoch ms), `alert` (PAGER green/yellow/orange/red, often null), `sig`, `tsunami`, `url`, point geometry `[lon, lat, depth]` |
| ReliefWeb API | `https://api.reliefweb.int/v2/disasters?appname=...` | REQUIRES an approved appname (request form; not instant). Unapproved appname gives 403. v1 gives 410 (decommissioned) | UNVERIFIED | BLOCKED. Not used by the script. | not tested past the error |
| Copernicus EMS Rapid Mapping | `https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/?limit=100&ordering=-eventTime` (single: `.../public-activations/?code=EMSR933`) | none | none observed | WORKS, 200, ~2 s, 268 activations total. `public-activations/` without `code` returns 400 "Activation code parameter is mandatory". Undocumented dashboard backend, so it may change. | `code` (EMSRnnn), `name`, `category` (Flood, Storm, Earthquake, Wildfire, Volcanic activity), `eventTime`, `activationTime`, `centroid` (WKT point), `countries`, `closed`, `gdacsId`, `n_aois`, `n_products`. Page: `https://rapidmapping.emergency.copernicus.eu/EMSR933` (200). In the last 45 d only 3 flood/EQ activations, no storm or landslide. |
| Dartmouth/Colorado Flood Observatory | `https://floodobservatory.colorado.edu/wiki/FloodRecords` | none | n/a | PAGE WORKS, but NOT A RECENT FEED: the public archive download is v0.9.0, January 1985 to December 2023 (Zenodo DOI 10.5281/zenodo.19288170); the page table shown ran to Feb 2024. No machine API found. Old URLs (`/Archives/index.html`) 404. | n/a |
| NASA Global Landslide Catalog | `https://maps.nasa.gov/arcgis/rest/services/Landslides/Global_Landslide_Catalog/FeatureServer/0` | n/a | n/a | UNVERIFIED. Host `maps.nasa.gov` did not connect (curl 000); `data.nasa.gov/resource/dd9e-wu2v.json` 404; `gpm.nasa.gov/landslides/index.html` 404. Do not rely on it. | n/a |

Sample events (all real, from the 45 days to 2026-11-15):

| Source | Sample 1 | Sample 2 | Sample 3 |
|---|---|---|---|
| EONET | `EONET_26330` Flood in Myanmar, 2026-11-09 (polygon, GDACS 1104280) | `EONET_25964` Tropical Cyclone Murasu, 2026-11-01 (JTWC) | `EONET_25728` Super Typhoon In-fa, 2026-10-23 (JTWC) |
| GDACS | `TC1001345` Tropical Cyclone ARNAB-26, 2026-10-26, Red, India | `FL1104225` Flood in Nepal, 2026-10-11, Green | `TC1001346` Tropical Cyclone MURASU-26, 2026-11-01, Red, India |
| USGS | `us7000ty84` M5.5 northern Mid-Atlantic Ridge, 2026-11-14, PAGER green | `us7000ty7d` M5.2 State of Yap, 2026-11-14 | `us7000ty6n` M5.2 off the west coast of northern Sumatra, 2026-11-14 |
| CEMS | `EMSR935` Flood in Alicante-Valencia, Spain, 2026-10-19 | `EMSR934` Earthquake in Los Santos, Panama, 2026-10-09 (gdacsId EQ1570339) | `EMSR933` Flood in Crete, Greece, 2026-10-01 |
| ReliefWeb | none (blocked, needs appname) | | |

Notes on overlap: EONET floods are GDACS events (the title carries the GDACS id and `sources[].id = GDACS`), and EONET storms come from JTWC/NOAA NHC. Combined GDACS plus EONET gives roughly one record per flood, so `recent_events.py` merges them by GDACS id, then by same category, within 3 days and within 100 km (300 km for storms).

## 2. Script

```
PY=/home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python
$PY backend/scripts/recent_events.py --days 45 --category flood
$PY backend/scripts/recent_events.py --days 45 --coverage           # flood + storm, ~1-2 min first run
$PY backend/scripts/recent_events.py --days 45 --coverage --json
```

Schema: `id, source, title, category, start_date, lat, lon, bbox [W,S,E,N], alert_level, url` (plus `also_in` for merged records, and `nisar` with `--coverage`). Point events get a ~25 km box. Results are cached 30 min in the system temp dir (`nisar_recent_events_cache`); `--no-cache` bypasses. A source that errors is skipped and reported on stderr. A run on 2026-11-15 gave GDACS 112, EONET 85, USGS 278, CEMS 3 raw events, 278 after de-dupe and filtering (169 earthquakes, 78 floods, 31 storms; 0 landslides).

Coverage method: `asf_search.geo_search(dataset="NISAR", processingLevel="GCOV", start="2026-06-17", end=today, intersectsWith=bbox)`. Passes are grouped by (path number, flight direction); the best track is the one with the most passes. "Before" = pass date earlier than the event start date, "after" = pass date on or after it. Verdicts: `enough for 2+2` (2+ before and 2+ after), `waiting for after-pass` (2+ before, fewer than 2 after, event 30 days old or less; a next pass is expected 12 days after the last), `none` (otherwise, including no coverage). Gap flag: set if the event falls inside 27 Jul to 10 Aug, or the baseline would need passes from before the gap (fewer than 2 before-passes after 10 Aug).

Caveats: event start date is the feed date (GDACS `fromdate`, EONET first geometry), not the true peak. Storm boxes are 25 km around the first feed position, so open-ocean storms show "none" (19 storms had zero passes) and this says nothing about the landfall area. GDACS and EONET can place the same flood differently (for example GDACS Portugal 1104276 is at 37.2N 8.2W while the EONET polygon is at 33.1N 16.3W), so check the location before running. The GCOV hits are products ASF lists as `NISAR_L2_UR_GCOV` (UR prefix); whether other GCOV products are missing is UNVERIFIED.

## 3. Recent events with NISAR coverage (flood and storm, last 45 days)

Of 109 flood/storm records: 49 enough for 2+2, 38 waiting for after-pass, 22 none (19 of those are open-ocean storms with zero passes). The gap (27 Jul to 10 Aug) did not matter for any flood or storm event in this window except the closed storm record `EONET:EONET_25457` (Tropical Cyclone Agueda, 2 passes before, south Indian Ocean); every other event is at least 12 weeks past the gap with 7+ before-passes. NISAR repeat is 12 days on every best track seen.

### 3a. Enough for 2+2 (49)

| start | cat | title | id (+merged) | alert | lat, lon | best track | before / after | newest pass | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-01 | storm | Tropical Cyclone Murasu | `EONET:EONET_25964` | closed | 11.40, 86.20 | 127A | 9 / 2 | 2026-11-13 | enough for 2+2 |
| 2026-10-26 | storm | Tropical Cyclone ARNAB-26 | `GDACS:TC1001345` | red | 16.40, 81.80 | 55A | 10 / 2 | 2026-11-09 | enough for 2+2 |
| 2026-10-25 | storm | Tropical Cyclone Arnab | `EONET:EONET_25729` | closed | 15.60, 89.30 | 98A | 10 / 2 | 2026-11-11 | enough for 2+2 |
| 2026-10-22 | flood | Flood in Argentina | `GDACS:FL1104250` +1 | green | -28.36, -59.26 | 10D | 9 / 2 | 2026-11-05 | enough for 2+2 |
| 2026-10-21 | storm | Tropical Cyclone JOSEPHINE-26 | `GDACS:TC1001342` | green | 40.00, -65.80 | 11D | 9 / 2 | 2026-11-05 | enough for 2+2 |
| 2026-10-20 | flood | Flood in India | `GDACS:FL1104248` +1 | green | 15.45, 80.17 | 156A | 9 / 2 | 2026-11-04 | enough for 2+2 |
| 2026-10-19 | flood | Flood in France | `GDACS:FL1104243` +1 | green | 50.48, 1.73 | 173A | 9 / 2 | 2026-11-05 | enough for 2+2 |
| 2026-10-19 | flood | Flood in Peru | `GDACS:FL1104262` | green | -3.57, -80.46 | 104A | 9 / 2 | 2026-10-31 | enough for 2+2 |
| 2026-10-19 | flood | Flood in Jamaica | `GDACS:FL1104249` | green | 17.95, -76.35 | 119A | 8 / 2 | 2026-11-01 | enough for 2+2 |
| 2026-10-19 | flood | Flood in Ukraine | `GDACS:FL1104242` +1 | green | 44.43, 34.09 | 108D | 9 / 2 | 2026-10-31 | enough for 2+2 |
| 2026-10-18 | flood | Flood in Thailand | `GDACS:FL1104241` +1 | green | 18.13, 100.15 | 105D | 9 / 2 | 2026-11-05 | enough for 2+2 |
| 2026-10-18 | flood | Flood in Guatemala | `GDACS:FL1104244` +1 | green | 15.38, -90.24 | 134A | 9 / 2 | 2026-11-02 | enough for 2+2 |
| 2026-10-18 | flood | Flood in South Korea | `GDACS:FL1104240` +1 | green | 37.28, 127.44 | 133D | 9 / 2 | 2026-11-02 | enough for 2+2 |
| 2026-10-16 | flood | Flood in Nicaragua | `GDACS:FL1104237` +1 | green | 14.03, -83.38 | 69D | 15 / 3 | 2026-11-05 | enough for 2+2 |
| 2026-10-15 | flood | Flood in Malaysia | `GDACS:FL1104239` +1 | green | 3.21, 101.30 | 76D | 9 / 2 | 2026-10-31 | enough for 2+2 |
| 2026-10-13 | flood | Flood in Uruguay | `GDACS:FL1104238` +1 | green | -32.27, -58.08 | 10D | 9 / 2 | 2026-11-05 | enough for 2+2 |
| 2026-10-13 | flood | Flood in Libya | `GDACS:FL1104231` +1 | green | 32.90, 13.18 | 51D | 9 / 2 | 2026-10-29 | enough for 2+2 |
| 2026-10-12 | flood | Flood in Türkiye | `GDACS:FL1104230` +1 | green | 41.12, 29.00 | 100A | 9 / 2 | 2026-10-31 | enough for 2+2 |
| 2026-10-12 | flood | Flood in Syria | `GDACS:FL1104233` +1 | green | 35.14, 40.21 | 50D | 9 / 2 | 2026-11-01 | enough for 2+2 |
| 2026-10-11 | flood | Flood in Uganda | `GDACS:FL1104255` | green | 0.13, 30.00 | 50D | 9 / 2 | 2026-11-06 | enough for 2+2 |
| 2026-10-11 | flood | Flood in Ecuador | `GDACS:FL1104245` | green | -1.55, -80.43 | 112D | 8 / 2 | 2026-10-31 | enough for 2+2 |
| 2026-10-11 | flood | Flood in Nepal | `GDACS:FL1104225` +1 | green | 28.00, 84.63 | 98A | 9 / 3 | 2026-11-11 | enough for 2+2 |
| 2026-10-10 | flood | Flood in Jordan | `GDACS:FL1104232` +1 | green | 32.19, 37.45 | 71A | 9 / 2 | 2026-10-29 | enough for 2+2 |
| 2026-10-09 | flood | Flood in Costa Rica | `GDACS:FL1104227` +1 | green | 10.03, -84.13 | 170D | 8 / 3 | 2026-11-05 | enough for 2+2 |
| 2026-10-09 | flood | Flood in Indonesia | `GDACS:FL1104224` +1 | green | -0.58, 100.61 | 76D | 9 / 2 | 2026-10-29 | enough for 2+2 |
| 2026-10-09 | flood | Flood in Panama | `GDACS:FL1104228` +1 | green | 8.19, -79.19 | 40D | 8 / 3 | 2026-11-07 | enough for 2+2 |
| 2026-10-08 | flood | Flood in Slovenia | `GDACS:FL1104221` +1 | green | 45.82, 13.84 | 80D | 9 / 2 | 2026-11-01 | enough for 2+2 |
| 2026-10-07 | storm | Tropical Cyclone SIMON-26 | `GDACS:TC1001335` | orange | 21.50, -110.30 | 27D | 8 / 3 | 2026-11-07 | enough for 2+2 |
| 2026-10-07 | storm | Hurricane Isaias | `EONET:EONET_25063` | closed | 22.00, -94.10 | 84D | 9 / 2 | 2026-10-30 | enough for 2+2 |
| 2026-10-07 | flood | Flood in Italy | `GDACS:FL1104220` +1 | green | 43.46, 11.14 | 144A | 8 / 3 | 2026-11-03 | enough for 2+2 |
| 2026-10-07 | flood | Flood in Ecuador | `GDACS:FL1104251` | green | 0.40, -78.45 | 76A | 9 / 2 | 2026-10-31 | enough for 2+2 |
| 2026-10-07 | flood | Flood in China | `GDACS:FL1104223` +1 | green | 19.20, 109.60 | 47D | 9 / 2 | 2026-10-27 | enough for 2+2 |
| 2026-10-07 | flood | Flood in Morocco | `GDACS:FL1104226` +1 | green | 31.88, -6.47 | 95D | 9 / 2 | 2026-11-01 | enough for 2+2 |
| 2026-10-07 | flood | Flood in Venezuela | `GDACS:FL1104219` +1 | green | 10.23, -66.38 | 61A | 9 / 2 | 2026-11-01 | enough for 2+2 |
| 2026-10-06 | storm | Tropical Cyclone ISAIAS-26 | `GDACS:TC1001334` | orange | 37.50, -84.00 | 55D | 9 / 2 | 2026-11-02 | enough for 2+2 |
| 2026-10-06 | flood | Flood in Chile | `GDACS:FL1104217` +1 | green | -36.83, -73.05 | 97D | 8 / 2 | 2026-10-30 | enough for 2+2 |
| 2026-10-06 | flood | Flood in Argentina | `GDACS:FL1104218` +1 | green | -31.40, -58.02 | 10D | 8 / 3 | 2026-11-05 | enough for 2+2 |
| 2026-10-06 | flood | Flood in Paraguay | `GDACS:FL1104222` +1 | green | -25.50, -54.83 | 82D | 9 / 2 | 2026-10-29 | enough for 2+2 |
| 2026-10-05 | flood | Flood in Thailand | `GDACS:FL1104169` +1 | green | 18.27, 98.97 | 112A | 7 / 4 | 2026-11-12 | enough for 2+2 |
| 2026-10-05 | flood | Flood in Mexico | `GDACS:FL1104191` +1 | green | 17.67, -100.00 | 19A | 8 / 3 | 2026-11-13 | enough for 2+2 |
| 2026-10-03 | flood | Flood in Brazil | `GDACS:FL1104229` | green | -29.76, -57.09 | 10D | 8 / 3 | 2026-11-05 | enough for 2+2 |
| 2026-10-03 | flood | Flood in Guatemala | `GDACS:FL1104213` +1 | green | 14.50, -90.56 | 134A | 8 / 3 | 2026-11-02 | enough for 2+2 |
| 2026-10-03 | flood | Flood in Mauritania | `GDACS:FL1104215` +1 | green | 15.93, -11.52 | 102A | 8 / 3 | 2026-10-31 | enough for 2+2 |
| 2026-10-02 | flood | Flood in Honduras | `GDACS:FL1104209` +1 | green | 14.55, -87.69 | 33A | 7 / 3 | 2026-10-26 | enough for 2+2 |
| 2026-10-02 | flood | Flood in Nicaragua | `GDACS:FL1104210` +1 | green | 13.40, -85.91 | 105A | 8 / 3 | 2026-10-31 | enough for 2+2 |
| 2026-10-01 | flood | Flood in Portugal 1104212 | `EONET:EONET_25031` | closed | 40.39, -7.52 | 52D | 8 / 3 | 2026-10-27 | enough for 2+2 |
| 2026-10-01 | flood | Flood in Crete, Greece | `CEMS:EMSR933` | activated | 35.23, 24.98 | 65D | 8 / 3 | 2026-10-28 | enough for 2+2 |
| 2026-10-01 | flood | Flood in Brazil | `GDACS:FL1104216` +1 | green | -27.22, -49.64 | 2A | 8 / 2 | 2026-11-01 | enough for 2+2 |
| 2026-10-01 | flood | Flood in Malaysia | `GDACS:FL1104207` | green | 5.94, 116.08 | 97A | 8 / 3 | 2026-10-30 | enough for 2+2 |

### 3b. Waiting for after-pass (newest 12 of 38; run the script for the rest)

| start | cat | title | id (+merged) | alert | lat, lon | best track | before / after | newest pass | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-10 | flood | Flood in Myanmar | `GDACS:FL1104280` +1 | green | 21.51, 98.01 | 112A | 10 / 1 | 2026-11-12 | waiting for after-pass |
| 2026-11-08 | flood | Flood in Argentina | `GDACS:FL1104277` +1 | green | -31.71, -60.57 | 161A | 10 / 0 | 2026-11-04 | waiting for after-pass |
| 2026-11-07 | flood | Flood in Portugal | `GDACS:FL1104276` +1 | green | 37.24, -8.15 | 44A | 11 / 0 | 2026-11-01 | waiting for after-pass |
| 2026-11-07 | flood | Flood in Venezuela | `GDACS:FL1104275` +1 | green | 10.18, -67.92 | 162A | 11 / 0 | 2026-11-04 | waiting for after-pass |
| 2026-11-07 | flood | Flood in Syria | `GDACS:FL1104274` +1 | green | 34.45, 40.92 | 122D | 10 / 0 | 2026-11-06 | waiting for after-pass |
| 2026-11-07 | flood | Flood in Israel | `GDACS:FL1104273` +1 | green | 32.33, 34.86 | 151D | 11 / 0 | 2026-11-03 | waiting for after-pass |
| 2026-11-07 | flood | Flood in Iraq | `GDACS:FL1104272` +1 | green | 36.19, 44.01 | 93D | 11 / 0 | 2026-11-06 | waiting for after-pass |
| 2026-11-06 | flood | Flood in Thailand | `GDACS:FL1104283` +1 | green | 10.38, 99.01 | 40A | 10 / 1 | 2026-11-07 | waiting for after-pass |
| 2026-11-06 | flood | Flood in Vietnam | `GDACS:FL1104271` +1 | green | 21.01, 105.85 | 148D | 11 / 0 | 2026-11-03 | waiting for after-pass |
| 2026-11-06 | flood | Flood in Dominican Republic | `GDACS:FL1104281` +1 | green | 19.34, -70.95 | 83D | 11 / 0 | 2026-10-29 | waiting for after-pass |
| 2026-11-06 | flood | Flood in Sri Lanka | `GDACS:FL1104284` | green | 7.12, 79.92 | 84A | 11 / 1 | 2026-11-11 | waiting for after-pass |
| 2026-11-05 | flood | Flood in Canada | `GDACS:FL1104282` | green | 50.32, -122.81 | 106A | 11 / 0 | 2026-10-31 | waiting for after-pass |

Not shown: 22 `none` records (19 open-ocean storms with zero passes; also El Salvador flood 2026-10-15 with 1 after-pass, and two ocean typhoon points with only June passes).

## 4. Recommendation: first three events for the full analysis

All three have 8 or more before-passes and 2 or more after-passes on a single track, so a 2+2 stack is available now.

1. Flood in Crete, Greece, 2026-10-01 (`CEMS:EMSR933`, lat 35.23, lon 24.98, track 65D, 8 before / 3 after, last before 2026-09-22, first after 2026-10-04). Reason: it is a Copernicus EMS activation, so authoritative flood-extent products exist to score the NISAR result against, and the before/after bracket is tight (9 days before, 3 days after).
2. Tropical Cyclone ARNAB-26, 2026-10-26 (`GDACS:TC1001345`, India, GDACS Red, lat 16.4, lon 81.8, track 55A, 10 before / 2 after, last before 2026-10-16, first after 2026-10-28, newest 2026-11-09). Reason: the only Red-alert storm with coverage on both sides, and 55A passed 2 days after the feed date. Caveat: the feed gives a position, not a landfall footprint, so confirm the area before running. Murasu (`GDACS:TC1001346`, 2026-11-01, same coast, track 156A) moves from waiting to 2+2 once the pass expected about 2026-11-16 is processed, and would give a second event in the same region.
3. Uruguay River floods, 2026-10-03 to 2026-10-13 (GDACS `FL1104229` Brazil -29.76/-57.09, `FL1104218` Argentina -31.40/-58.02, `FL1104238` Uruguay -32.27/-58.08, all track 10D, 8-9 before / 2-3 after, newest pass 2026-11-05). Reason: three GDACS flood records on one river share one track, so a single frame set covers the whole reach; flat floodplain terrain suits SAR water mapping; 3 after-passes allow a recession check. These are GDACS Green and not CEMS-activated, so there is no authoritative extent (validate against Sentinel-2 or Sentinel-1).

Runners-up with 2+2: Nepal flood 2026-10-11 (`GDACS:FL1104225`, track 98A, 9/3; terrain shadow and layover risk in the foothills), Thailand flood 2026-10-05 (`GDACS:FL1104169`, track 112A, 7 before / 4 after), Costa Rica and Panama 2026-10-09 (8/3).

Not yet usable: Valencia flood 2026-10-19 (`CEMS:EMSR935`, track 66D, 10 before / 1 after, next pass expected about 2026-11-09 but none in ASF as of 2026-11-15). It is the best CEMS-validated candidate once an after-pass appears, so re-run `--coverage` in a few days.

## 5. Blockers and open items

- ReliefWeb needs an approved appname (apply at the ReliefWeb API docs); skipped.
- No usable recent landslide feed: GDACS LS and EONET landslides returned 0 in the window, and the NASA Global Landslide Catalog endpoints were unreachable (UNVERIFIED).
- Dartmouth Flood Observatory has no recent machine-readable feed.
- CEMS dashboard API is undocumented and may change without notice.
- Storm coverage needs a landfall footprint (not provided by the feeds) to be meaningful.
