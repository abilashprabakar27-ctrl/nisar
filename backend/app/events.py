"""Recent calamities (floods, storms, quakes) from open feeds + NISAR coverage check.

Sources: GDACS, NASA EONET, USGS, Copernicus EMS. All public, no key. An event is only
"reported by <source>": the bbox is a default ~25 km box around the reported point, not a
footprint of the flood. Coverage uses the same ASF search as the rest of the app.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import catalog, config

UA = {"User-Agent": "nisar-change-explorer-recent-events/1.0"}
TIMEOUT = 25
CACHE_TTL = 30 * 60
HALF_BOX_KM = 12.5
REPEAT_DAYS = 12
CATEGORIES = ("flood", "storm", "landslide", "earthquake")
PRIORITY = {"GDACS": 0, "CEMS": 1, "USGS": 2, "EONET": 3}
DEDUPE_KM = {"flood": 100, "storm": 300, "landslide": 100, "earthquake": 100}

_cache: dict = {}
_lock = threading.Lock()


def _cache_get(key):
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key, value):
    with _lock:
        _cache[key] = (time.time(), value)


def clear_cache():
    with _lock:
        _cache.clear()


def _get_json(url, params=None):
    r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:  # GDACS sends a non-JSON body when nothing matches
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


def collect(days):
    """Fetch every source; a failing source is skipped and reported, never raised."""
    events, sources = [], []
    for name, fn in SOURCES.items():
        key = f"src:{name}:{days}:{date.today()}"
        rows, cached = _cache_get(key), True
        if rows is None:
            cached = False
            try:
                rows = fn(days)
                _cache_put(key, rows)
            except Exception as exc:
                sources.append({"source": name, "ok": False, "count": 0,
                                "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
                continue
        sources.append({"source": name, "ok": True, "count": len(rows), "cached": cached})
        events.extend(rows)
    return events, sources


def keep_wanted(events, category, days):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [e for e in events
            if e["start_date"][:10] >= cutoff and e["category"] in CATEGORIES
            and (category in (None, "all") or e["category"] == category)]


def dedupe(events):
    """Merge same-category events <=3 days and within DEDUPE_KM; keep highest-priority source."""
    kept = []
    for e in sorted(events, key=lambda e: (PRIORITY[e["source"]], e["start_date"])):
        for k in kept:
            same = e.get("xref") == k["id"] or (
                k["category"] == e["category"]
                and abs((_d(k) - _d(e)).days) <= 3
                and haversine_km(k["lat"], k["lon"], e["lat"], e["lon"]) <= DEDUPE_KM[e["category"]])
            if same:
                k.setdefault("also_in", []).append(e["id"])
                break
        else:
            kept.append(dict(e))
    kept.sort(key=lambda e: e["start_date"], reverse=True)
    for e in kept:
        e.pop("xref", None)
    return kept


def recent_events(days=45, category="all"):
    """Returns (events, sources). Cached 30 min in memory."""
    key = f"ev:{days}:{category}:{date.today()}"
    hit = _cache_get(key)
    if hit:
        return hit
    events, sources = collect(days)
    out = dedupe(keep_wanted(events, category, days))
    # do not cache a result built while a source was down
    if all(s["ok"] for s in sources):
        _cache_put(key, (out, sources))
    return out, sources


def find_event(event_id, days=90):
    events, _ = recent_events(days, "all")
    return next((e for e in events if e["id"] == event_id or event_id in e.get("also_in", [])), None)


def coverage_for(event, today=None):
    """Count NISAR GCOV passes before/after the event start on the best track over its bbox."""
    today = today or date.today()
    start = _d(event).isoformat()
    passes = catalog.search_passes(event["bbox"], end=today.isoformat())
    tracks = {}
    for p in passes:
        tracks.setdefault((p.track, p.direction), set()).add(p.date)
    out = {"event_id": event.get("id"), "n_passes": sum(len(v) for v in tracks.values()),
           "best_track": None, "before": 0, "after": 0, "newest_pass": None,
           "last_before": None, "first_after": None, "gap_matters": False,
           "gap": {"start": config.DATA_GAP[0], "end": config.DATA_GAP[1]},
           "next_pass_about": None, "verdict": "none"}
    if not tracks:
        out["message"] = "No NISAR passes over this area yet, so there is nothing to compare."
        return out
    (trk, direction), ds = max(tracks.items(), key=lambda kv: (len(kv[1]), sum(1 for x in kv[1] if x >= start)))
    ds = sorted(ds)
    before = [x for x in ds if x < start]
    after = [x for x in ds if x >= start]
    g0, g1 = config.DATA_GAP
    post_gap = [x for x in before if x > g1]
    gap = (g0 <= start <= g1) or (start > g1 and len(before) >= 2 and len(post_gap) < 2)
    need = config.MIN_PASSES_EACH_SIDE
    age = (today - _d(event)).days
    nxt = datetime.strptime(ds[-1], "%Y-%m-%d").date() + timedelta(days=REPEAT_DAYS)
    if len(before) >= need and len(after) >= need:
        verdict = "enough"
        msg = f"Enough NISAR passes: {len(before)} before and {len(after)} after on track {trk} {direction}."
    elif len(before) >= need and age <= 30:
        verdict = "waiting"
        msg = (f"{len(before)} pass(es) before, {len(after)} after so far. NISAR repeats about every "
               f"{REPEAT_DAYS} days, so the next pass may come about {nxt.isoformat()}. This is an "
               "estimate, not a scheduled date.")
        out["next_pass_about"] = nxt.isoformat()
    else:
        verdict = "none"
        msg = f"Only {len(before)} before and {len(after)} after on the best track; we need {need} on each side."
    if gap:
        msg += f" The {g0} to {g1} NISAR data gap affects this event's baseline."
    out.update(best_track=f"{trk}{direction[0]}", before=len(before), after=len(after),
               newest_pass=max(max(v) for v in tracks.values()),
               last_before=before[-1] if before else None,
               first_after=after[0] if after else None, gap_matters=gap,
               verdict=verdict, message=msg, dates=ds)
    return out


def analysis_request(event):
    """Ready-to-POST body for /analyses. The bbox is a default box, not a flood footprint."""
    return {"bbox": event["bbox"], "name": event["title"][:80],
            "event_date": event["start_date"][:10]}
