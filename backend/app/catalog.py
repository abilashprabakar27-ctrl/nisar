"""Find NISAR GCOV passes for an area (ASF search) and decide what can be answered."""
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

from . import config
from .models import Pass

os.environ.setdefault("TZ", "UTC")  # asf_search's tzlocal rejects some zone names


def _wkt(b):
    w, s, e, n = b
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def _quality(text: str) -> str:
    t = text.upper()
    for q in ("VALIDATED", "PROVISIONAL", "BETA"):
        if q in t:
            return q.title()
    return "Unknown"


NAME_RE = re.compile(r"GCOV_(\d{3})_(\d{3})_([AD])_(\d{3})")


def parse_product(props: dict) -> Pass | None:
    name = props.get("sceneName") or props.get("fileID") or ""
    if "QA" in name.upper() and "GCOV" not in name.upper():
        return None
    url = props.get("url") or ""
    if url and not url.endswith(".h5"):
        # some results point at QA or browse files; keep only the HDF5 product
        if ".h5" not in url:
            return None
    track = props.get("pathNumber")
    direction = props.get("flightDirection")
    frame = props.get("frameNumber")
    m = NAME_RE.search(name)
    if m:
        track = track if track is not None else int(m.group(2))
        direction = direction or {"A": "ASCENDING", "D": "DESCENDING"}[m.group(3)]
        frame = frame if frame is not None else int(m.group(4))
    if track is None or direction is None:
        return None
    pol = props.get("polarization") or ""
    pols = [p for p in re.split(r"[+,/ ]+", str(pol)) if p]
    return Pass(
        date=str(props.get("startTime", ""))[:10],
        track=str(int(track)), direction=str(direction)[:1].upper(),
        frame=None if frame is None else str(frame),
        quality=_quality(" ".join([url, name, str(props.get("processingLevel", ""))])),
        polarizations=pols, url=url or None, name=name,
    )


def search_passes(bbox, start=config.NISAR_START, end=None) -> list[Pass]:
    import asf_search as asf
    end = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res = asf.search(dataset="NISAR", processingLevel="GCOV", intersectsWith=_wkt(bbox),
                     start=f"{start}T00:00:00Z", end=f"{end}T23:59:59Z", maxResults=2000)
    out, seen = [], set()
    for prod in res:
        p = parse_product(prod.properties)
        if p and (p.track, p.direction, p.date, p.frame) not in seen:
            seen.add((p.track, p.direction, p.date, p.frame))
            out.append(p)
    return sorted(out, key=lambda p: p.date)


def group_by_track(passes: list[Pass]) -> dict[tuple, list[Pass]]:
    g = defaultdict(list)
    for p in passes:
        g[(p.track, p.direction)].append(p)
    for k in g:
        # one pass per date (several frames may cover the area; keep all in .name list order)
        g[k].sort(key=lambda p: p.date)
    return dict(g)


def in_gap(date: str) -> bool:
    return config.DATA_GAP[0] <= date <= config.DATA_GAP[1]


def availability(passes: list[Pass]) -> dict:
    groups = group_by_track(passes)
    tracks = []
    for (trk, d), ps in sorted(groups.items(), key=lambda kv: -len({p.date for p in kv[1]})):
        dates = sorted({p.date for p in ps})
        tracks.append({
            "track": trk, "direction": d, "passes": len(dates), "dates": dates,
            "quality": sorted({p.quality for p in ps}),
            "polarizations": sorted({x for p in ps for x in p.polarizations}),
        })
    best = tracks[0] if tracks else None
    n = best["passes"] if best else 0
    enough = n >= 2 * config.MIN_PASSES_EACH_SIDE
    return {
        "enough_data": enough,
        "verdict": "Enough data" if enough else ("Not enough data yet" if n else "No NISAR data here yet"),
        "best_track": best,
        "tracks": tracks,
        "total_passes": n,
        "gap": {"start": config.DATA_GAP[0], "end": config.DATA_GAP[1]},
        "can_answer": {
            "now": n >= 1,
            "change": enough, "diff": n >= 2, "much": enough, "why": enough,
        },
        "newest_pass": max((p.date for p in passes), default=None),
    }


def choose_groups(passes: list[Pass], event_date=None, before=None, after=None):
    """Pick the best same-track group, then the before and after passes.

    Returns (track_key, before_passes, after_passes, all_track_passes) or raises NotEnoughData.
    """
    groups = group_by_track(passes)
    best = None
    for key, ps in groups.items():
        dated = _one_per_date(ps)
        b, a = _split(dated, event_date, before, after)
        score = (min(len(b), 2) + min(len(a), 2), len(dated))
        if best is None or score > best[0]:
            best = (score, key, b, a, dated)
    if best is None:
        raise NotEnoughData("No NISAR passes cover this area in the chosen dates.")
    _, key, b, a, dated = best
    if len(b) < config.MIN_PASSES_EACH_SIDE or len(a) < config.MIN_PASSES_EACH_SIDE:
        raise NotEnoughData(
            f"Not enough NISAR data here yet: {len(b)} pass(es) before and {len(a)} after on track "
            f"{key[0]} {key[1]}. We need at least {config.MIN_PASSES_EACH_SIDE} on each side, so we won't guess.",
            detail={"track": key[0], "direction": key[1], "before": [p.date for p in b], "after": [p.date for p in a]})
    return key, b[-config.MIN_PASSES_EACH_SIDE:], a[:config.MIN_PASSES_EACH_SIDE], dated


def _one_per_date(ps):
    by = {}
    for p in ps:
        by.setdefault(p.date, p)
    return [by[d] for d in sorted(by)]


def _split(dated, event_date, before, after):
    if before and after:
        b = [p for p in dated if before[0] <= p.date <= before[1]]
        a = [p for p in dated if after[0] <= p.date <= after[1]]
    elif event_date:
        b = [p for p in dated if p.date < event_date]
        a = [p for p in dated if p.date >= event_date]
    else:  # no date given: first half vs second half
        h = len(dated) // 2
        b, a = dated[:h], dated[h:]
    return b, a


class NotEnoughData(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail or {}
