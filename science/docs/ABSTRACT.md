# NISAR Change Explorer: abstract and architecture

NASA Space Apps 2026, "Dancing with the SARs". Updated 15 Nov 2026 to describe the app that ships (`backend/`, method `water-change-v5-reliability-checks`). Every number below is a measured result; the sources are docs/ACCURACY_FINAL.md and the files it cites.

## Abstract

When a river bursts its banks or a lake swells with the monsoon, the first question is simple: where did the water go? Radar can answer it through cloud and at night, but the data is huge and hard to read, so most people never get to use it.

NISAR Change Explorer is a web app that makes one slice of that data easy to use. You pick a place on the map and ask what changed. The app compares two radar passes from before with two from after, from the same orbit track, and draws a map of where water likely appeared or likely went away. It gives the area in hectares, says how confident it is and why, and compares its map with a separate NASA water map (OPERA) where one exists. It works from NISAR's L-band GCOV data, which has been calibrated since 17 June 2026.

We built it to be honest before it is impressive. It says "likely became water", and does not claim water is confirmed. When there are fewer than two good passes on either side, or more than 30% of the area has to be masked out, it says "insufficient data" and gives no number. Sample data is always labelled as sample. The weeks NISAR has no data (27 July to 10 August) are never filled in.

What we measured. On the Tonle Sap flood window in Cambodia, we compared our "became water" map with OPERA's new-water map. On the east half, which was not used for the parameter sweeps, the overlap (IoU) is 0.68 (roughly 0.64 to 0.72), precision 0.88 and recall 0.75. That half adjoins the half we tuned on and was seen when the final setting was picked, so it is not an independent test. About half the window is scored; the other half is the lake itself, which OPERA's before map masks, and nearly all the land (97% of our new water) is scored. On a window further east only a 21% strip next to the main window could be scored (0.78 / 0.86 / 0.89); elsewhere in that window the comparable area was near zero, and where OPERA exists 60% of our new water is not water in OPERA on the same day. We do not count it as a success. Intervals come from the independent review (bootstrap over 2 km blocks) and are to be re-derived with a committed script.

What went wrong, stated plainly. On a neighbouring window to the south, the same settings scored 0.55 / 0.58 / 0.91 against OPERA. That is not a held-out number (it was used as a guard when we chose a setting): its west half scores 0.01 and its east half 0.78, the interval is wide (0.30 to 0.72), and a Sentinel-2 optical check, independent of NISAR, disagreed much more: precision 0.15. On a fresh window further south the score was 0.04. At Kanpur the Sentinel-2 check found far more new water than our map (recall 0.03). We tried scene-calibrated thresholds to fix this and they failed: they made the main-window score worse and did not help the neighbour or Kanpur. A JRC permanent-water mask, a DEM slope change, Otsu thresholds and region growing did not help either.

Because of this, the app does not trust itself equally everywhere. Each result carries a validation block that says what was measured, where the method is known to fail, and whether this place was checked at all. Outside the one Tonle Sap window, the place is labelled "not checked" and confidence cannot be High. Inside it, the tuned Tonle Sap main window is now the only place that reaches High, because OPERA agrees there, which is what we tuned for. The confidence levels are rule-based labels set from these same cases, a demonstration and not a test. Confidence is also capped when one radar pass is much brighter or darker than the others, and when most detected new water lies on cropland with no independent confirmation. The limits behind these rules (100 ha, 1.5 dB, 50% cropland) are provisional: they were set from single cases, and one was changed after we saw a result, which raised the tuned window from Lower to High. Accuracy against human-labelled points has not been measured, and the app says so.

The app also lists recent natural calamities (floods, storms) from public feeds, checks whether NISAR has passes before and after each, and prepares an analysis request when it does. It says "no NISAR pass yet" when it does not.

## Architecture

### The idea in one picture

```
 Browser  (web/)                                         <- frontend
    |  HTTPS + JSON, and Server-Sent Events for progress
 FastAPI server  (backend/app/main.py)
    |-- /places, /availability       place search, what can we answer here
    |-- /analyses                    start a job, returns an id at once
    |-- /analyses/{id}, /events      the result and progress steps
    |-- /analyses/{id}/agreement     comparison with OPERA
    |-- /events/recent, /events/coverage   recent calamities and NISAR coverage
    |
 Science (backend/app/science)
    |-- change.py     the detection, and the confidence rules
    |-- verify.py     comparison with OPERA
    |-- reliability checks: pass brightness, land cover (WorldCover), validation block
    |
 Data
    |-- NISAR GCOV (ASF DAAC)         main data; read only the window asked for
    |-- OPERA DSWx-S1 / HLS           second opinion, not ground truth, and not independent of our radar method
    |-- Copernicus DEM, ESA WorldCover helpers for masks and land type
    |-- NASA EONET, GDACS, USGS, Copernicus EMS   recent-calamity feeds
```

