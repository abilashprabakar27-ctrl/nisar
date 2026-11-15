# Independent review of the accuracy evaluation

Written 2026-11-15 on branch sanjay/accuracy. Reviewer brief: find leakage, circularity, selection bias, over-claiming and statistical weakness.
Nothing but this file was changed. Method reviewed: `water-change-v5-reliability-checks` (detection pixels = v4b).

Files read: docs/accuracy_log.md, GENERALISATION.md, SEN1FLOODS11_RESULTS.md, STORIES_RESULTS.md, DATASETS.md, the untracked drafts docs/ACCURACY_FINAL.md and the modified science/docs/ABSTRACT.md as they stood at review time, science/docs/FORM_ANSWERS.md, backend/scripts/eval_tonlesap.py, eval_s2.py, diagnose_generalisation.py, backend/app/science/change.py, verify.py, backend/app/pipeline.py, config.py, backend/web/app.js, backend/app/assistant.py.

Light checks I ran (read-only, a few seconds each, on the saved `backend/data/diag_cache/*.npz`, `backend/data/final.json`, `team_data/s2_reference/eval_s2_last.json`): I re-ran the frozen v4b call on the cached arrays and reproduced the published strict scores (main 0.678/0.884/0.745, neighbour 0.548/0.579/0.912, fresh 0.045/0.045/0.905, fresh_e 0.782/0.864/0.891), then cross-tabulated OPERA codes, and block-bootstrapped (2 km blocks, 2000 resamples). Numbers marked **[check]** below come from those runs; they are not in any committed file and should be re-derived by the team before being quoted.

Not verified: that the Sen1Floods11 sealed set was read only once (a process claim; no log proves it); the meaning of OPERA DSWx-HLS code 252 (I recall the product spec lists 252 as snow/ice and 253 as cloud/shadow; check the spec); weather on any date; anything about the ground.

---

## 0. The three findings that matter most

1. **The "fresh window to the east, 0.78 / 0.86 / 0.89" is not a fresh-window result.** Only 21% of that window is scored, and it is the westernmost strip (columns 0-25%: comparable share by column eighth is 0.97, 0.73, 0, 0, 0, 0, 0, 0 **[check]**), i.e. the strip touching the east half of the main window. The other 78% has no OPERA before tile (code 255, fill). 68% of the new water we predict in fresh_e lies in that unscored part, and where OPERA's after map exists there, **60% of our new water is "not water" in OPERA on the same day** (5 Oct) **[check]**. Over the whole window at most 55% of our new water is OPERA water after, so precision against OPERA cannot be above about 0.55 for the window and 0.40 for the unscored part. The abstract and ACCURACY_FINAL cite 0.78/0.86/0.89 as a generalisation success. It is not one.
2. **The app's OPERA check is not the check that produced 0.88.** `verify.run` calls `compare(classes, grid, opera)` with no `opera_before` (verify.py:128). So `overlap_pct` is "share of our new-water pixels that are any OPERA water class 1-3 on the after date", not "confirmed as new water". Kanpur shows why this matters: OPERA "confirms" 86% of our 68 ha (STORIES_RESULTS.md:17) while Sentinel-2 labels only 14% of the same pixels as new water (accuracy_log.md:152). The confidence texts say "OPERA confirms N% of the new water" (change.py:312, 318). OPERA never tested whether it was new.
3. **The spread between places is the result.** Never-tuned or lightly-used windows give IoU 0.68, 0.55, 0.04 and (selected strip) 0.78; the neighbour itself splits into west 0.01 and east 0.78 (final.json, never reported in the docs). A t-interval on the mean of four windows is 0.51 +/- 0.52, i.e. it covers everything from 0 to 1. Any single IoU quoted as "the accuracy" misleads.

---

## 1. Tuning contamination

Where each tuned parameter came from:

