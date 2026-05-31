"""Problem-position detection.

Problems are diagnosed per formation *slot* (GK/RB/LB/CB/MID/W/CF), each with a
required number of starters (SLOT_REQUIRED) describing a standard XI, from the
PRIOR season (Y-1):

  PRIMARY  flag: fewer than the required number of players in a slot reached
                 STARTER_MINUTES_SHARE (65%) of available league minutes -> not
                 enough nailed-on starters for that slot.
  VALIDATION layers (corroborate / raise severity), all per league:
    1. rating  : the slot's avg rating is below the league avg for that slot
    2. value   : the slot's total market value fell > DECLINING_VALUE_PCT YoY
    3. age     : the most-used player in the slot is older than 33 (least weight)

Also exposes `has_above_avg_incumbent` — whether any existing player in the slot
already rates above the league average there (the slot is well covered, so a new
signing in it is depth/rotation rather than a need).
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from .dataset import Dataset


GROUPS = config.SLOTS          # ("GK","RB","LB","CB","MID","W","CF")
AGING_AGE = 33


@dataclass
class ProblemFlag:
    group: str                 # slot code
    required: int
    starters: int              # how many reached the minutes threshold
    min_share: float           # share of the Nth-most-used player (N = required)
    top_min_age: int | None
    is_problem: bool
    club_rating: float | None
    league_rating: float | None
    rating_below_avg: bool
    has_above_avg_incumbent: bool
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


def _club_slot_rating(ds: Dataset, league: str, club_id: str, season: int,
                      club_name: str, slot: str, league_r: float | None) -> tuple:
    """Minutes-weighted slot rating, and whether any player beats the league avg."""
    num = den = 0.0
    above = False
    for p in ds.roster(club_id, season):
        if p.group != slot:
            continue
        r = ds.rating(league, season, p.name, club_name)
        if r is None:
            continue
        if league_r is not None and p.minutes > 0 and r > league_r:
            above = True
        w = max(p.minutes, 1)
        num += r * w
        den += w
    return (num / den if den else None), above


def detect(ds: Dataset, club_id: str, season: int) -> dict[str, ProblemFlag]:
    """Problem flags for the window of `season` (diagnosed on season-1)."""
    prev = season - 1
    league = ds.club_league.get((club_id, prev)) or ds.club_league.get((club_id, season))
    club_name = ds.club_name.get(club_id, "")
    avail = ds.available_minutes(club_id, prev, league)
    roster = ds.roster(club_id, prev)
    flags: dict[str, ProblemFlag] = {}
    for g in GROUPS:
        if not roster:
            continue                      # no prior-season data -> cannot diagnose
        required = config.SLOT_REQUIRED.get(g, 1)
        members = sorted((p for p in roster if p.group == g),
                         key=lambda p: p.minutes, reverse=True)
        # the Nth-most-used player (N = required starters) sets the bar:
        nth = members[required - 1] if len(members) >= required else None
        min_share = (nth.minutes / avail) if (nth and avail) else 0.0
        starters = sum(1 for p in members
                       if avail and p.minutes / avail >= config.STARTER_MINUTES_SHARE)
        top_age = members[0].age if members else None
        is_problem = starters < required

        league_r = ds.pos_avg_rating(league, prev, g) if league else None
        club_r, above_incumbent = _club_slot_rating(
            ds, league, club_id, prev, club_name, g, league_r) if league else (None, False)
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
            group=g, required=required, starters=starters,
            min_share=round(min_share, 3), top_min_age=top_age,
            is_problem=is_problem, club_rating=club_r, league_rating=league_r,
            rating_below_avg=rating_below, has_above_avg_incumbent=above_incumbent,
            mv_change_pct=mv_pct, mv_decline=mv_decline,
            aging=aging, severity=round(severity, 3), validated=validated)
    return flags
