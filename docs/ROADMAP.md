# Roadmap: remaining work, in order

Nothing here has been done. Effort is a rough guess for one person; risk is what could stop it or make the result misleading. Measured results are in docs/ACCURACY_FINAL.md.

## 1. Human spot-check of labelled points
- Why: the only accuracy number that does not depend on OPERA or Sentinel-2. The app's `human_labelled_accuracy` field reads "not measured" today (docs/accuracy_log.md). The plan asks for about 90 blind stratified points per area, with a person checking 20 AI-assisted labels (docs/ACCURACY_PLAN_V2.md).
- Data: clear Sentinel-2 chips of the test windows, a stratified sample file the labeller never sees alongside our map.
- Effort: about 15 minutes for the 20-label check; a day or two for a full labelled set.
- Risk: labels that are AI-assisted must be disclosed as such, not called human ground truth. Cloud limits which windows have a usable chip (Tonle Sap main and Morigaon had none within 6 days).

## 2. Label factory across the 13 AOIs
- Why: one window and one season is too small to know where the method fails. Agreement labels (pixels where OPERA and Sentinel-2 both say water or both say not water) give many cheap labels at the cost of being only as good as those two products.
- Data: OPERA DSWx-S1 and DSWx-HLS tiles and clear Sentinel-2 scenes for the 13 saved areas; NISAR passes already cached.
- Effort: a few days of scripting and fetching; the scripts `fetch_s2_reference.py` and `eval_s2.py` already exist.
- Risk: cloud leaves few comparable pixels (Sentinel-2 was 13% valid on two windows). Agreement labels share errors, for example flooded vegetation that both miss.

## 3. Leave-one-site-out learned classifier with calibrated probabilities
- Why: replace the fixed rules with a model whose confidence is a measured probability. Do it only after step 2 gives labels. Leave one site out so the score reflects an unseen place.
- Data: the step 2 labels plus HH, HV, ratio, change, persistence and land-cover features.
- Effort: about a week including calibration curves.
- Risk: the Sen1Floods11 test showed a logistic model is unstable across events (0.14 to 0.81 IoU by event; docs/SEN1FLOODS11_RESULTS.md). With few sites it may overfit. Report it only if it beats the fixed method on held-out sites.

## 4. SWOT, ERA5 wind and SMAP features
- Why: wind roughening and wet soil are plausible reasons for the Kanpur 23 Sep pass and for wet-field false alarms (docs/GENERALISATION.md; the wind explanation there is inferred, not verified).
- Data: SWOT water-surface products, ERA5 wind, SMAP soil moisture.
- Effort: about a week per source.
- Risk: coarse resolution against a 20 m grid; possibly large downloads; a feature that helps one site may not help others.

## 5. Run the three recent events once an Earthdata token is available
- Why: the real task is recent floods. Candidates are Crete EMSR933 (Copernicus analyst extents exist), Cyclone ARNAB-26 and the Uruguay River floods (docs/CALAMITY_FEEDS.md).
- Data: NISAR GCOV from ASF, which needs an Earthdata login; Copernicus EMS products already catalogued (docs/DATASETS.md).
- Effort: one to two days per event.
- Risk: the Crete label for one area is itself Sentinel-1 derived, so it is partly circular for C-band comparison; the Crete floods are small and flash-flood type; the cyclone feed gives a position, not a landfall footprint; the Uruguay River floods have no analyst extent. Report failures as well as successes. The token still needs to be revoked afterwards (docs/ACCURACY_PLAN_V2.md).

## 6. Nile Sudd OPERA check
- Why: the Nile Sudd site is unvalidated. Not done.
- Data: OPERA tiles for the Nile Sudd and dates (docs/ACCURACY_PLAN_V2.md says it stays unvalidated unless these are supplied).
- Effort: about a day if the tiles can be fetched.
- Risk: floodplain with flooded vegetation that OPERA S1 may miss, and HLS before-tiles may be cloudy; the result may be too little to compare.

## 7. Fix the south-neighbour and cropland-plains failures
- Why: these are the two known failures (Sentinel-2 precision 0.15 on the neighbour; IoU 0.04 on the south fresh window).
- Data: field or very high resolution imagery to learn what the false new water is; the labels from steps 1 and 2.
- Effort: open-ended. Nothing tested so far separates the false pixels (docs/GENERALISATION.md).
- Risk: flooded rice is only a hypothesis. A fix chosen by looking at the neighbour is not independent; the tested "height not lower than JRC water" rule was found that way. Keep a sealed test area.

## 8. Read data licences before redistributing
- Why: Sen1Floods11's licence is not stated in the repo; GFD and WorldFloods are non-commercial (docs/DATASETS.md). Do not commit or share any downloaded data until checked.
- Data: licence texts of each source used.
- Effort: a few hours.
- Risk: low effort, but a missed restriction is a real problem if the data or derived labels are shared.

## 9. Fix trailer formatting of some commits
- Why: several earlier commit messages put the Co-Authored-By and Claude-Session trailers on the same line as the subject or each other instead of in a separate block after a blank line.
- Data: git history of branch sanjay/accuracy.
- Effort: minutes.
- Risk: rewriting history on a shared branch breaks other people's copies; do it only if the branch is not yet shared, otherwise leave it and fix going forward.
