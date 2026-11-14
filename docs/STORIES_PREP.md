# Flood stories prep: Morigaon (Assam) and Kanpur (Uttar Pradesh)

Run date: 2026-11-15. All searches are public (no Earthdata login). No NISAR file was downloaded.
Python: `/home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python`.

Notes on the data:
- ASF returns one record per product. The same pass can appear under several collections:
  `NISAR_L2_GCOV_PROVISIONAL_V1` (Jun to mid-Oct), `NISAR_L2_GCOV_V1` (from about 20 Oct, validated "V1"), and `NISAR_UR_L2` (urgent-response duplicate). "Quality" below is that collection name (P05023 / P05036 are the CRIDs). I de-duplicated by pass, preferring V1 over PROVISIONAL over UR.
- Polarizations are `mainBandPolarization`. Some passes are quad-pol (HH,HV,VH,VV); the rest are dual (HH,HV). All are frameCoverage "Full" unless noted.
- Size is the main `.h5` file only (MB = bytes/1e6).
- Frame 75 = descending tracks, frame 15 = ascending tracks in these bboxes.
- The permanent NISAR data gap is 2026-07-27 to 2026-08-10. Confirmed in the results: no passes on any track dated 07-27 to 08-09.
- ASF dates are UTC acquisition start (the India local date can differ by a day).

## Exact queries

NISAR (one per story, bbox as WKT polygon):
```python
asf.geo_search(dataset=asf.DATASET.NISAR, processingLevel='GCOV',
  intersectsWith="POLYGON((92.15 26.15,92.4 26.15,92.4 26.4,92.15 26.4,92.15 26.15))",   # Morigaon
  start='2026-06-17T00:00:00Z', end='2026-11-16T00:00:00Z', maxResults=500)              # 41 products
asf.geo_search(dataset=asf.DATASET.NISAR, processingLevel='GCOV',
  intersectsWith="POLYGON((80.25 26.35,80.5 26.35,80.5 26.6,80.25 26.6,80.25 26.35))",   # Kanpur
  start='2026-06-17T00:00:00Z', end='2026-11-16T00:00:00Z', maxResults=500)              # 58 products
```
OPERA (earthaccess, no login):
```python
earthaccess.search_data(short_name='OPERA_L3_DSWX-S1_V1',  bounding_box=(92.15,26.15,92.4,26.4), temporal=('2026-08-13','2026-08-25'), count=200)  # Morigaon S1: 0
earthaccess.search_data(short_name='OPERA_L3_DSWX-HLS_V1', bounding_box=(92.15,26.15,92.4,26.4), temporal=('2026-07-08','2026-07-20'), count=200)  # Morigaon HLS: 5
earthaccess.search_data(short_name='OPERA_L3_DSWX-S1_V1',  bounding_box=(80.25,26.35,80.5,26.6), temporal=('2026-09-29','2026-10-11'), count=200)  # Kanpur S1: 2
earthaccess.search_data(short_name='OPERA_L3_DSWX-HLS_V1', bounding_box=(80.25,26.35,80.5,26.6), temporal=('2026-09-05','2026-09-17'), count=200)  # Kanpur HLS: 4
# widened check, Morigaon S1 2026-06-01..2026-10-15 (to see why the window was empty)
```

## Story 1: Morigaon, Assam (bbox [92.15,26.15,92.40,26.40], event 2026-07-20)

Passes by track + direction (de-duplicated; MB in brackets; Q = quad-pol, otherwise HH,HV):

| Track | Dir | Dates (all PROVISIONAL unless marked) |
|---|---|---|
| 91 | D | 06-20 (8502 Q), 07-02 (7059), 07-14 (8510 Q), 07-26 (7269), **gap**, 08-19 (7265), 08-31 (8733 Q), 09-12 (7059), 09-24 (8389 Q), 10-06 (7063), 10-18 (8489 Q), 10-30 (7265, V1), 11-11 (8397 Q, V1) |
| 141 | A | 06-23 (7286), 07-05 (7093), 07-17 (7290), **gap**, 08-10 (7093), 08-22 (5767), 09-03, 09-15, 09-27, 10-09 (about 7088 each), 10-21 (7080, V1), 11-02 (7286, V1) |
| 163 | D | 06-25 (7265), 07-19 (7072), **gap**, 08-12 (7265), 09-05 (7265; frame 76 also, 7437), 09-29 (7265; frame 76 also), 10-23 (7055, V1; frame 76 also) |

