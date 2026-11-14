# Accuracy log

## Summary: before vs after (2026-11-15, METHOD_VERSION water-change-v4b-before-margin-persist)

Strict score = our "became water" vs OPERA new water (OPERA is a second opinion, not ground truth; comparable area is only 29-72%).

| region | BASELINE IoU / prec / recall | FINAL IoU / prec / recall |
|---|---|---|
| whole window | 0.60 / 0.85 / 0.68 | 0.68 / 0.88 / 0.74 |
| WEST half (tuning set) | 0.65 / 0.85 / 0.73 | 0.69 / 0.90 / 0.74 |
| EAST half (held out) | 0.59 / 0.84 / 0.66 | 0.68 / 0.88 / 0.75 |
| south neighbour (held out) | 0.54 / 0.59 / 0.87 | 0.55 / 0.58 / 0.91 |

Honest summary. What worked: the water-before test was too generous (a pixel with HH just under -14.5 dB and HV just under -20.5 dB counted as
"already water", so real new water next to it was filed as permanent); requiring before-water to be 1 dB darker than the cut-off raised
recall and IoU on every region (east +0.09 IoU), and requiring the new water to be dark on every after pass raised precision by about 3-5
points at some cost in recall. The verify step now scores only "became water" (the old 0.92 headline was inflated by permanent
water; that number is kept but labelled), and High confidence needs a strict OPERA confirmation. What did not work: a JRC permanent-water
mask (no gain; JRC "permanent" water in this lake region is partly the new seasonal water), a DEM slope change (no effect), Otsu thresholds
(much worse), looser HV/HH cut-offs (worse), hysteresis/region growing (precision fell more than recall rose), after-pass variance filter
and bigger minimum patch (little or negative). Remaining weaknesses: the south neighbour still over-predicts new water (precision 0.58,
roughly 37k px predicted vs 24k in OPERA), probably flooded rice and wet fields that OPERA does not call water, and I found no
west-tunable feature that fixes it; margins above 1 dB help west and east more but lower neighbour IoU (0.50-0.53), so 1 dB was chosen as the
largest value that did not hurt the held-out neighbour (that choice used the neighbour as a guard, so treat the neighbour number as
slightly optimistic). Only about half the window can be compared, west only 29%, and one season/one track is a small test; differences of
a few IoU points are within noise.

Final settings: HH < -14.5 dB, HV < -20.5 dB, change 3 dB, before-water margin 1.0 dB, persistence required, min patch 1 ha, Lee 7, slope > 10 deg masked, JRC mask off.
Command: the default harness command (no flags). JSON: backend/data/eval_tonlesap_last.json.

## Experiment log (all runs, none omitted). Format: IoU / precision / recall (strict). "-" = west-only run, other regions not run (tuning rule).

Note on step 1: changing verify.py (strict headline, labelled all-water view) and METHOD_VERSION v4-strict-verify did not change any score above;
it changes only what the app reports and how confidence is derived. Test added: permanent water cannot confirm new water or give High.

