# Architecture

Reconstructed and extended from the Final Plan (§9) and Sprint Plan (§F). Items marked **[added]** are not in the source plans; **[verify]** means confirm on the first real file.

## 1. Principles
1. Science is pure: arrays in, `ChangeResult` + label raster out. No network, no files. Testable with synthetic scenes.
2. All I/O lives in one layer (`science/io.py`, **[added]**) so data access can fail or be swapped without touching detection.
3. Every result carries `source` (`live` | `saved` | `sample`) and its provenance. Sample is never described as live.
4. Fail soft: slow or down source -> saved result -> labelled sample.
5. Secrets exist only on the server (proxy-injected token); never in the repo or browser.

## 2. Components
```
Browser (React, MapLibre, Chart.js)
   | HTTPS JSON
FastAPI server/app.py ── jobs.py (threaded queue) ── cache.py (sha1 files)
   |                         |
   |                  science/io.py  ── ASF/CMR catalogue (search, no auth)
   |                         |        └─ NISAR GCOV .h5 (HTTP range reads, bearer token)
   |                  science/availability.py -> detect_change.py -> validate.py
   └─ data/catalog/*.csv (precomputed pass tables), data/samples/ (golden sample)
```

| Module | Responsibility | Depends on |
|---|---|---|
| `science/schema.py` | Frozen contract dataclasses | none |
| `science/availability.py` | Which passes are usable; insufficient-data rule | schema |
| `science/detect_change.py` | Composite, dB diff, thresholds, masks, 1 ha filter, confidence | schema, availability |
| `science/validate.py` | IoU/precision/recall vs OPERA and check points | numpy |
| `science/io.py` **[added]** | Subset one AOI window from a remote GCOV file -> array + geotransform | h5py/fsspec |
| `server/*` | Jobs, cache, endpoints, limits | science |
| `scripts/site_check.py` | Catalogue query -> `data/catalog/*.csv` | asf_search |

## 3. Data flow
**Availability (1-3 s):** bbox -> filter `pass_counts.csv` (or live ASF search) by same track/direction/frame -> counts, dates, quality, gap flag. No imagery downloaded.

**Analyze (job):** `finding passes` -> pick 2-3 before + 2-3 after of one geometry -> `fetching` (parallel subset reads) -> `comparing` (`detect_change`) -> `saving` (cache + overlay). Returns `job_id` at once; client polls `/jobs/{id}`.

**Subset reads [added]:** GCOV files are 1.9-6.8 GB, so never download whole files. Use HTTP range reads through `h5py` + `fsspec` and read only the window for the AOI. Expected layout **[verify]**: `/science/LSAR/GCOV/grids/frequencyA/HHHH` (+ `HVHV`), with `xCoordinates`, `yCoordinates` and an EPSG `projection`. Stop and re-plan if reads are too slow (fallback: precomputed AOI subsets saved under `data/raw/`, gitignored).

**Alignment [added]:** passes of one track/frame share the grid, so no resampling is needed within a geometry; `io.py` asserts identical shape/transform and rejects mixed geometry rather than resampling.

## 4. Contract and states
- `ChangeResult` fields: see `science/schema.py` (status, source, bbox, before/after `PassRef`s, `area_ha` by label, confidence + reason, masked_fraction, limits, result_map, message).
- Job states: `queued -> running(step) -> done | error`. Cache hit returns `done` at once with step `saved`.
- Errors (plain message + next step): `area_too_large` (422, >25x25 km), `no_data`, `insufficient_data` (200, status in body), `upstream_unavailable` (falls back to saved/sample), `unknown_job` (404).
- Cache key: `sha1(bbox, before/after dates, question)`; samples are never promoted to `saved`.

## 5. Science decisions (defaults in code as named constants)
HH linear power, 5x5 speckle filter, median composite, change at |diff| >= 3 dB with water < -18 dB, patches < 1 ha dropped, insufficient if < 2 passes per side or > 30% masked. Known bias **[added]**: smoothing erodes patch edges ~2 px, so area is slightly under-estimated (a planted 60 ha flood returns ~42 ha); state it in limits. Flooded-vegetation (brightness *rise* under canopy) is not a separate label yet; treat as experimental, HV/HH ratio later.
Thresholds are placeholders for synthetic data and **must be tuned on one real area, then validated on different points** (Final Plan §11).

## 6. Performance and fallback
Targets from the Final Plan §6 are design goals, not measured. Measure subset-read time per AOI first; if a full analysis exceeds ~2 min, ship precomputed demo AOIs (`saved`) and run live analysis as quick preview.

## 7. Security
Earthdata token lives only in the environment proxy/server env; `.env` is gitignored; CORS is open for the demo only (restrict in production).

## 8. Testing
Unit tests on synthetic scenes (planted flood, speckle-only, tiny patch, masks, mixed quality, gap straddle). Server tests via TestClient. Real-data acceptance = golden sample vs OPERA overlap/precision/recall, reported honestly.

## 9. Known gaps
Real flood events unconfirmed; quality levels inferred from catalogue metadata only; mixed processing versions in some stacks; no web UI in this repo; no tile server (image overlay first).
