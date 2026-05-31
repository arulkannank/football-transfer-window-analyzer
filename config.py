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


# ----- position slots (fine-grained, formation-based) -----
# Problems and league rating baselines are diagnosed per *slot*, not per broad
# line, so e.g. a weak right-back isn't masked by strong centre-backs. The
# required starter counts describe a standard XI (4-3-3 / 4-2-3-1):
#   GK 1 · RB 1 · LB 1 · CB 2 · MID 3 · W 2 · CF 1  (= 11)
POSITION_SLOTS = {
    "Goalkeeper": "GK",
    "Right-Back": "RB",
    "Left-Back": "LB",
    "Centre-Back": "CB", "Defender": "CB",
    "Defensive Midfield": "MID", "Central Midfield": "MID",
    "Attacking Midfield": "MID", "Midfielder": "MID",
    "Left Winger": "W", "Right Winger": "W",
    "Left Midfield": "W", "Right Midfield": "W",
    "Centre-Forward": "CF", "Second Striker": "CF", "Forward": "CF", "Attack": "CF",
}

SLOTS = ("GK", "RB", "LB", "CB", "MID", "W", "CF")
SLOT_REQUIRED = {"GK": 1, "RB": 1, "LB": 1, "CB": 2, "MID": 3, "W": 2, "CF": 1}
SLOT_NAMES = {
    "GK": "Goalkeeper", "RB": "Right-back", "LB": "Left-back", "CB": "Centre-back",
    "MID": "Midfield", "W": "Wingers", "CF": "Centre-forward",
}


def to_slot(position: str) -> str:
    if not position:
        return "MID"
    if position in POSITION_SLOTS:
        return POSITION_SLOTS[position]
    p = position.lower()
    if "keep" in p or "goal" in p:
        return "GK"
    if "right-back" in p or "right back" in p:
        return "RB"
    if "left-back" in p or "left back" in p:
        return "LB"
    if "back" in p or "defen" in p:
        return "CB"
    if "wing" in p:
        return "W"
    if "forward" in p or "strik" in p or "attack" in p:
        return "CF"
    return "MID"


# Broad line, for any display/aggregation that wants the old grouping.
_SLOT_LINE = {"GK": "GK", "RB": "DEF", "LB": "DEF", "CB": "DEF",
              "MID": "MID", "W": "FWD", "CF": "FWD"}


def to_group(position: str) -> str:
    return _SLOT_LINE[to_slot(position)]


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
LOW_RATING_THRESHOLD = 6.70       # slot avg SofaScore rating below this
# A slot is a problem if fewer than SLOT_REQUIRED[slot] players reached the
# starter-minutes share last season (not enough nailed-on starters for the XI).

# ----- degradation rule -----
# Failing to address a flagged problem for this many consecutive windows degrades
# the window rating.
CHRONIC_WINDOW_THRESHOLD = 2
PENALTY_PER_CHRONIC_POSITION = 15.0  # points off problem-resolution sub-score per chronic position

# ----- normalization knobs -----
FEE_FLOOR_EUR = 1_000_000.0    # avoids divide-by-near-zero for cheap/free deals
RATING_MIN, RATING_MAX = 6.0, 8.0  # SofaScore band mapped to 0..1
