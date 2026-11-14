"""Honest accuracy harness: team water-change method vs OPERA new-water on Tonle Sap.

Calls the team method ONLY through its public function (app.science.change.detect_water_change), so it can
be re-run unchanged after the method changes. Thresholds/options are CLI flags, so tuning can use --subset
west and be judged on east and on the neighbouring window.

    PYTHONPATH=/home/sanjayvasudevan/nasa/pydeps:backend \
      /home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python backend/scripts/eval_tonlesap.py

Scoring (strict): prediction = pixels classed "became water" (permanent water NOT counted);
reference = OPERA new water = DSWx-S1 open water (class 1) on the after date AND not open water (class 1)
on the nearest-in-time OPERA DSWx-HLS tile before. Only pixels where both OPERA products are usable
(before in 0/1/2, after in 0/1) and our method is not masked are compared ("comparable").
The "lenient" row reproduces what app/science/verify.py::compare does: our became+permanent water vs
all OPERA water (classes 1-3) on the after date, so the inflation from permanent water is visible.
OPERA is a second opinion, not ground truth.
"""
import argparse
import glob
import json
import os
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import config  # noqa: E402
from app.science import change, verify  # noqa: E402
from app.science.gcov import read_window  # noqa: E402
from app.science.grid import make_grid, resample  # noqa: E402

NISAR_DIR = Path(os.environ.get("NISAR_DATA", "/home/sanjayvasudevan/nisar_data"))
REF_DIR = Path("/home/sanjayvasudevan/nasa/nasa_project/data/reference/tonlesap")
BBOX = [103.90, 13.05, 104.12, 13.27]   # validated window (science/scripts/precompute_demo.py)


# ---------------------------------------------------------------- data
def pass_file(track: str, day: str) -> str:
    hits = glob.glob(str(NISAR_DIR / f"NISAR_L2_PR_GCOV_*_{track}_*_{day.replace('-', '')}T*.h5"))
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one file for track {track} on {day}, found {hits}")
    return hits[0]


def load_passes(bbox, track, days, grid_ref=None):
    wins = [read_window(pass_file(track, d), bbox, d) for d in days]
    return wins


def onto_grid(tif, grid):
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    dst = np.full(grid.shape, 255, "uint8")
    with rasterio.open(tif) as src:
        rw.reproject(rasterio.band(src, 1), dst,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=Resampling.nearest, dst_nodata=255)
    return dst


def merge_first_valid(layers):
    out = np.full_like(layers[0], 255)
    for l in layers:
        out = np.where(out == 255, l, out)
    return out


def tile_id(path):
    return os.path.basename(path).split("_")[3]


def opera_layers(grid, before_day, after_day):
    """OPERA S1 after (that date, all tiles) and HLS before (nearest in time, chosen per tile)."""
    s1 = sorted(glob.glob(str(REF_DIR / f"OPERA_L3_DSWx-S1_*_{after_day.replace('-', '')}T*_WTR.tif")))
    if not s1:
        raise SystemExit(f"no OPERA S1 tile for {after_day} in {REF_DIR}")
    hls = sorted(glob.glob(str(REF_DIR / "OPERA_L3_DSWx-HLS_*_WTR.tif")))
    bd = date.fromisoformat(before_day)
    best = {}
    for f in hls:
        d = os.path.basename(f).split("_")[4][:8]
        gap = abs((date(int(d[:4]), int(d[4:6]), int(d[6:])) - bd).days)
        if tile_id(f) not in best or gap < best[tile_id(f)][0]:
            best[tile_id(f)] = (gap, f)
    after = merge_first_valid([onto_grid(f, grid) for f in s1])
    before = merge_first_valid([onto_grid(f, grid) for _, f in best.values()])
    used = [os.path.basename(f) for f in s1] + [os.path.basename(f) for _, f in best.values()]
    return before, after, used


def slope_mask_for(grid, max_deg):
    """Slope > max_deg from the reference Copernicus DEM (same rule as app.data_sources.slope_mask)."""
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    dem = np.full(grid.shape, np.nan, "float32")
    with rasterio.open(REF_DIR / "dem_copernicus30.tif") as src:
        rw.reproject(rasterio.band(src, 1), dem,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=Resampling.bilinear, dst_nodata=np.nan)
    gy, gx = np.gradient(np.nan_to_num(dem, nan=float(np.nanmedian(dem))), grid.res)
    return np.degrees(np.arctan(np.hypot(gx, gy))) > max_deg


