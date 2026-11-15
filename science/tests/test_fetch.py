import threading
import time

import h5py
import numpy as np
import pytest
from pyproj import Transformer

from workers import fetch

EPSG = 32648                      # UTM 48N (Tonle Sap)
X0, Y0 = 400_000.0, 1_450_000.0   # upper-left corner of the grid
DX, DY = 20.0, -5.0               # 20 m x 5 m posting
NR, NC = 4000, 1500               # 20 km x 30 km
G = "/science/LSAR/GCOV/grids/frequencyA"


def make_file(path, hv=True, mask=None, seed=0, fill_block=None):
    rng = np.random.default_rng(seed)
    hh = rng.random((NR, NC), dtype=np.float32) + 0.01
    if fill_block is not None:
        hh[fill_block] = np.nan
    with h5py.File(path, "w") as f:
        g = f.create_group(G)
        g["xCoordinates"] = X0 + DX / 2 + DX * np.arange(NC)
        g["yCoordinates"] = Y0 + DY / 2 + DY * np.arange(NR)
        g["xCoordinateSpacing"] = DX
        g["yCoordinateSpacing"] = DY
        p = g.create_dataset("projection", data=np.uint32(EPSG))
        p.attrs["epsg_code"] = EPSG
        g.create_dataset("HHHH", data=hh, chunks=(256, 256))
        if hv:
            g.create_dataset("HVHV", data=hh * 0.25, chunks=(256, 256))
        if mask is not None:
            g.create_dataset("mask", data=mask, chunks=(256, 256))
    return hh


def bbox_for(r0, r1, c0, c1):
    """lon/lat bbox whose projected envelope selects about rows r0:r1, cols c0:c1."""
    to_ll = Transformer.from_crs(EPSG, 4326, always_xy=True)
    xs = [X0 + DX * c0, X0 + DX * c1]
    ys = [Y0 + DY * r1, Y0 + DY * r0]
    lon, lat = to_ll.transform([xs[0], xs[1], xs[0], xs[1]], [ys[0], ys[0], ys[1], ys[1]])
    return (max(lon[0], lon[2]), max(lat[0], lat[1]), min(lon[1], lon[3]), min(lat[2], lat[3]))


def expected_slices(bbox):
    """Independent derivation: pixel centres inside the projected envelope."""
    tf = Transformer.from_crs(4326, EPSG, always_xy=True)
    xmin, ymin, xmax, ymax = tf.transform_bounds(*bbox, densify_pts=21)
    xc = X0 + DX / 2 + DX * np.arange(NC)
    yc = Y0 + DY / 2 + DY * np.arange(NR)
    c = np.flatnonzero((xc >= xmin) & (xc <= xmax))
    r = np.flatnonzero((yc >= ymin) & (yc <= ymax))
    return slice(r[0], r[-1] + 1), slice(c[0], c[-1] + 1)


BBOX = bbox_for(1000, 1600, 300, 700)   # ~3 km x 8 km


def test_window_matches_planted_slice(tmp_path):
    p = tmp_path / "a.h5"
    hh = make_file(p)
    w = fetch.read_window(str(p), BBOX)
    rows, cols = expected_slices(BBOX)
    assert abs(rows.start - 1000) <= 3 and abs(rows.stop - 1600) <= 3
    assert abs(cols.start - 300) <= 3 and abs(cols.stop - 700) <= 3
    np.testing.assert_array_equal(w["HH"], hh[rows, cols])
    np.testing.assert_array_equal(w["HV"], (hh * 0.25)[rows, cols])
    assert w["HH"].dtype == np.float32
    assert w["shape"] == w["HH"].shape == (rows.stop - rows.start, cols.stop - cols.start)
    assert w["crs"] == f"EPSG:{EPSG}"
    assert w["nodata_fraction"] == 0.0
    t = w["transform"]
    assert (t.a, t.e, t.b, t.d) == (DX, DY, 0.0, 0.0)
    assert t.c == pytest.approx(X0 + DX * cols.start)      # upper-left corner, not centre
    assert t.f == pytest.approx(Y0 + DY * rows.start)


def test_only_window_is_read(tmp_path, monkeypatch):
    p = tmp_path / "a.h5"
    make_file(p)
    seen = []
    orig = fetch._read_layer
    monkeypatch.setattr(fetch, "_read_layer",
                        lambda ds, r, c: seen.append((r, c)) or orig(ds, r, c))
    w = fetch.read_window(str(p), BBOX)
    assert len(seen) == 2
    for r, c in seen:
        assert (r.stop - r.start, c.stop - c.start) == w["shape"]
        assert w["shape"][0] < NR and w["shape"][1] < NC


