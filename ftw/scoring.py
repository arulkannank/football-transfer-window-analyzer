"""Per-transfer scoring rubric (out of 10), faithful to the brief.

Sub-scores (STARTER, when eventually SOLD):
    minutes 6 | profit/loss 2 | rating improvement 1 | market efficiency 0.5 |
    market-value growth 0.5
When NOT sold (still at club / current), the 2 profit/loss points are
redistributed exactly as specified: minutes -> 6.5, rating -> 1.5, mv -> 1.5.

ROTATION uses gentler thresholds (40% minutes for full credit; "maintain"
rather than "grow"/"profit" for full credit) but the same 2.5x/5x/10x bonus
structure and the same not-sold redistribution.

Each component is evaluated per spell-season and averaged; one-off components
(profit/loss, efficiency) are evaluated at sale/purchase. Components with no data
are dropped and their weight is redistributed proportionally over the rest, so a
player isn't penalised for missing data.
"""
from __future__ import annotations

import config
from .dataset import Dataset
from .models import Signing

EFF_CUTOFF = 0.30          # paying 30%+ below market value -> full efficiency credit
MAX_WINDOW_SEASON = None   # set by pipeline to the last in-scope season

# Tunable thresholds (exposed as module attributes so the sensitivity analysis
# can perturb them without editing functions).
STARTER_PIVOT = 2.5        # profit/mv-growth multiple for full starter credit
STARTER_MINUTES_FULL = 0.90
ROTATION_MINUTES_FULL = 0.40

# Longevity weighting: a "successful season" = >= SUCCESS_MINUTES_SHARE of minutes;
# each extra successful season adds LONGEVITY_PER_SEASON to the weight multiplier,
# capped at LONGEVITY_CAP (so 1 season ->x1, 2 ->x1.5, 3 ->x2.0, 4+ ->x2.5).
SUCCESS_MINUTES_SHARE = 0.40
LONGEVITY_PER_SEASON = 0.5
LONGEVITY_CAP = 2.5

# A winter joiner (or a player sold in winter) was only at the club for ~half the
# season, so his minutes share is measured against ~half the available minutes
# rather than the whole season.
WINTER_AVAILABLE_FRACTION = 0.5


def _bonus_frac(ratio: float) -> float:
    """Fraction-of-max bonus for exceptional multiples (5x -> +0.25, 10x -> +0.5)."""
    if ratio >= 10:
        return 0.5
    if ratio >= 5:
        return 0.25
    return 0.0


def _ratio_unit(ratio: float | None, *, rotation: bool) -> float | None:
    """Unit score (1.0 == full credit) for the profit/loss & mv-growth families.

    STARTER:  2.5x -> 1.0, 1.0x -> 0.0, below 1 negative (can lose points).
    ROTATION: >=1.0x -> 1.0 (maintained), below 1 proportional down to 0.
    Plus the 5x/10x bonus on top (can exceed 1.0).
    """
    if ratio is None:
        return None
    if rotation:
        base = min(ratio, 1.0)
        base = max(base, 0.0)
    else:
        base = (ratio - 1.0) / (STARTER_PIVOT - 1.0)
        base = min(base, 1.0)
        base = max(base, -1.0)
    return base + _bonus_frac(ratio)


def _minutes_frac(share: float, *, rotation: bool) -> float:
    full = ROTATION_MINUTES_FULL if rotation else STARTER_MINUTES_FULL
    return max(0.0, min(share / full, 1.0))


def _rating_frac(improvement: float | None, *, rotation: bool) -> float | None:
    if improvement is None:
        return None
    if rotation:
        # full credit for not reducing the average; proportional penalty below
        return max(-1.0, min(1.0, 1.0 + min(improvement, 0.0)))
    return max(-1.0, min(1.0, improvement))


def _eff_frac(fee_eur, fee_known, is_free, mv) -> float | None:
    if mv is None or mv <= 0:
        return None
    if is_free:
        fee = 0
    elif fee_known and fee_eur is not None:
        fee = fee_eur
    else:
        return None
    diff = (mv - fee) / mv          # +ve = bought below market value
    return max(-1.0, min(1.0, diff / EFF_CUTOFF))


