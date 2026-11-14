# Sen1Floods11: do scene-calibrated water thresholds beat fixed ones?

Written 2026-11-15. Script: `backend/scripts/eval_sen1floods11.py` (`--stage tune`, then `--stage test` once). Data: Sen1Floods11 hand-labelled chips (`team_data/datasets/sen1floods11`), split by `splits_manifest.json`.

## 0. Scope (read first)

* This is **C-band Sentinel-1 (VV/VH)**, not NISAR L-band. It tests the **recipe** ("calibrate the cut-off on the scene's own JRC permanent water, no hand labels"), not any NISAR threshold.
* Labels are human labels made mainly from Sentinel-2 optical. They under-label flooded vegetation and anything under cloud; C-band SAR also fails over flooded vegetation, wind-roughened water, shadow and urban areas. Absolute IoU is therefore low for every method (best fixed cut-off per event, with labels, only reaches 0.44 pooled VV / 0.50 VH).
* `JRCWaterHand` ships as **binary 0/1** (permanent water), with no occurrence value. "Occurrence >= 90 %" could not be applied; JRC==1 is the water sample and JRC==0 the land sample. The JRC==0 sample includes the flood itself, so it is contaminated with flood water (affects the `youden` variant only).
* **Only one truly unseen event exists** in the sealed set (Bolivia, 15 chips). The "official test" chips come from the 10 tuning events (different chips, same events), so they test unseen chips, not unseen places. Bolivia has a single event, so its interval is wide and one place says little. The strongest evidence about generalising across places is the leave-one-event-out (LOEO) table over the 10 tuning events.

## 1. Method

Single date, water if dB < t. Everything is per polarisation (VV and VH).

| Id | Method | Parameters chosen on tuning events only |
|---|---|---|
| A | one fixed global cut-off | t (grid 0.1 dB) maximising mean per-event IoU |
| B | Otsu on all pixels of the chip (`BchipOtsu`) or of the event (`BeventOtsu`) | none |
| C | scene calibration, no hand labels: JRC water pixels = free water samples, JRC==0 = free land samples in the same scene | see below |
| D | logistic regression on VV, VH, VV-VH (balanced class weights, p>0.5) | weights, 3000 random labelled pixels per tuning chip |
| Oracle | best fixed cut-off for that event using its labels | reference only, not deployable |

C variants (each at event scale = all chips of the event pooled, and chip scale):
* `pct`: t = q-th percentile of the JRC-water dB distribution (q tuned over 50 to 99.5).
* `delta`: t = median of JRC-water dB + delta (delta tuned over 0 to 10 dB).
* `youden`: t = the dB that best separates the JRC-water from the JRC-land samples (no parameter).

Fallback when samples are too few (fixed a priori, not tuned): event needs >= 500 JRC-water px and >= 200 land px; chip scale needs >= 200 and >= 200. Chip falls back to the event calibration, then to the fixed A cut-off.

Protocol: the tuning events are the 10 manifest events (train+valid: Ghana, India, Mekong, Nigeria, Pakistan, Paraguay, Somalia, Spain, Sri-Lanka, USA). For LOEO each event is scored with every parameter chosen on the other nine. The sealed test was read once with the parameters frozen from all 10 tuning events. Metrics ignore label no-data. CIs: 95 % bootstrap over chips (stratified by event, 1000 resamples). "Macro" = mean of per-event IoU (each place counts once); "pooled" = pixels summed.

Frozen parameters: A = -16.0 dB (VV), -23.0 dB (VH); pct q = 95 (event), 90 (chip); delta = 6 dB (event), 5 dB (chip); youden none. (delta, after widening the grid from 6 to 10 dB, still chose 6.)

## 2. Result 1, leave-one-event-out on the 10 tuning events (pooled, 95 % CI)

