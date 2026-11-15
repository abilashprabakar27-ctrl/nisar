"""Common questions: only suggest and answer what this result's own data can back up."""
from app import assistant


def _res(**kw):
    r = {
        "headline": {"label": "Possible new water", "hectares": 285.0, "football_pitches": 399, "share_of_area_pct": 4.0},
        "window": {"before": ["2026-08-19", "2026-08-31"], "after": ["2026-09-12", "2026-09-24"]},
        "areas_ha": {"became_water": 284.8, "water_receded": 103.8, "permanent_water": 382.1},
        "confidence": {"level": "Lower", "reason": "Most of the new water is on farmland."},
        "limits": ["Wet fields can look like water."],
        "drivers": [{"name": "Heavy rain", "verdict": "Not checked", "evidence": "", "source": "IMERG"},
                    {"name": "River overflowed its banks", "verdict": "Likely", "evidence": "The new water lines the river.", "source": "HydroRIVERS"}],
        "agreement": None,
    }
    r.update(kw)
    return r


def test_no_rain_data_means_no_rain_question():
    qs = assistant.questions(_res())
    assert "Could rain have caused this?" not in qs
    a = assistant.answer(_res(), "Could rain have caused this?")
    assert a["answerable"] is False and a["answer"] == assistant.FALLBACK
    # with rain data the question is offered and answered from it
    rained = _res(drivers=[{"name": "Heavy rain", "verdict": "Likely", "evidence": "92 mm fell in 3 days.", "source": "IMERG"}])
    assert "Could rain have caused this?" in assistant.questions(rained)
    assert "92 mm" in assistant.answer(rained, "Could rain have caused this?")["answer"]


def test_no_receded_water_means_no_went_down_question():
    res = _res(areas_ha={"became_water": 284.8, "water_receded": 0, "permanent_water": 382.1})
    assert "Did the water go down anywhere?" not in assistant.questions(res)
    assert "Did the water go down anywhere?" in assistant.questions(_res())


def test_unknown_free_text_gets_fallback_not_an_invented_answer():
    res = _res()
    a = assistant.answer(res, "What is the population of this district?")
    assert a["answer"] == assistant.FALLBACK and a["answerable"] is False
    assert a["suggestions"] == assistant.questions(res) and a["suggestions"]


def test_every_suggested_question_is_answered_from_the_data():
    for res in (_res(), _res(limits=[], confidence={}), _res(drivers=[])):
        qs = assistant.questions(res)
        assert len(qs) <= assistant.MAX_SUGGESTED
        assert not any("accura" in q.lower() for q in qs)
        for q in qs:
            a = assistant.answer(res, q)
            assert a["answerable"] and a["answer"] != assistant.FALLBACK, q


def test_nothing_to_answer_means_no_questions():
    empty = _res(confidence={}, limits=[], drivers=[], areas_ha={"became_water": 0, "water_receded": 0, "permanent_water": 0})
    assert assistant.questions(empty) == []
