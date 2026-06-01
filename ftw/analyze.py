"""Analysis orchestration: turn a Dataset into scored signings and window grades.

Flow per (club, season, window):
  detect problems -> build signings from arrivals -> classify -> score ->
  aggregate to a weighted window rating (starter x2, rotation x1).
Window grades roll up to club-season, club and league, and a secondary
'window_grade' blends recruitment with problem resolution (config META weights,
chronic-problem penalty).
"""
from __future__ import annotations

import numpy as np

import config
from . import classify, problems, scoring, stats, util
from .dataset import Dataset
from .models import Signing

HIT_THRESHOLD = 5.0   # a signing "hits" (contributes meaningfully) at rating >= 5

# Reserve/academy-team name markers used to spot an internal promotion.
_RESERVE_MARKERS = ("castilla", "atletic", "u23", "u21", "u20", "u19", "u18", "u17",
                    "sub-23", "sub-21", "youth", "jugend", "juvenil", "reserve",
                    " ii", "yth", "academy", "b-team", "b ii")
_DROP_TOKENS = {"fc", "cf", "ac", "afc", "sc", "ssc", "as", "rc", "rcd", "ud", "cd",
                "club", "de", "real", "ii", "b", "u21", "u19", "u23", "u18", "u20", "sad"}


def is_internal_promotion(from_name: str | None, club_name: str | None) -> bool:
    """A player promoted from the club's OWN reserve/academy team (e.g. Real Madrid
    Castilla, FC Barcelona Atlètic, 'Man City U21') — not a market transfer."""
    if not from_name or not club_name:
        return False
    f, c = util.norm_name(from_name), util.norm_name(club_name)
    if not f or not c:
        return False
    if c in f or f in c:                       # parent name embedded in the reserve name
        return True
    if any(m in (" " + from_name.lower() + " ") for m in _RESERVE_MARKERS):
        ctoks = set(c.split()) - _DROP_TOKENS
        ftoks = set(f.split()) - _DROP_TOKENS
        if ctoks and ftoks and (ctoks & ftoks):
            return True
    return False


def _make_signing(ds: Dataset, club_id: str, season: int, window: str,
                  arrival: dict) -> Signing | None:
    fee = arrival.get("fee", {})
    # ignore all loan deals (paid or free) and players under 18
    if fee.get("loan"):
        return None
    age = arrival.get("age")
    if age is not None and age < 18:
        return None
    # ignore promotions from the club's own reserve/academy team
    if is_internal_promotion(arrival.get("counterpart_club_name"),
                             ds.club_name.get(club_id)):
        return None
    # skip undocumented returns (no fee, no value or selling club)
    if not fee.get("known") and not (arrival.get("mv_at") and arrival.get("counterpart_club_id")):
        return None
    pid = arrival["pid"]
    role = ds.player_in_roster(pid, club_id, season)
    group = role.group if role else arrival.get("group", "MID")
    league = ds.club_league.get((club_id, season)) or arrival.get("league")
    return Signing(
        pid=pid, name=arrival.get("name", ""), position=arrival.get("position", ""),
        group=group, age_at_signing=arrival.get("age"), club_id=club_id,
        league=league, season=season, window=window,
        fee_eur=fee.get("eur"), fee_known=bool(fee.get("known")),
        is_loan=bool(fee.get("loan")), is_free=bool(fee.get("free")),
        mv_at_purchase=arrival.get("mv_at"), from_club_id=arrival.get("counterpart_club_id"),
        date_iso=None,
    )


INSIGNIFICANT_FEE_RATIO = 0.20       # < 0.2x the club's average spend
INSIGNIFICANT_MINUTES_SHARE = 0.10   # and < 10% of available minutes -> ignore


def _insignificant(s: Signing, avg_spend: float | None) -> bool:
    """A cheap buy (< 0.2x avg spend) who barely played (< 10% of available
    minutes over his spell) is squad-filler noise -> drop it."""
    if not s.fee_known or s.fee_eur is None or not avg_spend or avg_spend <= 0:
        return False
    if s.fee_eur >= INSIGNIFICANT_FEE_RATIO * avg_spend:
        return False
    total_min = sum(e["minutes"] for e in s.season_evals)
    total_avail = sum(e["available"] for e in s.season_evals)
    share = (total_min / total_avail) if total_avail else 0.0
    return share < INSIGNIFICANT_MINUTES_SHARE


