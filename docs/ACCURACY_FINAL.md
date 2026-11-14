# Accuracy: final results page

Branch sanjay/accuracy. App method: `water-change-v5-reliability-checks` (`backend/app/store.py`). The detection pixels are those of v4b; v5 only changed the confidence rules.
Every number below is copied from the file named beside it. OPERA and Sentinel-2 are second opinions, not ground truth. IoU / precision / recall throughout.

## (a) Every measured result

| Test | Reference | Region | IoU / precision / recall | Source file |
|---|---|---|---|---|
| Tonle Sap window (headline) | OPERA new water | whole window, 103.90-104.12 E, 13.05-13.27 N | 0.68 / 0.88 / 0.74 (51% comparable) | docs/accuracy_log.md |
| Tuning half | OPERA new water | Tonle Sap west half | 0.69 / 0.90 / 0.74 (29% comparable) | docs/accuracy_log.md |
| Held-out half | OPERA new water | Tonle Sap east half | 0.68 / 0.88 / 0.75 (72% comparable) | docs/accuracy_log.md |
| Neighbour | OPERA new water | window 0.22 deg south | 0.55 / 0.58 / 0.91 | docs/accuracy_log.md |
| Fresh window, south | OPERA new water | 0.44 deg south (12.61-12.83 N), never tuned on | 0.04 / 0.05 / 0.91 | docs/GENERALISATION.md |
| Fresh window, east | OPERA new water | 0.22 deg east (104.12-104.34 E), never tuned on | 0.78 / 0.86 / 0.89 | docs/GENERALISATION.md |
| Sentinel-2 check, neighbour | Sentinel-2 MNDWI new water (40% comparable) | window 0.22 deg south | 0.14 / 0.15 / 0.83 | docs/accuracy_log.md |
| Sentinel-2 check, Kanpur | Sentinel-2 MNDWI new water (97% comparable) | Kanpur, track 77 D | 0.03 / 0.14 / 0.03 | docs/accuracy_log.md |
| Sentinel-2 check, Tonle Sap main, Morigaon | Sentinel-2 | not scored: no usable after-flood scene | none | docs/accuracy_log.md |
| Kanpur story | OPERA tile T44RMQ (1 Oct) | 68 ha new water | 58 ha (86%) of our new water is water in OPERA; share we missed not measured | docs/STORIES_RESULTS.md |
| Kanpur story, all water incl. permanent | OPERA | same window | IoU 0.40 (not a test of change) | docs/STORIES_RESULTS.md |
| Morigaon story | none (no OPERA S1 tile near the dates) | 3,299 ha new water | not measured | docs/STORIES_RESULTS.md |
| Sen1Floods11 recipe test | Human labels, C-band Sentinel-1 (not NISAR), leave-one-event-out over 10 events | fixed cut-off, VH | pooled IoU 0.462 [0.410, 0.509] VH / 0.417 VV | docs/SEN1FLOODS11_RESULTS.md |
| Sen1Floods11, best scene-calibrated (youden, event scale) | same | same | pooled IoU 0.466 [0.415, 0.509] VH / 0.395 VV | docs/SEN1FLOODS11_RESULTS.md |
| Sen1Floods11, sealed unseen event (Bolivia, 15 chips) | same | fixed VH / calibrated VH | 0.581 / 0.653, wide intervals, one event | docs/SEN1FLOODS11_RESULTS.md |

Notes that matter for reading the table:
- The older "0.92" is the lenient score (permanent water counted) and is not quoted. The strict score counts only "became water" (docs/accuracy_log.md).
- Before the work, whole window was 0.60 / 0.85 / 0.68 (docs/accuracy_log.md). The gain came from a 1 dB before-water margin and requiring persistence.
- The neighbour was used as a guard when the 1 dB margin was chosen, so its number is slightly optimistic (docs/accuracy_log.md).
- Kanpur 86% is precision on a tiny area; new water (68 ha) equals receded water (68 ha) there (docs/STORIES_RESULTS.md).
- Sentinel-2 scenes are up to 6 days from the radar passes and have their own errors. On the neighbour only 40% of the window was comparable (docs/accuracy_log.md).
- Differences of a few IoU points are within noise: one season, one track (docs/accuracy_log.md, docs/GENERALISATION.md).

## (b) What worked and what failed

Worked (docs/accuracy_log.md):
- Requiring before-water to be 1 dB darker than the cut-off: recall and IoU up on every region (east +0.09 IoU).
- Requiring new water to be dark on every after pass: precision up by about 3-5 points, some recall lost.
- Scoring only "became water" and requiring a strict OPERA confirmation for High confidence.

