"""Run one analysis from the command line (no server needed).

    python scripts/run_area.py --name "Patna, Bihar" --bbox 85.00 25.35 85.25 25.60 --event 2026-09-07
    python scripts/run_area.py --sample          # labelled sample, no login needed
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import catalog, pipeline, sample  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Study area")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    ap.add_argument("--event", help="change date YYYY-MM-DD")
    ap.add_argument("--quick", action="store_true", help="40 m preview")
    ap.add_argument("--passes-only", action="store_true", help="just list passes and stop")
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    if a.sample:
        res = sample.build_sample()
    else:
        if not a.bbox:
            ap.error("--bbox is required")
        if a.passes_only:
            print(json.dumps(catalog.availability(catalog.search_passes(a.bbox)), indent=2))
            return
        try:
            res = pipeline.run_analysis({"bbox": a.bbox, "name": a.name, "question": "change",
                                         "event_date": a.event, "looking_for": ["water"], "quick": a.quick})
        except catalog.NotEnoughData as e:
            print("NOT ENOUGH DATA:", e)
            sys.exit(2)
    print(json.dumps({k: res[k] for k in ("id", "headline", "areas_ha", "confidence", "window", "agreement")}, indent=2, default=str))
    print("Saved to data/results/" + res["id"])


if __name__ == "__main__":
    main()