| # | date | change | parameters | WEST | EAST | south nbr | decision |
|---|---|---|---|---|---|---|---|
| 0 | 2026-11-15 | baseline | see below | 0.65/0.85/0.73 | 0.59/0.84/0.66 | 0.54/0.59/0.87 | - |
| 1 | 2026-11-15 | JRC occurrence mask (extra_mask) | min 50 | 0.64/0.85/0.72 | - | - | rejected (west worse) |
| 2 | 2026-11-15 | JRC mask | min 75 | 0.64/0.85/0.72 | 0.59/0.84/0.66 | 0.54/0.58/0.87 | rejected (no gain, neighbour precision down) |
| 3 | 2026-11-15 | JRC mask | min 90 | 0.65/0.85/0.73 | - | - | rejected (no effect) |
| 4 | 2026-11-15 | DEM slope threshold | 5 / 15 / 0 deg | 0.65/0.85/0.73 each | - | - | no effect, keep 10 |
| 5 | 2026-11-15 | per-scene Otsu thresholds | mode otsu | 0.53/0.77/0.62 | - | - | rejected |
| 6 | 2026-11-15 | lower change dB | 2.5 / 2.0 / 1.5 / 1.0 | 0.65-0.66, recall 0.74 | - | - | negligible gain (+0.01), not adopted (more noise risk) |
| 7 | 2026-11-15 | looser HV cut-off | -19.5 / -18.5 / -17.5 | 0.64 / 0.63 / 0.63 | - | - | rejected |
| 8 | 2026-11-15 | looser HH cut-off | -13.5 / -12.5 | 0.58 / 0.52 | - | - | rejected |
| 9 | 2026-11-15 | HH only / Lee 5 | --no-hv / --lee-size 5 | 0.63 / 0.64 | - | - | rejected |
| 10 | 2026-11-15 | hysteresis grow (+1.5 dB, 5 px) | hyst 1.5/1.5 | 0.64/0.79/0.76 | 0.58/0.81/0.68 | 0.52/0.56/0.87 | rejected (precision down) |
| 11 | 2026-11-15 | hysteresis grow (+3 dB, 5 and 15 px) | hyst 3/3 | 0.61/0.73/0.78 | - | - | rejected |
| 12 | 2026-11-15 | before-water margin 0.5 dB | | 0.68/0.86/0.76 | 0.64/0.85/0.72 | 0.54/0.58/0.90 | candidate |
| 13 | 2026-11-15 | before-water margin 1 dB | | 0.70/0.86/0.79 | 0.68/0.85/0.77 | 0.54/0.56/0.92 | candidate (neighbour IoU equal) |
| 14 | 2026-11-15 | before-water margin 2 / 3 / 4 dB | | 0.72/0.87/0.81, 0.72/0.87/0.82, 0.72 | 0.74, 0.76, 0.76 | 0.51/0.52/0.97, 0.50/0.50/0.98, 0.50 | rejected (hurts neighbour) |
| 15 | 2026-11-15 | margin 2 + persistence | | 0.71/0.90/0.76 | 0.74/0.88/0.82 | 0.52/0.54/0.95 | rejected (neighbour down) |
| 16 | 2026-11-15 | persistence only (no margin) | | 0.63/0.89/0.68 | 0.59/0.87/0.64 | 0.55/0.61/0.86 | not adopted alone (west/east recall down) |
| 17 | 2026-11-15 | after-pass spread cap | 6 / 4 / 3 dB (+margin 2) | 0.71 / 0.63 / 0.51 | - | - | rejected |
| 18 | 2026-11-15 | min patch (+margin 2) | 2 / 5 / 10 ha | 0.73 / 0.73 / 0.73 | 5 ha: 0.75/0.88/0.84 | 5 ha: 0.51/0.52/0.97 | tiny west gain, neighbour unchanged; not adopted (user text says 1 ha) |
| 19 | 2026-11-15 | margin 1.5 + persistence + 5 ha | | 0.70/0.93/0.74 | 0.72/0.90/0.78 | 0.54/0.56/0.94 | rejected (neighbour precision 0.56 < 0.59) |
| 20 | 2026-11-15 | margin 1 + persistence + 5 ha | | 0.68/0.93/0.72 | 0.68/0.90/0.74 | 0.55/0.58/0.91 | no better than #21 |
| 21 | 2026-11-15 | **margin 1 + persistence (ADOPTED, v4b)** | margin 1.0 dB, persist on, 1 ha | 0.69/0.90/0.74 | 0.68/0.88/0.75 | 0.55/0.58/0.91 | accepted: west and east up, neighbour IoU +0.01, precision -0.01 (noise) |
| 22 | 2026-11-15 | margin 1 + persistence + 2 ha | | 0.69/0.91/0.74 | 0.68/0.89/0.74 | 0.55/0.58/0.91 | no gain |