def _unrated(s: Signing) -> bool:
    """No SofaScore rating in any spell season -> excluded (not redistributed)."""
    return not any(e.get("player_rating") is not None for e in s.season_evals)


def compute_starter_baselines(ds: Dataset, starter_share: float | None = None) -> dict:
    """Per (league, season, slot) average rating over STARTERS only.

    A "starter" reached `starter_share` of available minutes. This is a higher,
    more discriminating bar than averaging every squad player, so "rating
    improvement" only rewards beating a genuine starter. Falls back to the
    all-players average for a slot that happens to have no qualifying starter.
    """
    thr = config.STARTER_MINUTES_SHARE if starter_share is None else starter_share
    starter: dict = {}   # key -> [num, den]
    allp: dict = {}
    for (cid, s), roster in ds.rosters.items():
        lg = ds.club_league.get((cid, s))
        if not lg or (lg, s) not in ds.ratings_index:
            continue
        avail = ds.available_minutes(cid, s, lg)
        cname = ds.club_name.get(cid, "")
        for p in roster:
            if p.minutes <= 0 or not avail:
                continue
            r = ds.rating(lg, s, p.name, cname)
            if r is None:
                continue
            key = (lg, s, p.group)
            a = allp.setdefault(key, [0.0, 0.0])
            a[0] += r * p.minutes
            a[1] += p.minutes
            if p.minutes / avail >= thr:
                b = starter.setdefault(key, [0.0, 0.0])
                b[0] += r * p.minutes
                b[1] += p.minutes
    out = {}
    for key, (num, den) in allp.items():
        sn, sd = starter.get(key, [0.0, 0.0])
        out[key] = round((sn / sd) if sd > 0 else (num / den), 3)
    return out


# Value weighting: a cheap signing that succeeds, or an expensive one that flops,
# matters more for judging recruitment. "Cheapness/expensiveness" is judged vs a
# blend of the club's and the league's average spend; success/flop is vs the league
# average rating. The multiplier amplifies the two surprising quadrants.
VALUE_REWARD_K = 0.5
VALUE_PENALTY_K = 0.5
VALUE_MULT_CAP = 2.0


def _league_avg_spend(ds: Dataset) -> dict:
    acc: dict = {}
    for (cid, season, window), tr in ds.transfers.items():
        lg = ds.club_league.get((cid, season))
        if not lg:
            continue
        for a in tr.get("arrivals", []):
            if a.get("fee", {}).get("known"):
                acc.setdefault(lg, []).append(a["fee"].get("eur") or 0)
    return {lg: (sum(v) / len(v)) for lg, v in acc.items() if v}


def _apply_value_weighting(signings: list[Signing], priors: dict,
                           club_avg: dict, league_avg: dict) -> None:
    for s in signings:
        if not s.fee_known or s.fee_eur is None or s.overall_rating is None:
            continue
        avgs = [x for x in (club_avg.get(s.club_id), league_avg.get(s.league)) if x]
        blended = (sum(avgs) / len(avgs)) if avgs else None
        prior = priors.get(s.league)
        if not blended or blended <= 0 or prior is None:
            continue
        e = max(-1.0, min(3.0, (s.fee_eur / blended) - 1.0))   # <0 cheap, >0 expensive
        if s.overall_rating >= prior:                          # success
            mult = 1.0 + VALUE_REWARD_K * max(0.0, -e)         # cheaper -> bigger reward
        else:                                                  # flop
            mult = 1.0 + VALUE_PENALTY_K * max(0.0, e)         # pricier -> bigger penalty
        mult = min(VALUE_MULT_CAP, mult)
        s.value_multiplier = round(mult, 2)
        s.weight = round(s.weight * mult, 3)


