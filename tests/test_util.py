import datetime as dt

from ftw import tm, util


def test_parse_money_fee():
    assert util.parse_money("€90.00m")["eur"] == 90_000_000
    assert util.parse_money("€450k")["eur"] == 450_000
    m = util.parse_money("€90.00m")
    assert m["known"] and not m["loan"] and not m["free"]


def test_parse_money_free_loan_unknown():
    free = util.parse_money("free transfer")
    assert free["free"] and free["eur"] == 0 and free["known"]
    loan = util.parse_money("loan transfer")
    assert loan["loan"] and loan["eur"] == 0 and loan["known"]
    for blank in ("-", "?", "", None):
        assert util.parse_money(blank)["known"] is False


def test_parse_money_loan_with_fee():
    m = util.parse_money("Loan fee:€2.00m")
    assert m["loan"] and m["known"] and m["eur"] == 2_000_000


def test_parse_mv():
    assert util.parse_mv("€75.00m") == 75_000_000
    assert util.parse_mv("€800k") == 800_000
    assert util.parse_mv("-") is None


def test_norm_name_accents():
    assert util.norm_name("Jérémy Doku") == "jeremy doku"
    assert util.norm_name("N'Golo Kanté") == "n golo kante"


def test_window_of():
    assert util.window_of(dt.date(2023, 1, 15)) == "winter"
    assert util.window_of(dt.date(2023, 2, 1)) == "winter"
    assert util.window_of(dt.date(2023, 8, 5)) == "summer"
    assert util.window_of(None) == "summer"


def test_season_helpers():
    assert util.season_label(2023) == "23/24"
    assert util.season_end_date(2023) == dt.date(2024, 6, 30)


def test_parse_minutes():
    assert util.parse_minutes("2.788'") == 2788
    assert util.parse_minutes("-") == 0


def test_mv_at():
    pts = [(dt.date(2020, 1, 1), 10), (dt.date(2021, 1, 1), 20), (dt.date(2022, 1, 1), 30)]
    assert tm.mv_at(pts, dt.date(2021, 6, 1)) == 20      # most recent on/before
    assert tm.mv_at(pts, dt.date(2019, 1, 1)) == 10      # before first -> earliest
    assert tm.mv_at(pts, dt.date(2025, 1, 1)) == 30


def test_club_and_player_ids():
    assert util.club_id_from_href("/leipzig/transfers/verein/23826/saison_id/2023") == "23826"
    assert util.player_id_from_href("/ederson/profil/spieler/238223") == "238223"