Caveats on the log: the margin was chosen on WEST first (margins 2-4 look best there), then capped to 1 dB because larger margins hurt the held-out
neighbour; that makes the neighbour a guard rather than a clean held-out test. Wet-field/rice features (HV/HH ratio) were inspected on WEST only: false
positives and true positives have the same HV-HH gap (about -6.8 dB), so no ratio filter was tried. Pipeline wiring of JRC/DEM was not changed
since JRC gave no gain (the DEM slope mask was already wired).


Honest, re-runnable accuracy numbers for the water-change method (`backend/app/science/change.py::detect_water_change`),
produced by `backend/scripts/eval_tonlesap.py`. Append a new dated section after every method change; never overwrite old ones.

## Rules of the test

- OPERA is a **second opinion**, not ground truth (it has its own errors, misses flooded vegetation, and its before tile is cloud-limited).
- **Strict score (the number to quote):** prediction = pixels classed `became water`; reference = OPERA new water = DSWx-S1 open water
  (class 1) on the after date AND not open water on the nearest-in-time DSWx-HLS tile before. Permanent water is NOT counted.
  Compared only where both OPERA products are usable (before in 0/1/2, after in 0/1) and our method is not masked.
  "comparable" = share of the window pixels that satisfy this (HLS before is often cloud-covered, so it is only about half).
- **Lenient score:** what `backend/app/science/verify.py::compare` does today: our `became + permanent` water vs all OPERA water
  (classes 1-3) on the after date. Permanent water (Tonle Sap lake, rivers) makes this look far better than it is.
- Tuning rule: tune only with `--subset west`; judge on EAST and the south neighbour. Do not tune on the numbers you report.
- Data: NISAR GCOV track 083 (local files, 2 before 2026-07-13 + 2026-07-25, 2 after 2026-09-23 + 2026-10-05), OPERA tiles in
  `nasa_project/data/reference/tonlesap` (git-ignored). Window `[103.90, 13.05, 104.12, 13.27]`; neighbour = same box shifted 0.22 deg south.
  Slope > 10 deg masked from the Copernicus DEM (as the team pipeline does); JRC permanent-water mask OFF (the team pipeline does not use it).
- Differences from the older `science/` check: HLS before tile is picked per OPERA tile (T48PUV 2026-07-21, T48PVV 2026-07-13) instead of one tile only,
  so the east part is not dropped; "comparable" and numbers therefore differ slightly from the older 0.37/0.39/0.89 neighbour figures.

## 2026-11-15 - BASELINE (unmodified team method at HEAD 1b4387d)

Command (from repo root):

```
PYTHONPATH=/home/sanjayvasudevan/nasa/pydeps:backend /home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python backend/scripts/eval_tonlesap.py
```

Settings: HH < -14.5 dB, HV < -20.5 dB, change 3.0 dB, fixed thresholds, Lee 7, 20 m grid, HH+HV, min patch 1 ha. JSON: `backend/data/eval_tonlesap_last.json` (git-ignored; use `--json` to keep a copy).

Strict: became-water vs OPERA new-water

| region | IoU | precision | recall | F1 | comparable | pred px | OPERA px |
|---|---|---|---|---|---|---|---|
| whole window | 0.60 | 0.85 | 0.68 | 0.75 | 51% | 225194 | 280703 |
| WEST half | 0.65 | 0.85 | 0.73 | 0.78 | 29% | 58081 | 68306 |
| EAST half | 0.59 | 0.84 | 0.66 | 0.74 | 72% | 167113 | 212397 |
| south neighbour | 0.54 | 0.59 | 0.87 | 0.70 | 52% | 35124 | 23757 |

Lenient (current `verify.compare`: became + permanent vs all OPERA water)

