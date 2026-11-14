# Answer-key flood datasets (v3, Stage E)

Written 2026-11-15. Every URL below was requested during this session; "UNVERIFIED" marks anything not tested. Data live outside the repo in `/home/sanjayvasudevan/nasa/team_data/datasets/` (git-ignored; never commit). Nothing downloaded was executed; only data files were kept (zip members limited to `.shp/.shx/.dbf/.prj/.json/.xml/.tif`, no `.lyr/.sld`).

## 0. Honest scope

* No open, pixel-labelled **L-band** flood dataset was found. Every pixel-level answer key below is C-band (Sentinel-1), optical, or an analyst map made from VHR optical/SAR.
* So these sets validate the **change-detection logic, the false-alarm behaviour and the confidence calibration**, and give analyst extents for NISAR-era events. They do **not** validate NISAR L-band thresholds (L-band penetrates vegetation, so double-bounce flood-under-canopy is bright in L-band and often invisible or ambiguous in C-band/optical labels; flooded forest and dense crops are systematically under-labelled in these keys).
* Optical-derived labels (Sen1Floods11, WorldFloods, CEMS optical products) cannot see through cloud and mark cloud-free water only. Do not read their "dry" pixels as truth under canopy.
* Event dates matter: a label is only valid for the acquisition date it was made from. Pair it with a NISAR pass within about 1-3 days, otherwise report the gap.

## 1. Catalogue (all tested)

