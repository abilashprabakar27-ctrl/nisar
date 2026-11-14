import datetime as dt
from pathlib import Path

import h5py
import numpy as np
import pytest

from workers import drivers as D

D0 = dt.date(2026, 6, 1)


def make_file(dirp, d, value, fill_cell=False):
    lon = np.round(np.arange(-179.95, 180, 0.1), 2)
    lat = np.round(np.arange(-89.95, 90, 0.1), 2)
    a = np.full((1, 3600, 1800), value, dtype="float32")
    if fill_cell:
        a[0, 1000:1003, 1000:1003] = -9999.9
    with h5py.File(Path(dirp) / D.IMERG_PATTERN.format(ymd=d.strftime("%Y%m%d")), "w") as f:
        f["precipitation"] = a
        f["lon"], f["lat"] = lon, lat


def test_reader_missing_and_fill(tmp_path):
    make_file(tmp_path, D0, 10.0)
    make_file(tmp_path, D0 + dt.timedelta(days=2), 4.0, fill_cell=True)
    # lon index 1000 -> -79.95, lat index 1000 -> 10.05
    bbox = (-79.96, 10.04, -79.94, 10.06)
    ser, miss = D.read_rain_series(bbox, D0, D0 + dt.timedelta(days=2), tmp_path, return_missing=True)
    assert [d for d, _ in ser] == [D0, D0 + dt.timedelta(days=2)]
    assert miss == [D0 + dt.timedelta(days=1)]
    assert ser[0][1] == pytest.approx(10.0)
    assert ser[1][1] == pytest.approx(4.0)  # fill cells ignored, never -9999


def test_reader_all_fill_is_nan(tmp_path):
    make_file(tmp_path, D0, -9999.9)
    ser = D.read_rain_series((0, 0, 0.01, 0.01), D0, D0, tmp_path)
    assert np.isnan(ser[0][1])


def series(vals, start=D0):
    return [(start + dt.timedelta(days=i), v) for i, v in enumerate(vals)]


def test_rain_empty():
    r = D.rain_driver([], (D0, D0))
    assert r["label"] == "Not supported" and "No rainfall data" in r["note"]


def build(window_vals):
    # 60 baseline days at 2 mm/day, then the antecedent window, change starts on last day
    vals = [2.0] * 60 + window_vals
    s = series(vals)
    return s, (s[-1][0], s[-1][0] + dt.timedelta(days=3))


def test_rain_likely_possible_not():
    s, cr = build([5.0] * 14)  # 70 mm >= 1.5*28, max 5
    assert D.rain_driver(s, cr)["label"] == "Possible"
    s, cr = build([5.0] * 13 + [30.0])  # both
    r = D.rain_driver(s, cr)
    assert r["label"] == "Likely" and r["evidence"]["max_daily_mm"] == 30.0
    assert r["interpretation"] is True
    s, cr = build([2.0] * 14)
    assert D.rain_driver(s, cr)["label"] == "Not supported"


def test_rain_threshold_edges():
    s, cr = build([0.5] * 13 + [D.MAX_DAILY_MM_HEAVY])  # max exactly 25 counts, total low
    assert D.rain_driver(s, cr)["label"] == "Possible"
    s, cr = build([0.5] * 13 + [D.MAX_DAILY_MM_HEAVY - 0.1])
    assert D.rain_driver(s, cr)["label"] == "Not supported"


def test_rain_wording():
    s, cr = build([5.0] * 13 + [30.0])
    txt = str(D.rain_driver(s, cr)).lower()
    assert "confirmed" not in txt and "caused" not in txt


def test_terrain(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    p = tmp_path / "dem.tif"
    z = np.full((50, 50), 5.0, dtype="float32")
    z[:, 25:] = 200.0 + np.arange(25) * 20  # steep high half
    with rasterio.open(p, "w", driver="GTiff", height=50, width=50, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(104, 13.3, 0.0003, 0.0003)) as ds:
        ds.write(z, 1)
    r = D.terrain_driver(p)
    assert r["driver"] == "low_flat_terrain" and r["label"] == "Possible"
    assert 0.4 < r["evidence"]["low_flat_share"] < 0.55
    flat = tmp_path / "flat.tif"
    with rasterio.open(flat, "w", driver="GTiff", height=10, width=10, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(104, 13.3, 0.0003, 0.0003)) as ds:
        ds.write(np.full((10, 10), 3.0, dtype="float32"), 1)
    assert D.terrain_driver(flat)["label"] == "Likely"


def test_collect_drivers(tmp_path):
    for i in range(20):
        make_file(tmp_path, D0 + dt.timedelta(days=i), 3.0)
    out = D.collect_drivers((0, 0, 0.1, 0.1), (D0 + dt.timedelta(days=19),) * 2, imerg_dir=tmp_path,
                            season_start=D0)
    assert len(out) == 1 and out[0]["label"] in {"Likely", "Possible", "Not supported"}


REAL = Path.home() / "imerg"


@pytest.mark.skipif(not REAL.exists(), reason="no real IMERG dir")
def test_real_tonle_sap():
    ser = D.read_rain_series((103.85, 12.65, 104.35, 13.15), dt.date(2026, 9, 1), dt.date(2026, 9, 5), REAL)
    assert len(ser) == 5 and all(0 <= v < 300 for _, v in ser)
