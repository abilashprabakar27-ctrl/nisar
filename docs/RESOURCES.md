# Resources for NISAR Change Explorer (Space Apps 2026, "Dancing with the SARs")

Status key: [OK] = URL returned HTTP 200 when checked (content not read in depth).
UNVERIFIED = not fetched or no confirmed URL. No URLs were invented; where I know a
resource exists but could not confirm a URL, it is listed by name only.

## 1. Official challenge page

- https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/ : NOT FETCHED
  (TLS error "unable to get local issuer certificate"; one WebSearch retry found no
  page for this challenge). This URL was a guess at the slug: UNVERIFIED.
- https://www.spaceappschallenge.org/2026/ [OK per search result]: event home. Event is
  Nov 14-15, 2026. Global Offers (free tools/resources) are listed to release Nov 13 (third-party
  listing, UNVERIFIED). NASA requires citing every resource used, including open source.
- ACTION for team: open the challenge page in a normal browser and paste its resource list
  below. Likely links (UNVERIFIED as challenge-linked, but each is reachable):

### Likely challenge resources (reachable, not confirmed as linked from the challenge page)
- https://search.asf.alaska.edu [OK]: ASF Vertex. Search/download NISAR GCOV and OPERA
  DSWx-S1 granules by AOI/date.
- https://asf.alaska.edu/nisar/ [OK]: ASF NISAR landing page (data access, news).
- https://nisar-docs.asf.alaska.edu/ [OK]: ASF NISAR docs/tutorials. Check for GCOV HDF5 reading notebooks.
- https://nisar.jpl.nasa.gov/data/ [OK]: JPL NISAR data page (product list, access).
- https://nisar.jpl.nasa.gov/documents/ [OK]: NISAR official documents. Look here for the
  GCOV product spec / user guide and ATBDs (polarization, geocoding, calibration).
- https://www.earthdata.nasa.gov/data/instruments/l-sar/resources [OK]: Earthdata L-SAR
  resources hub (NISAR tutorials, ARSET trainings).
- https://www.earthdata.nasa.gov/s3fs-public/2026-05/arset-2026-nisar-agenda.pdf [OK]:
  ARSET 2026 NISAR training agenda (mentions NISAR products and a flood case study). Find
  the recorded sessions/slides it points to; flood case study is directly on-topic.
- https://docs.asf.alaska.edu/ [OK]: ASF general docs (APIs, bulk download).
- https://github.com/ASFHyP3/hyp3-docs and https://hyp3-docs.asf.alaska.edu/ [OK]: HyP3
  on-demand processing docs (RTC for Sentinel-1 to get comparison S1 flood layers).
- https://github.com/asfadmin/Discovery-asf_search [OK]: `asf_search` Python client to
  script granule search/download for NISAR and OPERA.
