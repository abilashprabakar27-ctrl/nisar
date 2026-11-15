import os
import tempfile
from datetime import date, timedelta

os.environ.setdefault("NCE_DATA_DIR", tempfile.mkdtemp())
os.environ["NCE_WATCH_CHECKER"] = "0"

import pytest
from fastapi.testclient import TestClient

from app import events
from app.main import app
from app.models import Pass

TODAY = date.today()


def _ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


class Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        if self.data is None:
            raise ValueError("empty")
        return self.data


def gdacs_payload():
    return {"features": [{"bbox": [10, 20, 10, 20], "geometry": {"type": "Point", "coordinates": [10, 20]},
                          "properties": {"eventtype": "FL", "eventid": 1, "name": "Flood in X",
                                         "fromdate": _ago(5) + "T00:00:00", "alertlevel": "Orange",
                                         "url": {"report": "https://gdacs/1"}}}]}


def eonet_payload():
    return {"events": [{"id": "EONET_9", "title": "Flood X (EONET)", "closed": None, "link": "https://eonet/9",
                        "categories": [{"id": "floods"}],
                        "sources": [{"id": "GDACS", "url": "https://gdacs?eventtype=FL&eventid=1"}],
                        "geometry": [{"date": _ago(5) + "T00:00:00Z", "type": "Point", "coordinates": [10.1, 20.1]}]},
                       {"id": "EONET_10", "title": "Storm Y", "closed": None, "link": "https://eonet/10",
                        "categories": [{"id": "severeStorms"}], "sources": [],
                        "geometry": [{"date": _ago(3) + "T00:00:00Z", "type": "Point", "coordinates": [80, 15]}]}]}


def usgs_payload():
    import time
    return {"features": [{"id": "us1", "geometry": {"coordinates": [100, 5, 10]},
                          "properties": {"time": int(time.time() * 1000) - 86400000, "mag": 6.1,
                                         "place": "Somewhere", "alert": None, "url": "https://usgs/1"}}]}


def cems_payload():
    return {"results": [{"code": "EMSR1", "name": "Flood Z", "eventTime": _ago(4) + "T00:00:00",
                         "category": "Flood", "centroid": "POINT (30.0 -2.0)"}], "next": None}


def fake_get(down=()):
    def get(url, params=None, **kw):
        for key, name, payload in (("gdacs.org", "GDACS", gdacs_payload), ("eonet", "EONET", eonet_payload),
                                   ("usgs", "USGS", usgs_payload), ("copernicus", "CEMS", cems_payload)):
            if key in url:
                if name in down:
                    raise ConnectionError("down")
                return Resp(payload())
        raise AssertionError(url)
    return get


@pytest.fixture(autouse=True)
def _clean():
    events.clear_cache()
    yield
    events.clear_cache()


def patch(monkeypatch, down=()):
    monkeypatch.setattr(events.requests, "get", fake_get(down))


def test_normalise_each_source(monkeypatch):
    patch(monkeypatch)
    rows = {n: fn(45) for n, fn in events.SOURCES.items()}
    keys = {"id", "source", "title", "category", "start_date", "lat", "lon", "bbox", "alert_level", "url"}
    for name, rs in rows.items():
        assert rs and keys <= set(rs[0]), name
    assert rows["GDACS"][0]["alert_level"] == "orange" and rows["GDACS"][0]["category"] == "flood"
    assert rows["USGS"][0]["category"] == "earthquake" and rows["USGS"][0]["title"].startswith("M6.1")
    assert rows["CEMS"][0]["lat"] == -2.0 and rows["CEMS"][0]["lon"] == 30.0
    assert rows["EONET"][0]["xref"] == "GDACS:FL1"
    w, s, e, n = rows["GDACS"][0]["bbox"]
    assert 20 < (n - s) * 111 < 30  # about 25 km


