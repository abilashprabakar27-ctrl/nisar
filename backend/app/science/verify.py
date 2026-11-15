"""Compare our water map with NASA OPERA DSWx-S1 (a separate NASA product, Sentinel-1 radar). Agreement is not proof:
OPERA is another radar-based map and is not asked whether the water is new.

Uses a local GeoTIFF if the reference team saved one (data/drivers/<slug>/opera.tif),
otherwise searches NASA Earthdata for the DSWx-S1 tile nearest the after date.
Headline = our new water only (permanent water excluded); the all-water view is labelled.
Water = classes 1-3 (open water, partial/moderate, inundated vegetation); 250+ = no data.
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from .change import BECAME_WATER, MASKED, PERMANENT
from .grid import Grid


def _read_onto_grid(src_path: str, grid: Grid) -> np.ndarray:
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    dst = np.full(grid.shape, 255, "uint8")
    with rasterio.open(src_path) as src:
        rw.reproject(rasterio.band(src, 1), dst,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=Resampling.nearest, dst_nodata=255)
    return dst


def find_opera(bbox, after_date: str, days: int = 6) -> list[str]:
    import earthaccess
    d = date.fromisoformat(after_date)
    res = earthaccess.search_data(short_name="OPERA_L3_DSWX-S1_V1", bounding_box=tuple(bbox),
                                  temporal=((d - timedelta(days=days)).isoformat(), (d + timedelta(days=days)).isoformat()))
    links = []
    for g in res:
        links += [u for u in g.data_links() if u.endswith("BWTR.tif") or u.endswith("_WTR.tif")]
    return links


ALL_WATER_NOTE = "includes permanent water, not a test of change"
MIN_NEW_PX = 25   # fewer new-water pixels than this and there is nothing meaningful to compare


def _overlap(ours: np.ndarray, theirs: np.ndarray, ha: float) -> dict:
    both = ours & theirs
    union = (ours | theirs).sum()
    return {
        "opera_water_ha": round(float(theirs.sum()) * ha, 1),
        "nisar_water_ha": round(float(ours.sum()) * ha, 1),
        "both_ha": round(float(both.sum()) * ha, 1),
        "only_nisar_ha": round(float((ours & ~theirs).sum()) * ha, 1),
        "only_opera_ha": round(float((theirs & ~ours).sum()) * ha, 1),
        "overlap_pct": round(100.0 * both.sum() / max(ours.sum(), 1), 1),   # share of our new-water pixels that are also OPERA water (class 1-3) on the after date
        "iou_pct": round(100.0 * both.sum() / max(union, 1), 1),
    }


def compare(classes: np.ndarray, grid: Grid, opera: np.ndarray, ours_water: np.ndarray | None = None,
            opera_before: np.ndarray | None = None) -> dict:
    """Headline = STRICT: our 'became water' pixels vs OPERA water on the after date.

    Permanent water is never counted, so a big river or lake cannot make the answer look like agreement.
    overlap_pct = share of our new water that OPERA also marks as water (a precision-style check).
    If opera_before (an OPERA water map before the event) is given, iou_pct / recall_pct are computed against
    OPERA *new* water (water after and not open water before), the real test of change.
    The old all-water number is kept under 'all_water' and labelled: it includes permanent water.
    ours_water: our water on the pass closest to OPERA's date, for the all-water detail only.
    OPERA is a second opinion, not ground truth.
    """
    valid = (opera < 250) & (classes != MASKED)
    theirs = np.isin(opera, (1, 2, 3)) & valid
    ha = grid.pixel_ha
    new = (classes == BECAME_WATER) & valid
    strict = _overlap(new, theirs, ha)
    strict_note = "our new water vs OPERA water on the after date"
    if opera_before is not None:
        ok = np.isin(opera_before, (0, 1, 2)) & np.isin(opera, (0, 1)) & valid
        ref_new = (opera == 1) & (opera_before != 1) & ok
        ours_ok = new & ok
        sc = _overlap(ours_ok, ref_new, ha)
        strict["iou_pct"] = sc["iou_pct"]
        strict["recall_pct"] = round(100.0 * (ours_ok & ref_new).sum() / max(ref_new.sum(), 1), 1)
        strict["precision_pct"] = sc["overlap_pct"]
        strict_note = "our new water vs OPERA new water (water after, not water before)"
    else:
        strict["iou_pct"] = None   # no before reference: an IoU against all OPERA water would be misleading
    n_new = int(new.sum())
    if n_new < MIN_NEW_PX:
        verdict, verdict_code, strict["overlap_pct"] = "No new water to check", "none", None
    else:
        o = strict["overlap_pct"]
        verdict_code = "agrees" if o >= 75 else ("partly" if o >= 50 else "disagrees")
        verdict = {"agrees": "Agrees with OPERA", "partly": "Partly agrees", "disagrees": "Disagrees"}[verdict_code]
    # all-water view (old headline): became + permanent vs all OPERA water
    ours_all = (ours_water if ours_water is not None else np.isin(classes, (BECAME_WATER, PERMANENT))) & valid
    all_water = _overlap(ours_all, theirs, ha)
    all_water["note"] = ALL_WATER_NOTE
    agree_map = np.zeros(classes.shape, "uint8")           # 1 both, 2 only ours, 3 only OPERA (new water only)
    agree_map[new & theirs] = 1
    agree_map[new & ~theirs] = 2
    agree_map[theirs & ~new & (classes != PERMANENT)] = 3
    strict.update({"verdict": verdict, "verdict_code": verdict_code, "basis": strict_note, "all_water": all_water, "map": agree_map})
    return strict


def run(classes, grid, bbox, after_date, local_dir: Path, online=True, ours_water=None):
    local = local_dir / "opera.tif"
    try:
        if local.exists():
            opera = _read_onto_grid(str(local), grid)
            source = "local file"
        elif online:
            links = find_opera(bbox, after_date)
            if not links:
                return None
            import earthaccess
            f = earthaccess.open(links[:1])[0]
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
                tmp.write(f.read())
            opera = _read_onto_grid(tmp.name, grid)
            source = links[0].rsplit("/", 1)[-1]
        else:
            return None
    except Exception as e:  # reference check is helpful, never fatal
        return {"error": f"OPERA check unavailable: {e.__class__.__name__}"}
    out = compare(classes, grid, opera)                 # our answer: new water on both later passes
    out["compared_with"] = "NISAR new water (water on both later passes) vs OPERA water"
    if ours_water is not None:                          # extra detail: the single pass nearest OPERA's date
        single = compare(classes, grid, opera, ours_water)["all_water"]
        out["single_pass"] = {"date": after_date, "nisar_water_ha": single["nisar_water_ha"],
                              "overlap_pct": single["overlap_pct"], "iou_pct": single["iou_pct"],
                              "note": ALL_WATER_NOTE}
    out["source"] = source
    return out
