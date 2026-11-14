"""Download feature: byte counting, % done / time left, caching, cancel, and the API."""
import time

import h5py
import numpy as np
import pytest

from app import catalog, config, downloads, store
from app.models import Pass
from app.science import gcov

BBOX = [85.0, 25.5, 85.1, 25.6]


def _make_gcov(path, seed):
    """A small file in the real NISAR GCOV layout, in UTM 45N, covering BBOX."""
    from pyproj import Transformer
    t = Transformer.from_crs(4326, 32645, always_xy=True)
    x0, y0 = t.transform(84.98, 25.48)
    x1, y1 = t.transform(85.12, 25.62)
    x = np.arange(x0, x1, 40.0)
    y = np.arange(y1, y0, -40.0)
    rng = np.random.default_rng(seed)
    g = gcov.GRID
    with h5py.File(path, "w") as f:
        f[f"{g}/xCoordinates"] = x
        f[f"{g}/yCoordinates"] = y
        f.create_dataset(f"{g}/HHHH", data=rng.random((y.size, x.size), dtype="float32") * 0.3, chunks=(64, 64))
        f.create_dataset(f"{g}/HVHV", data=rng.random((y.size, x.size), dtype="float32") * 0.05, chunks=(64, 64))
        f.create_dataset(f"{g}/mask", data=np.ones((y.size, x.size), "uint8"), chunks=(64, 64))
        f[f"{g}/projection"] = np.int32(32645)
        f[f"{g}/projection"].attrs["epsg_code"] = 32645


class SlowFile:
    """A local file that behaves like a slow network link."""

    def __init__(self, path, delay=0.0004):
        self.f, self.delay = open(path, "rb"), delay

    def read(self, n=-1):
        time.sleep(self.delay)
        return self.f.read(n)

    def readinto(self, b):
        time.sleep(self.delay)
        return self.f.readinto(b)

    def seek(self, *a):
        return self.f.seek(*a)

    def tell(self):
        return self.f.tell()

    def close(self):
        self.f.close()


@pytest.fixture
def fake_nasa(tmp_path, monkeypatch):
    files = {}
    passes = []
    for i, d in enumerate(["2026-08-19", "2026-08-31", "2026-09-12", "2026-09-24"]):
        p = tmp_path / f"g{i}.h5"
        _make_gcov(p, i)
        url = f"https://fake.nasa/{p.name}"
        files[url] = p
        passes.append(Pass(date=d, track="98", direction="A", frame="14", quality="Provisional",
                           polarizations=["HH", "HV"], url=url))
    monkeypatch.setattr(gcov, "_open", lambda url: SlowFile(files[url]))
    monkeypatch.setattr(gcov, "_login", lambda: None)
    monkeypatch.setattr(catalog, "search_passes", lambda bbox, *a, **k: passes)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    monkeypatch.setattr(config, "DL_STATS_FILE", tmp_path / "stats.json")
    return passes


def test_counting_and_cache(fake_nasa):
    got = []
    w = gcov.read_window(fake_nasa[0].url, BBOX, "2026-08-19", progress=got.append)
    assert w.hh.size > 0 and w.hv is not None
    assert sum(got) > 10_000                      # bytes were reported as they arrived
    assert gcov.is_cached(fake_nasa[0].url, BBOX)
    got.clear()
    gcov.read_window(fake_nasa[0].url, BBOX, "2026-08-19", progress=got.append)
    assert sum(got) == 0                          # second time: from this computer, nothing downloaded


def test_status_and_estimate(fake_nasa):
    st = downloads.status(BBOX, scope="all")
    assert st["frames_total"] == 4 and st["frames_to_download"] == 4 and not st["all_downloaded"]
    assert st["estimate"]["seconds"] > 0 and st["estimate"]["measured"] is False
    q = downloads.status(BBOX, "2026-09-01", scope="question")
    assert q["frames_total"] == 4 and q["passes_total"] == 4


def test_tracker_math():
    tr = downloads.Tracker(4)
    tr.add(50 * downloads.MB)
    tr.frame_done(50 * downloads.MB)              # now we know a frame is ~50 MB
    s = tr.snapshot()
    assert s["mb_total"] == 200 and 24 <= s["pct"] <= 26 and s["eta_s"] >= 0
    for _ in range(3):
        tr.add(50 * downloads.MB)
        tr.frame_done(50 * downloads.MB)
    assert tr.snapshot()["pct"] == 100 and tr.snapshot()["eta_s"] == 0


def test_download_job_end_to_end(fake_nasa):
    job = store.new_job("dl-test1", "download", {"bbox": BBOX, "scope": "all", "name": "Test"})
    downloads.run_job(job["id"], {"bbox": BBOX, "scope": "all", "name": "Test", "extras": False})
    j = store.load_job(job["id"])
    assert j["status"] == "done", j.get("error")
    assert j["download"]["frames_done"] == 4 and j["download"]["pct"] == 100 and j["download"]["mb_done"] > 0
    assert downloads.status(BBOX)["all_downloaded"]
    assert config.DL_STATS_FILE.exists()          # speed learned for the next estimate
    assert downloads.expected()["measured"]


def test_cancel(fake_nasa):
    job = store.new_job("dl-test2", "download", {"bbox": BBOX})
    downloads.cancel(job["id"])
    downloads.run_job(job["id"], {"bbox": BBOX, "scope": "all", "extras": False})
    assert store.load_job(job["id"])["status"] == "cancelled"


def test_api(fake_nasa):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    st = c.post("/downloads/status", json={"bbox": BBOX}).json()
    assert st["frames_to_download"] == 4
    r = c.post("/downloads", json={"bbox": BBOX, "name": "Test", "extras": False}).json()
    for _ in range(200):
        j = c.get(f"/downloads/{r['id']}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j
    assert c.post("/downloads/status", json={"bbox": BBOX}).json()["all_downloaded"]


def test_analysis_reports_download(fake_nasa, monkeypatch):
    from app import pipeline
    seen = []
    real = store.update_job

    def spy(job_id, **ch):
        if "download" in ch:
            seen.append(ch["download"])
        return real(job_id, **ch)
    monkeypatch.setattr(store, "update_job", spy)
    job = store.new_job("an-test", "k", {})
    req = {"bbox": BBOX, "name": "Test", "question": "change", "event_date": "2026-09-01", "looking_for": ["water"], "quick": True}
    try:
        pipeline.run_analysis(req, job["id"], passes=fake_nasa, online=False)
    except catalog.NotEnoughData:
        pass   # random test pixels may be judged unreadable; the download part is what we check
    assert seen and seen[-1]["frames_done"] == 4 and seen[-1]["pct"] == 100
