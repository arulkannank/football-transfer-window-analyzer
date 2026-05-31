from conftest import player, rating_index

from ftw import analyze
from ftw.dataset import Dataset


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
