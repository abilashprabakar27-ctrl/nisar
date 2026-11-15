# Form answers: NISAR Change Explorer

Plain text, ready to paste. Describes the app that ships (`backend/`, method `water-change-v5-reliability-checks`). Numbers are measured results as of 15 Nov 2026; sources are in docs/ACCURACY_FINAL.md.

## Detailed description with objective

**Objective.** Make NISAR radar data usable for one concrete question: where did water appear or go away between two dates? The answer should be something a non-expert can read, and it should say how far to trust it.

**The problem.** Floods arrive with cloud and rain, so ordinary satellite photos are often useless exactly when people need them. NISAR's L-band radar sees through cloud and at night. But each pass is a 2 to 7 GB file, the raw numbers need speckle filtering and terrain masking, and most tools hide how uncertain the result is.

**What we built.** A web app. You pick a place on the map and ask what changed. The server compares two passes from before with two from after, from the same orbit track. It returns:

- a map of where water likely appeared and where it likely went away
- the area in hectares
- a confidence level (High, Medium or Lower) with the reason
- a comparison with NASA's OPERA water maps where they exist (OPERA is another radar-based product, not ground truth)
- a validation block: what was measured, where the method is known to fail, and whether this place was checked at all
- the weeks of data we do not have, and the limits that apply to this place

The app also lists recent floods and storms from public feeds (NASA EONET, GDACS, USGS, Copernicus EMS) and checks whether NISAR has passes before and after each one.

**How the science works.** We read only the area asked for (25 x 25 km at most) from each file using range reads, resample to a 20 m grid, apply NISAR's validity mask and a 7x7 Lee speckle filter, and mask steep slopes (Copernicus DEM). Water is where HH is below -14.5 dB and HV below -20.5 dB. A pixel "became water" if it dropped by at least 3 dB, was clearly not water before (at least 1 dB darker than the cut-off), and is dark on every after pass. Patches under 1 hectare are dropped.

**The honesty rules.** The app does not claim water is confirmed. If there are fewer than two good passes on either side, or more than 30% of the area is masked, it says "insufficient data" and gives no number. High confidence needs at least 75% of our new-water pixels to be water in OPERA's after map (this does not test that the water is new). Confidence is lowered when one pass is more than 1.5 dB brighter or darker than the others, when the place has not been checked, when the area is under 100 ha, or when most new water lies on cropland with no independent confirmation. Sample data is always labelled as sample. The permanent gap in NISAR data (27 July to 10 August 2026) is never filled in.

## Feasibility

It already runs on real data, so feasibility is shown, not assumed.

- **Technical.** Everything uses open data and open tools: Python, FastAPI, numpy, scipy, rasterio and h5py. A small window reads from a 2 to 7 GB file without downloading it whole. Results are cached, so demo areas come back instantly.
- **Data access.** NISAR GCOV is free through the ASF DAAC with a NASA Earthdata login. OPERA, Copernicus DEM, ESA WorldCover and the calamity feeds are open without a login.
- **Accuracy, stated plainly.** We compared our NISAR "new water" map with NASA's OPERA water maps for one flood season at Tonle Sap, Cambodia. On the half of our main window that we did not use for parameter sweeps, the two maps overlap with IoU 0.68 (roughly 0.64 to 0.72), precision 0.88 and recall 0.75. That half adjoins the half we tuned on and we looked at it when picking the final setting, so it is not an independent test. The method does not transfer reliably: on a window 50 km south the overlap is 0.04, on the window in between it ranges from 0.01 to 0.78 by half, and a Sentinel-2 optical check there agrees with only 15% of our new water. At Kanpur, Sentinel-2 shows new water that we mostly miss. OPERA is another radar-based model, not ground truth, and we have no human-labelled accuracy yet. The app therefore reports its confidence as a rule-based label, shows where it disagrees with OPERA, and marks every place outside that one window as not checked. Treat its maps as leads to verify, not measurements. (Intervals are from an independent review using a bootstrap over 2 km blocks and will be re-derived with a committed script.)
- **Risks we know about.** The method is checked on one season and one track. OPERA and Sentinel-2 are second opinions, not ground truth. The confidence limits (100 ha, 1.5 dB, 50% cropland) are provisional, set from single cases, and one was changed after we saw a result, which raised the tuned window from Lower to High. No accuracy against human-labelled points has been measured, and there is no L-band benchmark.
- **Cost and scale.** No paid services. A run needs a laptop-class machine. Scaling to more places means adding areas and checking each one, not new technology.

