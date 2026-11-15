# Why the radar water-change method over-predicts on the south neighbour, and what was tried

Branch sanjay/accuracy. Method frozen at METHOD_VERSION water-change-v4b-before-margin-persist (not edited; every filter below is applied to its output).
Everything here is produced by `backend/scripts/diagnose_generalisation.py` (stages `prep`, `diagnose`, `candidates`, `calibrate`). All scores are the strict
score of `eval_tonlesap.py` (became-water vs OPERA new water, only where OPERA is valid; baseline reproduced exactly: main 0.68/0.88/0.74, west 0.69/0.90/0.74,
east 0.68/0.88/0.75, neighbour 0.55/0.58/0.91). IoU/precision/recall. OPERA and Sentinel-2 are second opinions, not ground truth.

Windows: main = [103.90,13.05,104.12,13.27] (west/east halves); nbr = 0.22 deg south; **fresh** = 0.44 deg south (12.61-12.83 N); **fresh_e** = 0.22 deg east
(104.12-104.34 E). Both fresh windows lie outside the main and neighbour windows, have local NISAR track 083 and OPERA tiles, and were never tuned on. Only the 21% strip of fresh_e next to the main window could be scored; elsewhere in that window the comparable area was near zero, so fresh_e is not a clean test and its scores are shown for completeness, not as a success (docs/REVIEW.md finding 1).
Extra data (window reads only, public): ESA WorldCover 2021 v200, Copernicus DEM 30 m (AWS), JRC Global Surface Water occurrence (Google storage).
Passes used for "more passes" candidates: before 19 Jun, 1 Jul, 13 Jul, 25 Jul; after 23 Sep, 5 Oct, 17 Oct, 29 Oct (no after-date data ever enters a before input).

## 1. Diagnosis in plain words

**The south neighbour is mostly the open lake.** WorldCover says 94% of the window is water and JRC says 96% of it is water at least 75% of the time. "New water" there is
only the shoreline fringe (about 37k px of 1.47M). The false positives (15.7k px at 20 m, 42% of what we call new water) are almost all in the
herbaceous-wetland fringe (83% of FPs, but also 80% of true positives, so land cover does not separate them).

What does separate false from true positives on the neighbour (share of FP vs share of TP; full tables are printed by `diagnose`):

| feature | false positives | true positives | reading |
|---|---|---|---|
| HV after, -26 to -20.5 dB (weak-dark) | 60% | 17% | FPs are marginal pixels, barely darker than the cut-off; TPs are dark (< -26 dB) |
| HV-HH gap above -5 dB | 48% | 19% | FPs have a smaller HV/HH gap (less water-like) |
| HH after brighter than -18 dB | 14% | 2% | same |
| height below the nearest JRC permanent water (DEM) | 17% | 0% | pixels lower than the lake they supposedly flood: lake-bed / DEM-over-water artefact or wet shoreline |
| dark on only 2-3 of 4 after passes | 12% | 1% | unstable (but 88% of FPs are dark on all 4) |
| HH before darker than -14 dB | 24% | 11% | already near-dark before: borderline before-state |
| patch size | 95% >= 1 km2 | 98% | no help: the FPs are big blobs, not speckle |
| distance to JRC water | no clear pattern | | |

Main window (OPERA precision 0.88): FPs are much smaller (27k px); they sit on trees (27% of FPs vs 3% of TPs), in small patches (< 5 ha: 25% of FPs vs 1.5% of TPs),
on dark on only 2-3 of 4 passes (30% vs 3%), with HH before brighter than -10 dB (58% vs 29%), and high above the lake (> 8 m: 7% vs 0%).
These are different from the neighbour's, so one rule does not cover both.

Missed detections (main window, 71.7k px): 58% were classed "permanent" and 42% "no change" by the method; 66% were already dark in the before composite and 43% darker than -16 dB before, so
most misses are pixels the method files as already-water before (OPERA says they were not water in its before tile); 17% were never dark on both after passes. The land cover of misses matches that of
true positives (cropland 58% vs 56%), so land cover does not explain them. (The patch-size column of the miss table is meaningless: missed pixels are by definition not in a predicted patch.)