| # | Dataset | Labels (who / how) | Sensor, band | Region, years | Licence | Size | No-login access (tested) | Tune or test only | Fetched |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Copernicus EMS Rapid Mapping, 2026 floods** (EMSR927 Nepal, EMSR933 Crete, EMSR935 Valencia/Alicante) | Analyst (EMS service providers), semi-automatic extraction with manual QC (attribute `det_method` = "Semi-automatic extraction") | Source images: Sentinel-1 C-band SAR (1 product, Crete AOI03 v0) plus VHR optical (WorldView-3, Legion, GeoEye-1, SPOT-6/7, Pleiades). Not L-band | Nepal Aug 2026, Crete Oct 2026, Spain Oct 2026 (all after 2026-06-17) | Copernicus EMS terms (free, attribution to "Copernicus EMS Rapid Mapping"; the in-file metadata points to the cite page, exact terms not re-read here: check before redistribution) | 190 MB zips, 288 MB extracted (these three activations) | `https://mapping.emergency.copernicus.eu/activations/api/activations/` (HTTP 200, 1069 activations) and `https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSRxxx` (HTTP 200) give `downloadPath` zip URLs (HTTP 200 via redirect to S3) | **TEST only (sealed)** | yes |
| 2 | **Sen1Floods11, hand-labelled subset** (446 chips, 11 events) | Trained human labellers on Sentinel-2 imagery with Sentinel-1 as aid (Bonafilia et al. 2020); QC values -1 nodata, 0 not water, 1 water. A `S1OtsuLabelHand` automatic comparison layer is also provided | Sentinel-1 IW GRD VV/VH (C-band), Sentinel-2 L1C 13 bands, 10 m, 512x512 chips | Bolivia 2018, Colombia 2018, Ghana 2018, India 2016, Cambodia/Mekong 2018, Nigeria 2018, Pakistan 2017, Paraguay 2018, Somalia 2018, Spain 2019, Sri-Lanka 2017, USA 2019 (dates in `Sen1Floods11_Metadata.geojson`) | UNVERIFIED (no LICENSE file in the repo, GitHub API returns no licence; the bucket is publicly readable; cite Bonafilia et al. 2020, CVPR-W) | hand-labelled subset ~1.75 GB; whole bucket ~14 GB per its README | `https://storage.googleapis.com/sen1floods11/v1.1/...` and bucket listing API, HTTP 200, no login | **TUNE (train+valid) and TEST (test, Bolivia)** | yes, hand-labelled subset |
| 3 | **GEOID-Flood** (Hugging Face `links-ads/geoid-flood`) | EMS Rapid Mapping delineations, "manually checked" 3-class labels (background / permanent water / flooded) on 219 activations | S1 GRD and RTC pre/post (C-band), S2 L2A, GLO-30 DEM, 10 m, 1024x1024 tiles | 65 countries, 2016-2026; held-out tiles from EMSR857-EMSR871 (Jan-Apr 2026) | CC BY 4.0 (dataset card) | 329 GB total; held-out labels only 28 MB fetched (held-out S1/S2 are ~30 GB, not fetched) | `https://huggingface.co/datasets/links-ads/geoid-flood/resolve/main/...` HTTP 200, not gated | **TEST only** for the held-out tiles; the train/val part could tune but is far over budget | labels only |
| 4 | **MMFlood** (Zenodo 6534637; Temporal MMFlood 12805033) | Derived from EMS delineations, "manually validated annotations" | Sentinel-1 VV/VH (C-band), DEM, OSM hydrography, 20 m | 95 events, 42 countries, 2014-2021 (record text) | CC BY 4.0 (Zenodo API) | 11.3 GB (`mmflood.zip`); Temporal version 108 GB in per-event zips | Zenodo API HTTP 200, no login | tune or test (its own split) | **not fetched (size)** |
| 5 | **UrbanSARFloods v1** (HF `S1Floodbenchmark/UrbanSARFloods_v1`) | Semi-automatic urban/open-area flood labels, 18 events (paper) | Sentinel-1 SLC intensity + InSAR coherence (C-band) | 18 events, 5 continents, 8,879 chips | UNVERIFIED (not stated in the HF card; GitHub API shows none) | 38 GB tar; `testing_case_256` 2.1 GB (996 files) | HF tree API HTTP 200, not gated | test (urban flooding, coherence logic) | **not fetched (size)** |
| 6 | **WorldFloods v2** (HF `isp-uv-es/WorldFloodsv2`) | EMS/UNOSAT analyst maps plus manual S2 labels, 509 pairs (paper) | Sentinel-2 optical, 10 m (water vs land vs cloud) | global | CC BY-NC 4.0 (README) | ~76-79 GB | HF API HTTP 200, not gated | optical test only | **not fetched (size, NC)** |
| 7 | **Global Flood Database (GFD)** bucket `gs://gfd_v1_4` | Algorithmic (MODIS 250 m, Cloud to Street / DFO), not human-labelled; 913 event zips, 17.5 GB | MODIS optical, 250 m | 2000-2018 | CC BY-NC 4.0 (LICENSE.txt in each zip) | 17.5 GB total, ~30 MB per event | `https://storage.googleapis.com/gfd_v1_4/DFO_<id>_From_<start>_to_<end>.zip` HTTP 200, listing API open | coarse **test only**, 250 m cannot judge 10-30 m extents | 7 South/SE Asia events |
| 8 | **Dartmouth/Colorado Flood Observatory archive** | News/government compiled event polygons ("area affected"), not pixel masks | mixed | 1985-2021-10 (public layer ends 2021, 0 events in 2026) | free for scholarly use (site text, per search; UNVERIFIED on the page) | 5131 polygons, 9 MB geojson | ArcGIS FeatureServer `https://services1.arcgis.com/AXaYBvnJsB5Q7sDF/ArcGIS/rest/services/Global_Archive_of_large_flood_events/FeatureServer/0/query` HTTP 200; the `floodobservatory.colorado.edu/Archives/index.html` page is 404 | **catalogue only, no validation** | geojson |
| 9 | **DeepFlood** (figshare 28328339) | Manually made masks (vegetation-aware classes) on aerial/UAV imagery plus S1/S2 | optical aerial, S1 (C-band), DEM | UNVERIFIED region/years | CC BY 4.0 (figshare API) | ~0.4 GB (listed files) | figshare API HTTP 200 | test of flooded vegetation (best for the L-band question, but C-band SAR) | not fetched (region unchecked) |
| 10 | **L-band labelled flood data** (UAVSAR Hurricane Florence 2018, ALOS-2 PALSAR-2 Japan 2026 JDR paper, others) | Research-paper ground-truth polygons | L-band | US/Japan | not open as a ready dataset | n/a | Web search found papers only; no downloadable labelled mask tested | would be the only true L-band check | **not available** (action: contact the authors; see section 6) |
| 11 | **Mosaic v0** (Zenodo 23582250) | Probabilistic reliability layers for the 446 Sen1Floods11 chips, 38 MB | derived | as Sen1Floods11 | CC BY 4.0 | 38.6 MB | Zenodo HTTP 200 | tune diagnostics (label-noise weighting) | not fetched (optional) |

2026 Copernicus floods found in the activation list: EMSR926 Latvia/Lithuania (22 Aug 2026; all products "N", no download, remote-sensing limitations), EMSR927 Nepal (GLOF), EMSR933 Crete, EMSR935 Valencia/Alicante, plus EMSN238 Sardinia dam-break scenarios (modelled, not an observed flood). Earlier 2026 floods (Jan-Apr; EMSR854-EMSR871: Albania, Mozambique/South Africa, Portugal/Spain, Colombia, France, Greece, Ecuador, Italy) predate 2026-06-17 and are only partly reachable through GEOID-Flood held-out labels (fetched), or by the same API (not fetched). Event extents not yet fetched are available with `list.py`-style calls to the same endpoint (code in the session scratchpad, easily reproduced).

