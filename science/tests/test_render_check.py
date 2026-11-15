import numpy as np
from workers.check import newest_pass_date
from workers.render import render_after


def test_newest_pass_date_skips_gap_and_other_areas():
    rows = [{"area": "a", "date": "2026-07-01", "in_gap": "False"},
            {"area": "a", "date": "2026-08-01", "in_gap": "True"},
            {"area": "a", "date": "2026-09-01", "in_gap": "False"},
            {"area": "b", "date": "2026-10-01", "in_gap": "False"}]
    assert newest_pass_date("a", rows) == "2026-09-01"
    assert newest_pass_date("zz", rows) is None


def test_render_after_writes_three_images_and_hh_only(tmp_path):
    hh = np.full((8, 9), 0.05, np.float32)
    hv = np.full((8, 9), 0.01, np.float32)
    f = render_after(hh, hv, tmp_path)
    assert set(f) == {"hh", "hv", "mix"} and all((tmp_path / p.split("/")[-1]).exists() for p in f.values())
    assert set(render_after(hh, None, tmp_path, "x")) == {"hh"}