**The south "fresh" window is a bigger failure than the neighbour.** The frozen method calls 301k px new water, OPERA 15k (IoU 0.04, precision 0.05). 65% of those FPs are cropland
(WorldCover 40), 28% herbaceous wetland. None of the tested features separates them (TP/(FP+TP) is 0.05 in nearly every bin of every feature). The same cropland
class in the main window is 92% correct. So land cover, HH/HV level, ratio, height, persistence and patch size cannot explain it. Plausible but UNTESTED: flooded or wet rice
paddies that the radar sees as dark but OPERA's S1 product does not label open water. The independent optical check (see below) also finds the neighbour precision is 0.15, not 0.58,
so OPERA agrees with us more than Sentinel-2 does there. Neither can say what is on the ground.

## 2. Candidates (parameter selected on WEST IoU only; then reported on east, neighbour and the two fresh windows)

Cells are IoU/precision/recall. "passed rule?" = neighbour IoU +0.005 or better, east not worse than -0.01, and no fresh window worse than -0.005. A pass means "passed the pre-set rule; not distinguishable from noise": the thresholds are inside the noise measured in docs/REVIEW.md (about +/- 0.04 on east, +/- 0.2 on the neighbour), and with 20 candidates and four windows some pass by chance. The fresh_e columns use only the scored strip.

