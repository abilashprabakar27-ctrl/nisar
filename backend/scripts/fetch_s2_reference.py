"""Fetch an INDEPENDENT optical reference (Sentinel-2 L2A) for the flood-water evaluation windows.

For each area: search the open AWS Earth Search STAC (no login), keep scenes within +/- DAYS of any NISAR
before-date (or after-date) the eval harness uses, read ONLY the study window from the public COGs
(B03 green, B11 SWIR, SCL scene classification) onto the harness grid (20 m, same make_grid as the eval),
rank candidate dates by the share of the WINDOW that is valid in SCL (not the scene's cloud metadata), and
save the clearest date per side. Tiles of the same date are mosaicked (first valid wins).

Rasters go to /home/sanjayvasudevan/nasa/team_data/s2_reference (git-ignored data; never commit them).

    PYTHONPATH=/home/sanjayvasudevan/nasa/pydeps:backend \
      /home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python backend/scripts/fetch_s2_reference.py [--area tonlesap]

Sentinel-2 is a different sensor with its own errors (cloud edges, shadows read as water, flooded
vegetation and turbid water confuse MNDWI). It is independent of NISAR and OPERA; it is not ground truth.
"""
import argparse
import json
import sys
import warnings
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.science.grid import make_grid  # noqa: E402

STAC = "https://earth-search.aws.element84.com/v1/search"
OUT_DIR = Path("/home/sanjayvasudevan/nasa/team_data/s2_reference")
RES = 20.0
TONLE = [103.90, 13.05, 104.12, 13.27]
SHIFT = 0.22   # south neighbour shift, degrees (same as eval_tonlesap.py)
# NISAR before/after dates the eval harness uses per area
AREAS = {
    "tonlesap": dict(bbox=TONLE, before=["2026-07-13", "2026-07-25"], after=["2026-09-23", "2026-10-05"]),
    "tonlesap_south": dict(bbox=[TONLE[0], TONLE[1] - SHIFT, TONLE[2], TONLE[3] - SHIFT],
                           before=["2026-07-13", "2026-07-25"], after=["2026-09-23", "2026-10-05"]),
    "kanpur": dict(bbox=[80.25, 26.35, 80.50, 26.60], before=["2026-08-30", "2026-09-11"], after=["2026-09-23", "2026-10-05"]),
    "morigaon": dict(bbox=[92.15, 26.15, 92.40, 26.40], before=["2026-06-20", "2026-07-02"], after=["2026-07-14", "2026-07-26"]),
}
# SCL classes treated as NOT usable: 0 no data, 1 saturated/defective, 3 cloud shadow, 8/9 cloud, 10 cirrus, 11 snow/ice.
# Kept as valid: 2 dark area pixels, 4 vegetation, 5 not vegetated, 6 water, 7 unclassified.
SCL_BAD = (0, 1, 3, 8, 9, 10, 11)


def utm_epsg(bbox):
    lon, lat = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1


def search(bbox, d0, d1):
    import requests
    items, page = [], {
        "collections": ["sentinel-2-l2a"], "bbox": bbox, "datetime": f"{d0}T00:00:00Z/{d1}T23:59:59Z", "limit": 100}
    r = requests.post(STAC, json=page, timeout=60)
    r.raise_for_status()
    items += r.json()["features"]
    return items


def read_band(href, grid, resampling, dtype, nodata):
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    dst = np.full(grid.shape, nodata, dtype)
    with rasterio.open(href) as src:
        rw.reproject(rasterio.band(src, 1), dst,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=resampling, src_nodata=0 if dtype == "uint8" else 0,
                     dst_nodata=nodata)
    return dst


def scale_offset(item, asset):
    rb = item["assets"][asset].get("raster:bands", [{}])[0]
    return rb.get("scale", 1e-4), rb.get("offset", -0.1)


def scl_valid(scl):
    return ~np.isin(scl, SCL_BAD)


def candidate_dates(items, nisar_days, days):
    want = [date.fromisoformat(d) for d in nisar_days]
    by = defaultdict(list)
    for it in items:
        d = date.fromisoformat(it["properties"]["datetime"][:10])
        gap = min(abs((d - w).days) for w in want)
        if gap <= days:
            by[d].append(it)
    return by


