#!/usr/bin/env python
"""Catalogue-only site check for NISAR GCOV flood/wetland demo areas.

Queries the ASF catalogue (asf_search) for NISAR L2 GCOV scenes over small
(~25x25 km) AOIs, and CMR (no auth) for OPERA DSWx-HLS / DSWx-S1 granules.
Nothing is downloaded.

Outputs (data/catalog/):
  pass_counts.csv   one row per (area, scene)
  aoi_ranking.csv   one row per (area, track, direction, frame) stack
  dswx_counts.csv   OPERA DSWx granule counts/dates per area

Usage: python scripts/site_check.py [--start 2026-06-17] [--end YYYY-MM-DD]

NOTE: `split_date` per AOI is a *climatological* seasonal-flood hypothesis
(typical rising-water timing), not a confirmed flood event.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import asf_search as asf
import pandas as pd
from shapely import wkt as shp_wkt
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "catalog"
RECORD_START = "2026-06-17"
GAP = (date(2026, 7, 27), date(2026, 8, 10))  # permanent NISAR data gap (inclusive)
HALF = 0.1125  # deg; ~25 km box near the equator (narrower in km at higher lat)

# name: (lat, lon, split_date [climatological hypothesis], note)
AOIS = {
    "assam_majuli":        (26.95, 94.20, "2026-07-01", "Brahmaputra braided floodplain, Majuli island"),
    "assam_kaziranga":     (26.65, 93.35, "2026-07-01", "Brahmaputra floodplain + grassland/woodland (Kaziranga NP)"),
    "bd_sylhet_haor":      (24.95, 91.15, "2026-07-01", "Sylhet haor basin (Tanguar haor), seasonal wetland"),
    "bd_jamuna_sirajganj": (24.45, 89.70, "2026-07-15", "Jamuna (Brahmaputra) floodplain, Bangladesh"),
    "bd_sundarbans":       (22.00, 89.50, "2026-08-15", "Sundarbans mangrove forest (tidal, not riverine flood)"),
    "mekong_tonlesap":     (12.90, 104.10, "2026-08-15", "Tonle Sap floodplain with seasonally flooded forest"),
    "mekong_delta_dongthap": (10.60, 105.50, "2026-08-15", "Mekong delta, Dong Thap / Plain of Reeds"),
    "niger_inner_delta":   (15.00, -4.20, "2026-09-15", "Inner Niger Delta, Mali (late-season flood pulse)"),
    "niger_delta_ng":      (5.20, 6.40, "2026-09-01", "Niger delta, Nigeria; swamp forest"),
    "nile_sudd":           (7.50, 30.50, "2026-09-01", "Sudd wetland, South Sudan"),
    "amazon_mamiraua":     (-2.90, -64.90, "2026-09-15", "Amazon varzea flooded forest (falling limb Jun-Nov)"),
    "amazon_curuai":       (-2.10, -55.50, "2026-09-15", "Lago Grande do Curuai varzea, lower Amazon"),
    "mississippi_atchafalaya": (30.30, -91.70, "2026-09-01", "Atchafalaya basin forested swamp, Louisiana"),
}

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
DSWX = {"DSWx-HLS": "OPERA_L3_DSWX-HLS_V1", "DSWx-S1": "OPERA_L3_DSWX-S1_V1"}


def aoi_box(lat, lon):
    return box(lon - HALF, lat - HALF, lon + HALF, lat + HALF)


def in_gap(d: date) -> bool:
    return GAP[0] <= d <= GAP[1]


def quality(p: dict, attrs: dict) -> str:
    """Inferred from catalogue processing fields; NOT a QA verdict."""
    parts = [
        f"cfg={p.get('productionConfiguration') or attrs.get('PRODUCTION_PIPELINE', '?')}",
        f"crid={p.get('crid', '?')}",
        f"pge={p.get('pgeVersion', '?')}",
        f"pv={attrs.get('PRODUCT_VERSION', '?')}",
        f"orbit={p.get('orbitType', '?')}",
        f"frame={p.get('frameCoverage', '?')}",
    ]
    if not any(p.get(k) for k in ("crid", "pgeVersion", "orbitType")):
        return "unknown"
    return ";".join(parts)


def search_area(name, lat, lon, start, end):
    aoi = aoi_box(lat, lon)
    rows = []
    for page in asf.search_generator(
        platform="NISAR", processingLevel="GCOV", intersectsWith=aoi.wkt,
        start=start, end=end,
    ):
        for r in page:
            p = r.properties
            attrs = {a["Name"]: (a.get("Values") or [None])[0]
                     for a in (r.umm.get("AdditionalAttributes") or [])}
            t = datetime.fromisoformat(p["startTime"].replace("Z", "+00:00"))
            fn = p.get("fileName")
            size = (p.get("bytes") or {}).get(fn, {}).get("bytes") if fn else None
            try:
                cover = aoi.intersection(shape(r.geometry)).area / aoi.area
            except Exception:
                cover = None
            rows.append({
                "area": name, "scene": p["sceneName"], "date": t.date().isoformat(),
                "time_utc": t.strftime("%H:%M:%S"),
                "track": p.get("pathNumber"), "direction": p.get("flightDirection"),
                "frame": p.get("frameNumber"), "quality": quality(p, attrs),
                "url": p.get("url"), "size_bytes": size,
                "aoi_cover": round(cover, 3) if cover is not None else None,
                "polarization": "+".join(p.get("mainBandPolarization") or []),
                "in_gap": in_gap(t.date()),
            })
    return rows


def cmr_dswx(lat, lon, start, end):
    b = aoi_box(lat, lon).bounds
    out = {}
    for label, sn in DSWX.items():
        dates, page = set(), 1
        while True:
            q = urllib.parse.urlencode({
                "short_name": sn, "bounding_box": ",".join(f"{x:.4f}" for x in b),
                "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
                "page_size": 2000, "page_num": page,
            })
            with urllib.request.urlopen(f"{CMR}?{q}", timeout=60) as resp:
                ents = json.load(resp)["feed"]["entry"]
            dates.update(e["time_start"][:10] for e in ents)
            if len(ents) < 2000:
                break
            page += 1
        out[label] = sorted(dates)
    return out


def rank(df: pd.DataFrame) -> pd.DataFrame:
    recs = []
    ok = df[(~df["in_gap"]) & (df["aoi_cover"].fillna(1) >= 0.9)]
    for (area, trk, dirn, frm), g in ok.groupby(["area", "track", "direction", "frame"]):
        dates = sorted(g["date"].unique())
        split = AOIS[area][2]
        before = [d for d in dates if d < split]
        after = [d for d in dates if d >= split]
        recs.append({
            "area": area, "track": trk, "direction": dirn, "frame": frm,
            "n_passes": len(dates), "first": dates[0], "last": dates[-1],
            "split_date_hypothesis": split, "n_before": len(before), "n_after": len(after),
            "usable_2x2": len(before) >= 2 and len(after) >= 2,
            "dates": " ".join(dates),
        })
    r = pd.DataFrame(recs)
    if r.empty:
        return r
    return r.sort_values(["usable_2x2", "n_passes"], ascending=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=RECORD_START)
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--areas", nargs="*", default=list(AOIS))
    ap.add_argument("--no-dswx", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows, dswx = [], []
    for name in a.areas:
        lat, lon, _, _ = AOIS[name]
        got = search_area(name, lat, lon, a.start, a.end)
        print(f"{name}: {len(got)} GCOV scenes", file=sys.stderr)
        rows += got
        if not a.no_dswx:
            d = cmr_dswx(lat, lon, a.start, a.end)
            for label, ds in d.items():
                dswx.append({"area": name, "product": label, "n_dates": len(ds),
                             "dates": " ".join(ds)})

    df = pd.DataFrame(rows).drop_duplicates(["area", "scene"]).sort_values(["area", "date"])
    df.to_csv(OUT / "pass_counts.csv", index=False)
    rk = rank(df)
    rk.to_csv(OUT / "aoi_ranking.csv", index=False)
    if dswx:
        pd.DataFrame(dswx).to_csv(OUT / "dswx_counts.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(rk.drop(columns=["dates"]).to_string(index=False))


if __name__ == "__main__":
    main()
