from conftest import signing

from ftw import classify
from ftw.problems import ProblemFlag

AVG = 20_000_000


def flag(slot="CF", is_problem=False, rating_below=False, covered=False):
    return ProblemFlag(
        group=slot, required=1, starters=1, min_share=0.8, top_min_age=28,
        is_problem=is_problem, club_rating=7.0, league_rating=6.9,
        rating_below_avg=rating_below, has_above_avg_incumbent=covered,
        mv_change_pct=0.0, mv_decline=False, aging=False, severity=0.0,
        validated=is_problem)


def test_addresses_problem_is_starter():
    sg = signing(fee=40_000_000)
    classify.classify(sg, {"CF": flag(is_problem=True)}, AVG, {})
    assert sg.is_starter_signing and sg.weight == 2.0
    assert sg.addressed_problem and "addresses_problem" in sg.classification


def test_cheap_old_non_problem_is_rotation():
    sg = signing(fee=5_000_000, age=28)            # < 0.5x avg, >24, non-problem
    classify.classify(sg, {"CF": flag()}, AVG, {})
    assert not sg.is_starter_signing and sg.weight == 1.0
    assert "rotation_option" in sg.classification


def test_covered_slot_is_rotation():
    sg = signing(fee=15_000_000, age=23)           # moderate fee, young, but slot covered
    classify.classify(sg, {"CF": flag(covered=True)}, AVG, {})
    assert not sg.is_starter_signing
    assert "rotation_option" in sg.classification


def test_expensive_covered_is_starter():
    sg = signing(fee=40_000_000, age=23)           # >= 1.2x avg (24m) -> never rotation
    classify.classify(sg, {"CF": flag(covered=True)}, AVG, {})
    assert sg.is_starter_signing
    assert "rotation_option" not in sg.classification


def test_significant_outlay_label_and_starter():
    sg = signing(fee=40_000_000)                   # > 1.25x avg (25m)
    classify.classify(sg, {"CF": flag()}, AVG, {})
    assert "significant_outlay" in sg.classification
    assert sg.is_starter_signing


def test_replaces_sold_is_starter():
    sg = signing(fee=5_000_000, age=30)            # cheap but replaces a sold CF
    classify.classify(sg, {"CF": flag()}, AVG, {"CF": 1})
    assert "replaces_sold" in sg.classification
    assert sg.is_starter_signing                   # a replacement is starter-type


def test_age_boundary_24_not_rotation_option():
    sg = signing(fee=5_000_000, age=24)            # exactly 24 -> not >24
    classify.classify(sg, {"CF": flag()}, AVG, {})
    assert "rotation_option" not in sg.classification
    assert not sg.is_starter_signing               # still rotation via cheap branch