| region | IoU | precision | recall | F1 | comparable |
|---|---|---|---|---|---|
| whole window | 0.92 | 0.94 | 0.97 | 0.96 | 100% |
| WEST half | 0.96 | 0.98 | 0.98 | 0.98 | 100% |
| EAST half | 0.87 | 0.90 | 0.96 | 0.93 | 100% |
| south neighbour | 0.95 | 0.95 | 1.00 | 0.97 | 100% |

Notes:
- Counting permanent water inflates whole-window IoU from 0.60 to 0.92 (neighbour 0.54 to 0.95). Quote the strict number.
- The method over-predicts new water on the south neighbour (precision 0.59 vs 0.85 on the main window), the same failure the older pipeline showed.
- Only about half the window is comparable; the strict score says nothing about the cloudy rest, and the west half is only 29% comparable, so its numbers are noisier.
- The tuning sample is small and OPERA-dependent; differences of a few IoU points are within noise.

## Sentinel-2 independent check (2026-11-15, report only, method untouched: water-change-v4b-before-margin-persist)

Reference: Sentinel-2 L2A from the open AWS Earth Search STAC, window reads only, resampled to the 20 m harness grid (`backend/scripts/fetch_s2_reference.py`,
rasters in git-ignored `team_data/s2_reference`). Scoring: `backend/scripts/eval_s2.py` (same `detect_water_change` call, config defaults, slope mask for Tonle Sap,
same west/east/south split as `eval_tonlesap.py`). Nothing was tuned on this data.

- Water = MNDWI = (B03 - B11)/(B03 + B11) > 0; sensitivity at > 0.1 is also reported. Reflectances are floored at 1e-4 so dark water cannot flip the sign.
- Valid = SCL not 0 no-data, 1 defective, 3 shadow, 8/9 cloud, 10 cirrus, 11 snow. Scenes are ranked by the valid share of the WINDOW (not scene cloud metadata);
  the clearest date within +/- 6 days of any NISAR before (or after) date is used; a side with under 30% valid is declared UNUSABLE.
- Score = our "became water" vs S2 new water (water after AND NOT water before), only where BOTH S2 scenes are valid and our method is not masked.
- Sentinel-2 is a different sensor with its own errors: cloud edges and shadows read as water, flooded vegetation and turbid water confuse MNDWI, and the scenes are
  up to 6 days from the NISAR passes. It is independent of NISAR and OPERA. It is not ground truth.

Which dates were usable (valid share of the window, best date per side):

| area | before (NISAR dates) | S2 before | after (NISAR dates) | S2 after |
|---|---|---|---|---|
| Tonle Sap window | 13 Jul, 25 Jul | 21 Jul, 71% | 23 Sep, 5 Oct | UNUSABLE (best 29 Sep, 13%) |
| Tonle Sap south neighbour | same | 21 Jul, 77% | same | 29 Sep, 49% (6 d from 23 Sep) |
| Kanpur | 30 Aug, 11 Sep | 9 Sep, 97% | 23 Sep, 5 Oct | 4 Oct, 100% |
| Morigaon | 20 Jun, 2 Jul | 26 Jun, 81% | 14 Jul, 26 Jul | UNUSABLE (best 29 Jul, 13%) |

Monsoon cloud: most S2 dates in the windows are 0-5% valid. Per-date valid shares are in `team_data/s2_reference/manifest.json`.

Results (strict-style: became-water vs S2 new water; OPERA = the final strict numbers above, IoU / precision / recall):

