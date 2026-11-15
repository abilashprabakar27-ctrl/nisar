# Per-pass change series. Run from repo root: .venv/bin/python scripts/make_series.py [tonlesap|nile_sudd|all]
import csv, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workers.series import FIELDS, series_for_area

AREAS = {  # name: (area key, bbox, track, frame, pols)
    "tonlesap": ("mekong_tonlesap", (103.90, 13.05, 104.12, 13.27), 83, 8, ("HHHH", "HVHV")),
    "nile_sudd": ("nile_sudd", (30.40, 7.40, 30.60, 7.60), 50, 85, ("HHHH",)),   # HH only: HV missing on 5 dates
}
OUT = Path("data/catalog")
want = sys.argv[1] if len(sys.argv) > 1 else "all"
for name, (area, bbox, track, frame, pols) in AREAS.items():
    if want not in ("all", name):
        continue
    t0 = time.time()
    rows, info = series_for_area(area, bbox, track, frame, pols=pols, on_step=print)
    with (OUT / f"series_{name}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    (OUT / f"series_{name}.json").write_text(json.dumps({**info, "rows": rows}, indent=1))
    print(f"{name}: {len(rows)} rows, {time.time()-t0:.1f}s, before={info['before_dates']}")
    for r in rows:
        print(r["date"], r["became_water_ha"], r["receded_ha"], r["masked_fraction"], r["quality_flag"])