- Earthdata Search (https://search.earthdata.nasa.gov): not checked, UNVERIFIED. Needed for
  OPERA DSWx-S1 via CMR if Vertex is awkward. Earthdata Login account required.

## 2. OPERA DSWx-S1 (our reference/validation layer)

- https://github.com/nasa/opera-sds [OK]: OPERA SDS umbrella repo; links to product specs.
- https://github.com/nasa/opera-sds-pcm [OK]: OPERA processing code (PCM); less useful for us.
- https://github.com/opera-adt/RTC [OK]: OPERA RTC-S1 code. DSWx-S1 is built on RTC, so
  this explains the backscatter normalization it consumes.
- https://github.com/opera-adt/PROTEUS [OK]: PROTEUS (DSWx-HLS / optical sibling). Context only.
- DSWx-S1 ATBD / product spec PDF: exists on NASA/JPL OPERA pages. The S3 URL I tried returned
  403, and https://www.jpl.nasa.gov/go/opera returned 403. UNVERIFIED URL. Find via
  Earthdata Search product page "OPERA_L3_DSWX-S1_V1". How it helps: confirms its water classes
  (open water, partial surface water, inundated vegetation), confidence/QA bands, and that it
  uses dual-pol Sentinel-1 with HAND and a fuzzy-logic/ML-assisted dynamic threshold. Needed to map
  our binary output onto its classes before scoring precision/recall.
- Known limits (from general knowledge of the product, UNVERIFIED until spec read): C-band,
  so vegetation penetration is weak; ~30 m; cannot see flooded vegetation reliably; wind-roughened water
  and radar-shadow/layover areas are error sources; it is a model output, not ground truth.
  How it helps: treat DSWx-S1 as a noisy reference, report agreement not "accuracy", and
  evaluate against an independent label where possible (see sec. 4).

## 3. Change detection and thresholding (method)

- https://developers.google.com/earth-engine/tutorials/community/detecting-changes-in-sentinel-1-imagery-pt-1 [OK]:
  GEE tutorial on SAR change detection (ratio image + significance test, speckle aware).
  Gain: replace a fixed dB threshold with a statistically grounded change test.
- Otsu thresholding: skimage.filters.threshold_otsu in scikit-image
  (https://scikit-image.org/docs/stable/api/skimage.filters.html, not fetched, UNVERIFIED URL).
  Gain: scene-adaptive water/non-water cut on the post-event HH (or HV) histogram.
- Bimodality-gated tiled Otsu / Kittler-Illingworth minimum-error thresholding: standard in
  SAR flood mapping literature (e.g. Chini et al. 2017 hierarchical split-based approach; Bioresita et al.
  2018 for log-ratio). I did not confirm paper URLs: UNVERIFIED. How: compute thresholds per tile,
  keep only tiles whose histogram is bimodal (e.g. Ashman D > 2 or bimodality coefficient), and
  interpolate thresholds across skipped tiles. Reduces false positives in tiles with no water.
- Log-ratio (post/pre in dB difference) with a threshold on the *difference* AND an absolute
  post-event water cut (e.g. HH below ~-18 to -20 dB, tune per scene). Requiring both lowers
  false alarms from seasonal/roughness change. Starting values are a heuristic, UNVERIFIED.
- Speckle filters: apply Refined Lee or Gamma-MAP before thresholding, or multilook (e.g. 3x3 to
  5x5). Python options: scikit-image / scipy (uniform/median), or the `pyroSAR`/`sarpy`
  ecosystems (not checked, UNVERIFIED). Gain: fewer salt-and-pepper false positives; always
  filter in linear power, not dB.

## 4. Benchmarks / labels (for honest precision/recall)

- https://github.com/cloudtostreet/Sen1Floods11 [OK]: Sen1Floods11, hand-labeled S1/S2 flood
  chips over 11 events. Gain: independent labels to tune and report P/R of the algorithm on
  S1 (C-band) as a sanity check, and to calibrate threshold choices. Note: C-band, not L-band.
- UrbanSARFloods (Sentinel-1 urban flood benchmark, Zhao et al. 2024/CVPRW): exists in the
  literature; I could not confirm a repo URL (GitHub guesses returned 404). UNVERIFIED.
  Gain: test urban double-bounce flooded-area handling.
- Other benchmarks to search for (names only, UNVERIFIED): WorldFloods (ML4Floods), SEN12-FLOOD,
  Kuro Siwo, MMFlood. Use as independent test sets if time allows.
- Practical alternative for NISAR: hand-label a few polygons ourselves from optical imagery
  (Sentinel-2 / Planet-like) coincident with the NISAR pass; even 100-200 points gives an
  honest estimate with confidence intervals. Report DSWx-S1 agreement separately from label accuracy.

## 5. Terrain / masks (largest false-positive reducers)

- https://data.hydrosheds.org/ [OK]: HydroSHEDS (includes drainage/flow direction). Gain: derive HAND
  (height above nearest drainage); mask pixels with HAND > ~15 m (typical value in flood
  literature, UNVERIFIED) since they cannot flood. Cuts hillside shadow/dark-surface false positives.
- https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM [OK]:
  Copernicus DEM (GLO-30). Gain: HAND + slope masks, and radar shadow/layover estimates.
  (Open mirror on AWS: "Copernicus DEM GLO-30" in the Registry of Open Data, URL not checked, UNVERIFIED.)
- https://www.eorc.jaxa.jp/ALOS/en/dataset/aw3d30/aw3d30_e.htm [OK]: ALOS AW3D30 DEM. Alternative DEM.
- Python HAND tooling: `pysheds` or `whitebox` (URLs not checked, UNVERIFIED). Gain: compute HAND locally from DEM.
- https://global-surface-water.appspot.com [OK]: JRC Global Surface Water. Gain: separate permanent water
  (occurrence/seasonality) from new flood water. Flood = water now AND not permanent water; or report
  "new water" vs "permanent". Also catch water bodies the SAR threshold misses.
- https://esa-worldcover.org [OK]: ESA WorldCover 10 m land cover. Gain: mask or down-weight classes that
  confuse SAR (built-up, bare/sparse sand, tree cover for flooded-vegetation logic, cropland / rice
  for paddy confusion) and compute per-class error.

## 6. L-band specifics (NISAR)

- Flooded vegetation: at L-band, double-bounce (water under canopy) raises HH backscatter, so
  flooded forest appears *brighter*, not darker. A "dark = water" rule misses it. Gain: add a second
  class "HH increase with HH/HV change" for inundated vegetation (HH up by several dB while HV stable
  or down). Source: general SAR literature, UNVERIFIED citation; DSWx-S1 also treats inundated
  vegetation as its own class.
- Rice paddies: flooded paddies early in the season look like open water (dark HH), later change as
  plants grow. Gain: use WorldCover cropland mask plus pre-event time series to flag
  agricultural flooding as likely-managed; report separately rather than counting as flood.
- HH vs HV: HV is more sensitive to volume scattering and less to water roughness; use HV change as a
  confirmation channel (water -> low HV in both). Heuristic, tune empirically.
- Look for NISAR user/product docs for GCOV (units are linear gamma0/sigma0 backscatter power in
  HDF5, with a layover-shadow-mask and number-of-looks layers) at the NISAR documents page above.
  Details from memory, UNVERIFIED: confirm dataset paths, units, and mask bit meanings in the spec
  before relying on them. Gain: use the shipped mask layer to drop shadow/layover pixels.
- Wind and look-angle effects are weaker at L-band than C-band; still compare same-orbit /
  same-track pairs to avoid incidence-angle differences. Gain: cleaner log-ratio.

## 7. Libraries

- https://github.com/mapbox/rasterio [OK]: raster I/O, reprojection (reproject DEM/HAND/WorldCover to GCOV grid).
- https://github.com/gee-community/geemap [OK]: GEE helpers (pull JRC GSW, WorldCover, Copernicus DEM
  without downloading tiles).
- h5py for GCOV HDF5 (https://docs.h5py.org not checked, UNVERIFIED).

## Top 8 to use first (ranked by expected accuracy gain)

1. JRC Global Surface Water: subtract permanent water so "flood" = new water; biggest precision win for little work.
2. HAND/slope mask from Copernicus DEM + HydroSHEDS: remove terrain false positives (shadow, dark slopes).
3. NISAR GCOV mask layer (layover/shadow) per product spec: drop invalid pixels. (Verify spec first.)
4. Speckle filter (Refined Lee or multilook) before any threshold: stable precision gain.
5. Dual criterion: absolute post-event water threshold AND log-ratio change; thresholds via tiled
   bimodality-gated Otsu or Kittler-Illingworth rather than fixed dB.
6. L-band flooded-vegetation rule (HH increase with stable/low HV) to recover recall in forests/swamps.
7. ESA WorldCover: class-wise masking (built-up, sand, cropland/rice) and per-class error reporting.
8. Honest evaluation: Sen1Floods11 for method sanity + a few hand-labeled NISAR-date polygons; report
   DSWx-S1 as agreement with a noisy reference, with confidence intervals.

## Gaps to close manually
- Official challenge page and its resource list (TLS failure here).
- DSWx-S1 product spec and NISAR GCOV spec PDFs (links blocked/unconfirmed).
- UrbanSARFloods repo URL.
