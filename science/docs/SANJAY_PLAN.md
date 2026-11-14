# Sanjay's plan (science + processing), status 14 Nov 2026

Source: Sprint Plan (Sanjay rows) + Final Architecture. Freeze Sun 7 PM IST, submit Sun 11 PM IST.
Rule: no accuracy claim beyond what the tables below show; sample data stays labelled "sample"; wording "likely".

## Status

| # | Task | State | Evidence |
|---|------|-------|----------|
| 1 | Download GCOV: Tonle Sap t83 (11 passes), Nile Sudd t50 (11) | DONE | `~/nisar_data`, 37 GB |
| 2 | Real HDF5 layout check, window reader on real files | DONE | names, EPSG:32648, mask coding match; 24 km window in ~2 s |
| 3 | Golden sample on real data (composites, masks, labels, areas) | DONE | `scripts/golden_tonlesap.py` |
| 4 | Masks: JRC permanent water, DEM slope | DONE (Tonle Sap window only) | `data/reference/tonlesap/` |
| 5 | Tune on one half, validate on the other vs OPERA | DONE (one site) | WATER_DB -18 -> -12 dB; east half IoU 0.55 -> 0.71 |
| 6 | Wire `run_analysis` (fetch -> detect -> OPERA check) | DONE | `workers/pipeline.py`; other areas fall back to labelled sample |
| 7 | OPERA agreement in `/agreement` (`_verify`) | DONE (Tonle Sap) | IoU 0.72, precision 0.90, recall 0.79, 51% of window compared |
| 8 | Hand-labelled check points (90) | NOT DONE, needs a human | `data/reference/tonlesap/checkpoints_tonlesap.csv` |
| 9 | Newest-pass-date function for "Watch this place" | DONE | `workers/check.py` |
| 10 | HH / HV / colour-mix images for the result | DONE (function; not yet served by the API) | `workers/render.py` |
| 11 | Run Nile Sudd (HH-only) | DONE, UNVALIDATED | 215 ha became water, 1,534 ha receded, no masks, no OPERA check, confidence Medium |
| 12 | Per-pass change series for the timeline chart | TODO | |
| 13 | Driver evidence (rain, river share, low-lying share) | TODO, needs IMERG | |
| 14 | One-page science note (inputs, steps, outputs, limits) | TODO | |
| 15 | Bbox-aware `/availability`; pre-compute demo areas into cache | TODO | |

## Known limits to state in the app and note
- Threshold tuned on one site and one season; accuracy elsewhere unknown.
- OPERA is a reference, not ground truth; before-flood HLS is cloudy, only ~51% of the window is comparable.
- Flooded forest brightens in HH (double bounce) and can look like no change; edges shrink ~2 px.
- Data gap 2026-07-27 to 2026-08-10 is never filled; 2026-10-29 Tonle Sap pass has a different processing version.
- Check-point accuracy (independent) not measured yet.

## Order for the rest
1. Check points labelled (human) -> score. 2. Nile Sudd run. 3. Series + drivers. 4. Science note. 5. Cache demo areas, bbox availability. 6. Sunday 10 AM: re-check every number in the app against saved results.
