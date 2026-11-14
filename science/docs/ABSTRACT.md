# NISAR Change Explorer: abstract and architecture

NASA Space Apps 2026, "Dancing with the SARs". Status as of 14 Nov 2026.

## Abstract

When a river bursts its banks or a lake swells with the monsoon, the first question is simple: where did the water go? Radar can answer it through cloud and at night, but the data is huge and hard to read, so most people never get to use it.

NISAR Change Explorer is a web app that makes one slice of that data easy to use. You pick a place on a map and ask what changed. The app compares a few radar passes from before with a few from after, draws a map of where water likely appeared or likely went away, gives the area in hectares, says how confident it is, and checks itself against NASA's own water maps (OPERA). It works from NISAR's L-band GCOV data, which has been calibrated since 17 June 2026.

We built it to be honest before it is impressive. It says "likely became water", never "confirmed". When there are fewer than two good passes on either side, or more than 30% of the area has to be masked out (steep ground, permanent lakes), it says "insufficient data" and gives no number. Sample data is always labelled as sample. The weeks NISAR has no data (27 July to 10 August) are never filled in.

What we can show so far: on the Tonle Sap flood window in Cambodia, our water map agrees with NASA's OPERA map with an overlap (IoU) of 0.72, precision 0.90 and recall 0.79. About half the window could be compared, because the before-flood optical images are cloudy. On a neighbouring window to the south, the same settings did much worse (overlap 0.37, precision 0.39), so we do not claim the method works everywhere. We have not yet measured accuracy against hand-labelled points, and our second site, the Nile Sudd in South Sudan, has no independent check yet. Both facts are stated in the app.

Beyond the map, the app lines the change up against NASA GPM IMERG daily rainfall, so a user can see whether heavy rain came before the water. Each possible driver is marked Likely, Possible or Not supported, and always as interpretation, not measurement.

## Architecture

### The idea in one picture

```
 Browser  (React, MapLibre, charts)                      <- frontend team
    |  HTTPS + JSON, and Server-Sent Events for progress
 FastAPI server  (api/app.py)
    |-- /places        place search (OpenStreetMap Nominatim)
    |-- /availability  "what can we answer here?"   no imagery downloaded, 1-3 s
    |-- /analyses      start a job, returns a job_id at once
    |-- /analyses/{id}            the result (checked by validate_result)
    |-- /analyses/{id}/events     progress steps
    |-- /analyses/{id}/agreement  check against OPERA
    |-- (planned) /analyses/{id}/drivers   rainfall and terrain evidence
    |
    |-- jobs.py   background threads, one job per analysis
    |-- cache.py  results saved by sha1 key, OPERA comparison saved beside them
    |
 Science layer
    |-- workers/check.py     which passes are usable; the insufficient-data rule
    |-- workers/fetch.py     read only the study-area window from big GCOV files
    |-- methods/floods.py    the change detection itself
    |-- workers/pipeline.py  glues fetch -> detect -> check against OPERA
    |-- workers/verify.py    overlap, precision, recall; check-point scoring
    |-- workers/series.py    one row per pass for the timeline chart
    |-- workers/drivers.py   rainfall (IMERG) and low-flat-terrain evidence
    |-- workers/render.py    HH, HV and colour-mix images
    |
 Data
    |-- NISAR GCOV (ASF DAAC)         main data; HDF5, 2 to 7 GB per pass
    |-- OPERA DSWx-S1 / HLS           referee: independent water maps
    |-- JRC water, Copernicus DEM,    helpers: masks for permanent water,
    |   ESA WorldCover                steep slopes, land type
    |-- GPM IMERG daily rain          drivers: evidence for "why"
    |-- data/catalog/*.csv            precomputed pass tables and rain series
```

### Design rules we kept

1. **The science is pure.** Arrays go in, a result and a label raster come out. No network and no files inside the detection code, so we can test it on synthetic scenes where we know the right answer.
2. **All reading and writing lives in one layer** (`workers/fetch.py`). If a data source breaks, detection is untouched.
3. **Every result says where it came from**: `live`, `saved` or `sample`. A sample is never passed off as live, and a sample is never promoted to saved.
4. **Fail soft.** If a source is slow or down, show the saved result and say so.
5. **No secrets in the repo or the browser.** The Earthdata login exists only on the server, as an environment variable.
6. **An honesty gate.** `validate_result` in `api/schemas.py` rejects a result that breaks the wording and labelling rules, before it can be served.

### How an analysis runs

