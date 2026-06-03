import pytest

from ftw import scoring


# ---- component helpers ----
def test_ratio_unit_starter():
    assert scoring._ratio_unit(2.5, rotation=False) == pytest.approx(1.0)
    assert scoring._ratio_unit(1.0, rotation=False) == pytest.approx(0.0)
    assert scoring._ratio_unit(0.5, rotation=False) == pytest.approx(-1 / 3, abs=1e-3)
    assert scoring._ratio_unit(5.0, rotation=False) == pytest.approx(1.25)   # +0.25 bonus
    assert scoring._ratio_unit(10.0, rotation=False) == pytest.approx(1.5)   # +0.5 bonus


def test_ratio_unit_rotation():
    assert scoring._ratio_unit(1.0, rotation=True) == pytest.approx(1.0)
    assert scoring._ratio_unit(0.5, rotation=True) == pytest.approx(0.5)
    assert scoring._ratio_unit(2.0, rotation=True) == pytest.approx(1.0)     # capped at maintain


def test_minutes_frac():
    assert scoring._minutes_frac(0.90, rotation=False) == pytest.approx(1.0)
    assert scoring._minutes_frac(0.45, rotation=False) == pytest.approx(0.5)
    assert scoring._minutes_frac(0.40, rotation=True) == pytest.approx(1.0)
    assert scoring._minutes_frac(0.20, rotation=True) == pytest.approx(0.5)


def test_rating_frac():
    assert scoring._rating_frac(1.0, rotation=False) == pytest.approx(1.0)
    assert scoring._rating_frac(0.0, rotation=False) == pytest.approx(0.0)
    assert scoring._rating_frac(-0.5, rotation=False) == pytest.approx(-0.5)
    assert scoring._rating_frac(0.0, rotation=True) == pytest.approx(1.0)
    assert scoring._rating_frac(-0.3, rotation=True) == pytest.approx(0.7)


def test_eff_frac():
    assert scoring._eff_frac(70, True, False, 100) == pytest.approx(1.0)     # 30% discount
    assert scoring._eff_frac(100, True, False, 100) == pytest.approx(0.0)    # paid MV
    assert scoring._eff_frac(130, True, False, 100) == pytest.approx(-1.0)   # 30% over
    assert scoring._eff_frac(0, False, True, 100) == pytest.approx(1.0)      # free
    assert scoring._eff_frac(50, False, False, 100) is None                  # unknown fee


# ---- full scoring ----
def _sale(ds, club, season, window, fee, mv):
    ds.departures_by_pid["9"] = [{
        "club_id": club, "season": season, "window": window, "fee_eur": fee,
        "fee_known": True, "is_loan": False, "mv": mv, "group": "CF", "to_club_id": "200"}]


def test_sold_starter_path(base_ds, make_signing):
    _sale(base_ds, "100", 2021, "summer", 150_000_000, 120_000_000)
    sg = make_signing(season=2019, fee=50_000_000, mv=50_000_000)
    sg.is_starter_signing = True
    scoring.score_signing(base_ds, sg, 2023)
    assert sg._sold is True
    assert [e["season"] for e in sg.season_evals] == [2019, 2020]   # summer sale excludes 2021
    assert sg._breakdown["minutes"] == pytest.approx(6.0)           # full minutes, /6 max
    assert sg._breakdown["profit_loss"] == pytest.approx(2.0)       # 3x -> capped base


def test_winter_sale_keeps_partial_season(base_ds, make_signing):
    _sale(base_ds, "100", 2021, "winter", 150_000_000, 120_000_000)
    sg = make_signing(season=2019, fee=50_000_000, mv=50_000_000)
    sg.is_starter_signing = True
    scoring.score_signing(base_ds, sg, 2023)
    assert [e["season"] for e in sg.season_evals] == [2019, 2020, 2021]