### Design rules we kept

1. Every result says where it came from and which method version made it (`METHOD_VERSION` in `backend/app/store.py`, so old cached answers are not reused after a method change).
2. Fail soft. If a helper source such as WorldCover or OPERA is missing, the check says "not checked" and the app carries on; it never errors out.
3. No secrets in the repo or the browser. The Earthdata login lives only on the server.
4. Honest wording: "likely", and no claim of confirmation; sample data is labelled sample.

### How an analysis runs

1. Find passes for the area. Keep one track and direction. Use the two closest before and two closest after.
2. Read just the window asked for from each GCOV file by HTTP range reads, resample to a 20 m grid, apply the validity mask, a 7x7 Lee speckle filter, and mask steep slopes (over 10 degrees, Copernicus DEM).
3. Detect with fixed cut-offs: water where HH is below -14.5 dB and HV below -20.5 dB. "Became water" needs a 3 dB drop, the before state at least 1 dB darker than the cut-off to count as water (which stops new water next to old water being filed as permanent), and darkness on every after pass. Patches under 1 hectare are dropped.
4. Compare with OPERA's new water where tiles exist, scoring only "became water". Permanent water is not counted, because counting it inflated the score from 0.60 to 0.92 on the first version.
5. Run the reliability checks, set the confidence level and write the validation block.

### Confidence in plain words

High needs at least 75% of our new-water pixels to be water in OPERA's after map (this does not test that the water is new). Three checks can lower it. A pass more than 1.5 dB off the others caps it at Medium. A place outside the one checked window caps it at Medium. Most new water on cropland with no independent confirmation caps it at Lower. Areas under 100 ha cap it. These limits are provisional.

### Testing

42 automated tests on synthetic or fixture data, including a planted flood, permanent water that must not confirm new water, and the reliability checks with the land-cover read mocked offline. Real-data checks are separate and are reported in docs/accuracy_log.md.

## Results and honest limits

| Item | Result | Source |
|---|---|---|
| Tonle Sap east half vs OPERA (not used for sweeps, seen at final selection) | IoU 0.68 [0.64-0.72], precision 0.88, recall 0.75 (interval from the review, re-derive before quoting) | docs/accuracy_log.md, docs/REVIEW.md |
| Tonle Sap whole window vs OPERA (includes the tuning half) | 0.68 / 0.88 / 0.74, 51% comparable | docs/accuracy_log.md |
| Window to the east vs OPERA | not claimed: only a 21% strip could be scored (0.78 / 0.86 / 0.89) | docs/GENERALISATION.md, docs/REVIEW.md |
| South neighbour vs OPERA (guard window, not held out) | 0.55 [0.30-0.72] / 0.58 / 0.91; west half 0.01, east half 0.78 | docs/accuracy_log.md, docs/REVIEW.md |
| South neighbour vs Sentinel-2 | 0.14 / 0.15 / 0.83 (40% comparable) | docs/accuracy_log.md |
| Fresh window to the south vs OPERA | 0.04 / 0.05 / 0.91 | docs/GENERALISATION.md |
| Kanpur vs Sentinel-2 | 0.03 / 0.14 / 0.03 | docs/accuracy_log.md |
| Kanpur story: 68 ha new water | 58 ha (86%) is water in OPERA; how much we missed is not measured | docs/STORIES_RESULTS.md |
| Morigaon story: 3,299 ha new water | no reference available | docs/STORIES_RESULTS.md |
| Scene-calibrated thresholds | failed: main-window recall 0.75 down to 0.53-0.63 | docs/GENERALISATION.md |

What we do not know, and say so:

- Accuracy against human-labelled points has not been measured.
- There is no L-band benchmark. The labelled flood datasets we found are C-band or optical.
- Accuracy is measured on one Tonle Sap window and a few nearby or story windows, one season and one track. Accuracy elsewhere is unknown and can be very low, as the south windows show.
- OPERA and Sentinel-2 are second opinions, not ground truth. OPERA is another radar-based product and can share our failure modes. Only about half the Tonle Sap window is scored (the rest is the lake).
- The Nile Sudd has no independent check.
- Recent-calamity analyses (Crete, Cyclone ARNAB-26, Uruguay River) are candidates, not run.
- Differences of a few IoU points are within noise (about +/- 0.04 on the east half, +/- 0.2 on the neighbour).
- The Sen1Floods11 experiment (C-band, human labels) is a side experiment and says nothing about the accuracy of our method.

## Files to know

`docs/ACCURACY_FINAL.md` the results page, `docs/accuracy_log.md` every experiment including failures, `docs/GENERALISATION.md` why it fails on some windows, `backend/app/science/change.py` the detection and confidence rules, `backend/app/store.py` the method version.