Can it be answered with 2 before + 2 after on a single track? Yes, but every option is weak:
- Track 91 D: before 07-02, 07-14; after 07-26 (+6 d), 08-19 (+30 d). 3 usable before passes (06-20 also). The two after passes straddle the permanent gap (07-26 to 08-19, 24 days apart). Flag this pair. The 07-26 pass is the very last one before the gap.
- Track 141 A: before 07-05, 07-17; after 08-10 (+21 d), 08-22. Event-to-first-after crosses the gap. 3 before passes (06-23, 07-05, 07-17).
- Track 163 D: before 06-25, 07-19 (1 day before the event, so effectively the event itself); after 08-12 (+23 d), 09-05. Only 2 before passes. Crosses the gap.
- Only 91 D has an after pass before the gap, and it is 6 days after the event. All other after passes are 3 weeks or more later, when the flood may have receded. There is no true "peak flood" capture in the data.

Nearest honest alternative with no gap straddle: move the event date to about 2026-07-08 (between the 07-02 and 07-14 passes). Track 91 D then gives before 06-20, 07-02 and after 07-14, 07-26, all before the gap, all within 5 weeks of the start of data. The reason is that 91 D has exactly four pre-gap passes (06-20, 07-02, 07-14, 07-26) at a 12-day repeat. The catch is that the story then becomes an early-July Brahmaputra rise instead of the 20 July peak. Track 141 A has only three pre-gap passes, so it cannot do 2+2 without the gap.

Recommended (keeping the 20 July event): Track 91 D, before 2026-07-02 + 2026-07-14, after 2026-07-26 + 2026-08-19 (gap-straddling after pair, flagged). All four are PROVISIONAL, frame 75, Full.
- Download: 7059 + 8510 + 7269 + 7265 = **30,103 MB (about 30.1 GB)**.
- All passes of track 91 D (12 unique Full passes, 06-20 to 11-11): **93,999 MB (about 94 GB)**.

OPERA DSWx-S1, +/-6 days of the last after pass 2026-08-19 (window 08-13 to 08-25): **none**. Widened query shows Morigaon S1 tiles exist for 06-04 to 06-26 and 09-13 onward (T46RDP and T46RDQ) but nothing between 06-26 and 09-13, so there is no S1 water mask for the July/August event at all. DSWx-HLS (optical, before reference), 2026-07-08 to 07-20, 5 tiles:
- OPERA_L3_DSWx-HLS_T46RDP_20260711T041551Z_..._S2C_30_v1.1 (07-11)
- OPERA_L3_DSWx-HLS_T46RDQ_20260714T041651Z_..._L8_30_v1.1 (07-14)
- OPERA_L3_DSWx-HLS_T46RDP_20260714T041739Z_..._L8_30_v1.1 (07-14)
- OPERA_L3_DSWx-HLS_T46RDQ_20260714T042701Z_..._S2C_30_v1.1 (07-14)
- OPERA_L3_DSWx-HLS_T46RDP_20260715T041115Z_..._L9_30_v1.1 (07-15)
(HLS is monsoon-cloud affected; check cloud flags before using it as a reference.)

Static layers: JRC Global Surface Water 10 deg tile `90E_30N` (lon 90-100E, lat 20-30N; e.g. `occurrence_90E_30N`). Copernicus DEM GLO-30 tile `Copernicus_DSM_COG_10_N26_00_E092_00_DEM` (N26 E092). The bbox fits inside one tile of each.

## Story 2: Kanpur, Uttar Pradesh (bbox [80.25,26.35,80.50,26.60], event 2026-09-22)

Passes by track + direction (de-duplicated; PROVISIONAL unless marked):

| Track | Dir | Dates (MB) |
|---|---|---|
| 5 | D | 06-26, 07-08, 07-20, **gap**, 08-13, 09-06 (8569 Q), 09-18 (8548 Q), 09-30 (8598 Q), 10-12 (7176), 10-24 (6996, V1), 11-05 (7176, V1); about 7180 for dual |
| 55 | A | 06-18, 06-30, 07-12, 07-24, **gap**, 08-17, 08-29, 09-10, **09-22 (event day)**, 10-04, 10-16 (about 6750 to 6940 each), 10-28, 11-09 (V1) |
| 77 | D | 06-19, 07-01, 07-13, 07-25, **gap**, 08-18, 08-30 (8871 Q), 09-11, 09-23 (8275 Q), 10-05, 10-17, 10-29 (V1), 11-10 (V1) |
| 127 | A | 06-22, 07-04, 07-16, **gap**, 08-21, 09-02, 09-14, 09-26, 10-20, 11-01 (V1), 11-13 |