| candidate | param | west | east | nbr | fresh | fresh_e (strip) | dIoU east | dIoU nbr | dIoU fresh | dIoU fresh_e | passed rule? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| frozen v4b (reference) | - | 0.69/0.90/0.74 | 0.68/0.88/0.75 | 0.55/0.58/0.91 | 0.04/0.05/0.91 | 0.78/0.86/0.89 | - | - | - | - | - |
| landcover: drop cropland(40) | 40 | 0.20/0.76/0.22 | 0.34/0.86/0.36 | 0.51/0.57/0.83 | 0.03/0.04/0.25 | 0.24/0.85/0.25 | -0.336 | -0.041 | -0.013 | -0.545 | no |
| landcover: drop cropland+grass(40,30) | 40,30 | 0.20/0.76/0.21 | 0.34/0.87/0.36 | 0.51/0.57/0.83 | 0.03/0.04/0.24 | 0.23/0.85/0.24 | -0.338 | -0.041 | -0.011 | -0.553 | no |
| landcover: drop crop+grass+herb.wetland | 40,30,90 | 0.03/0.40/0.03 | 0.03/0.58/0.03 | 0.09/0.54/0.09 | 0.02/0.04/0.03 | 0.01/0.52/0.01 | -0.649 | -0.462 | -0.030 | -0.771 | no |
| landcover: drop built+bare+crop(50,60,40) | 50,60,40 | 0.20/0.76/0.22 | 0.34/0.86/0.36 | 0.51/0.57/0.83 | 0.03/0.04/0.25 | 0.24/0.85/0.25 | -0.336 | -0.041 | -0.013 | -0.545 | no |
| HV-HH gap must be < t dB | t=-5 | 0.63/0.91/0.68 | 0.58/0.88/0.62 | 0.55/0.68/0.73 | 0.04/0.04/0.66 | 0.74/0.87/0.84 | -0.101 | -0.001 | -0.002 | -0.037 | no |
| HV stricter by m dB | m=0.5 | 0.69/0.90/0.74 | 0.68/0.88/0.75 | 0.55/0.58/0.91 | 0.05/0.05/0.91 | 0.78/0.86/0.89 | -0.000 | +0.000 | +0.000 | -0.000 | no |
| HH stricter by m dB | m=0.5 | 0.68/0.90/0.74 | 0.68/0.88/0.75 | 0.55/0.58/0.91 | 0.05/0.05/0.90 | 0.78/0.87/0.89 | +0.000 | +0.000 | +0.000 | +0.000 | no |
| exclude JRC water occurrence >= o % | o=90 | 0.69/0.90/0.74 | 0.68/0.88/0.75 | 0.55/0.58/0.91 | 0.04/0.04/0.88 | 0.78/0.86/0.89 | +0.000 | +0.002 | -0.001 | +0.000 | no |
| exclude WorldCover water (80) | wc80 | 0.68/0.90/0.74 | 0.67/0.88/0.74 | 0.52/0.57/0.86 | 0.04/0.04/0.89 | 0.78/0.87/0.89 | -0.007 | -0.027 | -0.001 | -0.000 | no |
| height above JRC water < h m | h=12 | 0.69/0.90/0.74 | 0.68/0.88/0.75 | 0.55/0.58/0.91 | 0.05/0.05/0.91 | 0.00/n/a/0.00 | +0.001 | +0.000 | +0.000 | -0.782 | no |
| not lower than JRC permanent water (height >= h m) | h=0 | 0.69/0.90/0.74 | 0.68/0.88/0.75 | 0.59/0.62/0.91 | 0.05/0.05/0.90 | 0.78/0.86/0.89 | -0.000 | +0.040 | +0.000 | +0.000 | passed rule; within noise |
| distance to JRC water < d m | d=5000 | 0.50/0.87/0.54 | 0.42/0.88/0.45 | 0.55/0.58/0.91 | 0.03/0.03/0.23 | 0.00/n/a/0.00 | -0.254 | +0.000 | -0.015 | -0.782 | no |
| dark on >= k of 4 after passes | k=3 | 0.68/0.90/0.74 | 0.68/0.89/0.74 | 0.55/0.59/0.91 | 0.05/0.05/0.90 | 0.80/0.89/0.89 | +0.005 | +0.006 | +0.001 | +0.016 | passed rule; within noise |
| before-pass spread < s dB | s=3.0 | 0.47/0.87/0.51 | 0.62/0.87/0.68 | 0.50/0.59/0.77 | 0.03/0.04/0.62 | 0.71/0.85/0.81 | -0.055 | -0.049 | -0.010 | -0.070 | no |
| min patch ha | 2 | 0.69/0.91/0.74 | 0.68/0.89/0.74 | 0.55/0.58/0.91 | 0.05/0.05/0.90 | 0.79/0.87/0.89 | +0.004 | +0.001 | +0.001 | +0.007 | no |
| change stricter than c dB | c=4 | 0.62/0.90/0.67 | 0.65/0.88/0.72 | 0.55/0.58/0.91 | 0.05/0.05/0.89 | 0.77/0.88/0.87 | -0.022 | -0.001 | +0.002 | -0.009 | no |
| re-run: 4 before passes (06-19..07-25) | - | 0.75/0.90/0.82 | 0.71/0.88/0.79 | 0.49/0.51/0.94 | 0.05/0.05/0.87 | 0.79/0.87/0.90 | +0.034 | -0.057 | +0.001 | +0.008 | no |
| re-run: 4 after passes (09-23..10-29) | - | 0.67/0.93/0.71 | 0.67/0.92/0.72 | 0.58/0.61/0.90 | 0.06/0.06/0.87 | 0.81/0.91/0.89 | -0.004 | +0.027 | +0.011 | +0.031 | passed rule; within noise |
| re-run: 4 before + 4 after | - | 0.74/0.93/0.79 | 0.71/0.92/0.76 | 0.51/0.53/0.93 | 0.06/0.06/0.84 | 0.82/0.91/0.89 | +0.034 | -0.036 | +0.011 | +0.036 | no |
| re-run: 3 after (09-23,10-05,10-17) | - | 0.67/0.91/0.72 | 0.67/0.90/0.73 | 0.55/0.59/0.90 | 0.05/0.05/0.89 | 0.80/0.90/0.88 | -0.005 | +0.005 | +0.001 | +0.021 | no |
| re-run 4 after passes + height >= 0 m above JRC water (pre-specified, not tuned) | - | 0.67/0.93/0.71 | 0.67/0.92/0.72 | 0.61/0.66/0.90 | 0.06/0.06/0.87 | 0.81/0.91/0.89 | -0.004 | +0.065 | +0.011 | +0.031 | passed rule; within noise |

West-only parameter sweeps (what selected each parameter):