def _spell_seasons(ds: Dataset, signing: Signing, max_season: int) -> list[int]:
    """Seasons the player was actually in the club's squad, from signing to sale.

    `max_season` is the last season that can count (the season of/ before the
    sale — see score_signing). Seasons AFTER the player is sold are never
    included, so they can't drag the average down as zeros; loan-out gaps within
    the spell are skipped (e.g. Saliba at Arsenal), not terminal.
    """
    seasons = [s for s in range(signing.season, max_season + 1)
               if ds.player_in_roster(signing.pid, signing.club_id, s)]
    return seasons or [signing.season]


def score_signing(ds: Dataset, signing: Signing, last_season: int) -> None:
    club = signing.club_id
    name = signing.name
    club_name = ds.club_name.get(club, "")
    rotation = not signing.is_starter_signing
    # Was the player already in this club's senior squad in an earlier season? Then
    # this "arrival" isn't a genuine new purchase (academy graduate, or bought before
    # the data window) and his arrival market value is NOT a reliable cost basis — so
    # don't fabricate a near-zero purchase price and an inflated profit on resale.
    bought_before = any(ds.player_in_roster(signing.pid, club, yr)
                        for yr in range(signing.season - 5, signing.season))
    cost_basis = None
    if signing.fee_known and signing.fee_eur:
        cost_basis = signing.fee_eur                       # a real, disclosed fee
    elif signing.mv_at_purchase and not bought_before:
        cost_basis = signing.mv_at_purchase                # MV proxy for a genuine new buy

    sale = ds.sale_of(signing.pid, club, signing.season)
    sold = sale is not None
    # last season that may count: a SUMMER sale in saison Y means the player left
    # before Y kicked off, so the spell ends at Y-1; a WINTER sale in Y means he
    # played part of Y, so Y still counts. Seasons after that are never scored.
    if sold:
        max_season = sale["season"] - (1 if sale["window"] == "summer" else 0)
    else:
        max_season = last_season
    seasons = _spell_seasons(ds, signing, max_season)
    min_fracs, rate_fracs, mv_units = [], [], []
    evals = []
    for s in seasons:
        league = ds.club_league.get((club, s)) or signing.league
        avail = ds.available_minutes(club, s, league)
        # winter joiners (first season) and winter sales (last season) were only
        # available for ~half the season — pro-rate the denominator accordingly.
        if (s == signing.season and signing.window == "winter") or \
           (sold and sale.get("window") == "winter" and s == sale.get("season")):
            avail = avail * WINTER_AVAILABLE_FRACTION
        mins = ds.minutes_at(signing.pid, club, s)
        mins = mins if mins is not None else 0
        share = (mins / avail) if avail else 0.0
        mfrac = _minutes_frac(share, rotation=rotation)
        min_fracs.append(mfrac)

        player_r = ds.rating(league, s, name, club_name)
        league_r = ds.pos_avg_rating(league, s, signing.group)
        improvement = (player_r - league_r) if (player_r is not None and league_r is not None) else None
        rfrac = _rating_frac(improvement, rotation=rotation)
        if rfrac is not None:
            rate_fracs.append(rfrac)

        mv_end = ds.mv_in_season(signing.pid, club, s)
        mv_ratio = (mv_end / signing.mv_at_purchase) if (mv_end and signing.mv_at_purchase) else None
        munit = _ratio_unit(mv_ratio, rotation=rotation)
        if munit is not None:
            mv_units.append(munit)

        evals.append({
            "season": s, "minutes": mins, "available": avail,
            "minutes_share": round(share, 3), "minutes_frac": round(mfrac, 3),
            "player_rating": player_r, "league_pos_rating": league_r,
            "rating_improvement": (round(improvement, 2) if improvement is not None else None),
            "mv_end_of_season": mv_end, "mv_ratio": (round(mv_ratio, 2) if mv_ratio else None),
        })
    signing.season_evals = evals

    # ---- one-off components (sale computed above) ----
    # efficiency: average of purchase & (if sold) sale efficiency
    effs = []
    ep = _eff_frac(signing.fee_eur, signing.fee_known, signing.is_free, signing.mv_at_purchase)
    if ep is not None:
        effs.append(ep)
    if sold:
        sf, sk = sale.get("fee_eur"), sale.get("fee_known")
        smv = sale.get("mv")
        if smv and smv > 0 and sk and sf is not None:
            effs.append(max(-1.0, min(1.0, ((sf - smv) / smv) / EFF_CUTOFF)))
    eff_frac = sum(effs) / len(effs) if effs else None

    # profit/loss unit (only when sold)
    pnl_unit = None
    if sold:
        sf, sk = sale.get("fee_eur"), sale.get("fee_known")
        if cost_basis and cost_basis > 0 and sk and sf is not None:
            pnl_unit = _ratio_unit(sf / cost_basis, rotation=rotation)
        elif signing.is_free and sk and sf is not None:
            # genuinely free transfer sold for a fee -> a real, large multiple
            pnl_unit = _ratio_unit(10.0 if sf > 0 else 1.0, rotation=rotation)
        # else: purchase price unknown (undisclosed fee on a pre-existing player) ->
        # leave P&L unknown so it's redistributed, not assumed to be bought for 0.

    min_frac_avg = sum(min_fracs) / len(min_fracs) if min_fracs else 0.0
    rate_frac_avg = sum(rate_fracs) / len(rate_fracs) if rate_fracs else None
    mv_unit_avg = sum(mv_units) / len(mv_units) if mv_units else None

    # ---- assemble with proportional redistribution of missing components ----
    if sold:
        comps = [
            ("minutes", min_frac_avg, 6.0, True),
            ("profit_loss", pnl_unit, 2.0, pnl_unit is not None),
            ("rating", rate_frac_avg, 1.0, rate_frac_avg is not None),
            ("efficiency", eff_frac, 0.5, eff_frac is not None),
            ("mv_growth", mv_unit_avg, 0.5, mv_unit_avg is not None),
        ]
    else:
        comps = [
            ("minutes", min_frac_avg, 6.5, True),
            ("rating", rate_frac_avg, 1.5, rate_frac_avg is not None),
            ("efficiency", eff_frac, 0.5, eff_frac is not None),
            ("mv_growth", mv_unit_avg, 1.5, mv_unit_avg is not None),
        ]

    present_max = sum(m for _, _, m, ok in comps if ok)
    total_max = sum(m for _, _, m, _ in comps)
    scale = (total_max / present_max) if present_max > 0 else 0.0

    breakdown = {}
    score = 0.0
    for label, frac, mx, ok in comps:
        if not ok or frac is None:
            breakdown[label] = None
            continue
        pts = frac * mx * scale
        breakdown[label] = round(pts, 3)
        score += pts

    signing.overall_rating = round(max(0.0, min(10.0, score)), 3)
    signing.sale_fee_eur = sale.get("fee_eur") if sold else None
    signing.sale_fee_known = sale.get("fee_known", False) if sold else False
    signing.sale_to_club_id = sale.get("to_club_id") if sold else None
    signing.sale_date_iso = sale.get("season") if sold else None
    signing._breakdown = breakdown          # type: ignore[attr-defined]
    signing._sold = sold                    # type: ignore[attr-defined]

    # Longevity: reward sustained success. A transfer that was a regular
    # (>= SUCCESS_MINUTES_SHARE) for several seasons carries more weight in the
    # club/window aggregates than a one-season success (the /10 score is unchanged).
    n_success = sum(1 for e in evals
                    if (e.get("minutes_share") or 0) >= SUCCESS_MINUTES_SHARE)
    mult = min(1.0 + LONGEVITY_PER_SEASON * max(0, n_success - 1), LONGEVITY_CAP)
    base_w = 2.0 if signing.is_starter_signing else 1.0
    signing.successful_seasons = n_success
    signing.longevity_multiplier = round(mult, 2)
    signing.weight = round(base_w * mult, 3)