| Method | Pooled IoU | Precision | Recall | F1 | Macro IoU |
|---|---|---|---|---|---|
| A fixed VV | 0.417 [0.360, 0.467] | 0.628 | 0.554 | 0.589 | 0.394 [0.347, 0.428] |
| B event Otsu VV | 0.249 [0.213, 0.290] | 0.272 | 0.743 | 0.398 | 0.321 |
| B chip Otsu VV | 0.169 [0.141, 0.200] | 0.180 | 0.741 | 0.289 | 0.186 |
| C pct event VV | 0.295 [0.250, 0.341] | 0.372 | 0.587 | 0.455 | 0.357 |
| C delta event VV | 0.266 [0.221, 0.308] | 0.311 | 0.648 | 0.420 | 0.370 |
| C youden event VV | 0.395 [0.345, 0.447] | 0.536 | 0.600 | 0.566 | 0.407 [0.360, 0.442] |
| C youden chip VV | 0.401 [0.345, 0.455] | 0.564 | 0.582 | 0.573 | 0.387 |
| A fixed VH | 0.462 [0.410, 0.509] | 0.620 | 0.644 | 0.632 | 0.431 [0.382, 0.465] |
| B event Otsu VH | 0.323 [0.278, 0.360] | 0.354 | 0.786 | 0.488 | 0.358 |
| C pct event VH | 0.405 [0.354, 0.451] | 0.528 | 0.634 | 0.576 | 0.420 |
| C delta event VH | 0.420 [0.372, 0.466] | 0.539 | 0.654 | 0.591 | 0.406 |
| C youden event VH | 0.466 [0.415, 0.509] | 0.612 | 0.660 | 0.635 | 0.441 [0.392, 0.474] |
| C youden chip VH | 0.445 [0.397, 0.491] | 0.591 | 0.644 | 0.616 | 0.415 |
| D logistic (VV,VH,VV-VH) | 0.368 [0.322, 0.410] | 0.411 | 0.779 | 0.538 | 0.397 |
| Oracle VV / VH (labels) | 0.476 / 0.505 | | | | 0.444 / 0.469 |

(Full table with all variants and per-metric intervals: run `--stage tune`.)

Per-event IoU, LOEO (VV | VH): fixed A, best C (youden, event scale), logistic.

| Event | water frac | JRC water px | A VV | C youden VV | A VH | C youden VH | D LR |
|---|---|---|---|---|---|---|---|
| Ghana | 0.058 | 21k | 0.346 | 0.399 | 0.356 | 0.413 | 0.463 |
| India | 0.099 | 171k | 0.392 | 0.404 | 0.382 | 0.407 | 0.420 |
| Mekong | 0.266 | 573k | 0.775 | 0.733 | 0.768 | 0.768 | 0.808 |
| Nigeria | 0.251 | 71k | 0.547 | 0.515 | 0.541 | 0.496 | 0.631 |
| Pakistan | 0.048 | 156k | 0.298 | 0.261 | 0.209 | 0.201 | 0.142 |
| Paraguay | 0.087 | 401k | 0.414 | 0.428 | 0.493 | 0.493 | 0.385 |
| Somalia | 0.065 | 0 | 0.138 | 0.138 | 0.118 | 0.118 | 0.106 |
| Spain | 0.106 | 298k | 0.596 | 0.656 | 0.555 | 0.629 | 0.380 |
| Sri-Lanka | 0.101 | 517k | 0.160 | 0.217 | 0.512 | 0.491 | 0.447 |
| USA | 0.049 | 215k | 0.269 | 0.319 | 0.378 | 0.396 | 0.183 |

## 3. Result 2, sealed test (read once, frozen parameters)

Bolivia, a place never seen in tuning (15 chips, one event; JRC water 58k px):

| Method | IoU | Precision | Recall | F1 |
|---|---|---|---|---|
| A fixed VV (-16.0 dB) | 0.508 [0.399, 0.566] | 0.864 | 0.551 | 0.673 |
| B event Otsu VV | 0.594 [0.390, 0.718] | 0.668 | 0.843 | 0.745 |
| C pct event VV | 0.295 [0.129, 0.470] | 0.298 | 0.964 | 0.456 |
| C delta event VV | 0.621 [0.414, 0.717] | 0.752 | 0.781 | 0.766 |
| C youden event VV | 0.619 [0.440, 0.705] | 0.779 | 0.751 | 0.765 |
| A fixed VH (-23.0 dB) | 0.581 [0.417, 0.678] | 0.856 | 0.644 | 0.735 |
| C delta event VH | 0.564 [0.337, 0.709] | 0.588 | 0.933 | 0.721 |
| C youden event VH | 0.653 [0.441, 0.776] | 0.722 | 0.872 | 0.790 |
| D logistic | 0.687 [0.483, 0.796] | 0.762 | 0.874 | 0.814 |
| Oracle VV / VH | 0.621 / 0.664 | | | |