def jrc_mask_for(grid, min_occ):
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    occ = np.zeros(grid.shape, "float32")
    with rasterio.open(REF_DIR / "jrc_occurrence.tif") as src:
        rw.reproject(rasterio.band(src, 1), occ,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=Resampling.nearest, dst_nodata=0)
    return occ >= min_occ


# ---------------------------------------------------------------- metrics
def prf(pred, ref, valid):
    p, r = pred & valid, ref & valid
    tp = int((p & r).sum())
    np_, nr = int(p.sum()), int(r.sum())
    union = int((p | r).sum())
    prec = tp / np_ if np_ else None
    rec = tp / nr if nr else None
    f1 = 2 * tp / (np_ + nr) if (np_ + nr) else None
    return {"iou": tp / union if union else None, "precision": prec, "recall": rec, "f1": f1,
            "pred_px": np_, "ref_px": nr, "tp_px": tp,
            "comparable": float(valid.mean()) if valid.size else None}


def score_region(classes, before_o, after_o, sl, grid):
    c, bo, ao = classes[sl], before_o[sl], after_o[sl]
    unmasked = c != change.MASKED
    valid = np.isin(bo, (0, 1, 2)) & np.isin(ao, (0, 1)) & unmasked
    strict = prf(c == change.BECAME_WATER, (ao == 1) & (bo != 1), valid)
    # Lenient = the team's current verify.compare (became + permanent vs all OPERA water, classes 1-3)
    cmp = verify.compare(c, grid, ao)["all_water"]
    both, ours, theirs = cmp["both_ha"], cmp["nisar_water_ha"], cmp["opera_water_ha"]
    union = ours + theirs - both
    lenient = {"iou": both / union if union else None, "precision": both / ours if ours else None,
               "recall": both / theirs if theirs else None,
               "f1": 2 * both / (ours + theirs) if (ours + theirs) else None,
               "pred_px": None, "ref_px": None, "tp_px": None,
               "comparable": float(((ao < 250) & unmasked).mean())}
    return {"strict": strict, "lenient": lenient}


