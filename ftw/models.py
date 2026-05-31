"""Data models for the pipeline. Kept simple & JSON-serializable."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class PlayerSeason:
    """A player's record for one club in one season (from the performance page)."""
    pid: str
    name: str
    position: str          # raw TM position, e.g. 'Centre-Back'
    group: str             # fine slot: GK/RB/LB/CB/MID/W/CF
    age: Optional[int]
    minutes: int
    club_id: str
    season: int            # season start year (2023 == 23/24)
    league: str


@dataclass
class ClubSeason:
    club_id: str
    name: str
    slug: str
    league: str
    season: int
    matches_played: int            # actual league matches (minutes denominator/90)
    roster: list[PlayerSeason] = field(default_factory=list)


@dataclass
class TransferMove:
    """One leg of a player's transfer history (purchase or sale)."""
    pid: str
    date_iso: Optional[str]
    season: Optional[str]          # TM label like '23/24'
    from_club_id: Optional[str]
    to_club_id: Optional[str]
    fee_eur: Optional[int]
    fee_known: bool
    is_loan: bool
    is_free: bool
    mv_at_eur: Optional[int]       # market value at the time of the move


@dataclass
class Signing:
    """A tracked incoming transfer for one club, the unit we score."""
    pid: str
    name: str
    position: str
    group: str
    age_at_signing: Optional[int]
    club_id: str
    league: str
    season: int                    # season the signing belongs to (start year)
    window: str                    # 'summer' | 'winter'
    fee_eur: Optional[int]
    fee_known: bool
    is_loan: bool
    is_free: bool
    mv_at_purchase: Optional[int]
    from_club_id: Optional[str]
    date_iso: Optional[str]
    # filled later:
    classification: list[str] = field(default_factory=list)
    is_starter_signing: bool = False        # starter-type vs rotation-type rubric
    addressed_problem: bool = False
    # sale (if any) — from transfer history:
    sale_date_iso: Optional[str] = None
    sale_fee_eur: Optional[int] = None
    sale_fee_known: bool = False
    sale_to_club_id: Optional[str] = None
    # per-season evaluations and overall:
    season_evals: list[dict] = field(default_factory=list)
    overall_rating: Optional[float] = None
    weight: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)