## 2. What was downloaded (`/home/sanjayvasudevan/nasa/team_data/datasets/`)

Full SHA-256 lists are in each folder (`SHA256SUMS_*.txt`, `MANIFEST_sha256.txt`). First 16 hex shown here.

### 2.1 `cems_2026/` (190 MB zips in `raw/`, extracted vectors per AOI)
Source: `https://rapidmapping.emergency.copernicus.eu/backend/<EMSR>/<AOI>/<PRODUCT>/<file>.zip`. Layer of interest: `*_observedEventA_v*.shp/.json` (observed event polygons); Crete/Spain also have `floodDepthA` (raster/vector) and `modelledEventA` (modelled, not observed: do not use as truth).

| File | Bytes | SHA-256 (first 16) | Content and caveat |
|---|---|---|---|
| EMSR927_AOI01_GRA_PRODUCT_v1.zip | 6,822,625 | e2fc2729d3e705ee | Nepal Syapru Besi, WorldView-3 2026-08-27, **landslide/debris polygons only, no water layer** |
| EMSR927_AOI02_GRA_PRODUCT_v2.zip | 6,910,842 | 1f57ba3370597055 | Nepal Timure, Legion 2026-08-27, landslide |
| EMSR927_AOI03_GRA_PRODUCT_v1.zip | 15,519,859 | 6e165c0297ecdfb0 | Nepal AOI03, Satellogic/BlackSky 2026-08-27, landslide |
| EMSR927_AOI03_GRA_MONIT01_v1.zip | 21,060,206 | d52ba875cf49b9b3 | Nepal AOI03 monitoring, PeruSAT-1/Resurs-P 2026-08-27/28 |
| EMSR927_AOI05_GRA_PRODUCT_v3.zip | 11,109,640 | 063b30ddfdb9a9fe | Nepal AOI05, Pleiades 2026-08-31 |
| EMSR927_AOI05_GRA_MONIT01_v2.zip | 18,143,514 | 46eea4ea497c05ad | Nepal AOI05, Legion/Pleiades Neo 2026-09-05 |
| EMSR933_AOI01_DEL_MONIT01_v1.zip | 20,299,154 | bbe7fe84c5f21fdf | Crete Kastelli, Legion 2026-10-06, 88 flash-flood polygons |
| EMSR933_AOI03_DEL_PRODUCT_v1.zip | 3,479,975 | 14789be38b4ded67 | Crete Tzermiado, **Sentinel-1 C-band 2026-10-04**, 13 polygons (the label is itself SAR-derived: circular for any C-band method) |
| EMSR933_AOI03_DEL_MONIT02_v1.zip | 14,343,107 | 07ae2fb6f7f1bf0c | Crete Tzermiado, GeoEye-1 2026-10-08, 618 polygons |
| EMSR933_AOI03_GRA_PRODUCT_v1.zip | 10,872,469 | 67908c72d1d736cc | Crete Tzermiado, Legion 2026-10-09, 6160 polygons (largest) |
| EMSR933_AOI04_DEL_MONIT01_v1.zip | 6,702,403 | 24339cffc56c67fe | Crete Agios Ioannis, WorldView-3 2026-10-06, 30 polygons |
| EMSR933_AOI06_DEL_MONIT01_v1.zip | 5,228,914 | a989df1406ee5f90 | Crete Agios Nikolaos, Legion 2026-10-08, 11 polygons |
| EMSR933_AOI07_DEL_MONIT01_v1.zip | 7,813,058 | 4e1f5386648915e6 | Crete Omalos, Legion 2026-10-06, 63 polygons |
| EMSR935_AOI01_DEL_PRODUCT_v1.zip | 18,692,927 | ccc7de41d3647b99 | Spain Moraira, SPOT-6/7 2026-10-20, 2 polygons |
| EMSR935_AOI02_GRA_PRODUCT_v1.zip | 22,937,803 | a70c54cac1ea12ff | Spain Gandia, GeoEye-1/SPOT-6/7 2026-10-20, 1676 polygons |