# ---------------------------------------------------------------- run
def run_window(name, bbox, args):
    wins_b = load_passes(bbox, args.track, args.before)
    wins_a = load_passes(bbox, args.track, args.after)
    grid = make_grid(bbox, wins_b[0].epsg, args.res)
    hh_b = [resample(w, grid, "hh") for w in wins_b]
    hh_a = [resample(w, grid, "hh") for w in wins_a]
    hv_b = [resample(w, grid, "hv") for w in wins_b] if not args.no_hv else None
    hv_a = [resample(w, grid, "hv") for w in wins_a] if not args.no_hv else None
    extra = np.zeros(grid.shape, bool)
    if args.slope_deg > 0:
        extra |= slope_mask_for(grid, args.slope_deg)
    if args.jrc_min > 0:
        extra |= jrc_mask_for(grid, args.jrc_min)
    r = change.detect_water_change(hh_b, hh_a, grid.pixel_ha, extra_mask=extra if extra.any() else None,
                                   before_hv=hv_b, after_hv=hv_a, lee_size=args.lee_size)
    before_o, after_o, used = opera_layers(grid, args.before[-1], args.after[-1])
    # split west/east at the window's centre longitude
    from pyproj import Transformer
    t = Transformer.from_crs(4326, grid.epsg, always_xy=True)
    xmid = t.transform((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)[0]
    k = int(np.searchsorted(grid.x, xmid))
    regions = {"whole": (slice(None), slice(None)), "west": (slice(None), slice(0, k)),
               "east": (slice(None), slice(k, None))}
    out = {n: score_region(r.classes, before_o, after_o, sl, grid) for n, sl in regions.items()}
    meta = {"bbox": bbox, "shape": list(grid.shape), "res_m": grid.res, "opera_files": used,
            "areas_ha": r.areas_ha, "threshold_hh_db": r.threshold_db, "threshold_hv_db": r.threshold_hv_db,
            "persistence": r.persistence, "masked_fraction": r.masked_fraction}
    return out, meta


def fmt(v, pct=False):
    return "  n/a" if v is None else f"{v:5.2f}"


def table(results, kind):
    rows = [("whole window", results["main"]["whole"]), ("WEST half", results["main"]["west"]),
            ("EAST half", results["main"]["east"]), ("south neighbour", results["neighbour"]["whole"])]
    lines = [f"{'region':<16}{'IoU':>7}{'prec':>7}{'recall':>7}{'F1':>7}{'comparable':>12}{'pred px':>10}{'ref px':>9}"]
    for n, d in rows:
        m = d[kind]
        lines.append(f"{n:<16}{fmt(m['iou']):>7}{fmt(m['precision']):>7}{fmt(m['recall']):>7}{fmt(m['f1']):>7}"
                     f"{m['comparable']:>12.0%}{(m['pred_px'] if m['pred_px'] is not None else '-'):>10}"
                     f"{(m['ref_px'] if m['ref_px'] is not None else '-'):>9}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track", default="083", help="NISAR track token in the file name (083 = Tonle Sap)")
    ap.add_argument("--before", nargs=2, default=["2026-07-13", "2026-07-25"], metavar="DATE")
    ap.add_argument("--after", nargs=2, default=["2026-09-23", "2026-10-05"], metavar="DATE")
    ap.add_argument("--bbox", nargs=4, type=float, default=BBOX, metavar=("W", "S", "E", "N"))
    ap.add_argument("--south-shift", type=float, default=0.22, help="degrees the neighbour window is shifted south")
    ap.add_argument("--water-hh", type=float, default=config.WATER_HH_DB, help="HH water threshold, dB")
    ap.add_argument("--water-hv", type=float, default=config.WATER_HV_DB, help="HV water threshold, dB")
    ap.add_argument("--change-db", type=float, default=config.CHANGE_DB, help="change threshold, dB")
    ap.add_argument("--min-patch-ha", type=float, default=config.MIN_PATCH_HA)
    ap.add_argument("--threshold-mode", choices=["fixed", "otsu"], default=config.THRESHOLD_MODE)
    ap.add_argument("--lee-size", type=int, default=7)
    ap.add_argument("--res", type=float, default=config.TARGET_RES_M, help="grid resolution, m")
    ap.add_argument("--no-hv", action="store_true", help="HH-only detection")
    ap.add_argument("--slope-deg", type=float, default=10.0, help="mask DEM slope above this (0 = off)")
    ap.add_argument("--jrc-min", type=float, default=0.0, help="mask JRC occurrence >= this %% (0 = off; team pipeline: off)")
    ap.add_argument("--subset", choices=["all", "west"], default="all",
                    help="'west' = compute and print WEST half only (for tuning without peeking at east/neighbour)")
    ap.add_argument("--json", default=None, help="JSON output path (default: eval_tonlesap_result.json beside this script's data dir)")
    args = ap.parse_args()

    config.WATER_HH_DB, config.WATER_HV_DB, config.CHANGE_DB = args.water_hh, args.water_hv, args.change_db
    config.MIN_PATCH_HA, config.THRESHOLD_MODE = args.min_patch_ha, args.threshold_mode
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    nb = [args.bbox[0], args.bbox[1] - args.south_shift, args.bbox[2], args.bbox[3] - args.south_shift]
    settings = {k: v for k, v in vars(args).items() if k != "json"}
    main_res, main_meta = run_window("main", args.bbox, args)
    if args.subset == "west":
        res = {"main": {"west": main_res["west"]}, "settings": settings}
        for kind in ("strict", "lenient"):
            m = main_res["west"][kind]
            print(f"WEST only [{kind}] IoU {fmt(m['iou'])} precision {fmt(m['precision'])} recall {fmt(m['recall'])} "
                  f"F1 {fmt(m['f1'])} comparable {m['comparable']:.0%}")
        _write(args, res)
        return
    nb_res, nb_meta = run_window("neighbour", nb, args)
    results = {"settings": settings, "main": main_res, "neighbour": nb_res,
               "meta": {"main": main_meta, "neighbour": nb_meta}}
    print(f"Tonle Sap eval | HH<{args.water_hh} HV<{args.water_hv} change {args.change_db} dB | before {args.before} "
          f"after {args.after} | track {args.track} | {'HH-only' if args.no_hv else 'HH+HV'} | mode {args.threshold_mode}")
    print(f"main bbox {args.bbox} | neighbour bbox {nb}")
    print("\nSTRICT: became-water vs OPERA new-water (permanent water excluded)")
    print(table(results, "strict"))
    print("\nLENIENT (as verify.compare): became+permanent vs all OPERA water -- inflated by permanent water")
    print(table(results, "lenient"))
    _write(args, results)


def _write(args, results):
    path = Path(args.json) if args.json else BACKEND / "data" / "eval_tonlesap_last.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nJSON written to {path}")


if __name__ == "__main__":
    main()