Official test chips (10 seen events, unseen chips; pooled, macro in last column):

| Method | Pooled IoU | Precision | Recall | F1 | Macro IoU |
|---|---|---|---|---|---|
| A fixed VV | 0.462 [0.349, 0.569] | 0.710 | 0.569 | 0.632 | 0.444 |
| B event Otsu VV | 0.322 [0.242, 0.387] | 0.371 | 0.712 | 0.487 | 0.410 |
| C pct event VV | 0.396 [0.287, 0.493] | 0.460 | 0.741 | 0.568 | 0.446 |
| C delta event VV | 0.356 [0.256, 0.453] | 0.417 | 0.708 | 0.525 | 0.430 |
| C youden event VV | 0.468 [0.376, 0.543] | 0.610 | 0.669 | 0.638 | 0.468 |
| C youden chip VV | 0.503 [0.405, 0.592] | 0.681 | 0.658 | 0.670 | 0.472 |
| A fixed VH | 0.539 [0.445, 0.622] | 0.714 | 0.687 | 0.700 | 0.516 |
| C pct event VH | 0.498 [0.397, 0.582] | 0.605 | 0.739 | 0.665 | 0.497 |
| C delta event VH | 0.516 [0.413, 0.602] | 0.649 | 0.716 | 0.681 | 0.498 |
| C youden event VH | 0.545 [0.448, 0.637] | 0.694 | 0.717 | 0.705 | 0.516 |
| D logistic | 0.455 [0.353, 0.532] | 0.507 | 0.818 | 0.626 | 0.472 |
| Oracle VV / VH | 0.444 / 0.499 | | | | 0.488 / 0.541 |

## 4. Findings

1. **Scene calibration does not clearly beat a fixed cut-off.** The best calibrated variant (JRC water vs JRC land separation, `youden`, event scale) ties the fixed cut-off: LOEO macro IoU 0.441 vs 0.431 (VH) and 0.407 vs 0.394 (VV); sealed official test 0.545 vs 0.539 (VH pooled). Every interval overlaps heavily. The water-only variants (`pct`, `delta`) are worse than fixed in VV (LOEO pooled 0.295 and 0.266 vs 0.417) and about equal or slightly worse in VH. I would not claim an advantage.
2. **Unseen place (Bolivia): calibration helped in VV.** `youden`/`delta` VV 0.62 vs fixed 0.51 (a fixed -16 dB is too strict there: oracle -13.6 dB, calibrated -13.9 / -13.5 dB, precision 0.86 but recall 0.55). In VH `youden` gave 0.653 vs 0.581. But `pct` calibration failed badly (0.27 to 0.30; threshold -8.8 dB, floods the scene) and the CI is wide (single event, 15 chips). The honest summary: promising on one new place, not proven.
3. **Better than Otsu, always.** Otsu on the chip (0.17 to 0.19 LOEO IoU) or event (0.25 to 0.32) over-detects (precision 0.18 to 0.35) because flood scenes are mostly land. Only on Bolivia (16 % water) does event Otsu work.
4. **Calibration is only as good as the JRC layer.** Calibration helped where JRC matched the scene (Spain +0.06, Ghana +0.05, USA +0.05, India +0.01 VV IoU), and hurt where it did not.
5. **VH beat VV as a single cut-off** (fixed A: 0.462 vs 0.417 LOEO pooled) because wind roughening hurts VV (Sri-Lanka below).
6. **Logistic regression is not a fix.** It is best on Bolivia (0.687) and Ghana/Nigeria/Mekong LOEO, but worst on Pakistan, Spain and USA (0.14, 0.38, 0.18). It over-detects (precision 0.41, recall 0.78 LOEO). It is also unstable across events.
7. **Nothing reaches the label.** Even an oracle cut-off per event (using the labels) gets only 0.44 to 0.50 pooled IoU. Most remaining error is not threshold choice.

## 5. Failure sizes per event, and why (reasons are inferred from precision/recall and thresholds, not verified pixel by pixel)

