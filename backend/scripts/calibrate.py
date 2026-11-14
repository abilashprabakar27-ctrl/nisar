"""Measure how dark water and land really are in HH and HV for one area, using the NASA OPERA map
as a reference. Uses the cached pass windows (fast after the first run).

    python scripts/calibrate.py --name "Patna, Bihar" --bbox 85.00 25.35 85.25 25.60 --event 2026-09-07
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import catalog, config, pipeline  # noqa: E402
from app.science import change, verify  # noqa: E402
from app.science.gcov import read_window  # noqa: E402
from app.science.grid import make_grid, resample  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--bbox", nargs=4, type=float, required=True)
ap.add_argument("--event", required=True)
a = ap.parse_args()

passes = catalog.search_passes(a.bbox)
(trk, d), before, after, _ = catalog.choose_groups(passes, a.event)
wanted = {p.date for p in after}
todo = [p for p in passes if p.track == trk and p.direction == d and p.date in wanted]
wins = {}
for p in todo:
    try:
        wins.setdefault(p.date, []).append(read_window(p.url, a.bbox, p.date))
    except ValueError:
        pass
grid = make_grid(a.bbox, wins[after[0].date][0].epsg, config.TARGET_RES_M)


def merged(date, band):
    out = None
    for w in wins[date]:
        x = resample(w, grid, band)
        out = x if out is None else np.where(np.isfinite(out), out, x)
    return out


hh = change.composite([change.lee_filter(change.to_db(merged(p.date, "hh")), 7) for p in after])
hv = change.composite([change.lee_filter(change.to_db(merged(p.date, "hv")), 7) for p in after])

links = verify.find_opera(a.bbox, after[0].date)
if not links:
    sys.exit("No OPERA map found near the after date")
import earthaccess, tempfile  # noqa: E401,E402
f = earthaccess.open(links[:1])[0]
with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
    tmp.write(f.read())
opera = verify._read_onto_grid(tmp.name, grid)
valid = (opera < 250) & np.isfinite(hh) & np.isfinite(hv)
water = np.isin(opera, (1, 2, 3)) & valid
land = (opera == 0) & valid


def pct(x, m):
    v = x[m]
    return "  ".join(f"p{q}={np.percentile(v, q):6.1f}" for q in (5, 25, 50, 75, 95)) if v.size else "none"


print(f"OPERA file: {links[0].rsplit('/', 1)[-1]}")
print(f"pixels: water {water.sum()}, land {land.sum()}, valid share {valid.mean():.0%}")
print("HH dB  water:", pct(hh, water))
print("HH dB  land :", pct(hh, land))
print("HV dB  water:", pct(hv, water))
print("HV dB  land :", pct(hv, land))
print(f"Otsu HH (clamped -24..-15): {change.otsu_threshold(hh):.1f}   Otsu HV (clamped -32..-22): {change.otsu_threshold(hv, -32, -22):.1f}")
best = None
for t_hh in np.arange(-24, -10.5, 0.5):
    for t_hv in list(np.arange(-34, -14.5, 0.5)) + [99]:
        ours = (hh < t_hh) & (hv < t_hv) & valid
        tp = (ours & water).sum(); fp = (ours & land).sum(); fn = (water & ~ours).sum()
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if best is None or f1 > best[0]:
            best = (f1, t_hh, t_hv, tp / max(tp + fp, 1), tp / max(tp + fn, 1))
print(f"Best agreement with OPERA: HH < {best[1]:.1f} dB and HV < {best[2] if best[2] < 50 else 'any'} dB "
      f"(F1 {best[0]:.2f}, precision {best[3]:.0%}, recall {best[4]:.0%})")
print("Paste these lines to Claude.")
