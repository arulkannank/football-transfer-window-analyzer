import pytest
from conftest import player, rating_index

from ftw import analyze
from ftw.dataset import Dataset


def test_is_internal_promotion():
    assert analyze.is_internal_promotion("Real Madrid Castilla", "Real Madrid")
    assert analyze.is_internal_promotion("FC Barcelona Atlètic", "FC Barcelona")
    assert analyze.is_internal_promotion("Man City U21", "Manchester City")
    assert not analyze.is_internal_promotion("AS Monaco", "Real Madrid")
    assert not analyze.is_internal_promotion("Sevilla FC", "FC Barcelona")
    assert not analyze.is_internal_promotion(None, "Real Madrid")


def test_value_weighting():
    from ftw.models import Signing

    def mk(rating, fee):
        s = Signing(pid="1", name="x", position="Centre-Forward", group="CF",
                    age_at_signing=25, club_id="100", league="GB1", season=2020,
                    window="summer", fee_eur=fee, fee_known=True, is_loan=False,
                    is_free=False, mv_at_purchase=fee, from_club_id="200", date_iso=None)
        s.overall_rating = rating
        s.weight = 2.0
        return s

    priors = {"GB1": 3.0}
    cavg, lavg = {"100": 10e6}, {"GB1": 10e6}        # blended avg spend = €10m
    cheap_success, exp_flop = mk(8.0, 2e6), mk(1.0, 30e6)
    exp_success, cheap_flop = mk(8.0, 30e6), mk(1.0, 2e6)
    analyze._apply_value_weighting(
        [cheap_success, exp_flop, exp_success, cheap_flop], priors, cavg, lavg)
    assert cheap_success.value_multiplier > 1.0      # cheap gem -> rewarded
    assert exp_flop.value_multiplier > 1.0           # expensive flop -> penalised
    assert exp_success.value_multiplier == 1.0       # paid for quality -> neutral
    assert cheap_flop.value_multiplier == 1.0        # low stakes -> neutral
    assert cheap_success.weight == round(2.0 * cheap_success.value_multiplier, 3)


def _win(season, window):
    return {"club_id": "100", "club": "X", "league": "GB1", "season": season,
            "season_label": "", "window": window, "n_signings": 1, "n_starter": 1,
            "n_rotation": 0, "weight_sum": 2.0, "window_rating": 5.0, "problems": ["CB"],
            "validated_problems": ["CB"], "problems_addressed": [],
            "problems_unaddressed": ["CB"], "signings": [], "chronic_unaddressed": [],
            "problem_resolution": None, "window_grade": None}


def test_chronic_penalty():
    windows = [_win(2020, "summer"), _win(2020, "winter")]   # same unfixed problem twice
    analyze._apply_chronic(None, windows)
    assert windows[0]["chronic_unaddressed"] == []          # streak 1 < threshold
    assert windows[0]["window_rating"] == 5.0               # no penalty yet
    assert windows[1]["chronic_unaddressed"] == ["CB"]      # streak 2 -> chronic
    assert windows[1]["window_rating"] == pytest.approx(4.25)   # 5.0 - 0.75 penalty
    assert windows[1]["window_rating_raw"] == 5.0


def fee(eur, known=True, loan=False, free=False):
    return {"eur": eur, "known": known, "loan": loan, "free": free}


def arrival(pid, name, pos, f, mv, age):
    return {"pid": pid, "name": name, "position": pos, "group": None, "age": age,
            "fee": f, "mv_at": mv, "counterpart_club_id": "200",
            "season": 2020, "league": "GB1"}


def build():
    ds = Dataset(seasons=[2020, 2021])
    c = "100"
    ds.club_name[c] = "TestFC"
    for s in (2019, 2020, 2021):
        ds.club_league[(c, s)] = "GB1"
        ds.matches[(c, s)] = 38
    # rosters: normal signing "9" plays a lot; insignificant "I" barely plays
    for s in (2020, 2021):
        ds.rosters[(c, s)] = [
            player("9", "Player X", "Centre-Forward", 3000, c, s),
            player("I", "Filler", "Centre-Forward", 100, c, s),
            player("k", "Keeper", "Goalkeeper", 3400, c, s),
        ]
        ds.squad_mv[(c, s)] = {"9": 40_000_000, "I": 1_000_000, "k": 5_000_000}
        ds.ratings_index[("GB1", s)] = rating_index(
            [("Player X", "TestFC", 7.0), ("Filler", "TestFC", 6.0), ("Keeper", "TestFC", 6.9)])
    ds.rosters[(c, 2019)] = [player("k", "Keeper", "Goalkeeper", 3400, c, 2019)]
    ds.transfers[(c, 2020, "summer")] = {
        "arrivals": [
            arrival("9", "Player X", "Centre-Forward", fee(40_000_000), 40_000_000, 25),
            arrival("L", "Loanee", "Centre-Back", fee(0, loan=True), 5_000_000, 25),
            arrival("Y", "Kid", "Right Winger", fee(5_000_000), 3_000_000, 17),
            arrival("I", "Filler", "Centre-Forward", fee(1_000_000), 1_000_000, 25),
        ],
        "departures": [],
    }
    return ds


def test_analyze_runs_and_has_structure():
    res = analyze.analyze(build(), log=lambda *a, **k: None, bootstrap=False)
    for key in ("windows", "signings", "rollups", "shrinkage_k", "league_priors"):
        assert key in res
    assert isinstance(res["shrinkage_k"], float)


def test_exclusions_loan_under18_insignificant():
    res = analyze.analyze(build(), log=lambda *a, **k: None, bootstrap=False)
    pids = {s.pid for s in res["signings"]}
    assert pids == {"9"}                 # loan, under-18 and the insignificant buy dropped


def test_kept_signing_scored():
    res = analyze.analyze(build(), log=lambda *a, **k: None, bootstrap=False)
    s = next(s for s in res["signings"] if s.pid == "9")
    assert s.overall_rating is not None and 0 <= s.overall_rating <= 10