| Parameter | Chosen on | Evidence | Verdict |
|---|---|---|---|
| HH < -14.5 dB, HV < -20.5 dB | Patna, Sep 2026 (medians of water/land) | config.py:33-38 | Clean with respect to Tonle Sap. Not checked how Patna values were derived. |
| Change 3 dB, Lee 7, min patch 1 ha, slope 10 deg | Inherited; sweeps on west only showed no reason to move | accuracy_log.md rows 4, 6, 9, 18 | Clean (unchanged). |
| Before-water margin 1.0 dB | West sweep first (2-4 dB best on west), then **capped at 1 dB by looking at the neighbour**; east was also printed for every candidate | rows 12-15, 19-22; lines 23-24, 62-63 | Leak into neighbour (admitted) and into east (not admitted). |
| Persistence on every after pass | Chosen with west, east and neighbour all visible; alone it lowered west IoU (0.65 to 0.63, row 16), adopted for precision | rows 16, 21 | Same leak. |
| Final choice among rows 12-22 | All three regions visible for 9 of 11 candidates | table columns EAST and south nbr are filled | The stated rule "tune only with --subset west" (line 80) was broken from row 10 on. |
| 100 ha cap | Kanpur 68 ha | config.py:47, commit 1ee0875 | Fitted to one case. |
| 1.5 dB pass drift | Kanpur "about 3 dB" | change.py:202 | Fitted to one case, and **it does not fire on that case** (0.54 dB, accuracy_log.md:197). It has never fired on any real run. |
| 50% cropland | Fresh south window (58%) | change.py:203 | Fitted to one case. |
| Cropland refinement (cap only if OPERA < 75% or missing) | Made after seeing the tuned window demoted | accuracy_log.md:203-204, commit d62b262 | Post hoc, admitted. Effect not stated: it moves the tuned window from Lower to **High** (see 4.2). |
| Height rule (not shipped) | Neighbour false-positive table | GENERALISATION.md:147 | Contaminated on neighbour, admitted. |

Rating of each headline number:

| Number | Rating | Why |
|---|---|---|
| Whole window 0.68 / 0.88 / 0.74 | **Partly contaminated** | Contains the west tuning half (24% of the reference pixels) and the config was selected with east visible. |
| West 0.69 / 0.90 / 0.74 | **Contaminated** | Tuning set. Correctly labelled. |
| East 0.68 / 0.88 / 0.75, labelled "held out" | **Partly contaminated, mildly** | Seen during selection; adjacent to west; same passes, same OPERA tile, same day. The search space was small (about 22 configs, 2 real parameters) and the gain over baseline (+0.09) is larger than the within-window interval (see 3), so the number is probably not inflated by much. But it is "selection-visible", not held out, and it is not an independent place. |
| Neighbour 0.55 / 0.58 / 0.91 | **Partly contaminated** | Used as a guard. Also an average of a failure and a success (west 0.01, east 0.78). |
| Fresh south 0.04 / 0.05 / 0.91 | **Clean** | Never tuned on, 89% comparable. The cleanest number in the project, and it is a failure. |
| Fresh east 0.78 / 0.86 / 0.89 | **Clean of tuning, invalid by selection** | See finding 1. |
| Sentinel-2 neighbour 0.14 / 0.15 / 0.83, Kanpur 0.03 / 0.14 / 0.03 | **Clean** | Report only, method frozen. |
| Lenient 0.92 | Not a change score | Correctly retired. |
| Old 0.72 / 0.90 / 0.79 (science pipeline) | **Contaminated and stale** | `WATER_DB` was tuned on Tonle Sap west against OPERA (science/methods/floods.py:15), a different method from the app. Still in FORM_ANSWERS.md:30, 39 and science/README.md:13. |
| Confidence levels on the five real cases (accuracy_log.md:188-194) | **In-sample** | Every threshold was set from these same cases. The table demonstrates the rules, it does not test them. |
| Sen1Floods11 LOEO and Bolivia | Clean by design | Process not verifiable from the repo. See 5. |

