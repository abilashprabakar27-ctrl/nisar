"""Prepare every demo area in one go: pass table -> supporting data -> analysis -> accuracy.

    python scripts/prepare_demo.py                 # all areas in demo_areas.json
    python scripts/prepare_demo.py --only "Patna"  # one area
    python scripts/prepare_demo.py --skip-analysis # only collect data

Writes data/demo_summary.md (paste it in the team chat) and keeps every result cached for the demo.
"""
import argparse
import json
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import accuracy, catalog, config, data_sources, partners, pipeline, store  # noqa: E402


def shift(d, days):
    return (date.fromisoformat(d) + timedelta(days=days)).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", default=str(Path(__file__).resolve().parent.parent / "demo_areas.json"))
    ap.add_argument("--only")
    ap.add_argument("--skip-analysis", action="store_true")
    a = ap.parse_args()
    areas = json.loads(Path(a.areas).read_text())
    if a.only:
        areas = [x for x in areas if a.only.lower() in x["name"].lower()]
    lines = ["| Area | Track | Passes before / after | Quality | Rain (mm) | Became water (ha) | Confidence | OPERA overlap | Precision / recall | Status |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for ar in areas:
        name, bbox, ev = ar["name"], ar["bbox"], ar["event_date"]
        folder = config.DRIVERS_DIR / pipeline.slug(name)
        print(f"\n=== {name} ===")
        row = {"track": "-", "ba": "-", "q": "-", "rain": "-", "ha": "-", "conf": "-", "ov": "-", "pr": "-", "status": ""}
        try:
            passes = catalog.search_passes(bbox)
            av = catalog.availability(passes)
            bt = av["best_track"] or {}
            b = [d for d in bt.get("dates", []) if d < ev]
            af = [d for d in bt.get("dates", []) if d >= ev]
            row.update(track=f"{bt.get('track', '-')} {bt.get('direction', '')}", ba=f"{len(b)} / {len(af)}",
                       q="/".join(bt.get("quality", [])) or "-")
            print("passes:", bt.get("dates"))
        except Exception as e:
            row["status"] = f"pass search failed: {e.__class__.__name__}"
            lines.append(_row(name, row))
            continue
        for label, fn in [("rain", lambda: data_sources.fetch_rain(bbox, shift(ev, -40), shift(ev, 20), folder)),
                          ("fires", lambda: data_sources.fetch_fires(bbox, shift(ev, -40), shift(ev, 20), folder)),
                          ("dem", lambda: data_sources.fetch_dem(bbox, folder))]:
            try:
                info = fn()
                print(label, info)
                if label == "rain" and "total_mm" in info:
                    row["rain"] = f"{info['total_mm']:.0f}"
            except Exception as e:
                print(label, "failed:", e)
        try:
            pr = partners.check_all(bbox, shift(ev, -40), shift(ev, 20), folder)
            (folder / "partners_found.json").write_text(json.dumps(pr, indent=2))
            print("partner radar:", {k: v.get("status") + (f" ({v.get('scenes')} scenes)" if v.get("scenes") is not None else "")
                                     for k, v in pr.items() if isinstance(v, dict)})
        except Exception as e:
            print("partner check failed:", e)
        if a.skip_analysis:
            row["status"] = "data collected"
            lines.append(_row(name, row))
            continue
        try:
            res = pipeline.run_analysis({"bbox": bbox, "name": name, "question": "change", "event_date": ev,
                                         "looking_for": ["water"], "quick": False})
            row.update(ha=f"{res['areas_ha']['became_water']:,.0f}", conf=res["confidence"]["level"])
            ag = res.get("agreement") or {}
            if "overlap_pct" in ag:
                row["ov"] = f"{ag['overlap_pct']:.0f}%"
            pts = folder / "checkpoints.csv"
            if pts.exists():
                acc = accuracy.score(res["id"], pts)
                row["pr"] = f"{acc['precision_pct']:.0f}% / {acc['recall_pct']:.0f}%"
            row["status"] = f"done ({res['id']})"
        except catalog.NotEnoughData as e:
            row["status"] = "not enough data"
            print(e)
        except Exception as e:
            traceback.print_exc()
            row["status"] = f"failed: {e.__class__.__name__}"
        lines.append(_row(name, row))
    out = config.DATA_DIR / "demo_summary.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print(f"\nSaved {out}")


def _row(name, r):
    return f"| {name} | {r['track']} | {r['ba']} | {r['q']} | {r['rain']} | {r['ha']} | {r['conf']} | {r['ov']} | {r['pr']} | {r['status']} |"


if __name__ == "__main__":
    main()
