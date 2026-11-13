from science.schema import PassRef
from science.availability import assess_availability


def P(date, q="VALIDATED", track=1, d="ASCENDING", frame=1):
    return PassRef("s" + date, date, track, d, frame, q)


B = [P("2026-06-01"), P("2026-06-13")]
A = [P("2026-08-20"), P("2026-09-01")]


def test_ok():
    s, w = assess_availability(B, [P("2026-06-25"), P("2026-07-07")], 0.1)
    assert s == "ok" and w == []


def test_one_pass_insufficient():
    assert assess_availability(B[:1], A, 0.0)[0] == "insufficient_data"
    assert assess_availability(B, A[:1], 0.0)[0] == "insufficient_data"


def test_masked_insufficient():
    s, r = assess_availability(B, [P("2026-06-25"), P("2026-07-07")], 0.31)
    assert s == "insufficient_data" and r


def test_mixed_geometry_insufficient():
    s, _ = assess_availability(B, [P("2026-06-25"), P("2026-07-07", track=2)], 0.0)
    assert s == "insufficient_data"


def test_mixed_beta_warns():
    s, w = assess_availability([P("2026-06-01", "BETA"), P("2026-06-13")],
                               [P("2026-06-25"), P("2026-07-07")], 0.0)
    assert s == "ok" and any("BETA" in x for x in w)


def test_gap_straddle_warns():
    s, w = assess_availability(B, A, 0.0)
    assert s == "ok" and any("gap" in x.lower() for x in w)
