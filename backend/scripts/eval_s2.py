"""Score the team water-change method against an INDEPENDENT optical reference (Sentinel-2 L2A MNDWI).

Report only: nothing here is tuned. The method is called exactly as eval_tonlesap.py calls it (same
function, same config defaults, same 20 m grid, same slope mask, same west/east/south-neighbour split;
its functions are imported, not copied). Reference rasters come from fetch_s2_reference.py.

    PYTHONPATH=/home/sanjayvasudevan/nasa/pydeps:backend \
      /home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python backend/scripts/eval_s2.py

Scoring: prediction = our class "became water"; reference = S2 new water = MNDWI water on the after scene
AND NOT MNDWI water on the before scene, compared only where BOTH S2 scenes are valid (SCL not cloud,
shadow, cirrus, snow, defective or no-data) and our method is not masked ("comparable").
MNDWI = (B03 - B11) / (B03 + B11); water = MNDWI > 0 (main) and > 0.1 (sensitivity).

Sentinel-2 is a different sensor with its own errors (cloud edges, shadows read as water, flooded
vegetation and turbid water confuse MNDWI). It is independent of NISAR and OPERA; it is not ground truth.

Kanpur / Morigaon: NISAR windows are read from the pipeline's local cache (NCE_DATA_DIR/cache, via
app.science.gcov.read_window with the catalogue URL), no network download of NISAR data; the method is
re-run on them with detect_water_change. Areas whose cache or S2 reference is missing are reported as skipped.
"""
import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np

os.environ.setdefault("NCE_DATA_DIR", "/home/sanjayvasudevan/nasa/team_data")   # where the pipeline cached NISAR windows
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import eval_tonlesap as et  # noqa: E402  (reuse: load_passes, slope_mask_for, prf, BBOX)
from app import config  # noqa: E402
from app.science import change  # noqa: E402
from app.science.grid import make_grid, resample  # noqa: E402
from fetch_s2_reference import AREAS, OUT_DIR, SCL_BAD, utm_epsg  # noqa: E402

THRESHOLDS = (0.0, 0.1)


def load_ref(name, side, grid):
    import rasterio
    b = OUT_DIR / f"{name}_{side}_b03_b11.tif"
    s = OUT_DIR / f"{name}_{side}_scl.tif"
    if not (b.exists() and s.exists()):
        return None
    with rasterio.open(b) as f:
        g, sw = f.read(1), f.read(2)
    with rasterio.open(s) as f:
        scl = f.read(1)
    if g.shape != grid.shape:
        raise SystemExit(f"{name}_{side}: reference shape {g.shape} != grid {grid.shape}; re-run fetch_s2_reference.py")
    # dark water can have SWIR reflectance slightly below zero after the L2A offset; a negative denominator would flip the
    # sign of MNDWI, so reflectances are floored at 1e-4 (a standard guard, not a tuned value)
    g, sw = np.maximum(g, 1e-4), np.maximum(sw, 1e-4)
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (g - sw) / (g + sw)
    valid = ~np.isin(scl, SCL_BAD) & np.isfinite(mndwi)
    return mndwi, valid


def s2_new_water(rb, ra, thr):
    (mb, vb), (ma, va) = rb, ra
    return (ma > thr) & ~(mb > thr), vb & va


def our_classes(name, bbox, args):
    """Run the method as eval_tonlesap does (local NISAR files) or from the pipeline cache (Kanpur, Morigaon)."""
    if name.startswith("tonlesap"):
        wb = et.load_passes(bbox, "083", ["2026-07-13", "2026-07-25"])
        wa = et.load_passes(bbox, "083", ["2026-09-23", "2026-10-05"])
        slope = True
    else:
        from app import catalog
        from app.science import gcov
        want = {"kanpur": ("77", AREAS["kanpur"]), "morigaon": ("91", AREAS["morigaon"])}[name]
        trk, a = want
        passes = [p for p in catalog.search_passes(bbox) if p.track == trk]
        by = {}
        for p in passes:
            if gcov.is_cached(p.url, bbox):
                by[p.date] = p
        miss = [d for d in a["before"] + a["after"] if d not in by]
        if miss:
            return None, f"NISAR pass(es) {miss} not in the local cache for track {trk}"
        wb = [gcov.read_window(by[d].url, bbox, d) for d in a["before"]]
        wa = [gcov.read_window(by[d].url, bbox, d) for d in a["after"]]
        slope = False
    grid = make_grid(bbox, wb[0].epsg, config.TARGET_RES_M)
    hh_b, hh_a = [resample(w, grid, "hh") for w in wb], [resample(w, grid, "hh") for w in wa]
    hv_b, hv_a = [resample(w, grid, "hv") for w in wb], [resample(w, grid, "hv") for w in wa]
    extra, note = np.zeros(grid.shape, bool), "no DEM slope mask (not wired in this script for this area)"
    if slope:
        extra |= et.slope_mask_for(grid, 10.0)
        note = "slope > 10 deg masked (reference Copernicus DEM, as eval_tonlesap)"
    r = change.detect_water_change(hh_b, hh_a, grid.pixel_ha, extra_mask=extra if extra.any() else None,
                                   before_hv=hv_b, after_hv=hv_a, lee_size=7)
    return (r, grid), note


