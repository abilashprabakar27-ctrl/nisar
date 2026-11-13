# HANDOFF: NISAR Change Explorer (Sanjay's part)

Read this first. Written 14 Nov 2026 (hackathon day 1, ~1 AM IST). Owner: Sanjay (NISAR science + processing, night team). Team lead: Abilash. Server: Arshad. Frontend: Arya, Vishal. Data checks: Nevedha.

## Project
NASA Space Apps 2026 "Dancing with the SARs". Map web app: pick a place, ask what changed, get before/after, labelled change map, headline number, charts, confidence, check vs NASA OPERA, honest limits. Source of truth docs (PDFs, not in repo): Final Plan, 48-Hour Sprint Plan, Final Architecture (Abilash, 14 Nov).
Core workflow to validate: FLOOD/WETLAND change from NISAR GCOV. Everything else experimental/optional. Freeze features Sun 7 PM IST; submit Sun 11 PM IST.

## Sanjay's scope only
Flood methods (`methods/`), verification (`workers/verify.py`), availability rules (`workers/check.py`), window reader (`workers/fetch.py`), API contract (`api/schemas.py`) and endpoints (`api/`), reference/data collection (`scripts/`, `data/`). Not his: React frontend, tiles, assistant, drivers, stories, partner radar (SAOCOM/RCM).

## Repo (local /home/user/nisar-change-explorer; remote github.com/sanjayvasudevan-c/nasa_project, branch main)
- `api/` FastAPI: `/places /availability /analyses /analyses/{id} /analyses/{id}/events (SSE) /analyses/{id}/agreement`; `schemas.py` (ChangeResult + `validate_result` honesty gate), `jobs.py` (`run_analysis` = the ONE seam still returning the labelled sample), `cache.py` (sha1 key incl. METHOD_VERSION floods-0.2.0).
- `methods/floods.py` `detect_change(...)`: Lee 5x5 filter, median composites, dB log-ratio, Otsu per tail (fallback 3 dB, noted in limits), water if after < -18 dB, flooded vegetation (label 3) only when HV given and HV not dropping, 1 ha min patch, masks, persistence-based confidence (High needs >=2 after passes), insufficient data if <2 passes a side or >30% masked.
- `workers/check.py` `assess_availability`, `lowest_quality` (mixed quality -> lowest level); `workers/verify.py` `validate` (IoU/precision/recall vs OPERA, check points); `workers/fetch.py` `read_window`, `fetch_passes` (range reads, pass cache).
- `scripts/site_check.py` (ASF catalogue -> `data/catalog/*.csv`), `scripts/download.py` (full-file downloader, token from env), `scripts/fetch_reference.py` (OPERA DSWx manifest -> `data/reference/manifest.csv`).
- `docs/ARCHITECTURE.md` (mine, older), `docs/site_check.md`, `docs/golden_sample_runbook.md`, `docs/RUN.md`. LICENSE Apache-2.0, Dockerfile, docker-compose.yml. `graphify-out/GRAPH_REPORT.md` + `graph.json` = code graph (AST only, docs not semantically extracted).
- Tests: `python3 -m pytest -q` -> 60 passed (all on SYNTHETIC data).
Graph highlights: god nodes `read_window`, `assess_availability`, `detect_change`, `PassRef`, `validate_result`; `read_window` and `assess_availability` are cross-community bridges; no import cycles.

## Chosen demo sites (from live ASF catalogue; flood events UNCONFIRMED, splits are seasonal guesses)
1. Sylhet haor, BD: track 69 asc, frame 14, 12 passes, 81 GB.  2. Tonle Sap, KH (flooded-forest demo): track 83 asc, frame 8, 11 passes, 20.6 GB.  3. Mamiraua, Amazon: track 161, 13 passes, 23.4 GB (water falling).  4. Nile Sudd: track 50 desc, 11 passes, 18.2 GB (HH-only on 5 dates).  Spare: Atchafalaya (track 84 desc, ~30 deg lat).
Calibrated record starts 2026-06-17; permanent gap 2026-07-27..08-10 (never fill). One Tonle Sap pass (2026-10-29) has processing version P05036 vs P05023 for the others: compare before keeping.
OPERA matches: 124 rows in `data/reference/manifest.csv` (nearest DSWx S1/HLS date per NISAR date, gap_days).

## What is DONE
Everything above, committed, tests green, pushed. Layout aligned to Final Architecture.

## What is NOT done / blockers
1. REAL NISAR DATA NOT DOWNLOADED. In the cloud sandbox the saved Earthdata token was injected malformed by the proxy ("Malformed Authorization header", 4 tries; token itself was valid). Download on the user's own machine: `export EARTHDATA_TOKEN=...; python scripts/download.py --area mekong_tonlesap --track 83 --out ~/nisar_data` (then nile_sudd track 50). Earthdata account exists (user sanjay0925, Public User, Hydrologic Cycle); authorize ASF apps + EULAs. A token was pasted in chat earlier: it must be revoked/regenerated.
2. HDF5 layout assumptions UNVERIFIED on a real file (confirmed in ASF docs: `/science/LSAR/GCOV/grids/frequencyA/{HHHH,HVHV}`, UTM/polar CRS). Assumed: `xCoordinates`, `yCoordinates`, `projection` (attr `epsg_code`), pixel-centre coords, float32 LINEAR power, NaN nodata, `mask` coding 0 invalid/255 fill/1-5 valid (if wrong, nodata_fraction ~1.0; use apply_mask=False). Check first with h5py visititems.
3. Thresholds/constants (-18 dB water ceiling, 3 dB fallback, 1 dB HV tolerance, 10 deg slope, ENL=1) are PLACEHOLDERS tuned on synthetic scenes. No accuracy number may be claimed until tuned on one real area and validated on SEPARATE hand-labelled points vs OPERA.
4. `api/jobs.py run_analysis` still returns the golden SAMPLE (source "sample"); wire `fetch_passes -> detect_change -> validate` in. `/availability` is not bbox-filtered (catalogue CSV has no coordinates; AOIs live in `scripts/site_check.py`).
5. Missing: JRC permanent-water, Copernicus DEM slope/shadow, WorldCover masks (hosts not allowlisted in sandbox); OPERA water maps and optical photos not downloaded (only the manifest); check points (~100) not labelled; `scripts/fetch_reference.py --download` untested (requests may drop Bearer on redirect; use asf_search/earthaccess session instead); Redis/RQ not used (threads); Docker untested; edge shrink bias (~2 px/edge, 60 ha flood -> ~47 ha) must be stated in limits.

## Next steps (in order)
1. Download Tonle Sap t83 (+ Nile Sudd t50) locally; run the h5py layout check; fix `workers/fetch.py` assumptions.
2. Follow `docs/golden_sample_runbook.md` -> `golden_sample_real.json` (label it live/saved, not sample).
3. Tune thresholds on one area; download OPERA DSWx for matching dates; hand-label ~100 points in QGIS (`data/reference/checkpoints_template.csv`) NOT used for tuning; run `workers.verify.validate`; publish real numbers (even if weak).
4. Wire `run_analysis`; add bbox-aware availability; pre-compute demo areas into cache (`saved`).
5. Write science note + validation page text; limits wording ("likely", never "confirmed"); handover note format: Completed / In progress / Blocked by / Next action / Files / Evidence.
Rules: sample data is always labelled sample; no secrets in repo; stuck 30 min -> post in help thread.

## Working conventions used so far
Small commits per stage with `Co-Authored-By: Claude` trailer; sub-agents per task with disjoint file ownership (opus for science decisions, sonnet for implementation, haiku for scripts); token-frugal; verify agent output by running tests before committing.
