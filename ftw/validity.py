"""External validity — does recruitment quality actually track league results?

For each club-season we pair the recruitment rating (weighted mean of that
season's signings) with the club's league finish that season, and with its
change in league position vs the previous season. Spearman correlations tell us
whether the model's verdicts line up with what happened on the pitch.

Convention: league position is "lower = better", so a NEGATIVE recruitment↔
position correlation and a POSITIVE recruitment↔improvement correlation both mean
"better recruitment → better results".
"""
from __future__ import annotations

import pandas as pd

from . import analyze as A
from .dataset import Dataset


def run(ds: Dataset, results: dict | None = None, log=print) -> dict:
    results = results or A.analyze(ds, log=lambda *a, **k: None)
    rows = []
    for r in results["rollups"]["by_club_season"]:
        cid, y = r["club_id"], r["season"]
        now = ds.standings.get((cid, y))
        prev = ds.standings.get((cid, y - 1))
        if not now or now.get("position") is None or r["rating"] is None:
            continue
        change = (prev["position"] - now["position"]) if (prev and prev.get("position")) else None
        rows.append({
            "club": r["club"], "season": r["season_label"], "league": r["league"],
            "recruitment": r["rating"], "n_signings": r["n_signings"],
            "position": now["position"], "points": now.get("points"),
            "pos_change": change,
        })
    df = pd.DataFrame(rows)
    out = {"n": len(df), "data": rows,
           "corr_recruitment_vs_position": None,
           "corr_recruitment_vs_improvement": None, "n_improvement": 0}
    if len(df) > 5:
        out["corr_recruitment_vs_position"] = round(
            float(df["recruitment"].corr(df["position"], method="spearman")), 3)
        ch = df.dropna(subset=["pos_change"])
        out["n_improvement"] = len(ch)
        if len(ch) > 5:
            out["corr_recruitment_vs_improvement"] = round(
                float(ch["recruitment"].corr(ch["pos_change"], method="spearman")), 3)
    log(f"  validity: n={out['n']} corr(recruitment,position)="
        f"{out['corr_recruitment_vs_position']} "
        f"corr(recruitment,improvement)={out['corr_recruitment_vs_improvement']}")
    return out