| region | S2 IoU | S2 prec | S2 recall | S2 F1 | S2 comparable | OPERA IoU / prec / recall |
|---|---|---|---|---|---|---|
| Tonle Sap whole / west / east | not scored: no usable after scene | | | | | 0.68 / 0.88 / 0.74 (west 0.69/0.90/0.74, east 0.68/0.88/0.75) |
| south neighbour (MNDWI > 0) | 0.14 | 0.15 | 0.83 | 0.25 | 40% | 0.55 / 0.58 / 0.91 |
| south neighbour (MNDWI > 0.1) | 0.14 | 0.15 | 0.83 | 0.25 | 40% | same |
| Kanpur (MNDWI > 0) | 0.03 | 0.14 | 0.03 | 0.05 | 97% | no OPERA number |
| Kanpur (MNDWI > 0.1) | 0.03 | 0.15 | 0.04 | 0.06 | 97% | no OPERA number |
| Morigaon | not scored: no usable after scene | | | | | no OPERA number |

Pixel counts (20 m): south neighbour 49,230 predicted vs 8,896 S2 new water (comparable area only); Kanpur 1,646 predicted vs 7,333 S2 new water.
The 0 vs 0.1 MNDWI threshold barely matters (about 0.2% of S2 new-water pixels change on the south window, 9% on Kanpur).

What this says, plainly:
- The south neighbour over-prediction is confirmed by an independent sensor and is worse than OPERA suggested: precision 0.15 against 0.58. Our recall there is high (0.83),
  so the extra radar "new water" is largely not water in the optical image (likely wet or flooded fields, or S2 missing flooded vegetation; S2 cannot tell which).
  Sanity check of the alignment: our became+permanent water vs S2 after water on the same valid pixels has IoU 0.87, so the grids line up.
- Kanpur: our map has far fewer new-water pixels than S2 shows (recall 0.03-0.04, precision 0.14). S2 new water there is small, scattered and the S2 dates are 2 days off the
  before pair and 1 day off the after pair, so these numbers say the two maps disagree, not which is right; no OPERA or ground check exists for Kanpur, and no DEM slope mask
  was applied in this script for it (the pipeline applies one).
- No independent score for the Tonle Sap main window (the one with the best OPERA numbers) or Morigaon: no clear after-flood optical scene within 6 days. We do not extend the window.
- One season, one pass pair per area, a different sensor with its own errors, and a 49% valid reference on the south window: treat as a warning, not a measured accuracy.

Re-run: `python backend/scripts/fetch_s2_reference.py` then `python backend/scripts/eval_s2.py` (same PYTHONPATH/venv as `eval_tonlesap.py`). Kanpur uses NISAR track 077 and Morigaon track 091 read from
the pipeline cache in `team_data/cache` (NCE_DATA_DIR), no NISAR re-download; Morigaon is skipped only because there is no S2 after scene.

## Reliability checks (2026-11-15, METHOD_VERSION water-change-v5-reliability-checks)

The detection itself is unchanged (same pixels, same areas). What changed is how honest the confidence is about where the method is known to fail.
Three fail-soft checks (data missing -> "not checked", never an error) feed `change.confidence()`; the old rules are kept. Numbers go in `provenance`, plain sentences in `limits`.

| check | rule | effect | source of the number |
|---|---|---|---|
| A. Radiometric stability | median HH (dB, Lee-filtered) per pass over pixels that are land in every pass (never water, not masked); a pass more than 1.5 dB from the median of all passes is flagged | plain limit "pass DATE is N dB brighter/darker than the others ... open water may be missed on that date"; a flagged pass cannot be High (cap Medium) | Kanpur 23 Sep seen about 3 dB brighter than other passes (wind/rain/soil moisture), recall 0.03 vs Sentinel-2 |
| B. Land cover | ESA WorldCover 10 m v200 2021 (open COG on AWS, window read only); share of 'became water' on cropland (40) and built-up (50) | cropland share above 50% -> not above Lower, with the reason "most detected new water lies on cropland ... this kind of place failed validation" | cropland plains south of Tonle Sap: 301k px predicted vs 15k in OPERA, IoU 0.04 |
| C. Validation status | `validation` block in every result: what was measured (Tonle Sap window vs OPERA: IoU 0.68, precision 0.88, recall 0.74), known failures, `this_place` ("validated against OPERA on one window and season" only if the bbox lies inside 103.90-104.12 E, 13.05-13.27 N, else "not validated"), `human_labelled_accuracy: "not measured"` | "not validated" place cannot be High (cap Medium); the small-area cap (100 ha) is kept | docs/accuracy_log.md, docs/GENERALISATION.md; nothing invented |

