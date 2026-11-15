#!/usr/bin/env python
"""Recent natural-calamity events from open feeds, normalised + NISAR coverage.

Sources (all public, no key): NASA EONET v3, GDACS, USGS earthquakes,
Copernicus EMS rapid-mapping activations.  ReliefWeb needs an approved appname
and is deliberately NOT used (see docs/CALAMITY_FEEDS.md).

Schema per event:
  id, source, title, category (flood|storm|landslide|earthquake), start_date
  (ISO UTC), lat, lon, bbox [W,S,E,N] (~25 km box when only a point),
  alert_level, url   (+ optional also_in: other sources merged by de-dupe)

Usage:
  recent_events.py --days 45 --category flood
  recent_events.py --days 45 --coverage          # flood+storm NISAR check
  recent_events.py --json --no-cache

Run with the venv that has asf_search (only needed for --coverage):
  /home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python recent_events.py ...

Stdlib + requests only (asf_search imported lazily for --coverage).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone

import requests

UA = {"User-Agent": "nisar-change-explorer-recent-events/1.0"}
TIMEOUT = 45
CACHE_TTL = 30 * 60
CACHE_DIR = os.path.join(tempfile.gettempdir(), "nisar_recent_events_cache")
HALF_BOX_KM = 12.5  # -> ~25 km box for point events
NISAR_START = "2026-06-17"
GAP = (date(2026, 7, 27), date(2026, 8, 10))  # NISAR GCOV acquisition gap
CATEGORIES = ("flood", "storm", "landslide", "earthquake")
PRIORITY = {"GDACS": 0, "CEMS": 1, "USGS": 2, "EONET": 3}
DEDUPE_KM = {"flood": 100, "storm": 300, "landslide": 100, "earthquake": 100}


# ---------------------------------------------------------------- helpers
def _cache_get(key: str):
    path = os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest() + ".json")
    try:
        if time.time() - os.path.getmtime(path) < CACHE_TTL:
            with open(path) as fh:
                return json.load(fh)
    except (OSError, ValueError):
        pass
    return None


def _cache_put(key: str, value) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest() + ".json")
        with open(path, "w") as fh:
            json.dump(value, fh)
    except OSError:
        pass


def _get_json(url: str, params=None):
    r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:  # GDACS returns an empty/non-JSON body when no events match
        return None


def point_bbox(lat: float, lon: float, half_km: float = HALF_BOX_KM):
    dlat = half_km / 111.0
    dlon = half_km / (111.0 * max(math.cos(math.radians(lat)), 0.05))
    return [round(max(-180, lon - dlon), 4), round(max(-90, lat - dlat), 4),
            round(min(180, lon + dlon), 4), round(min(90, lat + dlat), 4)]


def _fix_latlon(lat: float, lon: float):
    """EONET occasionally emits [lat, lon] for polygon vertices; swap if invalid."""
    if abs(lat) > 90 and abs(lon) <= 90:
        return lon, lat
    return lat, lon


def _min_box(bbox):
    """Ensure bbox is at least ~25 km on each side."""
    w, s, e, n = bbox
    clat = (s + n) / 2
    mn = point_bbox(clat, (w + e) / 2)
    return [min(w, mn[0]), min(s, mn[1]), max(e, mn[2]), max(n, mn[3])]


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _iso(s: str) -> str:
    s = s.replace("Z", "")
    return s[:19] + "Z" if "T" in s else s[:10] + "T00:00:00Z"


def _d(ev) -> date:
    return datetime.strptime(ev["start_date"][:10], "%Y-%m-%d").date()


# ---------------------------------------------------------------- sources
def fetch_eonet(days: int):
    out = []
    data = _get_json("https://eonet.gsfc.nasa.gov/api/v3/events",
                     {"days": days, "status": "all",
                      "category": "floods,severeStorms,landslides"})
    catmap = {"floods": "flood", "severeStorms": "storm", "landslides": "landslide"}
    for e in data.get("events", []):
        cats = [catmap[c["id"]] for c in e["categories"] if c["id"] in catmap]
        if not cats or not e.get("geometry"):
            continue
        geoms = sorted(e["geometry"], key=lambda g: g["date"])
        g0 = geoms[0]
        if g0["type"] == "Polygon":
            pts = [_fix_latlon(c[1], c[0]) for c in g0["coordinates"][0]]
            lats, lons = [p[0] for p in pts], [p[1] for p in pts]
            bbox = _min_box([min(lons), min(lats), max(lons), max(lats)])
            lat, lon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        else:
            lon, lat = g0["coordinates"][:2]
            lat, lon = _fix_latlon(lat, lon)
            bbox = point_bbox(lat, lon)
        xref = None
        for src in e.get("sources", []):
            if src["id"] == "GDACS" and "eventid=" in src["url"]:
                xref = "GDACS:FL" + src["url"].split("eventid=")[1].split("&")[0]
        out.append({"id": f"EONET:{e['id']}", "source": "EONET", "title": e["title"],
                    "xref": xref,
                    "category": cats[0], "start_date": _iso(g0["date"]),
                    "lat": round(lat, 4), "lon": round(lon, 4), "bbox": bbox,
                    "alert_level": "closed" if e.get("closed") else "open",
                    "url": e["link"]})
    return out


def fetch_gdacs(days: int):
    today = date.today()
    frm = (today - timedelta(days=days)).isoformat()
    out, page = [], 1
    while page <= 5:
        data = _get_json(
            "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
            {"eventlist": "FL;TC;LS", "fromdate": frm, "todate": today.isoformat(),
             "alertlevel": "green;orange;red", "pagenumber": page, "pagesize": 100})
        feats = (data or {}).get("features", [])
        catmap = {"FL": "flood", "TC": "storm", "LS": "landslide"}
        for f in feats:
            p = f["properties"]
            geom = f["geometry"]
            if geom["type"] == "Point":
                lon, lat = geom["coordinates"][:2]
            else:
                b = f.get("bbox") or [0, 0, 0, 0]
                lon, lat = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            bb = f.get("bbox")
            bbox = _min_box(bb) if bb and (bb[0] != bb[2] or bb[1] != bb[3]) else point_bbox(lat, lon)
            out.append({"id": f"GDACS:{p['eventtype']}{p['eventid']}", "source": "GDACS",
                        "title": p.get("name") or p.get("eventname") or p["eventtype"],
                        "category": catmap.get(p["eventtype"], "flood"),
                        "start_date": _iso(p["fromdate"]),
                        "lat": round(lat, 4), "lon": round(lon, 4), "bbox": bbox,
                        "alert_level": (p.get("alertlevel") or "").lower() or None,
                        "url": p["url"]["report"]})
        if len(feats) < 100:
            break
        page += 1
    return list({e["id"]: e for e in out}.values())  # paging can repeat rows


def fetch_usgs(days: int):
    start = (date.today() - timedelta(days=days)).isoformat()
    data = _get_json("https://earthquake.usgs.gov/fdsnws/event/1/query",
                     {"format": "geojson", "starttime": start, "minmagnitude": 5,
                      "orderby": "time"})
    out = []
    for f in data["features"]:
        p, (lon, lat) = f["properties"], f["geometry"]["coordinates"][:2]
        t = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc)
        out.append({"id": f"USGS:{f['id']}", "source": "USGS",
                    "title": f"M{p['mag']} {p['place']}", "category": "earthquake",
                    "start_date": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "lat": round(lat, 4), "lon": round(lon, 4),
                    "bbox": point_bbox(lat, lon),
                    "alert_level": p.get("alert") or "none", "url": p["url"]})
    return out


def fetch_cems(days: int):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    url = ("https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/"
           "public-activations-info/")
    catmap = {"Flood": "flood", "Storm": "storm", "Earthquake": "earthquake",
              "Landslide": "landslide", "Mud flow": "landslide"}
    out, params = [], {"limit": 100, "ordering": "-eventTime"}
    while url:
        data = _get_json(url, params)
        params = None
        stop = False
        for r in data["results"]:
            if r["eventTime"][:10] < cutoff:
                stop = True
                continue
            cat = catmap.get(r["category"])
            if not cat or not r.get("centroid"):
                continue
            lon, lat = (float(x) for x in
                        r["centroid"].replace("POINT (", "").rstrip(")").split())
            out.append({"id": f"CEMS:{r['code']}", "source": "CEMS", "title": r["name"],
                        "category": cat, "start_date": _iso(r["eventTime"]),
                        "lat": round(lat, 4), "lon": round(lon, 4),
                        "bbox": point_bbox(lat, lon), "alert_level": "activated",
                        "url": f"https://rapidmapping.emergency.copernicus.eu/{r['code']}"})
        url = None if stop else data.get("next")
    return out


SOURCES = {"GDACS": fetch_gdacs, "EONET": fetch_eonet, "USGS": fetch_usgs,
           "CEMS": fetch_cems}


# ---------------------------------------------------------------- pipeline
def collect(days: int, use_cache: bool = True):
    events, notes = [], []
    for name, fn in SOURCES.items():
        key = f"src2:{name}:{days}:{date.today()}"
        rows = _cache_get(key) if use_cache else None
        cached = rows is not None
        if rows is None:
            try:
                rows = fn(days)
                _cache_put(key, rows)
            except Exception as exc:  # source down -> skip, say so
                notes.append(f"SKIPPED {name}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
        notes.append(f"ok {name}: {len(rows)} events{' (cached)' if cached else ''}")
        events.extend(rows)
    return events, notes


def keep_wanted(events, category, days):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [e for e in events
            if e["start_date"][:10] >= cutoff
            and e["category"] in CATEGORIES
            and (category in (None, "all") or e["category"] == category)]


def dedupe(events):
    """Merge same category, <=3 days apart and within DEDUPE_KM; EONET records that
    cite a GDACS event id are merged on that id.  Highest-priority source is kept."""
    kept = []
    for e in sorted(events, key=lambda e: (PRIORITY[e["source"]], e["start_date"])):
        for k in kept:
            same = e.get("xref") == k["id"] or (
                k["category"] == e["category"]
                and abs((_d(k) - _d(e)).days) <= 3
                and haversine_km(k["lat"], k["lon"], e["lat"], e["lon"])
                <= DEDUPE_KM[e["category"]])
            if same:
                k.setdefault("also_in", []).append(e["id"])
                break
        else:
            kept.append(dict(e))
    kept.sort(key=lambda e: e["start_date"], reverse=True)
    return kept


# ---------------------------------------------------------------- NISAR coverage
def _wkt(b):
    w, s, e, n = b
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def nisar_coverage(ev, today=None):
    """Passes (NISAR GCOV) before/after ev start on the best track over its bbox."""
    import asf_search as asf  # lazy: only needed for --coverage
    today = today or date.today()
    key = f"cov2:{ev['id']}:{ev['start_date']}:{today}"
    hit = _cache_get(key)
    if hit:
        return hit
    res = asf.geo_search(dataset="NISAR", processingLevel="GCOV", start=NISAR_START,
                         end=today.isoformat(), intersectsWith=_wkt(ev["bbox"]),
                         maxResults=500)
    tracks = {}
    for r in res:
        p = r.properties
        tracks.setdefault((p["pathNumber"], p["flightDirection"]), set()).add(
            p["startTime"][:10])
    start = _d(ev)
    out = {"n_passes": sum(len(v) for v in tracks.values()), "best_track": None,
           "before": 0, "after": 0, "newest_pass": None, "last_before": None,
           "first_after": None, "gap_matters": False, "verdict": "none",
           "reason": "no NISAR GCOV over bbox"}
    if tracks:
        # best track = most passes, tie -> more passes after event
        def score(item):
            ds = item[1]
            return (len(ds), sum(1 for x in ds if x >= start.isoformat()))
        (path, direction), ds = max(tracks.items(), key=score)
        ds = sorted(ds)
        before = [x for x in ds if x < start.isoformat()]
        after = [x for x in ds if x >= start.isoformat()]
        newest = max(max(v) for v in tracks.values())
        age = (today - start).days
        post_gap = [x for x in before if x > GAP[1].isoformat()]
        # gap matters if the event is inside it, or the usable "before" baseline
        # would have to reach back across it (<2 passes after 10 Aug)
        gap = (GAP[0] <= start <= GAP[1]) or (
            start > GAP[1] and len(before) >= 2 and len(post_gap) < 2)
        nxt = datetime.strptime(ds[-1], "%Y-%m-%d").date() + timedelta(days=12)
        if len(before) >= 2 and len(after) >= 2:
            verdict, reason = "enough for 2+2", "2+ before and 2+ after on best track"
        elif len(before) >= 2 and age <= 30:
            verdict, reason = "waiting for after-pass", (
                f"{len(before)} before + {len(after)} after so far; 12-day repeat, "
                f"next best-track pass expected ~{nxt}")
        elif len(before) >= 1 and len(after) >= 1:
            verdict, reason = "none", (f"only {len(before)} before + {len(after)} after "
                                       "(need 2+2)")
        else:
            verdict, reason = "none", f"{len(before)} before / {len(after)} after"
        out.update(best_track=f"{path}{direction[0]}", before=len(before),
                   after=len(after), newest_pass=newest,
                   last_before=before[-1] if before else None,
                   first_after=after[0] if after else None, gap_matters=gap,
                   verdict=verdict, reason=reason, best_dates=ds)
    _cache_put(key, out)
    return out


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--category", default="all", choices=("all",) + CATEGORIES)
    ap.add_argument("--coverage", action="store_true",
                    help="NISAR GCOV coverage check for flood+storm events")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true", help="emit JSON, not a table")
    ap.add_argument("--limit", type=int, default=0, help="max events to print")
    a = ap.parse_args(argv)

    events, notes = collect(a.days, use_cache=not a.no_cache)
    events = dedupe(keep_wanted(events, a.category, a.days))
    if a.limit:
        events = events[:a.limit]
    if a.coverage:
        for ev in events:
            if ev["category"] in ("flood", "storm"):
                try:
                    ev["nisar"] = nisar_coverage(ev)
                except Exception as exc:
                    ev["nisar"] = {"verdict": "unknown",
                                   "reason": f"asf_search failed: {str(exc)[:100]}"}
    if a.json:
        print(json.dumps({"notes": notes, "events": events}, indent=1))
        return 0
    for n in notes:
        print("#", n, file=sys.stderr)
    print(f"{len(events)} events, last {a.days} d, category={a.category}")
    for e in events:
        line = (f"{e['start_date'][:10]} {e['category']:<10} {e['source']:<5} "
                f"{(e['alert_level'] or '-'):<9} {e['lat']:>8.3f} {e['lon']:>9.3f} "
                f"{e['title'][:48]:<48} {e['id']}")
        if "nisar" in e:
            c = e["nisar"]
            line += (f"\n    NISAR: track {c.get('best_track')} before={c.get('before')} "
                     f"after={c.get('after')} newest={c.get('newest_pass')} "
                     f"gap_matters={c.get('gap_matters')} -> {c['verdict']} "
                     f"({c['reason']})")
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
