"""Write data/catalog/imerg_rain_<area>.csv (date,mm_day) for each AOI centre (+-0.25 deg)."""
import csv, datetime as dt, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workers.drivers import read_rain_series  # noqa: E402

IMERG = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "imerg")
START, END = dt.date(2026, 6, 1), dt.date(2026, 10, 31)

for r in csv.DictReader(open(ROOT / "data/catalog/aoi_centres.csv")):
    lat, lon = float(r["lat"]), float(r["lon"])
    ser, miss = read_rain_series((lon - .25, lat - .25, lon + .25, lat + .25), START, END, IMERG, return_missing=True)
    with open(ROOT / f"data/catalog/imerg_rain_{r['area']}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "mm_day"])
        w.writerows((d.isoformat(), "" if v != v else round(v, 2)) for d, v in ser)
    tot = sum(v for _, v in ser if v == v)
    print(f"{r['area']:26s} n={len(ser)} missing={len(miss)} total={tot:7.0f} mm")