1. **Checking.** Find passes for the area. Keep only one track, one direction and one frame, because mixing geometries makes false change. If processing levels are mixed, the result takes the lowest one.
2. **Fetching.** Read just the window the user asked for (25 x 25 km at most) from each GCOV file using HTTP range reads. The files are far too big to download whole. Windows are cached on disk.
3. **Preparing.** Apply the NISAR validity mask and smooth speckle with a 5x5 Lee filter. Mask permanent water (JRC) and steep slopes (Copernicus DEM).
4. **Detecting.** Build a "before" composite and an "after" composite, each the median of 2 to 3 passes. Take the log-ratio in decibels. Threshold each tail with Otsu's method, falling back to a fixed 3 dB if the data gives no clear split (and say so in the limits). Call a pixel water if the after-image is darker than the water threshold. Drop patches under 1 hectare. Flooded vegetation is a separate label, used only when the HV channel is available and not dropping.
5. **Verifying.** Compare "likely became water" with OPERA's new-water pixels. Report overlap, precision, recall and what fraction of the window could be compared at all.
6. **Explaining.** Add the confidence level and its reason, the area per label, the limits, and where each piece of data came from.

Confidence is High only when the change shows on at least two "after" passes. A single pass is capped at Lower. Under two good passes on either side, or over 30% masked, the status is `insufficient_data` and no area is reported.

### The API contract (frozen with the server)

`ChangeResult` carries: status, source, bbox, the before and after passes used, area in hectares per label (likely became water, likely water receded, likely flooded vegetation, no change), confidence and its reason, masked fraction, limits, result map and a plain-language message. Errors give a plain message and a next step: `area_too_large` (422), `no_data`, `insufficient_data` (status in the body), `upstream_unavailable` (falls back to saved) and `unknown_job` (404).

### Drivers: why did it change?

Each driver gets a label (Likely, Possible, Not supported) and an evidence block, and is always marked as interpretation.

| Driver | Evidence | State |
|---|---|---|
| Heavy rain | GPM IMERG daily rain over the area for the 14 days before the change, against the same series' own season | built, 13 areas of rain data downloaded |
| Terrain | Share of the window that is low-lying and flat (Copernicus DEM) | built |
| River, fire, earthquake, human activity | GloFAS, FIRMS, USGS, OpenStreetMap | not started; outside our scope |

### Testing

83 automated tests, all on synthetic or fixture data: a planted flood, speckle only, a tiny patch, masks, mixed quality, a pair that straddles the data gap, API behaviour through a test client, and the rain and terrain rules. Real-data checks are separate and reported below.

## Results and honest limits

| Item | Result |
|---|---|
| Tonle Sap, Cambodia (track 83, 11 passes) | About 10,500 ha likely became water, 340 ha likely receded, 240 ha likely flooded vegetation. Confidence Medium. |
| Agreement with OPERA on that window | Overlap 0.72, precision 0.90, recall 0.79. 51% of the window comparable. |
| Same method on a window just south | Overlap 0.37, precision 0.39, recall 0.89. It over-predicts water there. |
| Nile Sudd, South Sudan (track 50, 11 passes) | About 170 ha likely became water, 1,200 ha likely receded. HH only. 6.6% masked. Confidence Medium. **Unvalidated.** |
| Per-pass timeline | Tonle Sap water rises from about 2,000 ha on 25 July to a peak near 11,200 ha on 5 October. Single-pass rows, so context only. |
| Rainfall (IMERG) | 153 days, 1 June to 31 October, 13 areas. Monthly totals follow the expected monsoon pattern. |

What we do not know, and say so:

- The thresholds were tuned on one site in one season. Accuracy elsewhere is unknown, and the southern Tonle Sap window shows it can be much worse.
- OPERA is a reference, not ground truth. Before-flood optical images are cloudy, so only about half the window is compared.
- Flooded forest can get brighter in HH from double-bounce, and then looks like no change. Smoothing also shrinks patch edges by about two pixels, so area is slightly under-counted.
- The data gap from 27 July to 10 August is permanent. One Tonle Sap pass (29 October) has a different processing version, so we keep it out of the compared set.
- Accuracy against hand-labelled check points has not been measured. The 90 points still need a human labeller, and they must never be used to set thresholds.
- Sylhet and Mamiraua are not downloaded or run. Only two sites are real.
- Rainfall and terrain are context, not proof of cause.

## Files to know

`docs/PLAN.md` the task plan, `docs/SANJAY_PLAN.md` live status, `docs/HANDOFF.md` handover, `docs/RUN.md` how to run the server, `methods/floods.py` the detection, `workers/pipeline.py` the pipeline, `api/schemas.py` the contract and honesty gate, `data/catalog/` pass tables, rain series and per-pass series.