| Event | LOEO IoU (A VV / A VH / C youden VH) | What happened |
|---|---|---|
| Somalia | 0.14 / 0.12 / 0.12 | **No JRC permanent water at all** (0 px, also in the test chips), so calibration always fell back to the fixed cut-off. Even the oracle only gets 0.15 (VV) / 0.12 (VH): the labels do not match a simple dark-water signal (precision 0.18; likely dry-soil/sand and flat surfaces that look dark, and shallow flood water that is not dark). |
| Pakistan | 0.30 / 0.21 / 0.20 | Calibration made it worse (`pct` 0.07, `delta` 0.14). Only 47 % of the JRC water pixels (9 % in the test chips) fall inside the hand-label water, so the JRC layer is stale or in the wrong place (river moved, dry channels). The calibrated cut-off is then set from the wrong pixels (-8.9 dB, precision 0.07). Over-detection. |
| Sri-Lanka | 0.16 / 0.51 / 0.49 | VV is the failure (fixed VV recall 0.18, oracle needs -13.0 dB instead of -16.4). Wind-roughened open water is bright in VV; VH is fine. Calibration partly follows (VV `youden` 0.217) but `delta` and `pct` over-detect (recall 0.95, precision 0.13). Use VH or cross-pol here. |
| USA | 0.27 / 0.38 / 0.40 | Precision 0.31 in VV: dark non-water (shadow, paved/urban, dry sand) is flagged; the labelled flood is small (4.9 % of pixels), so each false alarm costs a lot. |
| Ghana | 0.35 / 0.36 / 0.41 | Recall 0.39: small flooded areas under vegetation are labelled water but not dark in C-band. Only 21k JRC water pixels. In the test chips only 37 % of JRC water is inside the label. |
| India | 0.39 / 0.38 / 0.41 | Recall about 0.44: flooded vegetation and cropland, not detectable by a single dB cut-off in C-band. Calibration changes little (oracle 0.40). |
| Paraguay | 0.41 / 0.49 / 0.49 | Recall 0.45 to 0.48, precision 0.74 to 0.95: misses the flood under forest/wetland vegetation. |
| Nigeria | 0.55 / 0.54 / 0.50 | Fine but calibration slightly hurts (lower cut-off than the oracle, recall falls). Small event (14 chips). |
| Spain, Mekong | 0.60 / 0.78 | Open-water floods; all methods work; calibration is neutral (Spain +0.06 VV, Mekong -0.04). |

## 6. How often calibration had too few samples

* 6 % of the tuning chips (all of Somalia, 20 of 341) and 7 % of the official test chips (6 of 90) fell back to the fixed cut-off because the scene has **zero JRC permanent water**. No other event fell below the minimum at event scale.
* At chip scale only 38 % (tuning) / 43 % (test) / 47 % (Bolivia) of chips had enough own JRC water and land samples; 56 % / 50 % / 53 % used the event calibration instead. Chip-scale calibration was not better than event scale (LOEO macro `youden` 0.387 vs 0.407 VV, 0.415 vs 0.441 VH), so calibrating per scene beats per tile.
* Having samples is not enough: Pakistan had 156k JRC water pixels and the calibration was still wrong because the JRC layer did not match the day's water.

## 7. Implications for NISAR (recipe, not numbers)

* A JRC-based scene calibration is **worth keeping as an option but must not be the only gate**: it ties a fixed cut-off on average, helped on the one unseen event, and can fail badly where JRC is stale or absent. Use the separation (`youden`) form, not a raw percentile of the water distribution, and at scene scale (not per tile).
* Add a guard: if JRC water < 500 px, or too few of them are dark (the water distribution is not plausibly dark, e.g. median above the fixed cut-off), fall back to the fixed cut-off and say so.
* The fixed C-band numbers (-16 dB VV, -23 dB VH) are **not** NISAR numbers. Re-derive them on NISAR scenes with the same recipe (choose on tuning events, report on sealed events).
* The main accuracy limit here is the signal (flooded vegetation, wind, shadow, urban), not the cut-off. This is the case for the NISAR change-detection and L-band double-bounce route, not for more threshold tuning.

## 8. Reproduce

```
python backend/scripts/eval_sen1floods11.py --stage tune --frozen /path/frozen.json --out tune.md
python backend/scripts/eval_sen1floods11.py --stage test --frozen /path/frozen.json --out test.md   # sealed: run once
```
Python with `rasterio` and `numpy` only (no sklearn needed; the logistic regression is plain numpy). About 1 minute for the tuning stage, streaming one chip at a time.
