"""Problem-position detection.

For a club's window in season Y, problems are diagnosed from the PRIOR season
(Y-1):

  PRIMARY  flag: no single player in a position group reached STARTER_MINUTES_SHARE
                 (65%) of the club's available league minutes -> no nailed-on
                 starter / injury or rotation concern.
  VALIDATION layers (corroborate / raise severity):
    1. rating  : the group's avg rating is below the league avg for that position
    2. value   : the group's total market value fell > DECLINING_VALUE_PCT YoY
    3. age     : the most-used player in the group is older than 33 (least weight)
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from .dataset import Dataset


GROUPS = ("GK", "DEF", "MID", "FWD")
AGING_AGE = 33


@dataclass
class ProblemFlag:
    group: str
    min_share: float
    top_min_age: int | None
    is_problem: bool
    club_rating: float | None
    league_rating: float | None
    rating_below_avg: bool
    mv_change_pct: float | None
    mv_decline: bool
    aging: bool
    severity: float
    validated: bool


def _group_total_mv(ds: Dataset, club_id: str, season: int, group: str) -> int | None:
    mvs = ds.squad_mv.get((club_id, season))
    if not mvs:
        return None
    total, n = 0, 0
    for p in ds.roster(club_id, season):
        if p.group == group and p.pid in mvs:
            total += mvs[p.pid]
            n += 1
    return total if n else None


def _club_group_rating(ds: Dataset, league: str, club_id: str, season: int,
                       club_name: str, group: str) -> float | None:
    num = den = 0.0
    for p in ds.roster(club_id, season):
        if p.group != group:
            continue
        r = ds.rating(league, season, p.name, club_name)
        if r is None:
            continue
        w = max(p.minutes, 1)
        num += r * w
        den += w
    return num / den if den else None


def detect(ds: Dataset, club_id: str, season: int) -> dict[str, ProblemFlag]:
    """Problem flags for the window of `season` (diagnosed on season-1)."""
    prev = season - 1
    league = ds.club_league.get((club_id, prev)) or ds.club_league.get((club_id, season))
    club_name = ds.club_name.get(club_id, "")
    avail = ds.available_minutes(club_id, prev, league)
    roster = ds.roster(club_id, prev)
    flags: dict[str, ProblemFlag] = {}
    for g in GROUPS:
        members = [p for p in roster if p.group == g]
        if not members and not roster:
            # no prior-season data at all -> cannot diagnose
            continue
        top = max(members, key=lambda p: p.minutes, default=None)
        min_share = (top.minutes / avail) if (top and avail) else 0.0
        top_age = top.age if top else None
        is_problem = min_share < config.STARTER_MINUTES_SHARE

        club_r = _club_group_rating(ds, league, club_id, prev, club_name, g) if league else None
        league_r = ds.pos_avg_rating(league, prev, g) if league else None
        rating_below = bool(club_r is not None and league_r is not None and club_r < league_r)

        mv_now = _group_total_mv(ds, club_id, prev, g)
        mv_prev = _group_total_mv(ds, club_id, prev - 1, g)
        mv_pct = None
        if mv_now is not None and mv_prev:
            mv_pct = (mv_now - mv_prev) / mv_prev
        mv_decline = bool(mv_pct is not None and mv_pct < config.DECLINING_VALUE_PCT)

        aging = bool(top_age is not None and top_age > AGING_AGE)

        severity = 0.0
        if is_problem:
            severity = 0.4 + 0.3 * rating_below + 0.2 * mv_decline + 0.1 * aging
        validated = is_problem and (rating_below or mv_decline or aging)

        flags[g] = ProblemFlag(
            group=g, min_share=round(min_share, 3), top_min_age=top_age,
            is_problem=is_problem, club_rating=club_r, league_rating=league_r,
            rating_below_avg=rating_below, mv_change_pct=mv_pct, mv_decline=mv_decline,
            aging=aging, severity=round(severity, 3), validated=validated)
    return flags
