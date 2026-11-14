import os
import tempfile

os.environ["NCE_DATA_DIR"] = tempfile.mkdtemp()
os.environ["NCE_WATCH_CHECKER"] = "0"

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import catalog, config, sample, watch
from app.catalog import NotEnoughData
from app.main import app
from app.models import Pass
from app.science import change


def _p(date, track="98", d="A"):
    return Pass(date=date, track=track, direction=d, quality="Provisional", url=f"x://{date}")


def test_parse_product_name():
    p = catalog.parse_product({"sceneName": "NISAR_L2_PR_GCOV_035_098_A_010_0005_NASV_M_20261111T233557_x",
                               "startTime": "2026-11-11T23:35:57Z",
                               "url": "https://x/NISAR_L2_GCOV_VALIDATED_V1/a.h5"})
    assert (p.track, p.direction, p.frame, p.quality, p.date) == ("98", "A", "10", "Validated", "2026-11-11")


def test_choose_groups_needs_two_each_side():
    ps = [_p("2026-08-12"), _p("2026-08-24"), _p("2026-09-05")]
    with pytest.raises(NotEnoughData):
        catalog.choose_groups(ps, event_date="2026-09-01")
    ps.append(_p("2026-09-17"))
    key, b, a, _ = catalog.choose_groups(ps, event_date="2026-09-01")
    assert key == ("98", "A") and [x.date for x in b] == ["2026-08-12", "2026-08-24"]
    assert [x.date for x in a] == ["2026-09-05", "2026-09-17"]


def test_choose_groups_keeps_one_track():
    ps = [_p("2026-08-12"), _p("2026-08-24"), _p("2026-09-05"), _p("2026-09-17"),
          _p("2026-08-20", "40", "D"), _p("2026-09-10", "40", "D")]
    key, b, a, _ = catalog.choose_groups(ps, event_date="2026-09-01")
    assert key == ("98", "A")


def test_detect_water_change_finds_new_water():
    rng = np.random.default_rng(0)
    land = 10 ** (-8 / 10) * rng.gamma(4, 0.25, (200, 200))
    flooded = land.copy()
    flooded[50:150, 50:150] = 10 ** (-22 / 10) * rng.gamma(4, 0.25, (100, 100))
    r = change.detect_water_change([land, land * 1.01], [flooded, flooded * 0.99], pixel_ha=0.04)
    got = r.areas_ha["became_water"]
    assert 330 < got < 420           # 100 x 100 px x 0.04 ha = 400 ha (edges smoothed)
    assert r.persistence > 0.9


def test_borderline_before_is_not_permanent_and_one_pass_is_not_change():
    rng = np.random.default_rng(1)
    base = 10 ** (-8 / 10) * rng.gamma(4, 0.25, (160, 160))
    # block A: before only borderline dark (-14 dB HH, -20 dB HV), clearly water after -> new water
    # block B: dark on only ONE of the two after passes -> not counted
    def px(hh_db, hv_db):
        return 10 ** (hh_db / 10), 10 ** (hv_db / 10)
    b_hh, b_hv = base.copy(), base.copy() * 10 ** (-9 / 10)
    a1_hh, a1_hv, a2_hh, a2_hv = b_hh.copy(), b_hv.copy(), b_hh.copy(), b_hv.copy()
    sa, sb = (slice(20, 70), slice(20, 70)), (slice(90, 140), slice(90, 140))
    b_hh[sa], b_hv[sa] = px(-13.8, -20.0)
    for hh, hv in ((a1_hh, a1_hv), (a2_hh, a2_hv)):
        hh[sa], hv[sa] = px(-21, -27)
    a1_hh[sb], a1_hv[sb] = px(-21, -27)          # only the first after pass is dark here
    r = change.detect_water_change([b_hh, b_hh * 1.0], [a1_hh, a2_hh], 0.04,
                                   before_hv=[b_hv, b_hv * 1.0], after_hv=[a1_hv, a2_hv])
    assert (r.classes[sa] == change.BECAME_WATER).mean() > 0.8
    assert (r.classes[sb] == change.BECAME_WATER).mean() < 0.05


def test_confidence_rules():
    assert change.confidence(2, 2, 1.0, 87, 0.05, ["Provisional"])[0] == "High"
    assert change.confidence(2, 2, 1.0, 40, 0.05, ["Provisional"])[0] == "Lower"
    assert change.confidence(2, 2, 1.0, 87, 0.05, ["Beta"])[0] == "Lower"
    # no strict OPERA confirmation of the new water -> never High
    assert change.confidence(2, 2, 1.0, None, 0.05, ["Provisional"])[0] == "Medium"