Notes: Track 77 D has two products on many dates (a small "Full" about 1.9 GB and a "Partial" 4.4 to 6.0 GB, or a 6.8 to 8.9 GB Full on other dates). The small 1959 MB "Full" files on 09-11 and 10-05 look odd and should be checked (the 09-11 Partial is quad-pol 5847 MB). Tracks 5 and 55 are cleaner.

Can it be answered with 2+2 on one track? Yes, with no gap straddle, on three tracks:
- Track 77 D (recommended, closest after pass): before 2026-08-30 (8871 Q), 2026-09-11 (Full 1959; Partial 5847 Q available); after 2026-09-23 (8275 Q, only +1 day) and 2026-10-05 (Full 1959; Partial 5960).
- Track 5 D (cleanest fallback; every pass is Full and consistent): before 09-06, 09-18; after 09-30 (+8 d), 10-12. Total 8569 + 8548 + 8598 + 7176 = **32,892 MB (about 32.9 GB)**. All passes of track 5 D (10 Full passes): 75,988 MB (about 76 GB).
- Track 55 A: 08-29, 09-10 before; 09-22 is the event day itself; 10-04, 10-16 after. Depends on whether the app counts the event day as before or after.
- Track 127 A: before 09-02, 09-14; after 09-26, 10-20. After pair spans a 24-day jump, no gap issue.

Recommended: Track 77 D, before 2026-08-30 + 2026-09-11, after 2026-09-23 + 2026-10-05, all Full coverage frame 75.
- Download: 8871 + 1959 + 8275 + 1959 = **21,064 MB (about 21.1 GB)** (if the Full products are used; the Partial versions would be 8871 + 5847 + 8275 + 5960 = 28,953 MB). All Full passes of track 77 D: **56,430 MB** (85,878 MB including Partial products).
- If the small 77 D files are unsuitable, use Track 5 D (32.9 GB).

OPERA DSWx-S1, +/-6 days of the last after pass 2026-10-05 (window 09-29 to 10-11): **2 tiles**, both MGRS T44RMQ, Sentinel-1D:
- OPERA_L3_DSWx-S1_T44RMQ_20261001T123745Z_20261013T154312Z_S1D_30_v1.0 (10-01)
- OPERA_L3_DSWx-S1_T44RMQ_20261004T002727Z_20261013T101717Z_S1D_30_v1.0 (10-04)

DSWx-HLS (before reference), 2026-09-05 to 09-17, 4 tiles T44RMQ: 09-06 (S2A), 09-09 (S2B), 09-12 (S2B), 09-17 (L8).

Static layers: JRC GSW 10 deg tile `80E_30N` (lon 80-90E, lat 20-30N; e.g. `occurrence_80E_30N`). Copernicus DEM GLO-30 tile `Copernicus_DSM_COG_10_N26_00_E080_00_DEM` (N26 E080). Both bboxes sit fully inside a single tile.

## Summary table

| Story | Feasible with 2+2? | Recommended before / after | Download MB (2+2 / all of track) | OPERA available? | Verdict |
|---|---|---|---|---|---|
| Morigaon, Assam (event 07-20) | Yes, technically, but weak: only track 91 D has an after pass before the data gap (07-26, +6 d); the second after pass (08-19) crosses the 07-27 to 08-10 gap. All other tracks' first after pass is 3 weeks or more out. | Track 91 D: 07-02, 07-14 / 07-26, 08-19 (gap-straddling after pair) | 30,103 / 93,999 | S1: none near 08-19 (OPERA S1 has a hole 06-26 to 09-13). HLS before: 5 tiles 07-11 to 07-15. | Usable only as an "early peak plus recession" demo; weak flood-peak capture. Better: shift event to about 07-08 on 91 D (06-20, 07-02 / 07-14, 07-26, no gap). |
| Kanpur, UP (event 09-22) | Yes, on tracks 77 D, 5 D, 55 A, 127 A; no gap issue. | Track 77 D: 08-30, 09-11 / 09-23, 10-05 (fallback track 5 D: 09-06, 09-18 / 09-30, 10-12) | 21,064 / 56,430 (track 77 D Full); fallback 32,892 / 75,988 | S1: 2 tiles T44RMQ (10-01, 10-04). HLS before: 4 tiles (09-06 to 09-17). | Strong story. Go. |

What to do next: Run Kanpur first on track 77 D (check the odd small 1.9 GB "Full" files on 09-11 and 10-05, otherwise switch to track 5 D). For Morigaon, decide between keeping 07-20 with the gap-straddling after pair or moving the event to about 07-08 on track 91 D. Either way, state that OPERA S1 has no water mask for it. Downloads will need an Earthdata login.
