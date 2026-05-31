"""Transfermarkt scrapers.

Page types used (all cached via ftw.http.Client):
  league clubs   /<slug>/startseite/wettbewerb/<CODE>/plus/?saison_id=<Y>
  league table   /<slug>/tabelle/wettbewerb/<CODE>?saison_id=<Y>     (matches played)
  performance    /<slug>/leistungsdaten/verein/<id>/reldata/<CODE>%26<Y>/plus/1
  transfers      /<slug>/transfers/verein/<id>/saison_id/<Y>/plus/1
  transfer hist  /ceapi/transferHistory/list/<pid>                   (JSON)
  mv history     /ceapi/marketValueDevelopment/graph/<pid>           (JSON)
"""
from __future__ import annotations

import datetime as _dt

from bs4 import BeautifulSoup

from .http import Client
from .models import PlayerSeason, TransferMove
from . import util

BASE = "https://www.transfermarkt.com"


def _soup(client: Client, url: str) -> BeautifulSoup | None:
    html = client.get(url)
    if not html:
        return None
    return BeautifulSoup(html, "html.parser")


# --- league level -----------------------------------------------------------
def league_clubs(client: Client, league, season: int) -> list[dict]:
    """Return [{'club_id','name','slug'}] for a league-season."""
    url = f"{BASE}/{league.slug}/startseite/wettbewerb/{league.code}/plus/?saison_id={season}"
    soup = _soup(client, url)
    if soup is None:
        return []
    out, seen = [], set()
    for a in soup.select("td.hauptlink a[href*='/startseite/verein/']"):
        href = a.get("href", "")
        cid = util.club_id_from_href(href)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        slug = href.lstrip("/").split("/")[0]
        out.append({"club_id": cid, "name": a.get_text(strip=True), "slug": slug})
    return out


def league_matches(client: Client, league, season: int) -> dict[str, int]:
    """Return {club_id: matches_played} from the final league table."""
    url = f"{BASE}/{league.slug}/tabelle/wettbewerb/{league.code}?saison_id={season}"
    soup = _soup(client, url)
    if soup is None:
        return {}
    table = soup.select_one("table.items")
    if not table:
        return {}
    out: dict[str, int] = {}
    for r in table.select("tbody tr"):
        tds = r.find_all("td", recursive=False)
        if len(tds) < 4:
            continue
        a = r.select_one("a[href*='/verein/']")
        cid = util.club_id_from_href(a.get("href")) if a else None
        played = util.parse_int(tds[3].get_text(strip=True))
        if cid and played:
            out[cid] = played
    return out


# --- club performance (minutes / age / position) ----------------------------
def _player_cell(td) -> tuple[str | None, str, str]:
    """Return (pid, name, position) from a posrela player cell."""
    a = td.select_one("td.hauptlink a[href*='/spieler/']") or \
        td.select_one("a[href*='/spieler/']")
    pid = util.player_id_from_href(a.get("href")) if a else None
    name = a.get_text(strip=True) if a else ""
    inner_rows = td.select("table.inline-table tr")
    pos = ""
    if len(inner_rows) >= 2:
        pos = inner_rows[-1].get_text(strip=True)
    return pid, name, pos


def club_performance(client: Client, league, club_id: str, slug: str,
                     season: int) -> list[PlayerSeason]:
    url = (f"{BASE}/{slug}/leistungsdaten/verein/{club_id}"
           f"/reldata/{league.code}%26{season}/plus/1")
    soup = _soup(client, url)
    if soup is None:
        return []
    table = soup.select_one("table.items")
    if not table:
        return []
    from config import to_group
    out: list[PlayerSeason] = []
    for r in table.select("tbody > tr"):
        tds = r.find_all("td", recursive=False)
        if len(tds) < 5:
            continue
        pid, name, pos = _player_cell(tds[1])
        if not pid:
            continue
        age = util.parse_int(tds[2].get_text(strip=True))
        minutes = util.parse_minutes(tds[-1].get_text(strip=True))
        out.append(PlayerSeason(
            pid=pid, name=name, position=pos, group=to_group(pos),
            age=age, minutes=minutes, club_id=club_id, season=season,
            league=league.code))
    return out


# --- club transfers (arrivals / departures) ---------------------------------
def _header_index(table) -> dict[str, int]:
    idx = {}
    for i, th in enumerate(table.select("thead th")):
        idx[th.get_text(strip=True)] = i
    return idx


