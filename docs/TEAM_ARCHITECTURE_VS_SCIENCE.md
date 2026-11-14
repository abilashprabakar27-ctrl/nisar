# Team architecture PDFs vs the science pipeline

Read from: NISAR_Change_Explorer_Technical_Deep_Dive.pdf (17 pp) and NISAR_Change_Explorer_Architecture_Features_Screens_Data.pdf (23 pp, first 12 read), both dated 14 Nov 2026. They describe `backend/` and `web/`. This page lists where `science/` agrees or differs, so the two can be merged on purpose.

| Item | Team app (`backend/app`) | `science/` |
|---|---|---|
| Passes used | Closest 2 before and 2 after, one track | Median composite of 2 to 3 per side, one track, direction, frame |
| Min passes / masked stop | 2 each side / over 30% | Same / same |
| Min patch | 1 ha | 1 ha |
| Speckle filter | Lee 7x7 | Lee 5x5 |
| Grid | Resampled to 20 m UTM grid | Native window |
| Water rule | HH below -14.5 dB and HV below -20.5 dB (fixed, measured on Patna) | HH below -12 dB (tuned on Tonle Sap), HH only on Nile Sudd; Otsu with 3 dB fallback |
| Change rule | became: diff below -3 dB; receded: diff above +3 dB | Log-ratio with Otsu tails, fixed 3 dB fallback |
| Reference check | OPERA overlap % (share of our water OPERA confirms), plus IoU; verdict Confirmed at 75% or more | IoU, precision, recall, share of window comparable |
| Confidence | High needs persistence 0.8 or more and overlap 75% or more | High needs the change on 2 or more after passes; single pass capped at Lower |
| Rain driver | NASA POWER daily rain | GPM IMERG daily rain, 13 areas saved |
| Other drivers | River, flat land (DEM), USGS quakes, FIRMS fires | Rain, low-flat terrain |
| Accuracy points | 50 water + 50 dry random pixels, hand-labelled | About 90 stratified points, hand-labelled, never used for thresholds |
| Calibrated / validated on | Patna only, no independent check yet | Tonle Sap IoU 0.72 (0.37 on the window south of it); Nile Sudd unvalidated |

## Things to settle before merging
1. The two water thresholds were tuned on different sites. Neither has been shown to transfer. Run both on Patna, Tonle Sap and the Nile Sudd and report each against OPERA.
2. "Overlap %" in the team app is closer to our precision than to IoU. Show both names clearly, or the app and the deck will quote different numbers for the same thing.
3. The two confidence rules disagree. Pick one and bump `METHOD_VERSION` (`backend/app/store.py`) so old cached answers are not reused.
4. The team app's thresholds and 7x7 filter are described in their PDF; the repo code in `backend/app/science/change.py` is the source of truth.
