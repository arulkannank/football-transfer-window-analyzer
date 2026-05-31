"""Configuration: leagues, seasons, scoring weights, thresholds.

Edit LEAGUES to change which competitions are scraped. Transfermarkt competition
codes are in the URL: transfermarkt.com/<slug>/startseite/wettbewerb/<CODE>
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str          # Transfermarkt competition code, e.g. "GB1"
    name: str
    country: str
    slug: str          # URL slug for the competition page
    matches: int       # typical league matches per season (minutes denominator)
    sofa_tournament_id: int | None = None  # SofaScore uniqueTournament id (for ratings)


# Top-7 by UEFA coefficient. Add more League(...) rows here to widen scope;
# the BE1/TR1/SC1 entries from the wider list can be re-added the same way.
LEAGUES: list[League] = [
    League("GB1", "Premier League", "England",     "premier-league", 38, 17),
    League("ES1", "LaLiga",         "Spain",       "laliga",         38, 8),
    League("IT1", "Serie A",        "Italy",       "serie-a",        38, 23),
    League("L1",  "Bundesliga",     "Germany",     "bundesliga",     34, 35),
    League("FR1", "Ligue 1",        "France",      "ligue-1",        34, 34),
    League("PO1", "Liga Portugal",  "Portugal",    "liga-portugal",  34, 238),
    League("NL1", "Eredivisie",     "Netherlands", "eredivisie",     34, 37),
]

LEAGUES_BY_CODE = {lg.code: lg for lg in LEAGUES}

# Full coverage 2019/20 .. 2025/26. 2019 means the 2019/20 season.
# Problem-detection for a given window needs the PRIOR season's squad as baseline,
# so we additionally scrape 2018/19 squads/values as a baseline (BASELINE_SEASON).
# NOTE: 2019/20 (and 2020/21 Eredivisie) were COVID-disrupted / curtailed; the
# minutes denominator is therefore derived from each club's ACTUAL league matches
# played that season (from the league table) rather than the fixed `matches` field,
# which is kept only as a fallback. Ligue 1 also shrank 20->18 clubs from 2023/24.
SEASONS: list[int] = list(range(2019, 2026))  # 2019/20 .. 2025/26
BASELINE_SEASON: int = 2018                    # prior-year baseline for 2019/20 windows

WINDOWS = ("summer", "winter")


# ----- position groups -----
POSITION_GROUPS = {
    "Goalkeeper": "GK",
    "Centre-Back": "DEF", "Left-Back": "DEF", "Right-Back": "DEF", "Defender": "DEF",
    "Defensive Midfield": "MID", "Central Midfield": "MID", "Attacking Midfield": "MID",
    "Left Midfield": "MID", "Right Midfield": "MID", "Midfielder": "MID",
    "Left Winger": "FWD", "Right Winger": "FWD", "Centre-Forward": "FWD",
    "Second Striker": "FWD", "Forward": "FWD", "Attack": "FWD",
}


def to_group(position: str) -> str:
    if not position:
        return "MID"
    if position in POSITION_GROUPS:
        return POSITION_GROUPS[position]
    p = position.lower()
    if "keep" in p:
        return "GK"
    if "back" in p or "defen" in p:
        return "DEF"
    if "wing" in p or "forward" in p or "strik" in p or "attack" in p:
        return "FWD"
    return "MID"


# ----- per-transfer success weights (user-specified, sum to 1.0) -----
@dataclass(frozen=True)
class TransferWeights:
    minutes: float = 0.60
    pnl: float = 0.20
    rating: float = 0.10        # OPTIONAL — redistributed if no rating data
    mv_purchase: float = 0.05   # market value efficiency at purchase
    mv_growth: float = 0.05     # market value change after joining


DEFAULT_TRANSFER_WEIGHTS = TransferWeights()

# ----- window-level aggregation -----
# A window's grade blends how good the recruitment was with how well it fixed
# the squad's problems.
META_RECRUITMENT_WEIGHT = 0.70
META_PROBLEM_WEIGHT = 0.30

# ----- problem-detection thresholds -----
# A position group is flagged a problem if no player there reached this share of
# available minutes last season (no nailed-on starter / injury concern).
STARTER_MINUTES_SHARE = 0.65      # 65% of league minutes ~= a regular starter
# Corroborating signals raise severity:
DECLINING_VALUE_PCT = -0.10       # group lost >10% market value YoY
LOW_RATING_THRESHOLD = 6.70       # group avg SofaScore rating below this
MIN_DEPTH = {"GK": 2, "DEF": 3, "MID": 3, "FWD": 2}

# ----- degradation rule -----
# Failing to address a flagged problem for this many consecutive windows degrades
# the window rating.
CHRONIC_WINDOW_THRESHOLD = 2
PENALTY_PER_CHRONIC_POSITION = 15.0  # points off problem-resolution sub-score per chronic position

# ----- normalization knobs -----
FEE_FLOOR_EUR = 1_000_000.0    # avoids divide-by-near-zero for cheap/free deals
RATING_MIN, RATING_MAX = 6.0, 8.0  # SofaScore band mapped to 0..1