def analyze(ds: Dataset, log=print, bootstrap: bool = True) -> dict:
    last_season = max(ds.seasons)
    ds.pos_rating_avg = compute_starter_baselines(ds)   # starter-level baseline
    avg_spend = classify.compute_avg_spend(ds)
    league_spend = _league_avg_spend(ds)
    blocks: list[tuple] = []          # (club_id, season, window, flags, sigs)
    all_signings: list[Signing] = []

    # iterate clubs that appear in any window season
    club_seasons = sorted({(cid, s) for (cid, s, w) in ds.transfers
                           if s in ds.seasons})
    for club_id, season in club_seasons:
        flags = problems.detect(ds, club_id, season)
        sold = classify.departed_groups(ds, club_id, season)
        for window in config.WINDOWS:
            tr = ds.transfers.get((club_id, season, window))
            if not tr:
                continue
            sigs: list[Signing] = []
            for arrival in tr.get("arrivals", []):
                sg = _make_signing(ds, club_id, season, window, arrival)
                if sg is None:
                    continue
                classify.classify(sg, flags, avg_spend.get(club_id), sold)
                scoring.score_signing(ds, sg, last_season)
                if _insignificant(sg, avg_spend.get(club_id)) or _unrated(sg):
                    continue
                sigs.append(sg)
                all_signings.append(sg)
            blocks.append((club_id, season, window, flags, sigs))

    # value weighting (baseline prior from base x longevity weights), then build
    # window records with the FINAL weights
    _apply_value_weighting(all_signings, _league_priors(all_signings),
                           avg_spend, league_spend)
    windows = [_window_record(ds, cid, s, w, sigs, flags)
               for (cid, s, w, flags, sigs) in blocks]

    _apply_chronic(ds, windows)
    priors = _league_priors(all_signings)
    k = _data_driven_k(all_signings)
    rollups = _rollups(ds, windows, all_signings, priors, k, bootstrap=bootstrap)
    club_shrunk = {r["club_id"]: r["rating_shrunk"] for r in rollups["by_club"]}
    _apply_shrinkage(windows, priors, club_shrunk, k)
    log(f"Analyzed {len(all_signings)} signings across {len(windows)} windows "
        f"(shrinkage k≈{k}).")
    return {"windows": windows, "signings": all_signings, "rollups": rollups,
            "league_priors": priors, "shrinkage_k": k}


def _data_driven_k(signings: list[Signing], min_n: int = 5) -> float:
    """Empirical-Bayes shrinkage strength from club-level variance components."""
    byc: dict = {}
    for s in signings:
        byc.setdefault(s.club_id, []).append(s.overall_rating or 0.0)
    groups = [v for v in byc.values() if len(v) >= min_n]
    return round(stats.estimate_shrinkage_k(groups), 1)


def _league_priors(signings: list[Signing]) -> dict:
    """Weighted-mean transfer rating per league (the shrinkage target)."""
    acc: dict = {}
    for s in signings:
        a = acc.setdefault(s.league, [0.0, 0.0])
        a[0] += (s.overall_rating or 0) * s.weight
        a[1] += s.weight
    return {lg: round(num / den, 3) for lg, (num, den) in acc.items() if den}


def _apply_shrinkage(windows: list[dict], priors: dict, club_shrunk: dict, k: float) -> None:
    """Shrink each window toward its club's (already shrunk) level — hierarchical
    partial pooling, so a 1-signing window can't swing on a single player."""
    for w in windows:
        prior = club_shrunk.get(w["club_id"]) or priors.get(w["league"])
        weight = w.get("weight_sum") or (2 * w["n_starter"] + w["n_rotation"])
        w["window_rating_shrunk"] = stats.shrink(w["window_rating"], weight, prior, k)
        w["shrink_target"] = prior
        w["league_prior"] = priors.get(w["league"])


def _weighted(sigs: list[Signing]) -> float | None:
    num = sum((s.overall_rating or 0) * s.weight for s in sigs)
    den = sum(s.weight for s in sigs)
    return round(num / den, 3) if den else None


def _window_record(ds: Dataset, club_id: str, season: int, window: str,
                   sigs: list[Signing], flags) -> dict:
    validated = {g: f for g, f in flags.items() if f.validated}
    problem_groups = {g for g, f in flags.items() if f.is_problem}
    addressed = {s.group for s in sigs if s.addressed_problem}
    return {
        "club_id": club_id, "club": ds.club_name.get(club_id, club_id),
        "league": ds.club_league.get((club_id, season)),
        "season": season, "season_label": util.season_label(season),
        "window": window,
        "n_signings": len(sigs),
        "n_starter": sum(1 for s in sigs if s.is_starter_signing),
        "n_rotation": sum(1 for s in sigs if not s.is_starter_signing),
        "weight_sum": round(sum(s.weight for s in sigs), 2),
        "window_rating": _weighted(sigs),
        "problems": sorted(problem_groups),
        "validated_problems": sorted(validated),
        "problems_addressed": sorted(addressed & problem_groups),
        "problems_unaddressed": sorted(problem_groups - addressed),
        "signings": [_signing_summary(ds, s) for s in sigs],
        "chronic_unaddressed": [],   # filled by _apply_chronic
        "problem_resolution": None,
        "window_grade": None,
    }