def test_bbox_outside_raises(tmp_path):
    p = tmp_path / "a.h5"
    make_file(p)
    with pytest.raises(ValueError, match="does not intersect"):
        fetch.read_window(str(p), (10.0, 50.0, 10.1, 50.1))


def test_oversize_raises(tmp_path):
    p = tmp_path / "a.h5"
    make_file(p)
    w, s, e, n = BBOX
    with pytest.raises(ValueError, match="limit is 25 x 25 km"):
        fetch.read_window(str(p), (w, s, w + 0.5, n))       # ~54 km wide
    with pytest.raises(ValueError, match="limit"):
        fetch.read_window(str(p), (w, s, e, s + 0.3))       # ~33 km tall


def test_partial_overlap_clips_to_file(tmp_path):
    p = tmp_path / "a.h5"
    hh = make_file(p)
    w, s, e, n = bbox_for(0, 400, 0, 200)
    win = fetch.read_window(str(p), (w - 0.02, s, e, n + 0.02))   # spills over NW corner
    r, c = win["shape"]
    np.testing.assert_array_equal(win["HH"], hh[:r, :c])
    assert win["transform"].c == pytest.approx(X0) and win["transform"].f == pytest.approx(Y0)


def test_hv_missing_is_none(tmp_path):
    p = tmp_path / "a.h5"
    make_file(p, hv=False)
    w = fetch.read_window(str(p), BBOX)
    assert w["HV"] is None and w["HH"] is not None
    assert w["nodata_fraction"] == 0.0


def test_pixel_area_ha(tmp_path):
    p = tmp_path / "a.h5"
    make_file(p)
    assert fetch.read_window(str(p), BBOX)["pixel_area_ha"] == pytest.approx(20 * 5 / 10_000)


def test_spacing_derived_from_coordinates_when_spacing_datasets_absent(tmp_path):
    p = tmp_path / "a.h5"
    make_file(p)
    with h5py.File(p, "a") as f:
        del f[G]["xCoordinateSpacing"], f[G]["yCoordinateSpacing"]
    w = fetch.read_window(str(p), BBOX)
    assert w["pixel_area_ha"] == pytest.approx(0.01)
    assert w["transform"].e == pytest.approx(DY)


