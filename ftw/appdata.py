"""Pure (Streamlit-free) helpers that turn analysis results into tidy DataFrames
for the app. Kept separate so they're easy to test and cache."""
from __future__ import annotations

import pandas as pd

from . import util
from .dataset import Dataset


def signings_df(results: dict, ds: Dataset) -> pd.DataFrame:
    """One row per scored signing, with its parent-window metadata flattened in."""
    rows = []
    for w in results["windows"]:
        for s in w["signings"]:
            b = s.get("breakdown") or {}
            rows.append({
                "club_id": w["club_id"], "club": w["club"], "league": w["league"],
                "season": w["season"], "season_label": w["season_label"],
                "window": w["window"], "pid": s["pid"], "player": s["name"],
                "group": s["group"], "type": s["type"], "weight": s["weight"],
                "successful_seasons": s.get("successful_seasons"),
                "longevity_multiplier": s.get("longevity_multiplier"),
                "labels": ", ".join(s.get("labels", [])),
                "fee_eur": s.get("fee_eur"), "is_free": s.get("is_free"),
                "mv_at_purchase": s.get("mv_at_purchase"),
                "from_club": s.get("from_club"),
                "sold": bool(s.get("sold")), "sale_fee_eur": s.get("sale_fee_eur"),
                "seasons_evaluated": s.get("seasons_evaluated"),
                "rating": s.get("rating"),
                "fee_confidence": s.get("fee_confidence", "known"),
                "sc_minutes": b.get("minutes"), "sc_profit_loss": b.get("profit_loss"),
                "sc_rating": b.get("rating"), "sc_efficiency": b.get("efficiency"),
                "sc_mv_growth": b.get("mv_growth"),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["fee_m"] = df["fee_eur"].fillna(0) / 1e6
        df["sale_m"] = df["sale_fee_eur"].fillna(0) / 1e6
        df["mv_m"] = df["mv_at_purchase"].fillna(0) / 1e6
        df["profit_m"] = df.apply(
            lambda r: (r["sale_m"] - r["fee_m"]) if r["sold"] else None, axis=1)
    return df


def windows_df(results: dict) -> pd.DataFrame:
    rows = []
    for w in results["windows"]:
        rows.append({
            "club_id": w["club_id"], "club": w["club"], "league": w["league"],
            "season": w["season"], "season_label": w["season_label"],
            "window": w["window"], "n_signings": w["n_signings"],
            "n_starter": w["n_starter"], "n_rotation": w["n_rotation"],
            "window_rating": w["window_rating"],
            "window_rating_shrunk": w.get("window_rating_shrunk"),
            "problems": ", ".join(w["problems"]),
            "problems_addressed": ", ".join(w["problems_addressed"]),
            "problems_unaddressed": ", ".join(w["problems_unaddressed"]),
            "chronic": ", ".join(w["chronic_unaddressed"]),
            "problem_resolution": w["problem_resolution"],
            "window_grade": w["window_grade"],
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["order"] = df["season"] + df["window"].map({"summer": 0.0, "winter": 0.5})
    return df


def club_index(results: dict, ds: Dataset) -> pd.DataFrame:
    """One row per club: name, league(s), n, raw + shrunk rating, rank.

    Ratings come from the rollup (single source of truth, already shrunk)."""
    leagues: dict[str, set] = {}
    for s in results["signings"]:
        if s.league:
            leagues.setdefault(s.club_id, set()).add(s.league)
    keep = ("lo", "hi", "rank_lo", "rank_hi", "hit_rate", "quality_given_hit", "median")
    rows = []
    for r in results["rollups"]["by_club"]:
        cid = r["club_id"]
        row = {
            "club_id": cid, "club": r["club"],
            "leagues": ", ".join(sorted(leagues.get(cid, []))),
            "n_signings": r["n_signings"], "rating": r["rating"],
            "rating_shrunk": r["rating_shrunk"],
        }
        row.update({key: r.get(key) for key in keep})
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("rating_shrunk", ascending=False).reset_index(drop=True)
    df["rank"] = df["rating_shrunk"].rank(ascending=False, method="min").astype("Int64")
    return df


def club_problem_summary(wdf: pd.DataFrame, club_id: str) -> dict:
    sub = wdf[wdf["club_id"] == club_id]
    flagged = addressed = chronic = 0
    for _, r in sub.iterrows():
        probs = [p for p in r["problems"].split(", ") if p]
        addr = [p for p in r["problems_addressed"].split(", ") if p]
        chro = [p for p in r["chronic"].split(", ") if p]
        flagged += len(probs)
        addressed += len(addr)
        chronic += len(chro)
    return {"flagged": flagged, "addressed": addressed, "chronic": chronic}
