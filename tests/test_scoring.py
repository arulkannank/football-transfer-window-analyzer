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
    assert 0.0 <= sg.overall_rating <= 10.0