## What is ALREADY done

- A tested analysis pipeline and API: finding passes, reading windows, filtering, masking, change detection, area counting, the OPERA check, confidence rules and the insufficient-data rule. 42 automated tests pass, on synthetic scenes and fixtures where the right answer is known, including that permanent water cannot confirm new water.
- Rule-based confidence labels (not calibrated against outcomes): reliability checks on pass brightness, land cover (ESA WorldCover) and validation status, and a validation block in every result.
- A recent-calamity feed with a NISAR coverage check (EONET, GDACS, USGS, Copernicus EMS), tested on the real events of the last 45 days.
- Real comparisons with failures reported: Tonle Sap against OPERA (east half not used for sweeps: IoU 0.68, precision 0.88, recall 0.75), a window to the south that failed (0.04), a guard window in between, Sentinel-2 checks on the south neighbour and Kanpur, and, as a side experiment, a test of scene-calibrated thresholds on the Sen1Floods11 human-labelled C-band set. Scene calibration did not beat a fixed cut-off, so we did not ship it. That experiment is not our method and says nothing about NISAR accuracy. Every experiment, including the ones that failed, is logged.
- Two flood stories run on real NISAR data: Kanpur, Uttar Pradesh (68 ha new water; 58 ha, 86%, is also water in OPERA, new or not; Sentinel-2 marks only 14% of those pixels as new water; how much we missed is not measured) and Morigaon, Assam (3,299 ha new water, no independent check available).
- Presentation and written documentation.

## Future implementation plan


**Next:**
1. A human checks a set of labelled points on clear Sentinel-2 images. This gives an accuracy number that does not depend on OPERA. The points are never used to set thresholds.
2. Build agreement labels (where OPERA and Sentinel-2 both agree) across the saved areas, to find where the method fails.
3. Fix the two known failures: the south neighbour and the cropland plains south of Tonle Sap.
4. Run the recent events (Crete EMSR933, Cyclone ARNAB-26, Uruguay River floods) once an Earthdata token is available.
5. Check the Nile Sudd against OPERA, so it can leave "not checked".

**After this event:**
1. Train a classifier that is scored by leaving one site out, with probabilities that are checked against measured accuracy. We will only keep it if it beats the fixed method on sites it has not seen.
2. Try wind, soil-moisture and water-height data (ERA5, SMAP, SWOT) as extra evidence.
3. Check the licence of every dataset before sharing any of it.

## References

- NISAR L2 GCOV, NASA/JPL, distributed by the ASF DAAC: https://asf.alaska.edu
- OPERA DSWx-S1 and DSWx-HLS, NASA Earthdata: https://www.earthdata.nasa.gov
- Sentinel-2 L2A, ESA/Copernicus, via AWS Earth Search
- Sen1Floods11 (Bonafilia et al. 2020), for the threshold-recipe test
- Copernicus DEM GLO-30, ESA/Copernicus: https://spacedata.copernicus.eu
- ESA WorldCover 2021, ESA: https://esa-worldcover.org
- JRC Global Surface Water, European Commission Joint Research Centre: https://global-surface-water.appspot.com
- NASA EONET, GDACS, USGS earthquake feed and Copernicus EMS Rapid Mapping, for recent events
- OpenStreetMap Nominatim, for place search: https://nominatim.openstreetmap.org
