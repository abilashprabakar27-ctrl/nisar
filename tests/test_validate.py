import numpy as np
from science.validate import validate


def grid(r0, r1, c0, c1):
    g = np.zeros((20, 20), bool)
    g[r0:r1, c0:c1] = True
    return g


def pred_of(g):
    return g.astype(np.uint8)


def test_perfect():
    g = grid(5, 10, 5, 10)
    r = validate(pred_of(g), g, None, 2, [(6, 6, True), (0, 0, False), (7, 7, False)])
    assert r["overlap"] == 1 and r["precision"] == 1 and r["recall"] == 1
    assert r["n_checkpoints"] == 3 and abs(r["checkpoint_accuracy"] - 2 / 3) < 1e-9
    assert r["n_pixels"] == 400 and r["opera_date_gap_days"] == 2


def test_partial_and_before():
    p = pred_of(grid(0, 10, 0, 10))
    after = grid(0, 10, 0, 20)
    before = grid(0, 10, 10, 20)  # newly flooded = cols 0-9
    r = validate(p, after, before, 1)
    assert r["recall"] == 1 and r["precision"] == 1
    r = validate(p, after, None, 1)
    assert r["recall"] == 0.5 and r["precision"] == 1 and r["overlap"] == 0.5
    assert r["checkpoint_accuracy"] is None and r["n_checkpoints"] == 0


def test_empty_prediction():
    r = validate(np.zeros((20, 20), np.uint8), grid(0, 5, 0, 5), None, 0)
    assert r["precision"] is None and r["recall"] == 0 and r["overlap"] == 0


def test_all_empty():
    z = np.zeros((20, 20), np.uint8)
    r = validate(z, z.astype(bool), None, 0)
    assert r["overlap"] is None and r["precision"] is None and r["recall"] is None


def test_no_overlap():
    r = validate(pred_of(grid(0, 5, 0, 5)), grid(10, 15, 10, 15), None, 3)
    assert r["overlap"] == 0 and r["precision"] == 0 and r["recall"] == 0


def test_large_gap_carried():
    g = grid(0, 5, 0, 5)
    assert validate(pred_of(g), g, None, 11)["opera_date_gap_days"] == 11