def test_verify_strict_ignores_permanent_water():
    from app.science import verify
    from app.science.grid import Grid
    shape = (100, 100)
    classes = np.zeros(shape, "uint8")
    classes[:, :50] = change.PERMANENT           # huge river/lake
    classes[10:20, 60:70] = change.BECAME_WATER   # 100 px of genuinely new water
    opera = np.zeros(shape, "uint8")
    opera[:, :50] = 1                             # OPERA agrees on the permanent water, not on the new water
    grid = Grid(32648, np.arange(100) * 20.0, np.arange(100)[::-1] * 20.0, 20.0)
    cmp = verify.compare(classes, grid, opera)
    assert cmp["overlap_pct"] == 0.0 and cmp["verdict"] == "Sources disagree"
    assert cmp["all_water"]["overlap_pct"] > 90 and "permanent" in cmp["all_water"]["note"]
    assert change.confidence(2, 2, 1.0, cmp["overlap_pct"], 0.05, ["Provisional"])[0] != "High"
    opera[10:20, 60:70] = 1
    assert verify.compare(classes, grid, opera)["verdict"] == "Confirmed"
    none = verify.compare(np.zeros(shape, "uint8"), grid, opera)
    assert none["overlap_pct"] is None and none["verdict"] == "No new water to check"


def test_sample_endpoint_and_files():
    c = TestClient(app)
    r = c.get("/sample").json()
    assert r["source"] == "sample" and r["headline"]["label"] == "Likely flooding"
    assert r["confidence"]["level"] in ("High", "Medium", "Lower")
    for k in ("result", "hh", "hv", "mix"):
        path = r["images"][k].split("/files/")[1]
        assert c.get(f"/files/{path}").status_code == 200


def test_analysis_job_with_sample_data(monkeypatch):
    monkeypatch.setattr(catalog, "search_passes", lambda bbox, *a, **k: sample.sample_passes())
    from app import pipeline
    real = pipeline.run_analysis
    monkeypatch.setattr(pipeline, "run_analysis",
                        lambda req, job_id=None, **kw: real(req, job_id, reader=sample.sample_reader, online=False))
    c = TestClient(app)
    body = dict(sample.SAMPLE_REQUEST, name="Test area", bbox=[85.0, 25.35, 85.24, 25.59])
    job = c.post("/analyses", json=body).json()
    import time
    for _ in range(120):
        st = c.get(f"/analyses/{job['id']}").json()
        if st["status"] in ("done", "failed", "not_enough_data"):
            break
        time.sleep(0.5)
    assert st["status"] == "done", st
    assert c.get(f"/analyses/{job['id']}/drivers").json()["label"].startswith("Interpretation")


def test_not_enough_data_job(monkeypatch):
    monkeypatch.setattr(catalog, "search_passes", lambda bbox, *a, **k: sample.sample_passes()[:3])
    c = TestClient(app)
    job = c.post("/analyses", json=dict(sample.SAMPLE_REQUEST, name="Thin area", bbox=[85.0, 25.35, 85.2, 25.55])).json()
    import time
    for _ in range(40):
        st = c.get(f"/analyses/{job['id']}").json()
        if st["status"] != "queued" and st["status"] != "running":
            break
        time.sleep(0.25)
    assert st["status"] == "not_enough_data"
    assert "won't guess" in st["error"]


def test_bad_bbox_rejected():
    c = TestClient(app)
    assert c.post("/analyses", json={"bbox": [10, 10, 5, 20]}).status_code == 422


def test_watch_flow():
    c = TestClient(app)
    item = c.post("/watch", json={"bbox": [85, 25.3, 85.2, 25.5], "name": "Patna", "last_result_date": "2026-09-17"}).json()
    assert any(i["id"] == item["id"] for i in c.get("/watch").json())
    items = watch.check_all(newest_fn=lambda b: "2026-09-29")
    assert next(i for i in items if i["id"] == item["id"])["new_pass_available"] is True
    assert c.delete(f"/watch/{item['id']}").status_code == 204


def test_learn_lists_all_challenge_resources():
    c = TestClient(app)
    ids = {r["id"] for r in c.get("/learn").json()["resources"]}
    for need in ("earthdata-search", "asf-vertex", "nisar-guide", "intro-rs", "intro-sar", "arset", "storymaps",
                 "white-papers", "uavsar", "rcm", "csa-sar-tutorial", "radarsat1", "saocom", "saocom-registration"):
        assert need in ids


def test_partners_endpoint_never_crashes(monkeypatch):
    from app import partners
    monkeypatch.setattr(partners, "search_eodms", lambda key, *a, **k: {"status": "not reachable"})
    c = TestClient(app)
    out = c.post("/partners", json={"bbox": [85, 25.35, 85.25, 25.6], "start": "2026-08-01", "end": "2026-10-01"}).json()
    assert out["rcm"]["status"] == "not reachable" and out["saocom"]["status"] == "not checked"


def test_result_has_credits():
    c = TestClient(app)
    r = c.get("/sample?rebuild=true").json()
    titles = [s["title"] for s in r["credits"]["sources"]]
    assert "ASF Data Search Vertex" in titles


def test_tiny_new_water_cannot_be_high():
    lvl, why = change.confidence(2, 2, 1.0, 87, 0.05, ["Provisional"], new_water_ha=68.0)
    assert lvl == "Medium" and "too little" in why
    assert change.confidence(2, 2, 1.0, 87, 0.05, ["Provisional"], new_water_ha=3000.0)[0] == "High"