def _signing_summary(ds: Dataset, s: Signing) -> dict:
    return {
        "pid": s.pid, "name": s.name, "group": s.group,
        "type": "starter" if s.is_starter_signing else "rotation",
        "weight": s.weight, "successful_seasons": s.successful_seasons,
        "longevity_multiplier": s.longevity_multiplier,
        "value_multiplier": s.value_multiplier, "labels": s.classification,
        "fee_eur": s.fee_eur, "fee_known": s.fee_known, "is_free": s.is_free,
        "mv_at_purchase": s.mv_at_purchase,
        "from_club": ds.club_name.get(s.from_club_id or "", s.from_club_id),
        "sold": getattr(s, "_sold", False),
        "sale_fee_eur": s.sale_fee_eur,
        "rating": s.overall_rating,
        # P&L / efficiency rest on a market-value proxy when the fee is undisclosed
        "fee_confidence": "known" if s.fee_known else "estimated",
        "breakdown": getattr(s, "_breakdown", {}),
        "seasons_evaluated": len(s.season_evals),
        "season_evals": s.season_evals,
    }


def _apply_chronic(ds: Dataset, windows: list[dict]) -> None:
    """Penalise problems left unaddressed for >= CHRONIC_WINDOW_THRESHOLD windows."""
    by_club: dict[str, list[dict]] = {}
    for w in windows:
        by_club.setdefault(w["club_id"], []).append(w)
    for club_id, ws in by_club.items():
        ws.sort(key=lambda w: (w["season"], 0 if w["window"] == "summer" else 1))
        streak: dict[str, int] = {}
        for w in ws:
            unresolved = set(w["validated_problems"]) - set(w["problems_addressed"])
            chronic = []
            for g in w["validated_problems"]:
                if g in unresolved:
                    streak[g] = streak.get(g, 0) + 1
                    if streak[g] >= config.CHRONIC_WINDOW_THRESHOLD:
                        chronic.append(g)
                else:
                    streak[g] = 0
            for g in list(streak):
                if g not in w["validated_problems"]:
                    streak[g] = 0
            w["chronic_unaddressed"] = sorted(chronic)
            # PENALISE the window rating for each chronic unaddressed problem: the
            # club keeps failing to fix a long-standing weakness.
            raw = w["window_rating"]
            w["window_rating_raw"] = raw
            if raw is not None and chronic:
                w["window_rating"] = round(
                    max(0.0, raw - config.CHRONIC_RATING_PENALTY * len(chronic)), 3)
            # problem-resolution sub-score (0..10) and blended window grade
            vp = w["validated_problems"]
            res = (len(w["problems_addressed"]) / len(vp)) if vp else 1.0
            pr = res * 10.0 - config.PENALTY_PER_CHRONIC_POSITION / 10.0 * len(chronic)
            w["problem_resolution"] = round(max(0.0, min(10.0, pr)), 2)
            if raw is not None:                      # grade blends RAW recruitment + resolution
                w["window_grade"] = round(
                    config.META_RECRUITMENT_WEIGHT * raw
                    + config.META_PROBLEM_WEIGHT * w["problem_resolution"], 3)


