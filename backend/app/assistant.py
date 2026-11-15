"""'Ask about this result': answers built only from the saved result (no invented numbers).

Each answer says which facts it used. questions() lists only what this result's data can answer.
Anything else, or a question whose data is missing, gets the one-line FALLBACK plus those
questions as suggestions, never a guess.
"""
import re

FALLBACK = "I can only answer questions about what the satellite images show here. Try one of these:"
MAX_SUGGESTED = 4


def _f(x, unit=""):
    return "unknown" if x is None else (f"{x:,.0f}{unit}" if isinstance(x, (int, float)) else str(x))


def _rain(res):
    return next((d for d in res.get("drivers") or [] if d.get("name") == "Heavy rain"), None)


def questions(res: dict) -> list[str]:
    """The common questions this result's own data can answer, at most MAX_SUGGESTED.

    Accuracy questions are never suggested; they are answered only when asked (see answer()).
    """
    conf, areas = res.get("confidence") or {}, res.get("areas_ha") or {}
    rain = _rain(res)
    out = []
    if rain and rain.get("verdict") not in (None, "Not checked") and rain.get("evidence"):
        out.append("Could rain have caused this?")
    if conf.get("level") and conf.get("reason"):
        out.append("How sure can we be?")
    if res.get("limits"):
        out.append("What could be wrong?")
    if (areas.get("water_receded") or 0) > 0:
        out.append("Did the water go down anywhere?")
    if any(d.get("verdict") == "Likely" and d.get("evidence") for d in res.get("drivers") or []):
        out.append("What else could explain it?")
    return out[:MAX_SUGGESTED]


def answer(res: dict, q: str) -> dict:
    t = q.lower()
    h, ag, conf = res.get("headline", {}), res.get("agreement") or {}, res.get("confidence", {})
    w, areas = res.get("window", {}), res.get("areas_ha", {})
    drivers = res.get("drivers", [])
    based = [f"{len(w.get('before', [])) + len(w.get('after', []))} NISAR passes"]
    suggested = questions(res)

    def out(text, extra=None):
        return {"answer": text, "answerable": True, "based_on": based + (extra or []), "suggestions": suggested}

    def cannot():
        # nothing in this result answers it: say so in one line and offer only questions the data can answer
        return {"answer": FALLBACK, "answerable": False, "based_on": [], "suggestions": suggested}

    if re.search(r"precision|recall|\biou\b|accura|how good|how well", t):
        v = res.get("validation") or {}
        rows = v.get("measured") or []
        if not rows:
            return cannot()
        bits = []
        for r in rows:
            nums = ", ".join(f"{k} {r[k]:.2f}" for k in ("precision", "recall", "iou") if r.get(k) is not None)
            bits.append(f"Against {r['reference']}: {nums}. {r.get('note', '')}")
        return out(" ".join(bits) + " " + (v.get("reference_note") or "") + ".", ["validation"])
    if re.search(r"rain|wet|soil|weather", t):
        rain = _rain(res)
        if not rain or rain["verdict"] == "Not checked" or not rain.get("evidence"):
            return cannot()
        if rain["verdict"] in ("Likely", "Possible"):
            txt = f"Quite possibly. {rain['evidence']}"
        else:
            txt = f"Probably not on its own. {rain['evidence']}"
        return out(txt, ["rainfall (" + (rain or {}).get("source", "not loaded") + ")"])
    if re.search(r"agree|opera|other source|nasa|compare|check", t):
        if ag.get("overlap_pct") is not None:
            return out(f"NASA's OPERA water map ({ag.get('source', '')[:40]}...) marks {_f(ag.get('opera_water_ha'), ' ha')} "
                       f"as water; {_f(ag.get('overlap_pct'))}% of our new-water area is also water in OPERA (OPERA does not say whether it is new). Result: {ag.get('verdict')}. "
                       "Differences come from timing, pixel size (30 m vs 20 m) and wavelength (C-band vs L-band).",
                       ["NASA OPERA DSWx-S1"])
        return cannot()
    if re.search(r"sure|confiden|trust|right", t):
        if not (conf.get("level") and conf.get("reason")):
            return cannot()
        acc = res.get("accuracy")
        lvl = conf.get('level', '')
        lead = {"High": "Fairly sure.", "Medium": "Reasonably sure.", "Lower": "Not very sure, so treat this with care."}.get(lvl, "")
        reason = conf.get('reason', '')
        for pre in ('Why high: ', 'Why medium: ', 'Why lower: '):
            reason = reason.replace(pre, '')
        reason = reason[:1].upper() + reason[1:]
        txt = f"{lead} {reason}".strip()
        return out(txt, ["confidence rules", "check points" if acc else "no check points yet"])
    if re.search(r"wrong|limit|error|mistake", t):
        if not res.get("limits"):
            return cannot()
        return out(" ".join(res["limits"]), ["limits"])
    if re.search(r"why|cause|reason|explain", t):
        top = [d for d in drivers if d["verdict"] in ("Likely", "Possible", "Supporting")]
        if not top:
            return cannot()
        parts = [f"{d['name']}: {d['evidence']}" for d in top[:3]]
        return out("Our best guess. " + " ".join(parts), [d["source"] for d in top[:3]])
    if re.search(r"gone|reced|drain|down|now", t):
        rec = areas.get('water_receded') or 0
        if rec < 1:
            return out("No, not in any noticeable way. The water only spread between these dates.", ["water"])
        return out(f"Yes, about {_f(rec, ' hectares')} dried out, while {_f(areas.get('became_water'), ' hectares')} went under water.", ["water"])
    if re.search(r"how much|area|hectare|big|size|pitch", t):
        if h.get("hectares") is None:
            return cannot()
        return out(f"{_f(h.get('hectares'), ' ha')} ({h.get('label', '').lower()}), about "
                   f"{_f(h.get('football_pitches'))} football pitches or {h.get('share_of_area_pct', '?')}% of the study area.")
    if re.search(r"when|date|pass", t):
        if not (w.get("before") and w.get("after")):
            return cannot()
        return out(f"Before: {', '.join(w.get('before', []))}. After: {', '.join(w.get('after', []))}. "
                   "NISAR passes every 12 days; there is no data 27 Jul - 10 Aug 2026.")
    # anything else (including general radar explanations) is not answered from this place's data
    return cannot()
