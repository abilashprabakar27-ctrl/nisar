# Reference data

## manifest.csv

Pairs each NISAR pass date (from `data/catalog/pass_counts.csv`, five demo AOIs) with the
closest OPERA DSWx granule (S1 or HLS) found via CMR.

Regenerate (search only, no login needed):

    python scripts/fetch_reference.py

Columns: `area, nisar_date, opera_product, opera_granule, opera_date, gap_days, download_url`.
`gap_days` is the absolute day difference. `download_url` is the B01_WTR GeoTIFF.
Rows with blank OPERA fields mean no granule was found in the AOI box.

Download (needs an Earthdata token, never commit it):

    EARTHDATA_TOKEN=... python scripts/fetch_reference.py --download

Files go to `data/raw/opera/<area>/` (git-ignored).

## Hand-labelled check points

`checkpoints_template.csv` is the schema for ~100 hand-labelled points used to check
results.

Columns: `area, lon, lat, label, source, annotator, date`.
`label` is `water` or `not_water`. `source` names the optical image, for example a Sentinel-2 scene ID.

How to label in QGIS:
1. Load a clear optical image from the same period. Pick a cloud-free scene; avoid
   scenes with floods covering most of the view.
2. Create a point layer (CRS EPSG:4326). Place about 100 points, spread across the AOI
   and across both classes (roughly balanced). Use random or stratified placement, not
   only obvious open-water cells.
3. Assign `water` only when you are confident the pixel is open water on that date. Use
   `not_water` for clear dry land, forest or vegetation. Skip ambiguous pixels.
4. Export as CSV and map the fields to the template columns. Record the image date and
   your name or ID.

Rule: check points must never be the points used to set thresholds. Keep threshold
tuning samples and check points in separate files, and fix the check set before tuning.