- landcover: drop cropland(40): 40: 0.20/0.76/0.22  -> chose 40
- landcover: drop cropland+grass(40,30): 40,30: 0.20/0.76/0.21  -> chose 40,30
- landcover: drop crop+grass+herb.wetland: 40,30,90: 0.03/0.40/0.03  -> chose 40,30,90
- landcover: drop built+bare+crop(50,60,40): 50,60,40: 0.20/0.76/0.22  -> chose 50,60,40
- HV-HH gap must be < t dB: t=-5: 0.63/0.91/0.68; t=-6: 0.49/0.91/0.51; t=-7: 0.25/0.91/0.26; t=-8: 0.07/0.91/0.07; t=-9: 0.01/0.90/0.01  -> chose t=-5
- HV stricter by m dB: m=0.5: 0.69/0.90/0.74; m=1: 0.69/0.90/0.74; m=2: 0.68/0.91/0.73; m=3: 0.65/0.93/0.69; m=4: 0.53/0.95/0.54; m=5: 0.25/0.97/0.25; m=6: 0.03/0.97/0.03  -> chose m=0.5
- HH stricter by m dB: m=0.5: 0.68/0.90/0.74; m=1: 0.68/0.91/0.74; m=2: 0.67/0.92/0.71; m=3: 0.58/0.93/0.61; m=4: 0.36/0.94/0.37  -> chose m=0.5
- exclude JRC water occurrence >= o %: o=90: 0.69/0.90/0.74; o=75: 0.68/0.90/0.73; o=50: 0.67/0.90/0.72  -> chose o=90
- exclude WorldCover water (80): wc80: 0.68/0.90/0.74  -> chose wc80
- height above JRC water < h m: h=1: 0.06/0.94/0.06; h=2: 0.22/0.96/0.22; h=3: 0.37/0.96/0.38; h=5: 0.60/0.93/0.63; h=8: 0.69/0.90/0.74; h=12: 0.69/0.90/0.74  -> chose h=12
- not lower than JRC permanent water (height >= h m): h=0: 0.69/0.90/0.74; h=0.5: 0.67/0.90/0.73; h=1: 0.64/0.90/0.68  -> chose h=0
- distance to JRC water < d m: d=250: 0.03/0.98/0.03; d=500: 0.06/0.94/0.06; d=1000: 0.13/0.92/0.13; d=2000: 0.26/0.84/0.27; d=5000: 0.50/0.87/0.54  -> chose d=5000
- dark on >= k of 4 after passes: k=3: 0.68/0.90/0.74; k=4: 0.67/0.92/0.72  -> chose k=3
- before-pass spread < s dB: s=1.0: 0.10/0.81/0.10; s=1.5: 0.21/0.81/0.22; s=2.0: 0.31/0.83/0.34; s=3.0: 0.47/0.87/0.51  -> chose s=3.0
- min patch ha: 2: 0.69/0.91/0.74; 5: 0.68/0.93/0.72; 10: 0.67/0.94/0.70; 25: 0.64/0.97/0.65  -> chose 2
- change stricter than c dB: c=4: 0.62/0.90/0.67; c=5: 0.52/0.88/0.56; c=6: 0.41/0.86/0.44; c=8: 0.23/0.78/0.24  -> chose c=4

Notes: the west half is only 29% comparable, so west-only selection is weak and often a tie (for rules that do nothing in the west, the first value tried is
kept). The two "re-run" rows and the last row are pre-specified, not west-selected. "re-run 4 before" improves west and east (+0.03) but hurts the neighbour (-0.06),
the same pattern as the earlier margin experiments: a rule that helps the land-dominated main window hurts the lake-dominated neighbour.

## 3. Scene-self-calibrated cut-offs (no OPERA, no Sentinel-2, no site constants)

Idea: per scene, take free labels (JRC occurrence >= 90% = water; WorldCover tree/cropland/built/bare with JRC == 0 = land), pool the passes the method uses, and derive HH and HV
cut-offs; then run the unchanged method with those cut-offs. Variants: youden@90 (cut-off maximising TPR+TNR, JRC>=90 water), youden@50 (same with JRC>=50 water, for rivers
where >= 90 does not exist), cfar5 (5th percentile of the land distribution, needs no water labels). Cut-offs clamped to HH [-24,-8], HV [-32,-14]; fixed cut-offs kept if
there are under 2000 labelled pixels. Nothing was tuned: the variants were all run once.