def _avg(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _tot_weight(sigs: list[Signing]) -> float:
    return sum(s.weight for s in sigs)


def _hit_stats(sigs: list[Signing]) -> dict:
    """Two-part view of a zero-inflated, bimodal score: how often a signing 'hits'
    (rating >= HIT_THRESHOLD) and how good the hits are, plus the median."""
    rs = [s.overall_rating for s in sigs if s.overall_rating is not None]
    if not rs:
        return {"hit_rate": None, "quality_given_hit": None, "median": None}
    hits = [r for r in rs if r >= HIT_THRESHOLD]
    return {
        "hit_rate": round(len(hits) / len(rs), 3),
        "quality_given_hit": round(float(np.mean(hits)), 2) if hits else None,
        "median": round(float(np.median(rs)), 2),
    }


def _rollups(ds: Dataset, windows: list[dict], signings: list[Signing],
             priors: dict, k: float, bootstrap: bool = True) -> dict:
    def pool(sigs):
        return _weighted(sigs)

    by_club_season: dict = {}
    by_club: dict = {}
    by_league: dict = {}
    by_slot: dict = {}
    for s in signings:
        by_club_season.setdefault((s.club_id, s.season), []).append(s)
        by_club.setdefault(s.club_id, []).append(s)
        by_league.setdefault(s.league, []).append(s)
        by_slot.setdefault(s.group, []).append(s)

    def club_league(sigs):                 # the club's (most common) league
        return max(set(x.league for x in sigs), key=[x.league for x in sigs].count)

    club_season_rows = [{
        "club": ds.club_name.get(cid, cid), "club_id": cid, "season": season,
        "season_label": util.season_label(season),
        "league": ds.club_league.get((cid, season)),
        "n_signings": len(sigs), "rating": pool(sigs),
        "rating_shrunk": stats.shrink(pool(sigs), _tot_weight(sigs),
                                      priors.get(ds.club_league.get((cid, season))), k),
        **_hit_stats(sigs),
    } for (cid, season), sigs in by_club_season.items()]
    club_season_rows.sort(key=lambda r: -(r["rating_shrunk"] or 0))

    club_rows = [{
        "club": ds.club_name.get(cid, cid), "club_id": cid, "league": club_league(sigs),
        "n_signings": len(sigs), "rating": pool(sigs),
        "rating_shrunk": stats.shrink(pool(sigs), _tot_weight(sigs),
                                      priors.get(club_league(sigs)), k),
        **_hit_stats(sigs),
    } for cid, sigs in by_club.items()]

    if bootstrap:
        arrays = {cid: np.array([s.overall_rating or 0 for s in sigs])
                  for cid, sigs in by_club.items()}
        weights = {cid: np.array([s.weight for s in sigs])
                   for cid, sigs in by_club.items()}
        club_prior = {cid: priors.get(club_league(sigs)) or 0
                      for cid, sigs in by_club.items()}
        eligible = {cid for cid, sigs in by_club.items() if len(sigs) >= 10}
        ci = stats.bootstrap_club_intervals(arrays, weights, club_prior, k, eligible)
        for r in club_rows:
            r.update(ci.get(r["club_id"], {}))
    club_rows.sort(key=lambda r: -(r["rating_shrunk"] or 0))

    league_rows = sorted(
        [{"league": lg, "n_signings": len(sigs), "rating": pool(sigs)}
         for lg, sigs in by_league.items()],
        key=lambda r: -(r["rating"] or 0))

    # market efficiency by position
    pos_rows = []
    for slot, sigs in by_slot.items():
        fees = [s.fee_eur for s in sigs if s.fee_known and s.fee_eur]
        prem = [(s.mv_at_purchase - s.fee_eur) / s.mv_at_purchase
                for s in sigs if s.fee_known and s.fee_eur and s.mv_at_purchase]
        rats = [s.overall_rating for s in sigs if s.overall_rating is not None]
        avg_fee = (sum(fees) / len(fees)) if fees else 0
        pos_rows.append({
            "slot": slot, "position": config.SLOT_NAMES.get(slot, slot),
            "n_signings": len(sigs),
            "avg_fee_m": round(avg_fee / 1e6, 2),
            "avg_premium_pct": round(100 * sum(prem) / len(prem), 1) if prem else None,
            "avg_rating": round(sum(rats) / len(rats), 2) if rats else None,
            "rating_per_10m": round((sum(rats) / len(rats)) / (avg_fee / 1e7), 2)
            if rats and avg_fee >= 1e6 else None,
        })
    pos_rows.sort(key=lambda r: -(r["avg_premium_pct"] or -999))

    return {
        "overall_rating": pool(signings),
        "by_club_season": club_season_rows,
        "by_club": club_rows,
        "by_league": league_rows,
        "by_position": pos_rows,
        "league_priors": priors,
        "shrinkage_k": k,
    }
