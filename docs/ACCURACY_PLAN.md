# Accuracy plan (branch sanjay/accuracy)

Goal: make the water-change method measurably better (precision, recall, IoU) and finish the two remaining stories (Morigaon, Kanpur), with numbers that survive questions from judges.

## Rules that do not bend
1. OPERA is a second opinion, not ground truth. Never tune on it and then quote it as proof.
2. Tune on one part of the area, report on a part never used for tuning (west half / east half; neighbouring window).
3. Human-labelled check points are the real accuracy number. The labels come from a person, never from us.
4. Every method change bumps `METHOD_VERSION`, keeps `pytest` green, and is logged in `docs/accuracy_log.md` with before and after numbers. If it does not beat the baseline on held-out data, it is not merged.
5. Report weak numbers too. Sample data is always labelled sample.

## Facts that shape the plan
- Local NISAR data exists for Tonle Sap (track 83) and Nile Sudd (track 50) only. OPERA reference exists for Tonle Sap only.
- No Earthdata login is set, so Morigaon and Kanpur cannot be downloaded until a token is provided.
- Known weak spots in the team method (`backend/app/science/change.py`, `verify.py`): thresholds fixed from Patna only; agreement counts permanent water, which inflates it; no permanent-water (JRC) or terrain (DEM/HAND) mask; no wet-field filter.

## Stages
| Stage | Work | Output | Needs |
|---|---|---|---|
| 0 | Plan, branch, code map (graphify) | this file | nothing |
| 1a | Collect resources: official challenge page and resources, SAR flood-mapping literature, reference datasets | `docs/RESOURCES.md` | web |
| 1b | Evaluation harness: run the team method on Tonle Sap with a spatial tune/test split, report IoU / precision / recall vs OPERA, baseline first | `backend/scripts/eval_tonlesap.py`, `docs/accuracy_log.md` | local data |
| 1c | Story prep: ASF availability for Morigaon and Kanpur, tracks, dates, file sizes, download list | `docs/STORIES_PREP.md` | ASF search (public) |
| 2 | Method improvements, one at a time, each judged on the held-out half: fix agreement to new water only; JRC permanent-water mask; DEM slope / height-above-river mask; wet-field (rice) filter; per-site-type thresholds | changes in `change.py`, `verify.py`, tests | stage 1b |
| 3 | Run Morigaon and Kanpur, OPERA check where a tile exists | story results, numbers | Earthdata token |
| 4 | Final table: baseline vs improved, per area, with limits; update docs and deck numbers | `docs/accuracy_log.md` | all |

## Human steps (cannot be automated)
- Provide an Earthdata token for stage 3 (`! export EARTHDATA_TOKEN='...'`), and revoke it afterwards.
- Label about 90 check points on a clear Sentinel-2 image without looking at our answer. This is the only accuracy number that does not depend on OPERA.
