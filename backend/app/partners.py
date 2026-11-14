"""Partner radar (challenge resources): availability checks only, never mixed into NISAR numbers.

- RADARSAT Constellation Mission (C-band, CSA) and RADARSAT-1 (C-band, 1995-2013, open licence):
  searched through Canada's EODMS REST API. Set EODMS_USERNAME / EODMS_PASSWORD in .env
  (free account at eodms-sgdot.nrcan-rncan.gc.ca); without them a guest search is tried.
- SAOCOM (L-band, CONAE): the catalogue needs a ONE CLICK login, so the team records what it
  found in data/drivers/<slug>/partners.json, e.g.
  {"saocom": {"checked": "2026-11-14", "passes": ["2026-09-03", "2026-09-19"], "note": "found in catalogue"}}

Non-US Government sources: their own data-use terms apply (see app/resources.py).
"""
import json
import os
from pathlib import Path

import requests

EODMS = "https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/search"
COLLECTIONS = {"rcm": "RCMImageProducts", "radarsat1": "Radarsat1"}
UA = {"User-Agent": "NISAR-Change-Explorer/1.0 (Space Apps 2026)"}


def _poly(b):
    w, s, e, n = b
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def _dates(results):
    out = []
    for r in results:
        for k, v in (r.get("metadata2") or {}).items() if isinstance(r.get("metadata2"), dict) else []:
            if "date" in k.lower():
                out.append(str(v)[:10])
        for pair in r.get("metadata", []) or []:
            if isinstance(pair, list) and len(pair) == 2 and "date" in str(pair[0]).lower():
                out.append(str(pair[1])[:10])
    return sorted(set(d for d in out if d[:2] in ("19", "20")))


def search_eodms(key: str, bbox, start: str, end: str, timeout=30) -> dict:
    coll = COLLECTIONS[key]
    q = (f"CATALOG_IMAGE.THE_GEOM_4326 INTERSECTS {_poly(bbox)} AND "
         f"CATALOG_IMAGE.START_DATETIME>='{start}' AND CATALOG_IMAGE.START_DATETIME<='{end}'")
    user, pw = os.getenv("EODMS_USERNAME", ""), os.getenv("EODMS_PASSWORD", "")
    try:
        r = requests.get(EODMS, params={"collection": coll, "query": q, "format": "json", "maxResults": 200},
                         auth=(user, pw) if user else None, headers=UA, timeout=timeout)
        if r.status_code in (401, 403):
            return {"status": "login needed", "note": "Add EODMS_USERNAME / EODMS_PASSWORD to .env"}
        r.raise_for_status()
        res = r.json().get("results", [])
    except Exception as e:
        return {"status": "not reachable", "note": e.__class__.__name__}
    dates = _dates(res)
    return {"status": "checked", "scenes": len(res), "dates": dates,
            "found": bool(res), "collection": coll}


def manual_record(folder: Path) -> dict:
    p = folder / "partners.json"
    if not p.exists():
        return {"status": "not checked", "note": "Record SAOCOM catalogue findings in partners.json"}
    try:
        return {"status": "recorded", **json.loads(p.read_text()).get("saocom", {})}
    except Exception:
        return {"status": "file unreadable"}


def check_all(bbox, start, end, folder: Path) -> dict:
    return {
        "rcm": {"name": "RADARSAT Constellation Mission", "band": "C-band", "agency": "CSA (Canada)",
                **search_eodms("rcm", bbox, start, end)},
        "radarsat1": {"name": "RADARSAT-1 (archive 1995-2013)", "band": "C-band", "agency": "CSA (Canada)",
                      "use": "long-term history only", **search_eodms("radarsat1", bbox, "1995-11-01", "2013-12-31")},
        "saocom": {"name": "SAOCOM 1A/1B", "band": "L-band", "agency": "CONAE (Argentina)", **manual_record(folder)},
        "note": "Partner radar is shown separately and never changes a NISAR number.",
    }