| scene | fixed | youden@90 | youden@50 | cfar5 |
|---|---|---|---|---|
| main | -14.5 / -20.5 | -17.4 / -24.7 | -17.1 / -24.4 | -16.9 / -24.5 |
| neighbour | same | -16.9 / -23.6 | -16.9 / -23.4 | -11.8 / -19.1 |
| fresh (south) | same | -17.3 / -24.0 | -17.2 / -23.9 | -18.1 / -24.3 |
| fresh_e | same | no labels, fixed kept | fixed kept | -16.6 / -24.5 |
| Kanpur | same | no JRC >= 90 pixels (JRC max in the window is 76), fixed kept | -12.1 / -21.1 | -13.6 / -22.7 |

Versus OPERA new water (IoU/precision/recall):

| window | fixed v4b | youden@90 | youden@50 | cfar5 |
|---|---|---|---|---|
| main west | 0.69/0.90/0.74 | 0.19/0.99/0.19 | 0.31/0.99/0.31 | 0.29/0.99/0.29 |
| main east | 0.68/0.88/0.75 | 0.52/0.96/0.53 | 0.61/0.96/0.63 | 0.59/0.96/0.61 |
| neighbour | 0.55/0.58/0.91 | 0.49/0.54/0.85 | 0.49/0.54/0.85 | 0.46/0.57/0.72 |
| fresh (south) | 0.04/0.05/0.91 | 0.07/0.08/0.75 | 0.07/0.07/0.77 | 0.08/0.08/0.61 |
| fresh_e | 0.78/0.86/0.89 | = fixed | = fixed | 0.59/0.97/0.60 |

Versus Sentinel-2 new water (MNDWI > 0):

| scene | fixed v4b | youden@90 | youden@50 | cfar5 |
|---|---|---|---|---|
| neighbour | 0.14/0.15/0.83 | 0.12/0.13/0.84 | 0.12/0.13/0.85 | 0.10/0.12/0.47 |
| Kanpur | 0.03/0.14/0.03 | = fixed (no labels) | 0.03/0.15/0.03 | 0.03/0.14/0.03 |

**Verdict: scene-self-calibration did NOT help and is not recommended.** It makes the cut-offs about 3 dB darker on every Tonle Sap window (the permanent lake core is calm and very
dark, and flooded cropland counted as land is dark too), so recall on the main window drops from 0.75 to 0.53-0.63 while IoU falls 0.07-0.16; the neighbour and Kanpur do not improve.
Kanpur's recall of new water stays at 0.03 whatever the cut-off, so on that scene the **threshold is not the main reason for the miss**: with fixed cut-offs the radar flags 112,615
px as water after vs 134,001 for Sentinel-2 (youden@50: 174,745), yet only 1.6k px are "became water". The new water in S2 is a thin margin that the change rules (3 dB change,
before-water margin, every-pass persistence, minimum patch) remove. (The radar-water total here is our own count; it differs from the 86k quoted from the S2 check, which was a different tally.)

Why Kanpur's fixed cut-offs miss river water (radar on the 134,001 pixels Sentinel-2 calls water, `calibrate` stage):
- Only 43% of S2 water passes both fixed cut-offs on the mean after passes; 40% fail both, 16% fail HH only, 0% HV only.
- It is mostly a **shoreline / mixed-pixel effect**: S2-water pixels in the first pixel from the shore have median HH -8.7 / HV -16.9 dB and pass 5%; 2-4 px: 24%; 4-8 px: 53%; deep interior (>= 8 px = 160 m): HH -16.5 / HV -24.7 dB, pass 77%. The braided Ganga has long narrow channels, sandbars and 20 m resampling/Lee filtering mix land into most river pixels.
- **Per-pass instability**: on S2-water pixels the 23 Sep pass is about 3 dB brighter in HH (median -12.3) than 30 Aug (-14.7), 11 Sep (-15.1) and 5 Oct (-15.0), and only 39% pass both cut-offs on 23 Sep (51-59% on the others). That fits wind roughening or rain on that date; we did not verify the weather. Because the method needs water on every after pass, one rough pass removes the pixel.
- HV is rarely the problem (HV fails only: 0%); HH level is. Cross-track (column) position correlates weakly with HH on water (-0.23), so incidence angle is at most a minor factor over this 25 km window; sandy shallow water cannot be separated from the above with these data (no depth data).