def mosaic_scl(its, grid):
    from rasterio.enums import Resampling
    out = np.zeros(grid.shape, "uint8")
    for it in its:
        out = np.where(out == 0, read_band(it["assets"]["scl"]["href"], grid, Resampling.nearest, "uint8", 0), out)
    return out


def pick_side(name, side, items, nisar_days, days, grid):
    cands = candidate_dates(items, nisar_days, days)
    report = []
    best = None
    for d in sorted(cands):
        scl = mosaic_scl(cands[d], grid)
        v = float(scl_valid(scl).mean())
        gap = min(abs((d - date.fromisoformat(x)).days) for x in nisar_days)
        report.append({"date": d.isoformat(), "valid_frac": round(v, 3), "gap_days": gap,
                       "tiles": sorted(i["properties"].get("grid:code", i["id"]) for i in cands[d]),
                       "scene_cloud_meta": [round(i["properties"].get("eo:cloud_cover", -1), 1) for i in cands[d]]})
        print(f"  {name} {side} {d}: valid {v:.0%} (gap {gap} d, {len(cands[d])} tile(s))", flush=True)
        if best is None or (v, -gap) > (best[0], -best[1]):
            best = (v, gap, d, cands[d], scl)
    return best, report


def save_side(name, side, best, grid):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    v, gap, d, its, scl = best
    green = np.full(grid.shape, np.nan, "float32")
    swir = np.full(grid.shape, np.nan, "float32")
    for it in its:
        for arr, key, rs in ((green, "green", Resampling.average), (swir, "swir16", Resampling.bilinear)):
            raw = read_band(it["assets"][key]["href"], grid, rs, "float32", 0)
            sc, off = scale_offset(it, key)
            refl = np.where(raw > 0, raw * sc + off, np.nan).astype("float32")
            arr[:] = np.where(np.isfinite(arr), arr, refl)
    tr = from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res)
    prof = dict(driver="GTiff", height=grid.shape[0], width=grid.shape[1], crs=f"EPSG:{grid.epsg}", transform=tr,
                compress="deflate")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT_DIR / f"{name}_{side}_b03_b11.tif", "w", count=2, dtype="float32", nodata=np.nan, **prof) as f:
        f.write(green, 1)
        f.write(swir, 2)
    with rasterio.open(OUT_DIR / f"{name}_{side}_scl.tif", "w", count=1, dtype="uint8", nodata=0, **prof) as f:
        f.write(scl, 1)
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=["all"] + list(AREAS), default="all")
    ap.add_argument("--days", type=int, default=6, help="+/- days around each NISAR date")
    ap.add_argument("--min-valid", type=float, default=0.30,
                    help="below this valid share of the window a date is reported UNUSABLE and not saved")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    import os
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
    summary = {}
    for name, a in AREAS.items():
        if args.area not in ("all", name):
            continue
        grid = make_grid(a["bbox"], utm_epsg(a["bbox"]), RES)
        print(f"== {name} bbox {a['bbox']} grid {grid.shape} EPSG:{grid.epsg}")
        summary[name] = {"bbox": a["bbox"], "epsg": grid.epsg, "shape": list(grid.shape), "res_m": RES}
        for side in ("before", "after"):
            days = a[side]
            lo = (date.fromisoformat(min(days)) - timedelta(days=args.days)).isoformat()
            hi = (date.fromisoformat(max(days)) + timedelta(days=args.days)).isoformat()
            items = search(a["bbox"], lo, hi)
            best, report = pick_side(name, side, items, days, args.days, grid)
            rec = {"nisar_dates": days, "searched": [lo, hi], "n_items": len(items), "candidates": report}
            if best is None or best[0] < args.min_valid:
                rec["status"] = "UNUSABLE" if best else "NO SCENES"
                print(f"  -> {name} {side}: {rec['status']}")
            else:
                d = save_side(name, side, best, grid)
                rec.update(status="saved", date=d.isoformat(), valid_frac=round(best[0], 3))
                print(f"  -> {name} {side}: saved {d} valid {best[0]:.0%}")
            summary[name][side] = rec
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mp = OUT_DIR / ("manifest.json" if args.area == "all" else f"manifest_{args.area}.json")
    mp.write_text(json.dumps(summary, indent=2))
    print(f"manifest {mp}")


if __name__ == "__main__":
    main()
