"""Match NISAR pass dates to OPERA DSWx reference granules (search by default).

For each demo AOI and each NISAR pass date in data/catalog/pass_counts.csv, find the
OPERA DSWx granule (S1 or HLS) closest in time, and write data/reference/manifest.csv.
Search uses CMR and needs no login. Nothing is downloaded unless --download is given,
which reads the token from the EARTHDATA_TOKEN env var (never stored in the repo).

Usage:
  python scripts/fetch_reference.py                       # search + write manifest
  python scripts/fetch_reference.py --end 2026-11-01
  EARTHDATA_TOKEN=... python scripts/fetch_reference.py --download
gap_days is the absolute difference in days between NISAR and DSWx dates.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "pass_counts.csv"
SITE_CHECK = ROOT / "scripts" / "site_check.py"
MANIFEST = ROOT / "data" / "reference" / "manifest.csv"
RAW = ROOT / "data" / "raw" / "opera"

AREAS = ["mekong_tonlesap", "bd_sylhet_haor", "amazon_mamiraua", "nile_sudd", "mississippi_atchafalaya"]
COLLECTIONS = ["OPERA_L3_DSWX-S1_V1", "OPERA_L3_DSWX-HLS_V1"]
PRODUCT = {"OPERA_L3_DSWX-S1_V1": "DSWx-S1", "OPERA_L3_DSWX-HLS_V1": "DSWx-HLS"}
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
RECORD_START = "2026-06-17"
FIELDS = ["area", "nisar_date", "opera_product", "opera_granule", "opera_date", "gap_days", "download_url"]


def load_aois() -> tuple[dict, float]:
    """Read AOIS and HALF from site_check.py without importing its heavy dependencies."""
    consts = {}
    for node in ast.parse(SITE_CHECK.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("AOIS", "HALF"):
                consts[node.targets[0].id] = ast.literal_eval(node.value)
    return consts["AOIS"], consts["HALF"]


def nisar_dates(start: str) -> dict[str, list[str]]:
    """Unique NISAR pass dates per area, skipping rows flagged in_gap."""
    out = {a: set() for a in AREAS}
    with CATALOG.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["area"] in out and r["date"] >= start and r.get("in_gap", "").lower() not in ("true", "1"):
                out[r["area"]].add(r["date"])
    return {a: sorted(d) for a, d in out.items()}


def cmr_granules(short_name: str, box: tuple[float, float, float, float], start: str, end: str) -> list[dict]:
    w, s, e, n = box
    entries, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "short_name": short_name,
            "bounding_box": f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}",
            "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
            "page_size": 2000, "page_num": page,
        })
        req = urllib.request.Request(f"{CMR}?{q}", headers={"User-Agent": "nisar-change-explorer"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            batch = json.load(resp)["feed"]["entry"]
        entries.extend(batch)
        if len(batch) < 2000:
            return entries
        page += 1


def to_granule(entry: dict, collection: str) -> dict:
    """Pick the B01_WTR GeoTIFF (fallback: any .tif) as the download URL."""
    t = datetime.fromisoformat(entry["time_start"].replace("Z", "+00:00"))
    tifs = [l["href"] for l in entry.get("links", []) if l.get("href", "").endswith(".tif")]
    url = next((h for h in tifs if h.endswith("_B01_WTR.tif")), tifs[0] if tifs else "")
    return {"product": PRODUCT[collection], "granule": entry["title"], "date": t.date(), "url": url}


def match(area: str, ndate: str, granules: list[dict]) -> dict:
    nd = date.fromisoformat(ndate)
    best = min(granules, key=lambda g: (abs((g["date"] - nd).days), g["product"]))
    return {
        "area": area, "nisar_date": ndate, "opera_product": best["product"],
        "opera_granule": best["granule"], "opera_date": best["date"].isoformat(),
        "gap_days": abs((best["date"] - nd).days), "download_url": best["url"],
    }


def download(rows: list[dict]) -> None:
    token = os.environ.get("EARTHDATA_TOKEN")
    if not token:
        sys.exit("EARTHDATA_TOKEN is not set; export it to use --download.")
    import requests  # installed as an earthaccess dependency

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    todo = {r["download_url"]: r["area"] for r in rows if r["download_url"]}
    for url, area in sorted(todo.items()):
        dest = RAW / area / Path(urllib.parse.urlparse(url).path).name
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        with session.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.rename(dest)
        print(f"downloaded {dest}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=RECORD_START)
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--download", action="store_true", help="also fetch manifest granules (needs EARTHDATA_TOKEN)")
    args = ap.parse_args()

    aois, half = load_aois()
    dates = nisar_dates(args.start)
    rows, counts = [], Counter()
    for area in AREAS:
        lat, lon = aois[area][0], aois[area][1]
        box = (lon - half, lat - half, lon + half, lat + half)
        granules = []
        for coll in COLLECTIONS:
            found = [to_granule(e, coll) for e in cmr_granules(coll, box, args.start, args.end)]
            counts[(area, PRODUCT[coll])] = len(found)
            granules.extend(found)
        matched = 0
        for ndate in dates[area]:
            if granules:
                rows.append(match(area, ndate, granules))
                matched += 1
            else:
                rows.append({"area": area, "nisar_date": ndate, "opera_product": "", "opera_granule": "",
                             "opera_date": "", "gap_days": "", "download_url": ""})
        print(f"{area}: DSWx-S1={counts[(area, 'DSWx-S1')]} DSWx-HLS={counts[(area, 'DSWx-HLS')]} "
              f"granules; NISAR dates={len(dates[area])} matched={matched}")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {MANIFEST}")

    if args.download:
        download(rows)


if __name__ == "__main__":
    main()
