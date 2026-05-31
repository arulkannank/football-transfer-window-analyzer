"""External validity — does recruitment quality actually track league results?

Two levels of evidence:
  1. Raw association: Spearman of recruitment rating vs league finish, and vs the
     change in league position (lower position = better).
  2. Controlled effect: OLS of league position on recruitment rating, controlling
     for spend (log) and the prior-season position, with cluster-robust SEs (club
     -seasons are repeated measures), plus a club fixed-effects version that asks
     whether a club finishes better in the years it recruits better than its own
     norm. A negative recruitment coefficient = better recruitment, better finish.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from . import analyze as A, stats
from .dataset import Dataset


def run(ds: Dataset, results: dict | None = None, log=print) -> dict:
    results = results or A.analyze(ds, log=lambda *a, **k: None, bootstrap=False)
    spend = defaultdict(float)
    for s in results["signings"]:
        if s.fee_known and s.fee_eur:
            spend[(s.club_id, s.season)] += s.fee_eur

    rows = []
    for r in results["rollups"]["by_club_season"]:
        cid, y = r["club_id"], r["season"]
        now = ds.standings.get((cid, y))
        prev = ds.standings.get((cid, y - 1))
        if not now or now.get("position") is None or r["rating"] is None:
            continue
        change = (prev["position"] - now["position"]) if (prev and prev.get("position")) else None
        rows.append({
            "club": r["club"], "club_id": cid, "season": r["season_label"], "league": r["league"],
            "recruitment": r["rating"], "n_signings": r["n_signings"],
            "position": now["position"], "points": now.get("points"),
            "prev_position": prev["position"] if (prev and prev.get("position")) else None,
            "pos_change": change,
            "log_spend": math.log1p(spend.get((cid, y), 0.0) / 1e6),
        })

    rec = [r["recruitment"] for r in rows]
    pos = [r["position"] for r in rows]
    ch_rows = [r for r in rows if r["pos_change"] is not None]
    out = {
        "n": len(rows),
        "corr_recruitment_vs_position": stats.spearman(rec, pos),
        "corr_recruitment_vs_improvement": stats.spearman(
            [r["recruitment"] for r in ch_rows], [r["pos_change"] for r in ch_rows]),
        "n_improvement": len(ch_rows),
        "regression": _regression(rows),
        "data": rows,
    }
    reg = out["regression"]
    log(f"  validity: n={out['n']} corr(rec,pos)={out['corr_recruitment_vs_position']} "
        f"| controlled β(rec)={reg.get('pooled_beta')} (t={reg.get('pooled_t')}), "
        f"FE β(rec)={reg.get('fe_beta')} (t={reg.get('fe_t')})")
    return out


def _regression(rows: list) -> dict:
    """position ~ recruitment + log_spend + prev_position, cluster-robust by club;
    plus a club fixed-effects version. Negative recruitment β = better finish."""
    rs = [r for r in rows if r["prev_position"] is not None]
    if len(rs) < 30:
        return {}
    y = np.array([r["position"] for r in rs], float)
    rec = np.array([r["recruitment"] for r in rs], float)
    spend = np.array([r["log_spend"] for r in rs], float)
    prev = np.array([r["prev_position"] for r in rs], float)
    clusters = np.array([r["club_id"] for r in rs])
    out = {"n": len(rs)}

    # pooled, controlling for spend + prior position
    X = np.column_stack([np.ones(len(rs)), rec, spend, prev])
    beta, se, t = stats.ols_cluster(y, X, clusters)
    out["pooled_beta"] = round(float(beta[1]), 3)
    out["pooled_se"] = round(float(se[1]), 3)
    out["pooled_t"] = round(float(t[1]), 2)

    # club fixed effects (within transform), controlling for spend
    yd = stats.demean_by(y, clusters)
    recd = stats.demean_by(rec, clusters)
    spd = stats.demean_by(spend, clusters)
    Xf = np.column_stack([recd, spd])
    bf, sf, tf = stats.ols_cluster(yd, Xf, clusters)
    out["fe_beta"] = round(float(bf[0]), 3)
    out["fe_se"] = round(float(sf[0]), 3)
    out["fe_t"] = round(float(tf[0]), 2)
    return out
