"""Compare our water map with NASA OPERA DSWx-S1 (independent Sentinel-1 water map).

Uses a local GeoTIFF if the reference team saved one (data/drivers/<slug>/opera.tif),
otherwise searches NASA Earthdata for the DSWx-S1 tile nearest the after date.
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


def compare(classes: np.ndarray, grid: Grid, opera: np.ndarray, ours_water: np.ndarray | None = None) -> dict:
    """ours_water: our water on the pass closest to OPERA's date (better than the two-pass composite)."""
    valid = (opera < 250) & (classes != MASKED)
    theirs = np.isin(opera, (1, 2, 3)) & valid
    ours = (ours_water if ours_water is not None else np.isin(classes, (BECAME_WATER, PERMANENT))) & valid
    both = ours & theirs
    ha = grid.pixel_ha
    union = (ours | theirs).sum()
    overlap = 100.0 * both.sum() / max(union, 1)          # intersection over union
    agree_ours = 100.0 * both.sum() / max(ours.sum(), 1)   # share of our water confirmed
    verdict = "Confirmed" if agree_ours >= 75 else ("Partly confirmed" if agree_ours >= 50 else "Sources disagree")
    agree_map = np.zeros(classes.shape, "uint8")           # 1 both, 2 only ours, 3 only OPERA
    agree_map[both] = 1
    agree_map[ours & ~theirs] = 2
    agree_map[theirs & ~ours] = 3
    return {
        "opera_water_ha": round(float(theirs.sum()) * ha, 1),
        "nisar_water_ha": round(float(ours.sum()) * ha, 1),
        "both_ha": round(float(both.sum()) * ha, 1),
        "only_nisar_ha": round(float((ours & ~theirs).sum()) * ha, 1),
        "only_opera_ha": round(float((theirs & ~ours).sum()) * ha, 1),
        "overlap_pct": round(float(agree_ours), 1),
        "iou_pct": round(float(overlap), 1),
        "verdict": verdict,
        "map": agree_map,
    }


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
    out = compare(classes, grid, opera)                 # our answer: water on both later passes
    out["compared_with"] = "NISAR answer (water on both later passes)"
    if ours_water is not None:                          # extra detail: the single pass nearest OPERA's date
        single = compare(classes, grid, opera, ours_water)
        out["single_pass"] = {"date": after_date, "nisar_water_ha": single["nisar_water_ha"],
                              "overlap_pct": single["overlap_pct"], "iou_pct": single["iou_pct"]}
    out["source"] = source
    return out