## 4. Candidate changes (exact rules) and honest status

Passed the pre-set rule (not distinguishable from noise; none is shipped) (all use only general data and physics, no site constants):

1. **Height rule (small, neighbour-motivated): a pixel cannot be new water if it lies lower than the nearest JRC permanent water.** Rule: height = DEM(pixel) - DEM(nearest pixel with JRC occurrence >= 75%); drop "became water" where height < 0 m.
   Result: neighbour 0.55/0.58/0.91 -> 0.59/0.62/0.91; west, east, fresh, fresh_e unchanged to 0.00. CAUTION: the rule was found by looking at the neighbour's false-positive table, so the neighbour number is not independent; the two fresh windows show no gain (the rule almost never fires there) and no harm. Copernicus DEM over water is flat/noisy, so part of this may be DEM noise; it removes 2.7k px only.
2. **More after passes: run the same method on all four after passes (23 Sep, 5 Oct, 17 Oct, 29 Oct) instead of two.** Result: east 0.68 -> 0.67 (-0.004), neighbour 0.55 -> 0.58 (+0.027), fresh 0.04 -> 0.06, fresh_e 0.78 -> 0.81 (+0.031); precision up on every window (east 0.88 -> 0.92, neighbour 0.58 -> 0.61, fresh_e 0.86 -> 0.91), recall down 0.03 on east. West -0.02 (so it would NOT have been chosen by west tuning; it is a pre-specified candidate). It passes the rule on the neighbour and both fresh windows (fresh_e on the scored strip only). Caveat: the extra passes are later than the OPERA reference date (5 Oct), so OPERA need not describe the same state; and the Tonle Sap recedes after October, so for another event the "after" passes must still be after the event only.
3. Combination of 1 and 2: east 0.67/0.92/0.72, neighbour 0.61/0.66/0.90 (+0.065), fresh 0.06, fresh_e 0.81/0.91/0.89. Same caveats.

Not recommended (tried, no gain or harm): cropland/grass/wetland land-cover removal (kills recall on main, -0.34 IoU east), HV/HH gap test, stricter HV/HH, JRC permanent-water exclusion
(no effect), WorldCover-water exclusion (-0.03 neighbour), distance-to-water, stricter persistence/min patch (negligible), before-pass spread, stricter change threshold,
scene-self-calibrated cut-offs, 4 before passes (hurts the neighbour -0.06). "Dark on >= 3 of 4 after passes" passes the rule but its gains (+0.005 east, +0.006 neighbour) are inside noise, as are all the others that passed.

## 5. What remains unknown

- **What the false "new water" actually is.** No candidate that uses land cover, level, ratio, height or stability removes the fresh south window's 287k false pixels, and no field data was used. Flooded rice/wet fields are a hypothesis, not a finding. Sentinel-2 puts neighbour precision at 0.15 (only 40% comparable, 49k predicted vs 8.9k S2 new water), so even the OPERA-based 0.58 is generous.
- OPERA is itself limited: HLS-before is cloud-gapped on the fresh windows and masks the lake on the main window (west 29% comparable because it is mostly lake, fresh_e 21%, fresh 89%), and S1 open-water misses flooded vegetation. Differences of a few IoU points (including every "YES" above) are within the noise of this one season / one track / four windows.
- The fresh windows are one-off tests, not a distribution of unseen areas. fresh (south) is a failure (0.04). For fresh_e only the 21% strip next to the main window could be scored (0.78 / 0.86 / 0.89); elsewhere in that window the comparable area was near zero, and where OPERA exists there 60% of our new water is not water in OPERA on the same day (docs/REVIEW.md). We do not count fresh_e as a success. The spread between places is the result, and we cannot yet predict where the method fails.
- Kanpur and Sentinel-2 results rest on one scene each, a single optical date up to 6 days from the radar passes. The wind/rain explanation for the 23 Sep pass is inferred from backscatter only. Incidence angle and shallow-water effects were not isolated.
- Nothing here claims accuracy outside the windows and dates measured.
