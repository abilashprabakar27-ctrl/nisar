from datetime import date
from science.schema import PassRef, Status

MIN_PASSES = 2
MAX_MASKED_FRACTION = 0.30
GAP_START, GAP_END = date(2026, 7, 27), date(2026, 8, 10)


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
    if before and after and (min(date.fromisoformat(p.date) for p in before) < GAP_START
                             and max(date.fromisoformat(p.date) for p in after) > GAP_END):
        warn.append("Before/after passes straddle the permanent data gap 2026-07-27 to 2026-08-10; the gap is not filled.")
    return "ok", warn
