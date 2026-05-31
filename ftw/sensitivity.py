"""Sensitivity analysis — how stable are the club rankings to the rubric's
hand-set thresholds? For each threshold we re-run the whole analysis at a lower
and higher value and measure (a) the Spearman rank correlation of club ratings
vs the baseline, (b) how many of the top-20 clubs survive, and (c) the shift in
the overall mean. High Spearman / high overlap => conclusions are robust.
"""
from __future__ import annotations

import pandas as pd

import config
from . import analyze as A, classify, scoring
from .dataset import Dataset

# (label, module, attribute, default, [low, high])
PERTURBATIONS = [
    ("Starter minutes share", config, "STARTER_MINUTES_SHARE", 0.65, [0.55, 0.75]),
    ("Efficiency cutoff", scoring, "EFF_CUTOFF", 0.30, [0.20, 0.40]),
    ("Profit pivot (×)", scoring, "STARTER_PIVOT", 2.5, [2.0, 3.0]),
    ("Starter minutes full", scoring, "STARTER_MINUTES_FULL", 0.90, [0.80, 1.00]),
    ("Insignificant fee ratio", A, "INSIGNIFICANT_FEE_RATIO", 0.20, [0.10, 0.30]),
    ("Insignificant minutes", A, "INSIGNIFICANT_MINUTES_SHARE", 0.10, [0.05, 0.15]),
    ("Rotation min age", classify, "ROTATION_MIN_AGE", 24, [23, 26]),
]


def _club_ratings(results: dict, min_n: int = 10) -> dict:
    return {r["club_id"]: r["rating_shrunk"] for r in results["rollups"]["by_club"]
            if r["n_signings"] >= min_n and r["rating_shrunk"] is not None}


def _top(results: dict, n: int = 20) -> list:
    return [r["club_id"] for r in results["rollups"]["by_club"]
            if r["n_signings"] >= 10 and r["rating_shrunk"] is not None][:n]


def run(ds: Dataset, log=print) -> dict:
    base = A.analyze(ds, log=lambda *a, **k: None)
    base_r, base_top = _club_ratings(base), set(_top(base))
    base_mean = base["rollups"]["overall_rating"]
    rows = []
    for label, mod, name, default, values in PERTURBATIONS:
        for v in values:
            setattr(mod, name, v)
            try:
                res = A.analyze(ds, log=lambda *a, **k: None)
            finally:
                setattr(mod, name, default)
            r = _club_ratings(res)
            common = [c for c in base_r if c in r]
            rho = pd.Series([base_r[c] for c in common]).corr(
                pd.Series([r[c] for c in common]), method="spearman")
            overlap = len(base_top & set(_top(res)))
            rows.append({
                "param": label, "value": v, "default": default,
                "spearman": round(float(rho), 3),
                "top20_overlap": overlap,
                "mean": res["rollups"]["overall_rating"],
                "mean_delta": round(res["rollups"]["overall_rating"] - base_mean, 3),
            })
            log(f"  {label}={v}: spearman={rho:.3f} top20={overlap}/20 "
                f"mean Δ{rows[-1]['mean_delta']:+.3f}")
    return {"baseline_mean": base_mean, "rows": rows}


def write_report(result: dict, path) -> None:
    rows = result["rows"]
    by_param: dict = {}
    for r in rows:
        by_param.setdefault(r["param"], []).append(r)
    lines = ["# Sensitivity analysis", "",
             f"Baseline overall mean: **{result['baseline_mean']}/10**. Each threshold "
             "is moved down and up; high Spearman ρ and top-20 overlap mean the club "
             "rankings barely move (robust conclusion).", "",
             "| Threshold | Tested | Spearman ρ vs baseline | Top-20 kept | Mean Δ |",
             "|---|---|---:|---:|---:|"]
    worst = 1.0
    for param, rs in by_param.items():
        for r in rs:
            worst = min(worst, r["spearman"])
            lines.append(f"| {param} | {r['default']}→{r['value']} | {r['spearman']} "
                         f"| {r['top20_overlap']}/20 | {r['mean_delta']:+} |")
    verdict = ("Rankings are **robust** — every perturbation keeps ρ high."
               if worst >= 0.9 else
               "Rankings are **mostly stable**; watch the lower-ρ thresholds."
               if worst >= 0.8 else
               "Some thresholds **move the rankings materially** — treat those conclusions with care.")
    lines += ["", f"Lowest Spearman ρ across all perturbations: **{round(worst,3)}**. {verdict}"]
    path.write_text("\n".join(lines), encoding="utf-8")