def test_dedupe_merges_same_flood(monkeypatch):
    patch(monkeypatch)
    evs, sources = events.recent_events(45, "all")
    floods = [e for e in evs if e["category"] == "flood" and abs(e["lat"] - 20) < 1]
    assert len(floods) == 1 and floods[0]["source"] == "GDACS"
    assert "EONET:EONET_9" in floods[0]["also_in"]
    assert all(s["ok"] for s in sources) and len(sources) == 4
    assert not any("xref" in e for e in evs)


def test_category_filter(monkeypatch):
    patch(monkeypatch)
    evs, _ = events.recent_events(45, "earthquake")
    assert [e["source"] for e in evs] == ["USGS"]


def test_source_down_is_reported_not_raised(monkeypatch):
    patch(monkeypatch, down=("USGS", "GDACS"))
    evs, sources = events.recent_events(45, "all")
    bad = {s["source"] for s in sources if not s["ok"]}
    assert bad == {"USGS", "GDACS"}
    assert evs and all(e["source"] in ("EONET", "CEMS") for e in evs)


def test_cache_30min(monkeypatch):
    patch(monkeypatch)
    events.recent_events(45, "all")
    monkeypatch.setattr(events.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    evs, _ = events.recent_events(45, "all")
    assert evs


def _pass(d, track="98", direction="A"):
    return Pass(date=d, track=track, direction=direction, quality="Provisional", url=None)


EV = {"id": "GDACS:FL1", "title": "Flood", "start_date": "2026-10-20T00:00:00Z",
      "bbox": [9.8, 19.8, 10.2, 20.2]}


def cov(monkeypatch, dates, today=date(2026, 11, 1)):
    monkeypatch.setattr(events.catalog, "search_passes", lambda bbox, start=None, end=None: [_pass(d) for d in dates])
    return events.coverage_for(EV, today=today)


def test_coverage_enough(monkeypatch):
    c = cov(monkeypatch, ["2026-09-26", "2026-10-08", "2026-10-26", "2026-10-30"])
    assert c["verdict"] == "enough" and (c["before"], c["after"]) == (2, 2)


def test_coverage_waiting(monkeypatch):
    c = cov(monkeypatch, ["2026-09-26", "2026-10-08", "2026-10-14"])
    assert c["verdict"] == "waiting" and c["after"] == 0
    assert c["next_pass_about"] == "2026-10-26" and "about" in c["message"]


def test_coverage_none(monkeypatch):
    assert cov(monkeypatch, [])["verdict"] == "none"
    assert cov(monkeypatch, ["2026-10-08", "2026-10-30"])["verdict"] == "none"


def test_coverage_gap_flag(monkeypatch):
    ev = dict(EV, start_date="2026-08-01T00:00:00Z")
    monkeypatch.setattr(events.catalog, "search_passes", lambda *a, **k: [_pass("2026-07-10")])
    assert events.coverage_for(ev, today=date(2026, 8, 20))["gap_matters"] is True


def test_routes(monkeypatch):
    patch(monkeypatch)
    monkeypatch.setattr(events.catalog, "search_passes",
                        lambda bbox, start=None, end=None: [_pass(d) for d in ("2026-09-20", "2026-10-02")])
    c = TestClient(app)
    r = c.get("/events/recent?days=45&category=flood")
    assert r.status_code == 200
    body = r.json()
    assert body["events"] and all(e["category"] == "flood" for e in body["events"])
    assert "not a flood footprint" in body["note"] and body["events"][0]["reported_by"]
    assert c.get("/events/recent?category=bogus").status_code == 422

    eid = body["events"][0]["id"]
    r = c.get("/events/coverage", params={"id": eid})
    assert r.status_code == 200
    j = r.json()
    assert j["verdict"] in ("enough", "waiting", "none")
    assert set(j["analysis_request"]) == {"bbox", "name", "event_date"}
    assert c.get("/events/coverage?id=nope").status_code == 404

    r = c.post("/events/coverage", json={"bbox": [9, 19, 10, 20], "start_date": "2026-10-20"})
    assert r.status_code == 200 and r.json()["analysis_request"]["event_date"] == "2026-10-20"
    assert c.post("/events/coverage", json={"bbox": [9, 19, 8, 20], "start_date": "2026-10-20"}).status_code == 422
