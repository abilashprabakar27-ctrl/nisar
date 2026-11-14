"""Score a result against hand-checked points (precision, recall, confusion matrix).

Check-point CSV (from QGIS): lon,lat,label   where label is "water" or "not water" (also 1/0, yes/no)
Water in our map = became water or permanent water, read from result.png colours at each point.
"""
import csv
from pathlib import Path

import numpy as np
from PIL import Image

from . import config, store

WATER = {(29, 78, 216), (10, 12, 16)}  # became water, permanent water (see science/render.py)


def _is_water_label(v: str) -> bool:
    return str(v).strip().lower() in ("water", "1", "yes", "true", "w")


def score(key: str, points_csv: Path) -> dict:
    res = store.load_result(key)
    if not res:
        raise ValueError(f"No result {key}")
    w, s, e, n = res["images"]["bounds"]
    img = np.array(Image.open(config.RESULTS_DIR / key / "result.png").convert("RGBA"))
    H, W = img.shape[:2]
    tp = fp = fn = tn = skipped = 0
    with open(points_csv, newline="") as f:
        for row in csv.DictReader(f):
            lon, lat = float(row.get("lon") or row.get("x")), float(row.get("lat") or row.get("y"))
            truth = _is_water_label(row.get("label", row.get("class", "")))
            c = int((lon - w) / (e - w) * W)
            r = int((n - lat) / (n - s) * H)
            if not (0 <= r < H and 0 <= c < W):
                skipped += 1
                continue
            px = tuple(int(v) for v in img[r, c, :3])
            if img[r, c, 3] == 70:  # masked grey: cannot judge
                skipped += 1
                continue
            ours = bool(img[r, c, 3] > 0 and px in WATER)
            tp += int(ours and truth)
            fp += int(ours and not truth)
            fn += int((not ours) and truth)
            tn += int((not ours) and not truth)
    precision = 100.0 * tp / max(tp + fp, 1)
    recall = 100.0 * tp / max(tp + fn, 1)
    out = {"points": tp + fp + fn + tn, "skipped": skipped, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
           "precision_pct": round(precision, 1), "recall_pct": round(recall, 1),
           "accuracy_pct": round(100.0 * (tp + tn) / max(tp + fp + fn + tn, 1), 1)}
    res["accuracy"] = out
    store.save_result(key, res)
    return out
