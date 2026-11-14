"""Labelled sample data, so the website can be built before real NISAR data is processed.

Generates GCOV-like radar windows (river + a flood that appears after the event) and runs the
real pipeline on them. Results are marked source = "sample" everywhere.
"""
import numpy as np

from .models import Pass
from .science.gcov import Window, bbox_to_utm

SAMPLE_REQUEST = {
    "bbox": [85.00, 25.35, 85.25, 25.60], "name": "Sample area (Patna, Bihar)", "question": "change",
    "event_date": "2026-09-05", "looking_for": ["water"], "quick": False,
}
SAMPLE_DATES = ["2026-08-12", "2026-08-24", "2026-09-05", "2026-09-17"]


def sample_passes():
    return [Pass(date=d, track="98", direction="A", frame="10", quality="Provisional",
                 polarizations=["HH", "HV"], url=f"sample://{d}", name=f"SAMPLE_GCOV_{d}") for d in SAMPLE_DATES]


def _scene(bbox, date, res=10.0, epsg=32645):
    x0, y0, x1, y1 = bbox_to_utm(bbox, epsg)
    x = np.arange(x0 - 300, x1 + 300, res)
    y = np.arange(y1 + 300, y0 - 300, -res)
    X, Y = np.meshgrid((x - x0) / (x1 - x0), (y1 - y) / (y1 - y0))
    rng = np.random.default_rng(int(date.replace("-", "")))
    # river meander across the scene
    river_c = 0.5 + 0.12 * np.sin(X * 6.0) + 0.04 * np.sin(X * 17.0)
    d = np.abs(Y - river_c)
    river = d < 0.025
    flood_after = date >= SAMPLE_REQUEST["event_date"]
    flood = (d < 0.11 + 0.05 * np.sin(X * 9 + 1)) & (X > 0.15) & (X < 0.85) & flood_after
    hh_db = -7.5 + 1.5 * np.sin(X * 40) * np.cos(Y * 33)        # fields
    hv_db = -14.0 + 2.0 * np.sin(X * 25 + Y * 30)
    hh_db = np.where(river | flood, -22.0, hh_db)
    hv_db = np.where(river | flood, -29.0, hv_db)
    speckle = rng.gamma(4.0, 1 / 4.0, size=hh_db.shape)          # 4-look speckle
    hh = (10 ** (hh_db / 10)) * speckle
    hv = (10 ** (hv_db / 10)) * rng.gamma(4.0, 1 / 4.0, size=hh_db.shape)
    return Window(hh=hh.astype("float32"), hv=hv.astype("float32"), x=x + res / 2, y=y - res / 2, epsg=epsg, date=date)


def sample_reader(url, bbox, date):
    return _scene(bbox, date)


def build_sample(job_id=None):
    from .pipeline import run_analysis
    res = run_analysis(dict(SAMPLE_REQUEST), job_id, passes=sample_passes(), reader=sample_reader, online=False)
    res["source"] = "sample"
    res["note"] = "Sample result - not live data."
    from . import store
    store.save_result(res["id"], res)
    return res
