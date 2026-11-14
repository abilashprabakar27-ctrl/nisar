# Accuracy log

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
