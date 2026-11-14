"""Pre-compute demo areas into data/cache so POST /analyses returns an instant 'saved' result.

Runs the real pipeline (api.jobs.run_analysis -> workers.pipeline.run) for areas with real data under
$NISAR_DATA (default ~/nisar_data). Never saves the labelled sample: a result whose source is 'sample'
(or that is not a real run) is skipped. Usage: python scripts/precompute_demo.py [tonlesap] [sudd]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import cache, jobs  # noqa: E402
from api.schemas import validate_result  # noqa: E402

QUESTION = "Where did water appear or recede?"
H = 0.1  # deg half-size, ~22 km box (inside the 25 km limit)
WINDOWS = dict(before_start="2026-06-17", before_end="2026-07-27", after_start="2026-09-01", after_end="2026-10-31")
DEMOS = {
    # Validated window (thresholds tuned/checked here; OPERA S1 tiles dated 09-23 and 10-05). After-window ends 10-05 so the
    # OPERA check finds its tile and the 10-29 pass (different processing version) is not mixed in.
    "tonlesap": {"bbox": [103.90, 13.05, 104.12, 13.27], "after_end": "2026-10-05", "note": "Tonle Sap, track 83",
                 "limit": "Accuracy does not transfer well: on a neighbouring window to the south (12.8-13.0 N) the same method "
                          "agreed with OPERA much less (overlap 0.37, precision 0.39, recall 0.89), i.e. it over-predicted water. "
                          "Thresholds were tuned on this window only."},
    "sudd": {"centre": (7.5, 30.5), "note": "Nile Sudd, track 50 (HH-only, unvalidated)",
             "limit": "UNVALIDATED: HH-only. Permanent-water and terrain masks were applied, but no OPERA comparison has been run for this area."},
}


def demo_request(name: str) -> dict:
    d = DEMOS[name]
    if "bbox" in d:
        bbox = list(d["bbox"])
    else:
        lat, lon = d["centre"]
        bbox = [lon - H, lat - H, lon + H, lat + H]
    return {"bbox": bbox, **WINDOWS, **({"after_end": d["after_end"]} if "after_end" in d else {}), "question": QUESTION}


def request_key(req: dict) -> str:
    return cache.make_key(req["bbox"], [req["before_start"], req["before_end"]],
                          [req["after_start"], req["after_end"]], req["question"])


def precompute(name: str) -> str | None:
    req = demo_request(name)
    key = request_key(req)
    result = jobs.run_analysis(dict(req))
    verify = result.pop("_verify", None)
    if result.get("source") == "sample" or result.get("status") != "ok":
        print(f"{name}: SKIPPED (source={result.get('source')}, status={result.get('status')}); nothing saved")
        return None
    if DEMOS[name].get("limit") and (not verify or name == "tonlesap") and DEMOS[name]["limit"] not in result.get("limits", []):
        result["limits"] = list(result.get("limits", [])) + [DEMOS[name]["limit"]]
    validate_result(result)
    result["source"] = "saved"  # real pipeline output, stored; jobs.start_analysis also labels cache hits 'saved'
    cache.save(key, result)
    if verify:
        cache.save_verify(key, verify)
    print(f"{name}: saved {key} confidence={result.get('confidence')} area_ha={result.get('area_ha')}")
    return key


if __name__ == "__main__":
    names = sys.argv[1:] or list(DEMOS)
    for n in names:
        precompute(n)
