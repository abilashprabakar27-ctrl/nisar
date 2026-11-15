# Accuracy: final results page

Branch sanjay/accuracy. App method: `water-change-v5-reliability-checks` (`backend/app/store.py`). The detection pixels are those of v4b; v5 only changed the confidence rules.
Every number below is copied from the file named beside it. OPERA and Sentinel-2 are second opinions, not ground truth. IoU / precision / recall throughout.

## (a) Every measured result

Intervals marked "review" come from docs/REVIEW.md: bootstrap over 2 km blocks, within-window sampling only, not yet re-derived by a committed script; re-derive before quoting. They do not capture the much larger spread between places (0.04 to 0.78).

### NISAR new water vs OPERA new water (our method)

| Test | Region | IoU / precision / recall | Status |
|---|---|---|---|
| East half of the main window (lead number) | Tonle Sap east half (72% comparable) | 0.68 [0.64-0.72] / 0.88 / 0.75 (review) | Not used in the west sweeps, but seen when the final setting was picked. It adjoins the tuning half and uses the same passes. Not an independent test. |
| West half | Tonle Sap west half (29% comparable) | 0.69 [0.60-0.74] / 0.90 / 0.74 (review) | Tuning half. |
| Whole main window | 103.90-104.12 E, 13.05-13.27 N (51% comparable) | 0.68 [0.64-0.71] / 0.88 / 0.74 (review) | Includes the tuning half; not a headline. |
| Neighbour | window 0.22 deg south | 0.55 [0.30-0.72] / 0.58 / 0.91 (review) | Not a held-out number: it was used as a guard when the setting was chosen. Its west half scores 0.01 and its east half 0.78 (backend/data/final.json, review). |
| Fresh window, south | 0.44 deg south (12.61-12.83 N), never tuned on | 0.04 [0.02-0.07] / 0.05 / 0.91 (review) | Cleanest number in the project, and a failure. |
| Fresh window, east | 0.22 deg east (104.12-104.34 E) | not claimed | Only the 21% strip next to the main window could be scored (0.78 / 0.86 / 0.89). Elsewhere in that window the comparable area was near zero, and where OPERA does exist there, 60% of our new water is not water in OPERA on the same day (review). We do not count this as a success. |
| Sentinel-2 check, neighbour | Sentinel-2 MNDWI new water (40% comparable) | 0.14 / 0.15 / 0.83 | Report only. Sentinel-2 is independent of NISAR but shares its before image with the OPERA before map. |
| Sentinel-2 check, Kanpur | Sentinel-2 MNDWI new water (97% comparable), track 77 D | 0.03 / 0.14 / 0.03 | Report only. |
| Sentinel-2 check, Tonle Sap main, Morigaon | not scored: no usable after-flood scene | none | |
| Kanpur story | OPERA tile T44RMQ (1 Oct), 68 ha new water | 58 ha (86%) of our new-water pixels are water in OPERA, new or not | Sentinel-2 marks only 14% of the same pixels as new water. We cannot say this is new water. Share we missed not measured. |
| Kanpur story, all water incl. permanent | OPERA, same window | IoU 0.40 | Not a test of change. |
| Morigaon story | none (no OPERA S1 tile near the dates) | 3,299 ha new water | not measured |

Per-window class balance differs a lot (reference new water is about 38% of the comparable area on main, 3% on the neighbour, 1% on fresh south, review), so do not rank windows by IoU alone.

### Side experiment, C-band, not our method

