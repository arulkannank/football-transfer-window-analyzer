from conftest import player, rating_index

from ftw import problems
from ftw.dataset import Dataset


def build():
    """Prior season (2020) for a 2021 window: CB short of a 2nd starter; GK fine."""
    ds = Dataset(seasons=[2021])
    c = "100"
    ds.club_name[c] = "TestFC"
    ds.club_league[(c, 2020)] = "GB1"
    ds.club_league[(c, 2021)] = "GB1"
    ds.matches[(c, 2020)] = 38            # available = 3420
    ds.rosters[(c, 2020)] = [
        player("g1", "Keeper", "Goalkeeper", 3400, c, 2020),
        player("c1", "Rock", "Centre-Back", 3300, c, 2020),
        player("c2", "Backup", "Centre-Back", 400, c, 2020),     # only 1 CB starter
    ]
    ds.squad_mv[(c, 2020)] = {"g1": 10_000_000, "c1": 20_000_000, "c2": 2_000_000}
    ds.ratings_index[("GB1", 2020)] = rating_index(
        [("Keeper", "TestFC", 7.2), ("Rock", "TestFC", 6.3), ("Backup", "TestFC", 6.4)])
    # league baselines per slot
    ds.pos_rating_avg[("GB1", 2020, "GK")] = 6.8
    ds.pos_rating_avg[("GB1", 2020, "CB")] = 6.9
    return ds, c


def test_cb_flagged_needs_two_starters():
    ds, c = build()
    flags = problems.detect(ds, c, 2021)
    assert flags["CB"].required == 2
    assert flags["CB"].starters == 1
    assert flags["CB"].is_problem is True


def test_gk_not_flagged():
    ds, c = build()
    flags = problems.detect(ds, c, 2021)
    assert flags["GK"].required == 1
    assert flags["GK"].is_problem is False


def test_rating_below_average_validation():
    ds, c = build()
    flags = problems.detect(ds, c, 2021)
    # CB minutes-weighted club rating (~6.3) is below the league CB avg (6.9)
    assert flags["CB"].rating_below_avg is True
    assert flags["CB"].validated is True


def test_above_average_incumbent_for_gk():
    ds, c = build()
    flags = problems.detect(ds, c, 2021)
    # the keeper (7.2) beats the league GK avg (6.8) -> slot is covered
    assert flags["GK"].has_above_avg_incumbent is True
