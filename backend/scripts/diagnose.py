"""Show what each NISAR file holds for an area (for fixing coverage problems).

    python scripts/diagnose.py --bbox 85.00 25.35 85.25 25.60 --dates 2026-08-19 2026-08-31 2026-09-12 2026-09-24
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import catalog  # noqa: E402
from app.science import gcov  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--bbox", nargs=4, type=float, required=True)
ap.add_argument("--dates", nargs="*")
ap.add_argument("--track")
a = ap.parse_args()
passes = catalog.search_passes(a.bbox)
for p in passes:
    if a.dates and p.date not in a.dates:
        continue
    if a.track and p.track != a.track:
        continue
    print(f"\n{p.date} track {p.track}{p.direction} frame {p.frame} quality {p.quality}\n  {p.name}")
    try:
        import h5py
        with h5py.File(gcov._open(p.url), "r") as f:
            g = f[gcov.GRID]
            x, y = g["xCoordinates"][()], g["yCoordinates"][()]
            epsg = gcov._epsg(f)
            x0, y0, x1, y1 = gcov.bbox_to_utm(a.bbox, epsg)
            print(f"  EPSG {epsg}; file x {x.min():.0f}-{x.max():.0f}, y {y.min():.0f}-{y.max():.0f}; spacing {x[1]-x[0]:.1f} m")
            print(f"  area  x {x0:.0f}-{x1:.0f}, y {y0:.0f}-{y1:.0f}")
            xi = np.where((x >= x0) & (x <= x1))[0]
            yi = np.where((y >= y0) & (y <= y1))[0]
            cover = (len(xi) * abs(x[1] - x[0])) * (len(yi) * abs(y[1] - y[0])) / ((x1 - x0) * (y1 - y0))
            print(f"  file covers {min(cover, 1):.0%} of the area box; layers: {sorted(g.keys())}")
            if len(xi) and len(yi):
                sl = (slice(yi.min(), yi.max() + 1), slice(xi.min(), xi.max() + 1))
                hh = g["HHHH"][sl]
                print(f"  HHHH: finite {np.isfinite(hh).mean():.0%}, >0 {np.mean(hh > 0):.0%}, median {np.nanmedian(hh):.4g}")
                if "mask" in g:
                    m = g["mask"][sl]
                    vals, cnt = np.unique(m, return_counts=True)
                    top = sorted(zip(cnt, vals), reverse=True)[:8]
                    print("  mask values (value: share): " + ", ".join(f"{v}: {c / m.size:.0%}" for c, v in top))
                    print("  mask attrs:", {k: str(v)[:120] for k, v in g["mask"].attrs.items()})
    except Exception as e:
        print("  ERROR:", e.__class__.__name__, e)