def test_nodata_fraction_and_mask(tmp_path):
    rows, cols = expected_slices(BBOX)
    nr, nc = rows.stop - rows.start, cols.stop - cols.start
    blk = (slice(rows.start, rows.start + nr // 2), cols)      # top half NaN
    p = tmp_path / "nan.h5"
    make_file(p, fill_block=blk)
    w = fetch.read_window(str(p), BBOX)
    assert w["nodata_fraction"] == pytest.approx((nr // 2) / nr)
    assert np.isnan(w["HH"][: nr // 2]).all()

    mask = np.ones((NR, NC), np.uint8)
    mask[rows.start:rows.start + 10, cols] = 0
    mask[rows.start + 10:rows.start + 20, cols] = 255
    p2 = tmp_path / "mask.h5"
    make_file(p2, mask=mask)
    w2 = fetch.read_window(str(p2), BBOX)
    assert np.isnan(w2["HH"][:20]).all() and np.isfinite(w2["HH"][20:]).all()
    assert w2["nodata_fraction"] == pytest.approx(20 / nr)
    assert fetch.read_window(str(p2), BBOX, apply_mask=False)["nodata_fraction"] == 0.0


def test_url_path_via_fsspec_without_network(tmp_path):
    p = tmp_path / "a.h5"
    make_file(p)
    local = fetch.read_window(str(p), BBOX)
    remote = fetch.read_window(p.as_uri(), BBOX)       # file:// goes through fsspec
    np.testing.assert_array_equal(remote["HH"], local["HH"])
    assert remote["transform"] == local["transform"]


def test_https_sends_bearer_token_from_env(tmp_path, monkeypatch, capsys):
    import fsspec

    p = tmp_path / "a.h5"
    make_file(p)
    calls = []
    real_open = fsspec.open

    def fake_open(url, mode="rb", **kw):
        calls.append((url, kw))
        return real_open(str(p), mode)

    monkeypatch.setattr(fsspec, "open", fake_open)
    monkeypatch.setenv("MY_TOKEN", "s3cr3t-token")
    w = fetch.read_window("https://example.invalid/x.h5", BBOX, token_env="MY_TOKEN")
    assert w["HH"] is not None
    url, kw = calls[0]
    assert kw["headers"] == {"Authorization": "Bearer s3cr3t-token"}
    assert kw["block_size"] > 0
    out = capsys.readouterr()
    assert "s3cr3t-token" not in out.out + out.err

    monkeypatch.delenv("MY_TOKEN")
    fetch.read_window("https://example.invalid/x.h5", BBOX, token_env="MY_TOKEN")
    assert "headers" not in calls[1][1]


def test_window_key():
    k = fetch.window_key("SCENE_A", BBOX)
    assert len(k) == 40 and int(k, 16) >= 0
    assert k == fetch.window_key("SCENE_A", list(BBOX))
    assert k != fetch.window_key("SCENE_B", BBOX)
    assert k != fetch.window_key("SCENE_A", (BBOX[0] + 0.01, *BBOX[1:]))


def test_cache_hit_does_not_reread(tmp_path, monkeypatch):
    p = tmp_path / "a.h5"
    make_file(p, hv=False)
    refs = [{"scene": "S1", "path": str(p)}]
    cache = tmp_path / "cache"
    msgs = []
    first = fetch.fetch_passes(refs, BBOX, cache, on_step=msgs.append)
    assert first[0]["cached"] is False and len(list(cache.glob("*.npz"))) == 1

    def boom(*a, **k):
        raise AssertionError("read_window called on a cache hit")

    monkeypatch.setattr(fetch, "read_window", boom)
    second = fetch.fetch_passes(refs, BBOX, cache, on_step=msgs.append)
    assert second[0]["cached"] is True
    np.testing.assert_array_equal(second[0]["HH"], first[0]["HH"])
    assert second[0]["HV"] is None
    for k in ("transform", "crs", "pixel_area_ha", "shape", "nodata_fraction"):
        assert second[0][k] == first[0][k]
    assert any("fetching" in m for m in msgs) and any("cache hit" in m for m in msgs)

    with pytest.raises(AssertionError):                 # different area -> miss
        fetch.fetch_passes(refs, bbox_for(100, 300, 100, 300), cache)


def test_parallel_fetch_preserves_order(tmp_path, monkeypatch):
    refs, planted = [], {}
    for i in range(6):
        p = tmp_path / f"s{i}.h5"
        planted[f"S{i}"] = make_file(p, seed=i)
        refs.append({"scene": f"S{i}", "path": str(p)})
    rows, cols = expected_slices(BBOX)
    real = fetch.read_window
    threads = set()

    def slow(src, bbox, **kw):
        threads.add(threading.get_ident())
        i = int(src[-4])
        time.sleep(0.05 * (5 - i))                      # first ref finishes last
        return real(src, bbox, **kw)

    monkeypatch.setattr(fetch, "read_window", slow)
    msgs = []
    out = fetch.fetch_passes(refs, BBOX, tmp_path / "c", workers=4, on_step=msgs.append)
    assert [o["scene"] for o in out] == [f"S{i}" for i in range(6)]
    for o in out:
        np.testing.assert_array_equal(o["HH"], planted[o["scene"]][rows, cols])
    assert len(threads) > 1 and len(msgs) == 6
    assert not any(str(tmp_path) in m for m in msgs)    # messages never carry the source path/URL


def test_http_range_reads_fetch_a_fraction_of_the_file(tmp_path, monkeypatch):
    """Real fsspec HTTP path against a loopback range server (no external network)."""
    import http.server
    import re

    p = tmp_path / "a.h5"
    make_file(p)
    blob = p.read_bytes()
    stats = {"bytes": 0, "auth": set(), "full": 0}

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _serve(self, body):
            stats["auth"].add(self.headers.get("Authorization"))
            m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
            if m:
                a = int(m.group(1))
                b = min(int(m.group(2)) if m.group(2) else len(blob) - 1, len(blob) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {a}-{b}/{len(blob)}")
                data = blob[a:b + 1]
            else:
                self.send_response(200)
                data = blob
                stats["full"] += body
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if body:
                stats["bytes"] += len(data)
                self.wfile.write(data)

        def do_GET(self):
            self._serve(True)

        def do_HEAD(self):
            self._serve(False)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("EARTHDATA_TOKEN", "tok-123")
        monkeypatch.setattr(fetch, "HTTP_BLOCK_BYTES", 256 * 1024)
        small = bbox_for(1000, 1100, 300, 400)
        w = fetch.read_window(f"http://127.0.0.1:{srv.server_address[1]}/a.h5", small)
    finally:
        srv.shutdown()
    np.testing.assert_array_equal(w["HH"], fetch.read_window(str(p), small)["HH"])
    assert stats["auth"] == {"Bearer tok-123"}
    assert stats["full"] == 0
    assert stats["bytes"] < len(blob) / 4, (stats["bytes"], len(blob))