def regions_for(bbox, grid, split):
    if not split:
        return {"whole": (slice(None), slice(None))}
    from pyproj import Transformer
    t = Transformer.from_crs(4326, grid.epsg, always_xy=True)
    xmid = t.transform((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)[0]
    k = int(np.searchsorted(grid.x, xmid))
    return {"whole": (slice(None), slice(None)), "west": (slice(None), slice(0, k)), "east": (slice(None), slice(k, None))}


def evaluate(name, split, args):
    bbox = AREAS[name]["bbox"]
    grid0 = make_grid(bbox, utm_epsg(bbox), config.TARGET_RES_M)
    rb, ra = load_ref(name, "before", grid0), load_ref(name, "after", grid0)
    if rb is None or ra is None:
        return {"skipped": "no usable Sentinel-2 scene on the " + " and ".join(
            s for s, r in (("before", rb), ("after", ra)) if r is None) + " side (see manifest.json)"}
    res, note = our_classes(name, bbox, args)
    if res is None:
        return {"skipped": note}
    r, grid = res
    if grid.shape != grid0.shape:
        raise SystemExit(f"{name}: NISAR grid {grid.shape} != S2 grid {grid0.shape}")
    out = {"note": note, "regions": {}}
    pred = r.classes == change.BECAME_WATER
    unmasked = r.classes != change.MASKED
    for rn, sl in regions_for(bbox, grid, split).items():
        out["regions"][rn] = {}
        for thr in THRESHOLDS:
            ref, v = s2_new_water(rb, ra, thr)
            valid = v & unmasked
            out["regions"][rn][f"mndwi>{thr}"] = et.prf(pred[sl], ref[sl], valid[sl])
    return out


def fmt(v):
    return "  n/a" if v is None else f"{v:5.2f}"


def show(name, label, res):
    print(f"\n== {label}")
    if "skipped" in res:
        print("   SKIPPED:", res["skipped"])
        return
    print("   ", res["note"])
    for thr in THRESHOLDS:
        print(f"   MNDWI > {thr}")
        print(f"   {'region':<8}{'IoU':>7}{'prec':>7}{'recall':>7}{'F1':>7}{'comparable':>12}{'pred px':>10}{'S2 px':>9}")
        for rn, d in res["regions"].items():
            m = d[f"mndwi>{thr}"]
            print(f"   {rn:<8}{fmt(m['iou']):>7}{fmt(m['precision']):>7}{fmt(m['recall']):>7}{fmt(m['f1']):>7}"
                  f"{m['comparable']:>12.0%}{m['pred_px']:>10}{m['ref_px']:>9}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=["all"] + list(AREAS), default="all")
    ap.add_argument("--json", default=str(OUT_DIR / "eval_s2_last.json"))
    args = ap.parse_args()
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    labels = {"tonlesap": ("Tonle Sap window", True), "tonlesap_south": ("Tonle Sap south neighbour", False),
              "kanpur": ("Kanpur", False), "morigaon": ("Morigaon", False)}
    results = {}
    for name, (label, split) in labels.items():
        if args.area not in ("all", name):
            continue
        results[name] = evaluate(name, split, args)
        show(name, label, results[name])
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(results, indent=2, default=float))
    print(f"\nJSON written to {args.json}")


if __name__ == "__main__":
    main()
