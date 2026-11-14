# Form answers: NISAR Change Explorer

Plain text, ready to paste. Numbers are from the saved results as of 14 Nov 2026.

## Detailed description with objective

**Objective.** Make NISAR radar data usable for one concrete question: where did water appear or go away between two dates? The answer should be something a non-expert can read, and it should say how far to trust it.

**The problem.** Floods arrive with cloud and rain, so ordinary satellite photos are often useless exactly when people need them. NISAR's L-band radar sees through cloud and at night. But each pass is a 2 to 7 GB file, the raw numbers need speckle filtering and terrain masking, and most tools hide how uncertain the result is.

**What we built.** A web app. You pick a place on the map and ask what changed. The server compares a few passes from before with a few from after, taken from the same orbit track, direction and frame. It returns:

- a map of where water likely appeared and where it likely went away
- the area in hectares
- a confidence level (High, Medium or Lower) with the reason
- a check against NASA's own OPERA water maps: overlap, precision and recall
- the weeks of data we do not have, and the limits that apply to this place
- driver evidence: whether heavy rain (GPM IMERG) or flat low-lying land fits the change, each marked Likely, Possible or Not supported, and always as interpretation

**How the science works.** We read only the area asked for (25 x 25 km at most) from each file using range reads. We apply NISAR's validity mask and a 5x5 Lee speckle filter, and mask permanent water (JRC) and steep slopes (Copernicus DEM). Each side becomes a median composite of 2 to 3 passes. We take the log-ratio in decibels, threshold it with Otsu's method, call a pixel water if the after-image is darker than the water threshold, and drop patches under 1 hectare.

**The honesty rules.** The app never says "confirmed". If there are fewer than two good passes on either side, or more than 30% of the area is masked, it says "insufficient data" and gives no number. High confidence needs the change on at least two passes. Sample data is always labelled as sample. The permanent gap in NISAR data (27 July to 10 August 2026) is never filled in.

## Feasibility

It already runs on real data, so feasibility is shown, not assumed.

- **Technical.** Everything uses open data and open tools: Python, FastAPI, xarray, numpy, scipy, rasterio and h5py. A 24 km window reads from a 2 to 7 GB file in about 2 seconds, so nothing needs to be downloaded whole. Results are cached, so demo areas come back instantly.
- **Data access.** NISAR GCOV is free through the ASF DAAC with a NASA Earthdata login. OPERA, IMERG, JRC, Copernicus DEM and WorldCover are all open.
- **Accuracy, stated plainly.** On our Tonle Sap test window in Cambodia, our water map agrees with OPERA with an overlap (IoU) of 0.72, precision 0.90 and recall 0.79, over the 51% of the window where OPERA could be compared. On a neighbouring window to the south, the same settings reached only 0.37 overlap and 0.39 precision, because they over-predict water there. So we claim the method works where it was tuned and checked, and nothing wider than that.
- **Risks we know about.** Thresholds were tuned on one site and one season. OPERA is a reference, not ground truth. Flooded forest can brighten in HH and look like no change. Smoothing shrinks patch edges by about 2 pixels, so areas are slightly under-counted.
- **Cost and scale.** No paid services. A run needs a laptop-class machine. Scaling to more places means adding areas and checking each one, not new technology.

## What is ALREADY done

- A tested analysis pipeline: finding passes, reading windows, filtering, masking, compositing, change detection, area counting, confidence rules and the insufficient-data rule. 83 automated tests pass, on synthetic scenes where the right answer is known.
- A working API with place search, availability, background analyses with progress events, and the OPERA agreement check, plus an honesty gate that rejects results that break the wording rules.
- Real data processed: 22 NISAR GCOV passes (37 GB) for two sites, Tonle Sap in Cambodia and the Nile Sudd in South Sudan.
- **Tonle Sap:** about 10,500 ha likely became water, about 340 ha likely receded, and about 240 ha likely flooded vegetation, with Medium confidence. Checked against OPERA: overlap 0.72, precision 0.90, recall 0.79.
- **Nile Sudd:** about 170 ha likely became water and about 1,200 ha likely receded, with permanent-water and slope masks applied (6.6% masked). It is clearly labelled **unvalidated** because no independent check has been run yet.
- A per-pass timeline. For Tonle Sap, water area rises from about 2,000 ha on 25 July to a peak near 11,200 ha on 5 October. These are single passes, labelled as context.
- Rainfall evidence: 153 days of GPM IMERG rain (1 June to 31 October) for 13 areas, and rain and terrain driver rules.
- A bbox-aware availability check: it tells you whether we have checked NISAR coverage in a place, and says so honestly when we have not.
- Both demo areas are pre-computed and saved, so they return instantly with their OPERA comparison attached.
- A 7-slide presentation, written documentation, an architecture description and a handoff note.

## Future implementation plan

**Before the deadline (what is left of this weekend):**
1. Hand-label about 90 check points on a clear Sentinel-2 image and score the result against them. They are never used to set thresholds. This gives an accuracy number that does not depend on OPERA.
2. Download OPERA water maps for the Nile Sudd and score it, so it can leave "unvalidated".
3. Serve the driver evidence from the API, so the frontend can show "why did it change".
4. Re-check every number shown in the app against the saved results before the feature freeze.

**After this event:**
1. Add two more sites, Sylhet haor in Bangladesh and the Mamirauá reserve in the Amazon, and validate each. This tests whether our thresholds transfer, which the southern Tonle Sap result says is the biggest open question.
2. Tune thresholds per site type, using separate tuning and checking areas, and publish the accuracy for each.
3. Add the other drivers: river discharge (GloFAS), fire hotspots (FIRMS), earthquakes (USGS).
4. Add experimental layers, clearly labelled: ground movement from NISAR GUNW, and vegetation loss from the HV channel.
5. Add a tile server and a stronger job queue so more people can use it at once.

## References

- NISAR L2 GCOV, NASA/JPL, distributed by the ASF DAAC: https://asf.alaska.edu
- OPERA DSWx-S1 and DSWx-HLS, NASA Earthdata: https://www.earthdata.nasa.gov
- GPM IMERG V07 daily precipitation, NASA GES DISC: https://gpm.nasa.gov
- Copernicus DEM GLO-30, ESA/Copernicus: https://spacedata.copernicus.eu
- JRC Global Surface Water, European Commission Joint Research Centre: https://global-surface-water.appspot.com
- ESA WorldCover 2021, ESA: https://esa-worldcover.org
- OpenStreetMap Nominatim, for place search: https://nominatim.openstreetmap.org