Findings on these:
* Nepal (the only South-Asia 2026 event) is a **glacial-lake flash flood**: the observed layer is landslide/debris, not inundation. It documents where NISAR-visible surface change should be (debris, destroyed bridges), not flood water. Treat as a change-detection test, not a water-mask test.
* Crete and Spain are small-AOI, VHR-optical, cloud-free-day maps made 1-9 days after the peak; water may have receded. These are the best NISAR-era answer keys, but they are small areas (hectares to a few km2) and mostly flash/urban floods.
* Whether NISAR actually imaged these AOIs on or near those dates is **UNVERIFIED** here (not checked against the NISAR archive); the next step is to query NISAR coverage per AOI footprint (`*imageFootprintA*` and `*areaOfInterestA*` shapefiles are included).

### 2.2 `sen1floods11/` (hand-labelled subset)
Source base: `https://storage.googleapis.com/sen1floods11/v1.1/` (files `data/flood_events/HandLabeled/{S1Hand,S2Hand,LabelHand,JRCWaterHand,S1OtsuLabelHand}/<Event>_<Chip>_<Layer>.tif`, `splits/flood_handlabeled/*.csv`, `Sen1Floods11_Metadata.geojson`). All 446 hand-labelled chips for 5 layers were fetched and every file size was checked against the bucket listing (2230 files, 0 mismatches): `S1Hand` (697 MB, 2-band VV/VH dB), `S2Hand` (973 MB, 13-band L1C), `LabelHand` (3.3 MB, the human answer key), `S1OtsuLabelHand` (2.6 MB, automatic Otsu labels from S1, comparison only), `JRCWaterHand` (1.8 MB, JRC permanent water). Total 1.75 GB. SHA-256 of every file: `sen1floods11/MANIFEST_sha256.txt`. Split CSVs (first 16 hex): flood_train_data 57be4dc440bf8a52 (252 chips), flood_valid_data 04999b82b93e393c (89), flood_test_data 8b598c9438042f3e (90), flood_bolivia_data 4775d100fae1f1ca (15), Sen1Floods11_Metadata.geojson 29790ad85135d03e. Events and dates are in the metadata (e.g. India 2016-08-12, Pakistan 2017-06-28, Sri-Lanka 2017-05-30, Cambodia 2018-08-05, Bolivia 2018-02-15). The rest of the bucket (weakly labelled chips, ~12 GB, checkpoints) was not fetched.

### 2.3 `geoid_flood_heldout/` (46 MB, labels only)
Source: `https://huggingface.co/datasets/links-ads/geoid-flood/resolve/main/geoid-flood-heldout/...`. Hashes verified against the dataset's own `SHA256SUMS` (label, permwater and validity tars and the catalogue parquet all matched; the csv was not cross-checked).

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| shards/test/label/test-label-00000-of-00001.tar | 12,697,600 | c44864c1d483840c |
| shards/test/permwater/test-permwater-00000-of-00001.tar | 7,424,000 | cc12941ce81d7dd0 |
| shards/test/validity/test-validity-00000-of-00001.tar | 7,669,760 | 66ba3ca642b09817 |
| tile_catalog.parquet | 85,227 | 9b531b90ca534d30 |
| data_tiles_s256_st128.csv | 17,510,245 | a6a8c0f311c8874d |

Tars are left packed (not extracted). The paired S1/S2 imagery for these tiles (~30 GB) was not fetched; labels alone cannot be scored without the NISAR scene anyway, only the geometry (tile catalogue) is needed to pick EMSR857-871 areas for NISAR re-tests.

### 2.4 `gfd_southasia/` (203 MB zips in `raw/`, extracted per event)
Source: `https://storage.googleapis.com/gfd_v1_4/<name>.zip` (CC BY-NC 4.0, MODIS 250 m, algorithmic labels, 3-day composites).

| Event zip | Country (DFO) | Dates | Bytes | SHA-256 (first 16) |
|---|---|---|---|---|
| DFO_4092_From_20130930_to_20131014 | Thailand | 2013 | 28,427,638 | ec032511aefc6425 |
| DFO_4198_From_20141012_to_20141027 | India (Hudhud) | 2014 | 28,814,630 | f3406ad85b093d97 |
| DFO_4382_From_20160725_to_20160826 | Bangladesh | 2016 | 41,706,484 | 90f0d51ce7bcfaaa |
| DFO_4507_From_20170810_to_20170826 | India/Nepal/Bangladesh | 2017 | 41,055,679 | 7cb4e7828d3f17e8 |
| DFO_4508_From_20170810_to_20170826 | Bangladesh | 2017 | 35,916,301 | 94becd1b6e7fc7f8 |
| DFO_4653_From_20180717_to_20180723 | Vietnam (Son-Tinh) | 2018 | 15,348,794 | cb3918a85959cd3a |
| DFO_4666_From_20180715_to_20180810 | Myanmar | 2018 | 12,219,157 | 6251ac72de091467 |