def _transfer_rows(table, league_code: str, season: int, *, incoming: bool) -> list[dict]:
    from config import to_group
    hi = _header_index(table)
    counterpart_col = hi.get("Left" if incoming else "Joined")
    fee_col = hi.get("Fee")
    mv_col = hi.get("Market value")
    age_col = hi.get("Age")
    rows = []
    seen_pids = set()
    for r in table.select("tbody > tr"):
        tds = r.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        pid, name, pos = _player_cell(tds[1])
        if not pid or pid in seen_pids:
            continue
        seen_pids.add(pid)
        cp_id = None
        if counterpart_col is not None and counterpart_col < len(tds):
            a = tds[counterpart_col].select_one("a[href*='/verein/']")
            cp_id = util.club_id_from_href(a.get("href")) if a else None
        fee = util.parse_money(tds[fee_col].get_text(strip=True)) if fee_col is not None else util.parse_money(None)
        mv = util.parse_mv(tds[mv_col].get_text(strip=True)) if mv_col is not None else None
        age = util.parse_int(tds[age_col].get_text(strip=True)) if age_col is not None else None
        rows.append({
            "pid": pid, "name": name, "position": pos, "group": to_group(pos),
            "age": age, "fee": fee, "mv_at": mv, "counterpart_club_id": cp_id,
            "season": season, "league": league_code,
        })
    return rows


def club_transfers(client: Client, league, club_id: str, slug: str,
                   season: int, window: str | None = None) -> dict:
    """Arrivals/departures for a club-season. window='summer'|'winter' filters
    via TM's w_s param (s/w); None returns the whole season."""
    if window in ("summer", "winter"):
        ws = "s" if window == "summer" else "w"
        url = (f"{BASE}/{slug}/transfers/verein/{club_id}/saison_id/{season}"
               f"/pos//detailpos/0/w_s/{ws}/plus/1")
    else:
        url = f"{BASE}/{slug}/transfers/verein/{club_id}/saison_id/{season}/plus/1"
    soup = _soup(client, url)
    out = {"arrivals": [], "departures": []}
    if soup is None:
        return out
    for box in soup.select("div.box"):
        head_el = box.select_one(".content-box-headline, h2")
        head = head_el.get_text(strip=True) if head_el else ""
        table = box.select_one("table.items")
        if not table:
            continue
        if head.startswith("Arrivals"):
            out["arrivals"] = _transfer_rows(table, league.code, season, incoming=True)
        elif head.startswith("Departures"):
            out["departures"] = _transfer_rows(table, league.code, season, incoming=False)
    return out


# --- club squad values (historical market value per player) ------------------
def club_squad_values(client: Client, club_id: str, slug: str,
                      season: int) -> dict[str, int]:
    """Return {pid: market_value_eur} from the kader page for that season.

    TM's kader/saison_id page carries the player's value AT THAT SEASON (a
    historical snapshot), which is exactly what the position-MV-decline layer
    and the per-season market-value sub-score need.
    """
    url = f"{BASE}/{slug}/kader/verein/{club_id}/saison_id/{season}/plus/1"
    soup = _soup(client, url)
    if soup is None:
        return {}
    table = soup.select_one("table.items")
    if not table:
        return {}
    out: dict[str, int] = {}
    for r in table.select("tbody > tr"):
        tds = r.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        a = tds[1].select_one("a[href*='/spieler/']")
        pid = util.player_id_from_href(a.get("href")) if a else None
        if not pid:
            continue
        mv = util.parse_mv(tds[-1].get_text(strip=True))
        if mv is not None:
            out[pid] = mv
    return out


# --- per-player JSON endpoints (optional; not required by the pipeline) ------
def player_transfer_history(client_json: Client, pid: str) -> list[TransferMove]:
    j = client_json.get_json(f"{BASE}/ceapi/transferHistory/list/{pid}")
    if not j:
        return []
    moves = []
    for t in j.get("transfers", []):
        if t.get("upcoming") or t.get("futureTransfer"):
            continue
        fee = util.parse_money(t.get("fee"))
        moves.append(TransferMove(
            pid=pid,
            date_iso=t.get("dateUnformatted") or None,
            season=t.get("season"),
            from_club_id=util.club_id_from_href((t.get("from") or {}).get("href")),
            to_club_id=util.club_id_from_href((t.get("to") or {}).get("href")),
            fee_eur=fee["eur"], fee_known=fee["known"],
            is_loan=fee["loan"], is_free=fee["free"],
            mv_at_eur=util.parse_mv(t.get("marketValue")),
        ))
    return moves


def player_mv_history(client_json: Client, pid: str) -> list[tuple[_dt.date, int]]:
    j = client_json.get_json(f"{BASE}/ceapi/marketValueDevelopment/graph/{pid}")
    if not j:
        return []
    pts = []
    for p in j.get("list", []):
        d = util.parse_date(p.get("datum_mw"))
        y = p.get("y")
        if d is not None and isinstance(y, (int, float)):
            pts.append((d, int(y)))
    pts.sort(key=lambda x: x[0])
    return pts


def mv_at(points: list[tuple[_dt.date, int]], when: _dt.date) -> int | None:
    """Market value as of `when` (most recent point on/before that date)."""
    val = None
    for d, v in points:
        if d <= when:
            val = v
        else:
            break
    if val is None and points:
        val = points[0][1]   # before first datapoint -> earliest known value
    return val