A side effect worth knowing: the guard decision itself rested on noise. Margins of 2-3 dB took east from 0.68 to 0.74-0.76 (outside east's interval) and were rejected because the neighbour fell from 0.55 to 0.50-0.51, which is far inside the neighbour's interval of [0.30, 0.72] **[check]**. Do not re-tune now; just do not present the 1 dB choice as evidence-driven.

---

## 2. Circularity and selection

**OPERA as reference.**
- DSWx-S1 is itself a SAR dark-surface product. It shares failure modes with our method (wind, smooth wet soil, flooded vegetation), so agreement overstates accuracy. The one place with both references shows it: neighbour precision 0.58 against OPERA, 0.15 against Sentinel-2.
- Calling it "independent" (verify.py:1, app.js:823, 833, resources.py:48) is too strong. Say "a separate NASA product from a different radar".
- The reference "new water" mixes two sensors: S1 open water after AND NOT HLS open water before (eval_tonlesap.py:147). `bo != 1` counts "partial surface water" before as "not water", so partial-to-open counts as new. Share of reference new water that was already partial water before: main 5%, fresh 29%, **neighbour 37%** **[check]**. On the neighbour over a third of the "new water" target is water OPERA already half-saw.
- Pixels OPERA labels inundated vegetation after (class 3) are dropped from scoring (`np.isin(ao, (0, 1))`). 65% of our unscored predictions on the fresh south window are in that class **[check]**. The hardest class is excluded, in a way that could help or hurt us; nobody measured which.

**The "comparable" mask. The docs give the wrong reason for it.** accuracy_log.md:77, 118 and the abstract say half the window is not comparable because the before optical image is cloudy. On the main window the non-comparable 49% is the lake: OPERA-before code 252 covers 48.7% of the window, and 98% of it is our permanent water, 97% JRC >= 75%, 98% WorldCover water **[check]**. 97% of the land is comparable and 97.3% of our predicted new water is inside the comparable area.
- Good news: on the main window the selection effect on new water is small. The score covers nearly all of what we predict.
- Bad news 1: OPERA-before contains 0.0% open water in the main window. The before layer contributes a mask, not a before-water test. The strict score there is effectively "our new water vs OPERA S1 open water after, on land", so it does not independently test the before/after logic.
- Bad news 2: west is "29% comparable" because west is mostly lake, not because it is noisier cloud. West and east differ in land share, not just sample size.
- Selection is severe elsewhere: share of our new water outside the comparable area is 24% on the neighbour, 17% on fresh south, 68% on fresh east **[check]**.

**Sentinel-2.** Independent of NISAR, and independent of OPERA on the after side. **Not independent of the OPERA reference on the before side**: the OPERA before tile is `DSWx-HLS_T48PUV_20260721..._S2B` (final.json meta) and the S2 before scene is 21 Jul (accuracy_log.md:138), the same Sentinel-2 acquisition. "It is independent of NISAR and OPERA" (accuracy_log.md:132, eval_s2.py:16) needs that qualifier. MNDWI > 0 also misses flooded vegetation and turbid shallows, and the reported alignment check (IoU 0.87 on all water) is dominated by the lake, so it says little about the fringe where the disagreement is. The S2 result is a strong warning, not a precision measurement.

**Shared inputs.** Our pipeline uses the Copernicus DEM (slope mask). OPERA DSWx-S1 also uses the Copernicus DEM (HAND) and, to my knowledge, reference water and land-cover layers of the JRC/WorldCover family (check the ATBD). In these flat windows the slope mask removes 0.01% of pixels, so this is harmless today. It matters for the proposed fixes: the height rule (JRC + DEM) and any WorldCover filter would be scored against a reference built partly from the same layers. JRC is OFF in the shipped method.

**"Strict" definitions.** The harness strict score (OPERA class 1 after, not class 1 before) and the app's "strict" overlap (any class 1-3 after, no before) are different things with the same name (verify.py:72-77 vs eval_tonlesap.py:146-147). On the windows I checked the two agree on main (88.6 vs 88.4) and neighbour (58.9 vs 57.9) and differ on fresh south (17.3 vs 4.5) and fresh east (54.8 vs 86.4) **[check]**. Also `verify.run` reads only the first OPERA link (`links[:1]`, verify.py:118) although the main window spans two tiles.

---

## 3. Statistics

- **Sample size is 1.** One event, one season, one track, one pass pair, four windows within about 50 km. Hundreds of thousands of pixels are not hundreds of thousands of observations.
- **No interval is reported for any NISAR number.** Pixel-level binomial intervals would be meaningless (+/- 0.001). 2 km block bootstrap **[check]**:

| Region | IoU | Precision | Recall | Note |
|---|---|---|---|---|
| main whole | 0.68 [0.64, 0.71] | 0.88 [0.85, 0.91] | 0.74 [0.71, 0.78] | 88 blocks with data |
| main east | 0.68 [0.64, 0.72] | 0.88 [0.84, 0.91] | 0.75 [0.70, 0.79] | 60 blocks |
| main west | 0.69 [0.60, 0.74] | 0.90 [0.81, 0.96] | 0.74 [0.69, 0.78] | 28 blocks |
| neighbour | 0.55 [0.30, 0.72] | 0.58 [0.30, 0.76] | 0.91 [0.79, 0.98] | all reference new water sits in 10% of blocks; about 12 effective blocks |
| fresh south | 0.04 [0.02, 0.07] | 0.05 [0.02, 0.07] | 0.91 [0.85, 0.95] | |
| fresh east (scored strip only) | 0.78 [0.70, 0.84] | 0.86 [0.78, 0.92] | 0.89 [0.85, 0.92] | 39 blocks |

  These cover within-window sampling only. Between-place variation (0.04 to 0.78) is far larger and is not captured by any interval. Per-block IoU inside the main window already ranges from 0.33 (10th percentile) to 0.84 (90th).
- **"Differences of a few IoU points are within noise"** (accuracy_log.md:25-26, 119) was asserted, never measured. Now measured: about +/- 0.04 on east, +/- 0.2 on the neighbour. The baseline-to-final gain on east (+0.09) is likely real relative to OPERA (a paired bootstrap would settle it). Every neighbour difference in the log (0.54 vs 0.55, 0.50 to 0.61) is noise.
- **The "generalises? YES" column** (GENERALISATION.md:48-73) uses thresholds of +0.005 IoU. The doc admits these are inside noise (line 158) but the table still says YES and section 4 says "Wins". With 20 candidates and four windows, some pass by chance.
- **IoU and precision are compared across windows whose class balance differs by 30x.** Prevalence of reference new water in the comparable area: main 38%, fresh east 23%, neighbour 3.1%, fresh south 1.2% **[check]**. False-alarm rate per reference-negative pixel: main 5.9%, fresh east 4.3%, **neighbour 2.2%**, fresh south 22% **[check]**. So per non-water pixel the method makes fewer false alarms on the neighbour than on the main window; with the main window's error rates at the neighbour's prevalence precision would be about 0.29. "The neighbour over-predicts" is partly a prevalence artefact (its negatives are mostly open lake, so the rates are not strictly comparable either). The real failure is fresh south. Report precision, recall and false-alarm rate with prevalence beside them; do not rank windows by IoU.
- **Aggregation hides structure.** Neighbour 0.55 = west 0.01 (11.8k px predicted, 282 in OPERA) + east 0.78 (final.json). The docs never show this.
- **The guard.** Covered in 1. A window used to veto settings is a validation set, and its number must be labelled as such everywhere it appears (ACCURACY_FINAL does this; the abstract does not).
- **Reference uncertainty.** OPERA vs Sentinel-2 on the same window differ by 0.43 in precision. Reference disagreement is larger than every effect the tuning chased.

---

## 4. Claims to correct

### 4.1 Documents

| Where | Says | Problem | Say instead |
|---|---|---|---|
| science/docs/ABSTRACT.md "What we measured"; ACCURACY_FINAL.md row 15 and (e); GENERALISATION.md:9, 159 | "a fresh window to the east scored 0.78 / 0.86 / 0.89"; "fresh_e is a success" | Finding 1 | "On a window to the east only the 21% strip next to our main window could be scored (0.78 / 0.86 / 0.89). In the rest of that window, 60% of our new water is not water in OPERA on the same day. We do not count it as a success." |
| ABSTRACT; accuracy_log.md:5, 25, 77, 118 | "About half the window could be compared, because the before-flood optical images are cloudy" | Wrong cause on the main window | "About half the window is scored. The other half is the lake itself, which OPERA's before map masks; nearly all the land, and 97% of our new water, is scored." |
| accuracy_log.md:11; ABSTRACT; ACCURACY_FINAL row 12 | "EAST half (held out)" | East was printed for the candidates the final setting was chosen from | "East half: not used in the west sweeps, but seen when the final setting was picked. It adjoins the tuning half and uses the same passes." |
| ACCURACY_FINAL row 10; change.py:209 | Whole-window 0.68 / 0.88 / 0.74 as "headline" | Includes the tuning half | Lead with east, add the interval: "0.68 [0.64-0.72] IoU on the half not used for sweeps". |
| accuracy_log.md:16 | margin "raised recall and IoU on every region" | Neighbour IoU did not rise (0.54 to 0.54, row 13) | "raised recall on every region and IoU on west and east" |
| accuracy_log.md:24 | neighbour "slightly optimistic" | Understates: S2 gives 0.15, interval is [0.30, 0.76], west half is 0.01 | "not a held-out number; its west half scores 0.01 and its east half 0.78; Sentinel-2 puts precision at 0.15" |
| accuracy_log.md:132; eval_s2.py:16 | S2 "is independent of NISAR and OPERA" | Same S2 acquisition feeds the OPERA before tile | "independent of NISAR; shares its before image with the OPERA before map" |
| accuracy_log.md:183; ACCURACY_FINAL (c) | limits "were not tuned to make any output look better" | Twenty lines later a rule is changed after an output looked bad | "set from single cases; one was changed after seeing a result, which raised the tuned window from Lower to High" |
| ACCURACY_FINAL (c) "Current levels" | lists four cases, omits Tonle Sap main | It is now High, the only High, in the tuned window | State it. |
| ACCURACY_FINAL (c); accuracy_log.md:18 | High needs "a strict OPERA confirmation" | Finding 2 | "needs 75% of our new-water pixels to be water in OPERA's after map (this does not test that the water is new)" |
| ACCURACY_FINAL table (a) | Sen1Floods11 rows in the same table and column as NISAR scores | Different sensor, task, method and reference | Separate table titled "Side experiment, C-band, not our method". See 5. |
| STORIES_RESULTS.md:16 | Kanpur "Confidence: High (see caveat)" | Stale; v5 gives Medium (accuracy_log.md:193) | "Medium" |
| STORIES_RESULTS.md:21 | 86% "says our 68 ha are probably real" | S2 calls 14% of them new water | "86% of those pixels are water in OPERA, new or not. Sentinel-2 marks 14% as new water. We cannot say this is new water." |
| GENERALISATION.md:48-73, 144 | "generalises? YES", "Wins" | Inside noise; one rule found on the test window | "passed the pre-set rule; not distinguishable from noise" |
| SEN1FLOODS11_RESULTS.md:110 | "Better than Otsu, always." | Bolivia: event Otsu VV 0.594 vs fixed 0.508, same paragraph | "Better than Otsu on the ten tuning events; not on Bolivia" |
| SEN1FLOODS11_RESULTS.md:109 | "Unseen place: calibration helped in VV" | One event, 15 chips, about 14 variants compared, one calibrated variant failed badly | "On one unseen event two of three calibrated variants scored higher; intervals overlap; not evidence" |
| science/docs/FORM_ANSWERS.md:30, 39; science/README.md:13; docs/TEAM_ARCHITECTURE_VS_SCIENCE.md:19 | 0.72 / 0.90 / 0.79, "10,500 ha ... Medium confidence" | Old pipeline, threshold tuned against OPERA on that site; not the app's numbers | Replace with the paragraph in 6. |
| ABSTRACT | "checks itself against NASA's own water maps" | Reads as verification | "compares its map with a separate NASA water map where one exists" |

### 4.2 App texts and the confidence / validation logic

| Where | Says | Problem | Say instead |
|---|---|---|---|
| change.py:312 | "NASA's OPERA water map confirms N% of the new water" | Finding 2 | "N% of the area we mark as new water is water in NASA's OPERA map on the later date. OPERA does not tell us whether that water is new." |
| change.py:318; app.js:648, 859, 984; assistant.py:35 | "N% of our water confirmed", "NASA OPERA confirms" | Same; "confirms" also implies truth | "N% of our new-water area is also water in OPERA" |
| verify.py:94; app.js:651, 823 | verdict "Confirmed"; "Two independent radar sources mark the same places as water." | Agreement of two SAR maps is not confirmation, and the docs promise the app "never says confirmed" (ABSTRACT, ACCURACY_FINAL (c)). It does, as a verdict chip. | "Agrees with OPERA" / "Partly agrees" / "Disagrees"; "Two radar-based maps mark the same places as water." |
| verify.py:1; app.js:833; resources.py:48 | "independent" | Section 2 | "separate NASA product (Sentinel-1 radar)" |
| app.js:425, 640 | chip "Water and floods VALIDATED METHOD"; "only water is validated" | Flatly contradicts `human_labelled_accuracy: "not measured"`. This is the first thing a judge sees. | "Water and floods (compared with OPERA on one site)"; "only water has been checked at all" |
| change.py:226 | `this_place`: "validated against OPERA on one window and season" for any request inside the bbox | Returned for any dates and any track. A dry-season query in that box is told it is validated. | "compared with OPERA here for Jul to Oct 2026, track 83; other dates are not checked", and set `this_place_validated` only when dates and track match. |
| change.py:207-211, 224 | key and constant names `validated_against_opera`, `VALIDATED_AGAINST_OPERA`; text quotes the whole-window score | "Validated" for agreement with another model; includes tuning half | Text: "the settings were chosen on this window; score on the half not used for sweeps: IoU 0.68 [0.64-0.72], precision 0.88, recall 0.75". Renaming keys is optional. |
| change.py:297, 311 | High requires `persistence >= 0.8`; reason "the change shows on both later passes" | With `REQUIRE_PERSISTENT` on, persistence is 1.0 by construction (change.py:153-154, 168). The gate cannot fail and the Medium branch at 314 is dead. Presenting it as evidence is misleading. | Drop it from the reason, or say "by design we only keep water seen on every later pass". |
| change.py:296; pipeline.py:247 | "this kind of place failed validation" | One window, judged by OPERA | "on one cropland window our map and OPERA disagreed almost completely" |
| pipeline.py:214, 218 | label "Likely flooding"; "New water, most likely flooding." | Measured precision ranges 0.05 to 0.88 by place, 0.15 on the one optical check | When level is not High: "Possible new water" / "Radar suggests new water; this has not been checked here." |
| pipeline.py:239 | "numbers may shift slightly when reprocessed" | "slightly" is unsupported | "numbers may change when reprocessed" |
| change.py:1-13 | docstring: "NISAR HH", "threshold from Otsu on the after image" | Stale: default is fixed HH+HV cut-offs | Fix the docstring. |
| change.py:279 | docstring: overlap_pct "must be the STRICT figure" | Not the harness's strict figure | Say which definition. |
| UI | the `validation` block (known failures, "not measured") | Not rendered anywhere in backend/web/app.js; only `limits` and the confidence reason are (lines 875, 980, 989). The honest block is invisible, the "VALIDATED METHOD" chip is not. | Render `known_failures` and `human_labelled_accuracy` beside the confidence. |

**Is the confidence honest about what was measured?** Partly.
- Honest: High is impossible outside one bbox; Kanpur and Morigaon no longer read High; the 100 ha cap and "not validated" limit are shown; `human_labelled_accuracy` says "not measured"; the log admits check A never fired and check B misses the neighbour.
- Not honest enough: (a) High is now reachable only in the window the method was tuned on, and it is reached because OPERA agrees there, which is what the tuning optimised. High means "agrees with the reference we tuned against, where we tuned". (b) The levels are uncalibrated: no level has ever been compared with an outcome it was not fitted to. (c) The south neighbour gets Medium with Sentinel-2 precision 0.15 and no rule catches it (accuracy_log.md:191). Medium currently spans "probably fine" and "85% wrong by the optical check". (d) The cropland exemption lets OPERA agreement override the cropland warning, and the app's OPERA agreement is the weak form of finding 2. Describe the levels as rule-based labels, not probabilities.

---

## 5. Citing Sen1Floods11 next to the NISAR numbers

Not valid as support for the app's accuracy. It differs in sensor (C-band VV/VH vs L-band HH/HV), task (single-date water mask vs before/after change), method (one dB cut-off or a logistic regression vs our change rules), reference (human labels vs OPERA), and the idea it tested (scene-calibrated cut-offs) tied on Sen1Floods11, failed on NISAR (GENERALISATION.md:130) and is not in the app.

May be said:
- "We tested one idea, calibrating the cut-off on each scene's known permanent water, on a public human-labelled C-band benchmark with leave-one-event-out and one sealed event. It did not beat a fixed cut-off (macro IoU 0.44 vs 0.43 VH, intervals overlap), so we did not ship it."
- "That experiment shows our evaluation habit: tune on some events, report on others, with intervals."
- "Even a per-event oracle cut-off reaches only 0.44-0.50 there, so most error is not threshold choice."

May not be said:
- "Validated on Sen1Floods11", "validated against human labels", or anything placing 0.46 / 0.58 / 0.65 / 0.69 beside 0.68 as if they measure the same thing.
- "Our method scored 0.69 on an unseen event." That is a logistic regression on C-band, not the app.
- Any NISAR threshold or accuracy inferred from it.
- "Read once" as a proven fact; say "by protocol".

Weaknesses inside that study, for completeness: the "official test" is unseen chips of seen events; Bolivia is one event of 15 chips with about 14 variants compared; "Better than Otsu, always" is contradicted by Bolivia; "calibration helped in VV" is a post hoc subgroup.

---

## 6. What is solid

- The experiment log keeps every run, including the 20 that failed. Rare and valuable.
- The lenient 0.92 was caught and retired by the team itself, and permanent water is excluded from the headline.
- The harness is re-runnable and I reproduced all four published strict scores to three decimals from the cache.
- The base thresholds come from another site (Patna), so the core of the method was not fitted to the test window.
- On the main window the score covers 97% of predicted new water, so the main-window number has little selection bias; the east-half gain over baseline (+0.09) exceeds its interval.
- The team went looking for bad news (two fresh windows, Sentinel-2, a labelled benchmark), found it, and wrote it down. The south failure (0.04) and the S2 disagreement are reported plainly.
- Negative results are stated as negative (scene calibration, JRC, Otsu, land-cover filters).
- The confidence rules err downward almost everywhere, and the post hoc change is disclosed.
- Sen1Floods11 was done with LOEO, a sealed set and bootstrap intervals, and its scope section says it is not NISAR.

## 7. Five corrections before submission (ranked, each under an hour)

1. **Withdraw the fresh-east success claim.** Edit ABSTRACT, ACCURACY_FINAL rows 15 and (e), GENERALISATION.md:9, 159 with the wording in 4.1. Text only, 15 minutes.
2. **Stop saying OPERA "confirms new water" and stop saying "validated".** Reword change.py:312, 318, 296, 226; verify.py verdict strings; app.js:425, 640, 648, 823, 833, 859, 984; assistant.py:35. String edits plus the matching test assertions (test_reliability.py:66 checks "failed validation"), 45 minutes.
3. **Replace the stale 0.72 / 0.90 / 0.79 everywhere** (FORM_ANSWERS.md:30, 39, science/README.md:13, TEAM_ARCHITECTURE_VS_SCIENCE.md:19) with the paragraph below, and fix the Kanpur row in STORIES_RESULTS.md (Medium; 86% vs 14%). 20 minutes.
4. **Relabel the splits and add intervals.** "Held out" becomes "not used for sweeps, seen at final selection"; lead with east 0.68 [0.64-0.72]; show the neighbour as west 0.01 / east 0.78 with interval [0.30-0.72]; fix the "cloudy" explanation; state that Tonle Sap main is now High and why. Re-derive the block bootstrap with a committed script first (about 40 lines over the existing cache). 45 minutes.
5. **Separate Sen1Floods11 from the NISAR table** and apply the may/may-not list in 5; fix "always". 15 minutes.

If time remains: render `validation.known_failures` in the UI, and make `this_place_validated` depend on dates and track.

### What we can truthfully say (one paragraph for the form)

We compared our NISAR "new water" map with NASA's OPERA water maps for one flood season at Tonle Sap, Cambodia. On the half of our main window that we did not use for parameter sweeps, the two maps overlap with IoU 0.68 (roughly 0.64 to 0.72), precision 0.88 and recall 0.75; that half adjoins the half we tuned on and we looked at it when picking the final setting, so it is not an independent test. The method does not transfer reliably: on a window 50 km south the overlap is 0.04, on the window in between it ranges from 0.01 to 0.78 by half, and a Sentinel-2 optical check there agrees with only 15% of our new water. At Kanpur, Sentinel-2 shows new water that we mostly miss. OPERA is another radar-based model, not ground truth, and we have no human-labelled accuracy yet. The app therefore reports its confidence as a rule-based label, shows where it disagrees with OPERA, and marks every place outside that one window as not checked. Treat its maps as leads to verify, not measurements.