### 2.5 `dfo_archive/`
`FloodArchive_region.geojson`, 8,984,616 bytes, SHA-256 3f3b10a79d0ae77750c803afaddc9f09ef76f5d20f00b3712c8dbcfe93c580b7, 5131 event polygons 1985-01-01 to 2021-10-06 from the ArcGIS FeatureServer above. Use to look up the DFO ID for GFD events; no pixel truth.

Total on disk for all datasets: 2.51 GB (2,514,228,690 bytes; under the 3 GB cap; `gfd_southasia/` holds both the zips and their extracted contents, so ~0.2 GB is duplicated).

## 3. Sealed test split and tuning split (rule)

**Rule (write once, do not change).** The sealed set is touched by exactly one script, `eval_sealed`, run once per frozen method version after all thresholds, weights and calibration curves are fixed. Nobody looks at per-chip or per-polygon sealed results to adjust anything; only the aggregate metrics are read. Any chip, event or AOI seen during tuning (even visually) moves to the tuning side permanently. Splits are by event or activation, not by chip, because chips from one event are spatially autocorrelated.

**Tuning side (free to use, cross-validate by event):**
* Sen1Floods11 official `flood_train_data.csv` (252 chips) and `flood_valid_data.csv` (89 chips). For leave-event-out cross-validation use the event prefix of each chip name (Ghana, India, Mekong, Nigeria, Pakistan, Paraguay, Somalia, Spain, Sri-Lanka, USA).
* The same lists are in `splits_manifest.json` under `"tune"`.

**Sealed test side (never tune):**
1. Sen1Floods11 `flood_bolivia_data.csv` (15 chips): a wholly unseen event, the only event-blocked set in Sen1Floods11. Official `flood_test_data.csv` (90 chips) is a secondary sealed set, but its events also appear in train, so expect optimistic scores; report it separately.
2. All Copernicus EMS 2026 NISAR-era products: EMSR933 (Crete), EMSR935 (Spain), EMSR927 (Nepal). These are the primary sealed set for the real task.
3. GEOID-Flood held-out EMSR857-871 labels.
4. GFD South/SE Asia events (coarse; report as a sanity check only).

Machine-readable version: `/home/sanjayvasudevan/nasa/team_data/datasets/splits_manifest.json` (SHA-256 first 16: 1079cfb1bc87ea52).

## 4. What each set can and cannot validate

| Question | Sen1Floods11 | CEMS 2026 | GEOID held-out | GFD |
|---|---|---|---|---|
| Does the change-detection logic find water at all? | yes (C-band GRD, optical co-registered) | yes, small AOIs | yes | coarse |
| Is the confidence score calibrated (reliability curve)? | yes, 446 chips, 11 events | too few pixels per event alone, pool across AOIs | yes | no |
| Flooded vegetation / forest (the L-band advantage)? | no (labels optical, vegetation under-labelled) | partial, mostly urban/flash | no | no |
| NISAR thresholds (dB, HH/HV)? | no (C-band VV/VH) | needs NISAR pass over the AOI (UNVERIFIED availability) | no | no |
| South/SE Asian monsoon behaviour? | India, Pakistan, Sri-Lanka, Mekong: 168 of 446 chips (38 percent), 2016-2018 monsoon/cyclone events | Nepal (GLOF, debris) only | no | yes, coarse |

## 5. Blockers and caveats
* Sen1Floods11 licence is not stated in the repo (UNVERIFIED); check before any redistribution. GFD and WorldFloods are non-commercial.
* No pixel-labelled L-band flood set is publicly downloadable; the 2026 EMS maps are the nearest.
* The EMS activation listing endpoint also supports `?limit` paging; activation 926 (Latvia/Lithuania) has no downloadable product.
* The EMS terms of reuse were not re-read from the official page in this session (HTTP check of the cite page not done); the in-file XML only links to it.

## 6. Next steps (not done)
1. Query the NISAR archive for the footprints in `cems_2026/*imageFootprintA*` and list the NISAR-vs-EMS date gaps.
2. Ask the authors of the ALOS-2 (JDR 2026) and UAVSAR Florence papers for their ground-truth polygons (the only route to a labelled L-band check).
3. If budget allows, fetch MMFlood (11 GB) or UrbanSARFloods `testing_case_256` (2.1 GB) for a larger SAR-logic test.
