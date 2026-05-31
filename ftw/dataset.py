"""In-memory dataset assembled by collect.py and consumed by the analysis modules.

All keys use string club_ids and int season start-years. Helper accessors keep
the analysis code readable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import PlayerSeason


@dataclass
class Dataset:
    seasons: list[int] = field(default_factory=list)         # window seasons (2019..2025)
    # league/season -> list[{club_id,name,slug}]
    clubs: dict[tuple[str, int], list[dict]] = field(default_factory=dict)
    club_name: dict[str, str] = field(default_factory=dict)
    club_slug: dict[str, str] = field(default_factory=dict)
    club_league: dict[tuple[str, int], str] = field(default_factory=dict)  # (club_id,season)->league
    matches: dict[tuple[str, int], int] = field(default_factory=dict)      # (club_id,season)->matches
    rosters: dict[tuple[str, int], list[PlayerSeason]] = field(default_factory=dict)
    squad_mv: dict[tuple[str, int], dict[str, int]] = field(default_factory=dict)  # (club,season)->{pid:mv}
    transfers: dict[tuple[str, int, str], dict] = field(default_factory=dict)  # (club,season,window)->{arr,dep}
    ratings_index: dict[tuple[str, int], dict] = field(default_factory=dict)   # (league,season)->name index
    pos_rating_avg: dict[tuple[str, int, str], float] = field(default_factory=dict)  # (league,season,grp)->avg
    # sale index: pid -> list of {club_id,season,window,fee_eur,fee_known,mv,is_loan}
    departures_by_pid: dict[str, list[dict]] = field(default_factory=dict)

    # -- accessors ----------------------------------------------------------
    def roster(self, club_id: str, season: int) -> list[PlayerSeason]:
        return self.rosters.get((club_id, season), [])

    def player_in_roster(self, pid: str, club_id: str, season: int) -> PlayerSeason | None:
        for p in self.roster(club_id, season):
            if p.pid == pid:
                return p
        return None

    def minutes_at(self, pid: str, club_id: str, season: int) -> int | None:
        p = self.player_in_roster(pid, club_id, season)
        return p.minutes if p else None

    def available_minutes(self, club_id: str, season: int, league: str | None = None) -> int:
        m = self.matches.get((club_id, season))
        if m:
            return m * 90
        # fallback to the league's typical match count
        from config import LEAGUES_BY_CODE
        league = league or self.club_league.get((club_id, season))
        lg = LEAGUES_BY_CODE.get(league)
        return (lg.matches if lg else 38) * 90

    def mv_in_season(self, pid: str, club_id: str, season: int) -> int | None:
        return self.squad_mv.get((club_id, season), {}).get(pid)

    def rating(self, league: str, season: int, name: str, team_name: str | None = None):
        idx = self.ratings_index.get((league, season))
        if not idx:
            return None
        from . import sofa
        return sofa.lookup_rating(idx, name, team_name)

    def pos_avg_rating(self, league: str, season: int, group: str) -> float | None:
        return self.pos_rating_avg.get((league, season, group))

    def sale_of(self, pid: str, club_id: str, after_season: int) -> dict | None:
        """Earliest permanent departure of pid from club_id in/after `after_season`."""
        best = None
        for d in self.departures_by_pid.get(pid, []):
            if d["club_id"] != club_id:
                continue
            if d["season"] < after_season:
                continue
            if d.get("is_loan"):
                continue
            if best is None or (d["season"], d["window"] == "winter") < (best["season"], best["window"] == "winter"):
                best = d
        return best
