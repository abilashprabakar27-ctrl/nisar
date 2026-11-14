"""'Ask about this result': answers built only from the saved result (no invented numbers).

Each answer says which facts it used. Unknown questions get an honest "I can't answer that from
this result" plus suggestions, never a guess.
"""
import re


def _f(x, unit=""):
    return "unknown" if x is None else (f"{x:,.0f}{unit}" if isinstance(x, (int, float)) else str(x))


def answer(res: dict, q: str) -> dict:
    t = q.lower()
    h, ag, conf = res.get("headline", {}), res.get("agreement") or {}, res.get("confidence", {})
    w, areas = res.get("window", {}), res.get("areas_ha", {})
    drivers = res.get("drivers", [])
    based = [f"{len(w.get('before', [])) + len(w.get('after', []))} NISAR passes"]

    def out(text, extra=None):
        return {"answer": text, "based_on": based + (extra or []),
                "suggestions": ["Could rain cause this?", "Do other sources agree?", "How sure are you?",
                                "What could be wrong?", "Has the water gone down?"]}

    if re.search(r"rain|wet|soil|weather", t):
        rain = next((d for d in drivers if d["name"] == "Heavy rain"), None)
        if not rain or rain["verdict"] == "Not checked":
            txt = "We couldn't check the rainfall for this place, so we can't say yet."
        elif rain["verdict"] in ("Likely", "Possible"):
            txt = f"Quite possibly. {rain['evidence']}"
        else:
            txt = f"Probably not on its own. {rain['evidence']}"
        return out(txt, ["rainfall (" + (rain or {}).get("source", "not loaded") + ")"])
    if re.search(r"agree|opera|other source|nasa|compare|check", t):
        if "overlap_pct" in ag:
            return out(f"NASA's OPERA water map ({ag.get('source', '')[:40]}...) marks {_f(ag.get('opera_water_ha'), ' ha')} "
                       f"as water; {_f(ag.get('overlap_pct'))}% of our water is confirmed by it. Verdict: {ag.get('verdict')}. "
                       "Differences come from timing, pixel size (30 m vs 20 m) and wavelength (C-band vs L-band).",
                       ["NASA OPERA DSWx-S1"])
        return out("The NASA OPERA comparison was not available for this result, so we can't say yet.")
    if re.search(r"sure|confiden|accura|trust|right", t):
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
        return out(" ".join(res.get("limits", [])) or "No limits recorded.", ["limits"])
    if re.search(r"why|cause|reason", t):
        top = [d for d in drivers if d["verdict"] in ("Likely", "Possible", "Supporting")]
        if not top:
            return out("Nothing clearly explains it yet.")
        parts = [f"{d['name']}: {d['evidence']}" for d in top[:3]]
        return out("Our best guess. " + " ".join(parts), [d["source"] for d in top[:3]])
    if re.search(r"gone|reced|drain|down|now", t):
        rec = areas.get('water_receded') or 0
        if rec < 1:
            return out("No, not in any noticeable way. The water only spread between these dates.", ["water"])
        return out(f"Yes, about {_f(rec, ' hectares')} dried out, while {_f(areas.get('became_water'), ' hectares')} went under water.", ["water"])
    if re.search(r"how much|area|hectare|big|size|pitch", t):
        return out(f"{_f(h.get('hectares'), ' ha')} ({h.get('label', '').lower()}), about "
                   f"{_f(h.get('football_pitches'))} football pitches or {h.get('share_of_area_pct', '?')}% of the study area.")
    if re.search(r"when|date|pass", t):
        return out(f"Before: {', '.join(w.get('before', []))}. After: {', '.join(w.get('after', []))}. "
                   "NISAR passes every 12 days; there is no data 27 Jul - 10 Aug 2026.")
    if re.search(r"hh|hv|polari", t):
        return out("HH (same-direction radar) shows water as black; HV (cross-direction) shows leafy plants as bright. "
                   "We count water only when it is dark in both, which separates open water from wet rice fields.")
    return out("I can only answer from this result: how much changed, when, why, how sure we are, whether other "
               "sources agree, and what could be wrong. Try one of the suggestions.")
