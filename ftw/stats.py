"""Dependency-light statistics helpers (numpy + pandas only — no scipy).

pandas' ``.corr(method="spearman")`` pulls in scipy, which breaks lightweight
deploys; Spearman here is Pearson-on-ranks. Also holds the empirical-Bayes
shrinkage, bootstrap intervals and cluster-robust OLS used by the analysis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def spearman(a, b) -> float | None:
    df = pd.DataFrame({"a": list(a), "b": list(b)}).dropna()
    if len(df) < 3:
        return None
    r = df["a"].rank().corr(df["b"].rank())      # Pearson on ranks -> no scipy
    return None if pd.isna(r) else round(float(r), 3)


# ---- variance components & empirical-Bayes shrinkage -----------------------
def variance_components(groups: list) -> tuple | None:
    """(within_var, between_var, nbar) by method of moments."""
    gs = [np.asarray(g, float) for g in groups if len(g) >= 2]
    if len(gs) < 3:
        return None
    within = float(np.mean([np.var(g, ddof=1) for g in gs]))
    means = np.array([g.mean() for g in gs])
    nbar = float(np.mean([len(g) for g in gs]))
    between = float(np.var(means, ddof=1) - within / nbar)
    return within, between, nbar


def estimate_shrinkage_k(groups: list, default: float = 20.0,
                         lo: float = 2.0, hi: float = 200.0) -> float:
    """EB shrinkage strength k = within-var / between-var (James–Stein flavour)."""
    vc = variance_components(groups)
    if not vc:
        return default
    within, between, _ = vc
    if between <= 1e-6:
        return hi
    return float(min(hi, max(lo, within / between)))


def shrink(raw, weight: float, prior, k: float):
    """Pull `raw` toward `prior` by k pseudo-observations."""
    if raw is None or prior is None:
        return raw
    return round((weight * raw + k * prior) / (weight + k), 3)


def bootstrap_club_intervals(arrays: dict, weights: dict, club_prior: dict,
                             k: float, eligible: set, B: int = 300,
                             seed: int = 0) -> dict:
    """Per-club 95% CI on the shrunk rating + rank CI among `eligible` clubs.

    Resamples each club's signings with replacement; deterministic (seeded) so
    results are cache-stable.
    """
    rng = np.random.default_rng(seed)
    clubs = list(arrays)
    boot = {c: np.empty(B) for c in clubs}
    elig = [c for c in eligible if c in arrays]
    ranks = {c: np.empty(B) for c in elig}
    for b in range(B):
        shr = {}
        for c in clubs:
            a, w = arrays[c], weights[c]
            idx = rng.integers(0, len(a), len(a))
            wa = w[idx]
            tot = wa.sum()
            raw = float((a[idx] * wa).sum() / tot) if tot else 0.0
            shr[c] = (tot * raw + k * club_prior[c]) / (tot + k)
            boot[c][b] = shr[c]
        for rank, c in enumerate(sorted(elig, key=lambda c: -shr[c]), 1):
            ranks[c][b] = rank
    out = {}
    for c in clubs:
        lo, hi = np.percentile(boot[c], [2.5, 97.5])
        out[c] = {"lo": round(float(lo), 2), "hi": round(float(hi), 2)}
        if c in ranks:
            rlo, rhi = np.percentile(ranks[c], [2.5, 97.5])
            out[c]["rank_lo"], out[c]["rank_hi"] = int(round(rlo)), int(round(rhi))
    return out


# ---- regression: cluster-robust OLS + fixed-effects ------------------------
def ols_cluster(y, X, clusters) -> tuple:
    """OLS with CR1 cluster-robust SEs. X includes an intercept column.
    Returns (beta, se, t) arrays."""
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    clusters = np.asarray(clusters)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    n, kk = X.shape
    meat = np.zeros((kk, kk))
    uniq = pd.unique(clusters)
    for c in uniq:
        m = clusters == c
        s = X[m].T @ resid[m]
        meat += np.outer(s, s)
    g = len(uniq)
    adj = (g / (g - 1)) * ((n - 1) / (n - kk)) if g > 1 and n > kk else 1.0
    vcov = adj * (XtX_inv @ meat @ XtX_inv)
    se = np.sqrt(np.clip(np.diag(vcov), 0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, np.nan)
    return beta, se, t


def demean_by(values, groups) -> np.ndarray:
    """Within (fixed-effects) transform: subtract each group's mean."""
    df = pd.DataFrame({"v": list(values), "g": list(groups)})
    return (df["v"] - df.groupby("g")["v"].transform("mean")).to_numpy()
