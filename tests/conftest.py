"""Shared test helpers: build tiny synthetic Datasets so the analysis logic can be
unit-tested without any scraping."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import to_slot                      # noqa: E402
from ftw import sofa                            # noqa: E402
from ftw.dataset import Dataset                 # noqa: E402
from ftw.models import PlayerSeason, Signing    # noqa: E402


def player(pid, name, pos, minutes, club, season, league="GB1", age=25):
    return PlayerSeason(pid=pid, name=name, position=pos, group=to_slot(pos),
                        age=age, minutes=minutes, club_id=club, season=season, league=league)


def rating_index(entries):
    """entries: list of (name, team, rating)."""
    return sofa.build_rating_index(
        [{"name": n, "team": t, "rating": r, "minutes": 3000} for n, t, r in entries])


def signing(pid="9", name="Player X", pos="Centre-Forward", club="100", league="GB1",
            season=2020, window="summer", fee=40_000_000, mv=40_000_000, age=25,
            fee_known=True, is_free=False, is_loan=False, from_club="200"):
    return Signing(pid=pid, name=name, position=pos, group=to_slot(pos), age_at_signing=age,
                   club_id=club, league=league, season=season, window=window,
                   fee_eur=fee, fee_known=fee_known, is_loan=is_loan, is_free=is_free,
                   mv_at_purchase=mv, from_club_id=from_club, date_iso=None)


@pytest.fixture
def make_signing():
    return signing


@pytest.fixture
def base_ds():
    """A one-club dataset: striker plays two full seasons, valued €50m, rated +0.5."""
    ds = Dataset(seasons=[2019, 2020, 2021, 2022, 2023])
    c = "100"
    ds.club_name[c] = "TestFC"
    for s in (2019, 2020, 2021):
        ds.club_league[(c, s)] = "GB1"
        ds.matches[(c, s)] = 38
        ds.rosters[(c, s)] = [player("9", "Player X", "Centre-Forward", 3200, c, s)]
        ds.squad_mv[(c, s)] = {"9": 50_000_000}
        ds.pos_rating_avg[("GB1", s, "CF")] = 6.8
        ds.ratings_index[("GB1", s)] = rating_index([("Player X", "TestFC", 7.3)])
    return ds
