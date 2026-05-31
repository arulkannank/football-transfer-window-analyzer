"""SofaScore ratings scraper + TM<->Sofa name matching.

We only need a season-average rating per player per league-season. Positions and
minutes come from Transfermarkt, so matching is by (normalized name [+ team]).
"""
from __future__ import annotations

from .http import Client
from . import util

API = "https://api.sofascore.com/api/v1"
SOFA_REFERER = "https://www.sofascore.com/"


def make_client(verbose: bool = True) -> Client:
    return Client("sofa", referer=SOFA_REFERER, want_json=True, verbose=verbose)


def tournament_season_id(client: Client, utid: int, season_year: int) -> int | None:
    """Map a season start year (2023) to SofaScore's season id via the '23/24' label."""
    j = client.get_json(f"{API}/unique-tournament/{utid}/seasons")
    if not j:
        return None
    label = util.season_label(season_year)             # '23/24'
    for s in j.get("seasons", []):
        if s.get("year") == label:
            return s.get("id")
    return None


def league_ratings(client: Client, utid: int, season_id: int) -> list[dict]:
    """Paginate the season statistics endpoint; return per-player ratings."""
    out: list[dict] = []
    offset, pages = 0, 1
    while True:
        params = {
            "limit": 100, "order": "-rating", "offset": offset,
            "accumulation": "total",
            "fields": "rating,appearances,minutesPlayed",
        }
        j = client.get_json(f"{API}/unique-tournament/{utid}/season/{season_id}/statistics",
                            params=params)
        if not j:
            break
        pages = j.get("pages", 1)
        for r in j.get("results", []):
            pl = r.get("player", {})
            out.append({
                "name": pl.get("name", ""),
                "team": (r.get("team") or {}).get("name", ""),
                "rating": r.get("rating"),
                "apps": r.get("appearances"),
                "minutes": r.get("minutesPlayed"),
            })
        offset += 100
        if offset // 100 >= pages:
            break
    return out


def build_rating_index(ratings: list[dict]) -> dict:
    """Index ratings for matching: exact name -> [(team_norm, rating, minutes)]."""
    idx: dict[str, list[tuple[str, float, int]]] = {}
    for r in ratings:
        rt = r.get("rating")
        if rt is None:
            continue
        key = util.norm_name(r["name"])
        if not key:
            continue
        idx.setdefault(key, []).append(
            (util.norm_name(r.get("team", "")), float(rt), r.get("minutes") or 0))
    return idx


def lookup_rating(index: dict, name: str, team_name: str | None = None) -> float | None:
    """Find a player's season rating; disambiguate by team when names collide."""
    cands = index.get(util.norm_name(name))
    if not cands:
        # fallback: 'f surname' / surname keys
        for k in util.name_keys(name):
            if k in index:
                cands = index[k]
                break
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][1]
    if team_name:
        tn = util.norm_name(team_name)
        # prefer same/overlapping team name
        for team_norm, rating, _ in cands:
            if team_norm and (tn in team_norm or team_norm in tn):
                return rating
    # otherwise take the highest-minutes candidate (most likely the regular)
    return max(cands, key=lambda c: c[2])[1]