def test_not_sold_redistribution(base_ds, make_signing):
    sg = make_signing(fee=50_000_000, mv=50_000_000)
    sg.is_starter_signing = True
    scoring.score_signing(base_ds, sg, 2021)
    assert sg._sold is False
    assert "profit_loss" not in sg._breakdown                      # no P&L when not sold
    assert sg._breakdown["minutes"] == pytest.approx(6.5)          # redistributed max


def test_longevity_multi_season(base_ds, make_signing):
    sg = make_signing(season=2019, fee=50_000_000, mv=50_000_000)
    sg.is_starter_signing = True
    scoring.score_signing(base_ds, sg, 2021)                       # regular 3 seasons
    assert sg.successful_seasons == 3
    assert sg.longevity_multiplier == 2.0                          # 1 + 0.5*(3-1)
    assert sg.weight == pytest.approx(4.0)                         # starter base 2 x 2.0


def test_winter_denominator(make_signing):
    from conftest import player, rating_index
    from ftw.dataset import Dataset
    ds = Dataset(seasons=[2019, 2020])
    c = "100"
    ds.club_name[c] = "X"
    for s, mins in [(2019, 1500), (2020, 3000)]:
        ds.club_league[(c, s)] = "GB1"
        ds.matches[(c, s)] = 38                      # full available = 3420
        ds.rosters[(c, s)] = [player("9", "P", "Centre-Forward", mins, c, s)]
        ds.squad_mv[(c, s)] = {"9": 40_000_000}
        ds.pos_rating_avg[("GB1", s, "CF")] = 6.8
        ds.ratings_index[("GB1", s)] = rating_index([("P", "X", 7.0)])
    sg = make_signing(pid="9", name="P", club="100", season=2019, window="winter",
                      fee=40_000_000, mv=40_000_000)
    sg.is_starter_signing = True
    scoring.score_signing(ds, sg, 2020)
    e19 = next(e for e in sg.season_evals if e["season"] == 2019)
    # winter joiner: 1500 / (3420 * 0.5) = 0.877, not the un-prorated 0.44
    assert e19["minutes_share"] == pytest.approx(0.877, abs=0.01)


def test_bought_before_no_fabricated_profit(make_signing):
    from conftest import player, rating_index
    from ftw.dataset import Dataset
    ds = Dataset(seasons=[2020, 2021])
    c = "100"
    ds.club_name[c] = "X"
    for s, mins in [(2019, 2000), (2020, 3000), (2021, 3000)]:   # present in 2019, before signing
        ds.club_league[(c, s)] = "GB1"
        ds.matches[(c, s)] = 38
        ds.rosters[(c, s)] = [player("9", "P", "Centre-Forward", mins, c, s)]
        ds.squad_mv[(c, s)] = {"9": 500_000}                     # tiny pre-breakout value
        ds.pos_rating_avg[("GB1", s, "CF")] = 6.8
        ds.ratings_index[("GB1", s)] = rating_index([("P", "X", 7.0)])
    ds.departures_by_pid["9"] = [{"club_id": c, "season": 2022, "window": "summer",
                                  "fee_eur": 15_000_000, "fee_known": True, "is_loan": False,
                                  "mv": 12_000_000, "group": "CF", "to_club_id": "200"}]
    sg = make_signing(pid="9", name="P", club="100", season=2020, window="summer",
                      fee=None, mv=500_000)
    sg.fee_known = False
    sg.is_starter_signing = True
    scoring.score_signing(ds, sg, 2021)
    # purchase price unknown (already at the club, undisclosed fee) -> P&L not fabricated
    assert sg._sold is True
    assert sg._breakdown.get("profit_loss") is None


def test_longevity_single_season(base_ds, make_signing):
    _sale(base_ds, "100", 2020, "summer", 60_000_000, 50_000_000)  # sold after one season
    sg = make_signing(season=2019, fee=50_000_000, mv=50_000_000)
    sg.is_starter_signing = True
    scoring.score_signing(base_ds, sg, 2021)
    assert sg.successful_seasons == 1
    assert sg.longevity_multiplier == 1.0
    assert sg.weight == pytest.approx(2.0)
    assert 0.0 <= sg.overall_rating <= 10.0