**The limits 1.5 dB, 50% cropland and 100 ha are provisional, from 2 observed failures. They were not tuned to make any output look better and must be revisited when a labelled score exists.**
Scene-self-calibrated thresholds were tried and failed (docs/GENERALISATION.md section 3); they are NOT implemented.

Re-run of the cached real cases (checks run for real, WorldCover read live; OPERA overlap for Tonle Sap taken from the strict scores above as a stand-in, 88/58/5%):

| case | new water | brightness check (offset of each pass from median of passes) | cropland share | confidence now | why |
|---|---|---|---|---|---|
| Tonle Sap main window | 9,719 ha | none flagged (max 0.5 dB) | 53% | Lower | cropland share above 50%. This is the best-validated window (IoU 0.68), so the blunt cropland rule demotes the one place with a good score; the diagnosis found cropland there is 92% correct. Rule kept as specified, not tuned. |
| Tonle Sap south neighbour | 1,970 ha | none flagged (max 1.25 dB) | 6% | Medium | OPERA 58%, not validated place; the Sentinel-2 precision of 0.15 is NOT caught by any of the three checks |
| Tonle Sap fresh window (0.44 deg south) | 14,522 ha | none flagged | 58% | Lower | OPERA overlap 5%; also cropland above 50% |
| Kanpur 77 D (30 Aug, 11 Sep / 23 Sep, 5 Oct) | 68 ha | none flagged: 23 Sep is only +0.54 dB on stable land | 49% (just under the limit) | Medium | no OPERA check (the OPERA call fails offline here: AttributeError), place not validated, 68 ha under 100 ha |
| Morigaon 91 D (20 Jun, 2 Jul / 14 Jul, 26 Jul) | 3,299 ha | none flagged | 97% | Lower | most new water on cropland (earlier: Medium) |

Honest limits of these checks:
- **Check A did not reproduce the Kanpur ~3 dB.** On land that is stable in every pass, 23 Sep is only 0.5 dB above the median of the passes. The whole-window HH median of that pass is 0.8 dB brighter and its darkest 10% is 1.7 dB brighter (-13.1 dB vs -14.8 dB), so the brightening is concentrated on the dark (water) end, which a land-only median cannot see. The check follows the pre-stated rule and is not changed; a water-end statistic would be a new rule that needs its own test.
- Check B treats all cropland alike: it flags Tonle Sap main (good score) and Morigaon (unchecked) the same way, and misses the south neighbour (6% cropland, S2 precision 0.15). It is a warning about a failure type, not a measured error rate.
- With 2 passes per side, a flagged pass needs a 3 dB gap between the two members of its group, so the check is weak with few passes.
- No human-labelled accuracy exists; the field reads "not measured".
- Tests: `backend/tests/test_reliability.py` (synthetic inputs, WorldCover read monkeypatched offline). WorldCover tile name verified live (N12E102 for Tonle Sap).

### Refinement to the cropland cap (made after seeing the first result, so treat as post hoc)
The first v5 run demoted the Tonle Sap main window to Lower because 53% of its new water is on cropland. That window is the best-validated one (IoU 0.68; OPERA confirms 88% of the new water), and its floodplain really does flood its paddies. The only evidence behind the cap was a window where OPERA also failed (5% overlap), so the cap now applies only when no independent reference confirms the new water (OPERA missing or under 75%). Effect on the real cases: Tonle Sap main is no longer capped by cropland; Morigaon (97% cropland, no OPERA) and the fresh south window (58%, OPERA 5%) stay Lower. This change was chosen after seeing the outcome, so it is not an independent result.