Failed or no gain (docs/accuracy_log.md unless stated):
- Scene-calibrated thresholds (docs/GENERALISATION.md section 3): cut-offs came out about 3 dB darker on every Tonle Sap window; main-window recall fell from 0.75 to 0.53-0.63 and IoU fell 0.07-0.16; the neighbour and Kanpur did not improve. Not implemented.
- Sen1Floods11 recipe test: scene calibration ties a fixed cut-off on average and is not shown to beat it (docs/SEN1FLOODS11_RESULTS.md). This is C-band and tests the recipe, not a NISAR threshold.
- JRC permanent-water mask: no gain (the "permanent" water in this lake region is partly the new seasonal water).
- DEM slope change: no effect.
- Per-scene Otsu thresholds: IoU 0.53 vs 0.65 on the tuning half.
- Hysteresis / region growing: precision fell more than recall rose.
- Looser HV or HH cut-offs: worse. Variance filter and larger minimum patch: little or negative.
- Land-cover removal of cropland: east IoU fell by 0.336 (docs/GENERALISATION.md).
- Open failures: the south neighbour (Sentinel-2 precision 0.15) and the cropland plains south of Tonle Sap (301k px predicted vs 15k in OPERA, IoU 0.04; docs/GENERALISATION.md). Cause not identified; flooded rice is a hypothesis only.

## (c) The confidence rules and the validation block, in plain words

Confidence has three levels: High, Medium, Lower. The app never says "confirmed" (docs/accuracy_log.md, v5 section).
- High needs persistence, a strict OPERA confirmation of at least 75%, and must survive three extra checks below.
- Pass brightness check: if one pass is more than 1.5 dB brighter or darker than the others over stable land, that pass cannot support High (cap Medium) and the app says so.
- Cropland check: if more than 50% of the detected new water lies on cropland and no independent reference confirms it (OPERA missing or under 75%), confidence is not above Lower, with the reason shown.
- Validation status: every result carries a `validation` block that lists what was measured (Tonle Sap window vs OPERA: IoU 0.68, precision 0.88, recall 0.74), the known failures, whether this place was checked (only inside the one Tonle Sap window; anywhere else "not validated", which caps confidence at Medium) and `human_labelled_accuracy: "not measured"`. The small-area cap of 100 ha is kept.

Two things to say plainly about these rules (docs/accuracy_log.md):
- The 100 ha, 1.5 dB and 50% cropland limits are provisional. They come from two observed failures and were not tuned to improve any output. They must be revisited when a labelled score exists.
- The cropland refinement was made after seeing a result. The first v5 run put the best-validated window (Tonle Sap main, IoU 0.68, 53% of new water on cropland) at Lower; the cap was then changed to apply only when no independent reference confirms the new water. This is a post hoc choice, not an independent result.
- The checks are weak by design: the brightness check did not reproduce the Kanpur 3 dB brightening on land-only pixels (23 Sep read +0.54 dB), the cropland rule misses the south neighbour (6% cropland, Sentinel-2 precision 0.15), and with two passes per side the brightness check needs a 3 dB gap.

Current levels on the cached real cases after v5 (docs/accuracy_log.md; the first-run table was written before the cropland refinement, so Tonle Sap main is no longer capped by cropland): Tonle Sap south neighbour Medium, Kanpur Medium, Morigaon Lower, fresh south window Lower.

## (d) What has NOT been measured

- Accuracy against human-labelled points. The field reads "not measured". Hand-labelled points are the only accuracy number that does not depend on OPERA or Sentinel-2 (docs/STORIES_RESULTS.md).
- Any L-band benchmark. No open, pixel-labelled L-band flood dataset was found; every key found is C-band, optical or analyst maps (docs/DATASETS.md). Sen1Floods11 is C-band and says nothing about NISAR thresholds.
- Most places. Accuracy is measured on one Tonle Sap window and three nearby or story windows, one season, one track. Where the method fails cannot yet be predicted (docs/GENERALISATION.md).
- Sentinel-2 on the Tonle Sap main window and on Morigaon (no usable after-flood scene). OPERA on Morigaon (no S1 tile near the dates).
- Recent events (Crete EMSR933, Cyclone ARNAB-26, Uruguay River): chosen as candidates in docs/CALAMITY_FEEDS.md, not run.
- The Nile Sudd has no OPERA check.

## (e) Summary

The method agrees reasonably with OPERA on the Tonle Sap window it was tuned on (IoU 0.68, precision 0.88, recall 0.74) and on the held-out east half (0.68 / 0.88 / 0.75), and on one fresh window to the east (0.78 / 0.86 / 0.89). It does not transfer reliably. On the neighbour OPERA gives precision 0.58 and Sentinel-2 gives 0.15; on a fresh window to the south the IoU is 0.04; at Kanpur the independent optical check found far more new water than the radar map (recall 0.03). Scene-calibrated thresholds, JRC masks, DEM slope, Otsu and hysteresis did not fix this. Because the true accuracy elsewhere is unknown, the app lowers or caps its confidence where it knows the method has failed, and states that no human-labelled accuracy exists. The confidence limits are provisional and one of them was adjusted after seeing a result. A person should treat a map as a lead to check, not a measurement.
