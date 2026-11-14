"""Evidence for "Why did it change?". Every driver gets a verdict and the evidence behind it.

Inputs the reference team can drop into data/drivers/<slug>/:
  rain.csv   columns: date,mm        (NASA GPM IMERG daily rainfall over the area)
  fires.csv  columns: date,lat,lon   (NASA FIRMS hotspots; optional)
Earthquakes are fetched live from the public USGS feed when the network allows.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from scipy import ndimage

from .change import BECAME_WATER, PERMANENT


def _read_csv(p: Path):
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def rain_driver(folder: Path, before_last: str, after_first: str):
    rows = _read_csv(folder / "rain.csv")
    if not rows:
        return {"name": "Heavy rain", "verdict": "Not checked", "evidence": "No rainfall file yet for this area.",
                "source": "NASA POWER daily precipitation", "series": []}
    series = [{"date": r["date"], "mm": float(r["mm"])} for r in rows if r.get("date") and r.get("mm")]
    window = [s["mm"] for s in series if before_last <= s["date"] <= after_first]
    earlier = [s["mm"] for s in series if s["date"] < before_last]
    total = round(sum(window), 1)
    days = max(len(window), 1)
    base = (sum(earlier) / len(earlier)) if earlier else None
    ratio = (total / days) / base if base else None
    if total >= 150 or (ratio and ratio >= 2):
        verdict = "Likely"
    elif total >= 60 or (ratio and ratio >= 1.3):
        verdict = "Possible"
    else:
        verdict = "Not supported"
    ev = f"{total:.0f} mm fell between {before_last} and {after_first}"
    if ratio:
        ev += f", about {ratio:.1f} times the daily average before it"
    return {"name": "Heavy rain", "verdict": verdict, "evidence": ev + ".", "source": "NASA POWER daily precipitation",
            "series": series}


def river_driver(classes: np.ndarray, pixel_m: float):
    new = classes == BECAME_WATER
    river = classes == PERMANENT
    if not new.any():
        return {"name": "River overflowed its banks", "verdict": "Not supported",
                "evidence": "No new water was found.", "source": "NISAR change map"}
    if not river.any():
        return {"name": "River overflowed its banks", "verdict": "Possible",
                "evidence": "No permanent river inside the area to compare with.", "source": "NISAR change map"}
    dist = ndimage.distance_transform_edt(~river) * pixel_m
    lab, n = ndimage.label(new, structure=np.ones((3, 3)))
    touching = ndimage.minimum(dist, lab, index=np.arange(1, n + 1)) <= 2 * pixel_m
    sizes = ndimage.sum(new, lab, index=np.arange(1, n + 1))
    share = float(sizes[touching].sum() / max(sizes.sum(), 1))
    verdict = "Likely" if share >= 0.6 else ("Possible" if share >= 0.3 else "Not supported")
    return {"name": "River overflowed its banks", "verdict": verdict,
            "evidence": f"{share:.0%} of the new water is connected to the river channel.",
            "source": "NISAR change map", "share": round(share, 3)}


def flat_land_driver(classes: np.ndarray, dem: np.ndarray | None):
    if dem is None:
        return {"name": "Flat, low-lying land", "verdict": "Not checked",
                "evidence": "No elevation model loaded for this area.", "source": "Copernicus DEM 30 m"}
    new = classes == BECAME_WATER
    river = classes == PERMANENT
    if not new.any() or not river.any():
        return {"name": "Flat, low-lying land", "verdict": "Not checked", "evidence": "Not enough water to compare.",
                "source": "Copernicus DEM 30 m"}
    river_level = float(np.nanmedian(dem[river]))
    share = float(np.mean(dem[new] - river_level < 2.0))
    verdict = "Supporting" if share >= 0.5 else "Not supported"
    return {"name": "Flat, low-lying land", "verdict": verdict,
            "evidence": f"{share:.0%} of the flooded land is less than 2 m above the river.",
            "source": "Copernicus DEM 30 m"}


def quake_driver(bbox, start: str, end: str, timeout=8):
    try:
        import requests
        w, s, e, n = bbox
        r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query", timeout=timeout, params={
            "format": "geojson", "starttime": start, "endtime": end, "minlatitude": s - 0.5, "maxlatitude": n + 0.5,
            "minlongitude": w - 0.5, "maxlongitude": e + 0.5, "minmagnitude": 4})
        r.raise_for_status()
        feats = r.json().get("features", [])
    except Exception:
        return {"name": "Earthquake", "verdict": "Not checked", "evidence": "USGS feed not reachable.", "source": "USGS"}
    if feats:
        m = max(f["properties"]["mag"] for f in feats)
        return {"name": "Earthquake", "verdict": "Possible", "evidence": f"{len(feats)} quake(s) of magnitude 4+ nearby, largest M{m:.1f}.",
                "source": "USGS"}
    return {"name": "Earthquake", "verdict": "Not supported", "evidence": "No earthquakes of magnitude 4+ nearby in these dates.",
            "source": "USGS"}


def fire_driver(folder: Path, start: str, end: str):
    rows = [r for r in _read_csv(folder / "fires.csv") if start <= r.get("date", "") <= end]
    if not (folder / "fires.csv").exists():
        return {"name": "Fire", "verdict": "Not checked", "evidence": "No fire hotspot file yet.", "source": "NASA FIRMS"}
    if rows:
        return {"name": "Fire", "verdict": "Possible", "evidence": f"{len(rows)} fire hotspot(s) inside the area.", "source": "NASA FIRMS"}
    return {"name": "Fire", "verdict": "Not supported", "evidence": "No fire hotspots inside the area in these dates.", "source": "NASA FIRMS"}


def all_drivers(folder: Path, bbox, classes, pixel_m, before_dates, after_dates, dem=None, online=True):
    before_last, after_first = before_dates[-1], after_dates[0]
    start = (date.fromisoformat(before_dates[0]) - timedelta(days=1)).isoformat()
    end = (date.fromisoformat(after_dates[-1]) + timedelta(days=1)).isoformat()
    d = [rain_driver(folder, before_last, after_first), river_driver(classes, pixel_m), flat_land_driver(classes, dem)]
    if online:
        d.append(quake_driver(bbox, start, end))
    d.append(fire_driver(folder, start, end))
    order = {"Likely": 0, "Possible": 1, "Supporting": 2, "Not supported": 3, "Not checked": 4}
    return sorted(d, key=lambda x: order.get(x["verdict"], 9))