Sen1Floods11 is C-band Sentinel-1 (VV/VH) with human labels and a single-date water task. It is not NISAR, not change detection and not our method, so none of these numbers belong beside the table above. It tested one idea (calibrating the cut-off on each scene's permanent water) and the idea did not beat a fixed cut-off, so it was not shipped. Never read it as "validated on Sen1Floods11" (docs/SEN1FLOODS11_RESULTS.md).

| Test | Result | Source file |
|---|---|---|
| Leave-one-event-out over 10 events, fixed cut-off | pooled IoU 0.462 [0.410, 0.509] VH / 0.417 VV | docs/SEN1FLOODS11_RESULTS.md |
| Best scene-calibrated variant (youden, event scale) | pooled IoU 0.466 [0.415, 0.509] VH / 0.395 VV; ties the fixed cut-off, intervals overlap | docs/SEN1FLOODS11_RESULTS.md |
| One sealed event (Bolivia, 15 chips; sealed by protocol) | fixed VH 0.581, calibrated VH 0.653; wide intervals, one event, many variants compared; not evidence | docs/SEN1FLOODS11_RESULTS.md |

Notes that matter for reading the tables:
- The older "0.92" is the lenient score (permanent water counted) and is not quoted. The strict score counts only "became water" (docs/accuracy_log.md).
- Before the work, the whole window was 0.60 / 0.85 / 0.68 (docs/accuracy_log.md). The gain came from a 1 dB before-water margin and requiring persistence.
- The main window is about half scored. The other half is the lake itself, which OPERA's before map masks; nearly all the land, and 97% of our new water there, is scored (review). OPERA's before layer contains almost no open water in that window, so the score is mostly "our new water vs OPERA open water after, on land".
- The neighbour was used as a guard when the 1 dB margin was chosen. It is not a held-out number.
- Kanpur 86% is the share of our pixels that are water in OPERA on a tiny area; new water (68 ha) equals receded water (68 ha) there (docs/STORIES_RESULTS.md).
- Sentinel-2 scenes are up to 6 days from the radar passes and have their own errors. On the neighbour only 40% of the window was comparable (docs/accuracy_log.md).
- Differences of a few IoU points are within noise. The review measured it: about +/- 0.04 on the east half and about +/- 0.2 on the neighbour.

## (b) What worked and what failed

Worked (docs/accuracy_log.md):
- Requiring before-water to be 1 dB darker than the cut-off: recall up on every region and IoU up on west and east (east +0.09 IoU); neighbour IoU did not rise.
- Requiring new water to be dark on every after pass: precision up by about 3-5 points, some recall lost.
- Scoring only "became water". High confidence needs 75% of our new-water pixels to be water in OPERA's after map; this does not test that the water is new.

Failed or no gain (docs/accuracy_log.md unless stated):
- Scene-calibrated thresholds (docs/GENERALISATION.md section 3): cut-offs came out about 3 dB darker on every Tonle Sap window; main-window recall fell from 0.75 to 0.53-0.63 and IoU fell 0.07-0.16; the neighbour and Kanpur did not improve. Not implemented.
- Side experiment (C-band, not our method): scene calibration ties a fixed cut-off on average and is not shown to beat it (docs/SEN1FLOODS11_RESULTS.md). It tests the recipe, not a NISAR threshold.
- JRC permanent-water mask: no gain (the "permanent" water in this lake region is partly the new seasonal water).
- DEM slope change: no effect.
- Per-scene Otsu thresholds: IoU 0.53 vs 0.65 on the tuning half.
- Hysteresis / region growing: precision fell more than recall rose.
- Looser HV or HH cut-offs: worse. Variance filter and larger minimum patch: little or negative.
- Land-cover removal of cropland: east IoU fell by 0.336 (docs/GENERALISATION.md).
- Open failures: the south neighbour (Sentinel-2 precision 0.15) and the cropland plains south of Tonle Sap (301k px predicted vs 15k in OPERA, IoU 0.04; docs/GENERALISATION.md). Cause not identified; flooded rice is a hypothesis only.

## (c) The confidence rules and the validation block, in plain words

Confidence has three levels: High, Medium, Lower. The confidence levels are rule-based labels, not probabilities. No level has ever been compared with an outcome it was not fitted to. (The app wording is being reworded; see docs/REVIEW.md section 4.2.)
- High needs 75% of our new-water pixels to be water in OPERA's after map (this does not test that the water is new), and must survive three extra checks below. Persistence is true by construction in the shipped method, so it adds no evidence.
- Pass brightness check: if one pass is more than 1.5 dB brighter or darker than the others over stable land, that pass cannot support High (cap Medium) and the app says so.
- Cropland check: if more than 50% of the detected new water lies on cropland and no independent reference confirms it (OPERA missing or under 75%), confidence is not above Lower, with the reason shown.
- Validation status: every result carries a `validation` block that lists what was measured (Tonle Sap window compared with OPERA), the known failures, whether this place was checked (only inside the one Tonle Sap window; anywhere else "not validated", which caps confidence at Medium) and `human_labelled_accuracy: "not measured"`. The small-area cap of 100 ha is kept.

Two things to say plainly about these rules (docs/accuracy_log.md, docs/REVIEW.md):
- The 100 ha, 1.5 dB and 50% cropland limits are provisional. They were set from single cases; one was changed after seeing a result, which raised the tuned window from Lower to High. They must be revisited when a labelled score exists.
- The cropland refinement was made after seeing a result. The first v5 run put the best-validated window (Tonle Sap main, IoU 0.68, 53% of new water on cropland) at Lower; the cap was then changed to apply only when no independent reference confirms the new water. This is a post hoc choice, not an independent result. Its effect is that the tuned window moved from Lower to High.
- The checks are weak by design: the brightness check did not reproduce the Kanpur 3 dB brightening on land-only pixels (23 Sep read +0.54 dB), the cropland rule misses the south neighbour (6% cropland, Sentinel-2 precision 0.15), and with two passes per side the brightness check needs a 3 dB gap.

Current levels on the cached real cases after v5 (docs/accuracy_log.md; the first-run table was written before the cropland refinement): Tonle Sap main window High (now the only High, and it is the window the method was tuned on; High is reached because OPERA agrees there, which is what the tuning optimised), Tonle Sap south neighbour Medium, Kanpur Medium, Morigaon Lower, fresh south window Lower.

This table is in-sample: every threshold was set from these same cases, so it demonstrates the rules and is not a test of them. Medium currently spans "probably fine" and "85% wrong by the optical check" (the south neighbour gets Medium with Sentinel-2 precision 0.15 and no rule catches it).

## (d) What has NOT been measured

- Accuracy against human-labelled points. The field reads "not measured". Hand-labelled points are the only accuracy number that does not depend on OPERA or Sentinel-2 (docs/STORIES_RESULTS.md).
- Any L-band benchmark. No open, pixel-labelled L-band flood dataset was found; every key found is C-band, optical or analyst maps (docs/DATASETS.md). Sen1Floods11 is C-band and says nothing about NISAR thresholds or about the accuracy of our method.
- Most places. Accuracy is compared with OPERA on one Tonle Sap window and three nearby or story windows, one season, one track. Where the method fails cannot yet be predicted (docs/GENERALISATION.md).
- Sentinel-2 on the Tonle Sap main window and on Morigaon (no usable after-flood scene). OPERA on Morigaon (no S1 tile near the dates).
- Recent events (Crete EMSR933, Cyclone ARNAB-26, Uruguay River): chosen as candidates in docs/CALAMITY_FEEDS.md, not run.
- The Nile Sudd has no OPERA check.

## (e) Summary

On the half of the Tonle Sap main window that was not used for parameter sweeps, our map overlaps OPERA's new-water map with IoU 0.68 [0.64-0.72], precision 0.88, recall 0.75 (interval from the review, bootstrap over 2 km blocks, re-derive before quoting). That half adjoins the half we tuned on and was seen when the final setting was picked, so it is not an independent test. The method does not transfer reliably. On a window to the south the IoU is 0.04. On the window in between, the score is 0.55 [0.30-0.72] but that is an average of 0.01 in its west half and 0.78 in its east half, and Sentinel-2 puts precision at 0.15. Only a 21% strip of the window to the east could be scored (0.78 / 0.86 / 0.89); in the rest, the comparable area was near zero, so we do not claim a success there. At Kanpur the Sentinel-2 check found far more new water than the radar map (recall 0.03). Scene-calibrated thresholds, JRC masks, DEM slope, Otsu and hysteresis did not fix this. Because the true accuracy elsewhere is unknown, the app lowers or caps its confidence where it knows the method has failed, and states that no human-labelled accuracy exists. The confidence limits are provisional and one was adjusted after seeing a result. A person should treat a map as a lead to check, not a measurement.
