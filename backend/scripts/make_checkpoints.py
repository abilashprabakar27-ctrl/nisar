"""Make a check-point file for accuracy: 50 points our map calls water, 50 it calls dry.

    python scripts/make_checkpoints.py --key <result id> --name "Patna, Bihar"

Writes data/drivers/<slug>/checkpoints.csv with lon,lat,ours,label. Open it in QGIS over a clear
photo (or OPERA map), fill the label column with "water" or "not water" WITHOUT looking at "ours",
then run prepare_demo.py again (or scripts/score.py) to get precision and recall.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, pipeline, store  # noqa: E402
from app.accuracy import WATER  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--key", required=True)
ap.add_argument("--name", required=True)
ap.add_argument("--n", type=int, default=50)
a = ap.parse_args()
res = store.load_result(a.key)
w, s, e, n = res["images"]["bounds"]
img = np.array(Image.open(config.RESULTS_DIR / a.key / "result.png").convert("RGBA"))
H, W = img.shape[:2]
water = np.zeros((H, W), bool)
for col in WATER:
    water |= (img[..., 0] == col[0]) & (img[..., 1] == col[1]) & (img[..., 2] == col[2]) & (img[..., 3] > 0)
dry = (img[..., 3] == 0)
rng = np.random.default_rng(7)
rows = []
for mask, ours in ((water, "water"), (dry, "not water")):
    rr, cc = np.nonzero(mask)
    if len(rr) == 0:
        continue
    pick = rng.choice(len(rr), size=min(a.n, len(rr)), replace=False)
    for i in pick:
        rows.append((round(w + (cc[i] + 0.5) / W * (e - w), 6), round(n - (rr[i] + 0.5) / H * (n - s), 6), ours, ""))
rng.shuffle(rows)
out = config.DRIVERS_DIR / pipeline.slug(a.name) / "checkpoints.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["lon", "lat", "ours", "label"])
    wr.writerows(rows)
print(f"Wrote {len(rows)} points to {out}")
