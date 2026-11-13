from datetime import date
from api.schemas import PassRef, Status

MIN_PASSES = 2
MAX_MASKED_FRACTION = 0.30
GAP_START, GAP_END = date(2026, 7, 27), date(2026, 8, 10)
QUALITY_ORDER = ("BETA", "PROVISIONAL", "VALIDATED")  # low -> high


def lowest_quality(passes: list[PassRef]) -> str | None:
    """Lowest quality level among passes; unknown labels rank below BETA."""
    q = {p.quality for p in passes}
    if not q:
        return None
    return min(q, key=lambda x: QUALITY_ORDER.index(x) if x in QUALITY_ORDER else -1)


def assess_availability(before: list[PassRef], after: list[PassRef],
                        masked_fraction: float) -> tuple[Status, list[str]]:
    bad, warn = [], []
    for name, s in (("before", before), ("after", after)):
        if len(s) < MIN_PASSES:
            bad.append(f"Only {len(s)} usable pass(es) {name}; need at least {MIN_PASSES}.")
    allp = before + after
    if len({(p.track, p.direction, p.frame) for p in allp}) > 1:
        bad.append("Passes mix track/direction/frame; only one geometry can be compared.")
    if masked_fraction > MAX_MASKED_FRACTION:
        bad.append(f"{masked_fraction:.0%} of the area is masked (limit {MAX_MASKED_FRACTION:.0%}).")
    if bad:
        return "insufficient_data", bad
    q = {p.quality for p in allp}
    if "BETA" in q and len(q) > 1:
        warn.append("BETA-quality data mixed with calibrated (PROVISIONAL/VALIDATED) data; treat results with extra caution.")
    if len(q) > 1:
        warn.append(f"Mixed quality levels ({', '.join(sorted(q))}); result reported at the lowest level: {lowest_quality(allp)}.")
    if before and after and (min(date.fromisoformat(p.date) for p in before) < GAP_START
                             and max(date.fromisoformat(p.date) for p in after) > GAP_END):
        warn.append("Before/after passes straddle the permanent data gap 2026-07-27 to 2026-08-10; the gap is not filled.")
    return "ok", warn


def newest_pass_date(area: str, catalog_rows) -> str | None:
    """ISO date of the newest usable (not in the data gap) pass for an area, or None. For "Watch this place"."""
    dates = [r["date"] for r in catalog_rows
             if r.get("area") == area and str(r.get("in_gap", "")).lower() != "true"]
    return max(dates) if dates else None
