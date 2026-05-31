"""Emit analysis results as CSV + JSON + a readable markdown summary."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import config
from .http import DATA_DIR
from .dataset import Dataset

OUT_DIR = DATA_DIR / "output"
_LEAGUE = {lg.code: lg.name for lg in config.LEAGUES}


def _lg(code) -> str:
    return _LEAGUE.get(code, code)


def _eur(v) -> str:
    if v is None:
        return ""
    if v >= 1_000_000:
        return f"€{v/1_000_000:.1f}m"
    if v >= 1_000:
        return f"€{v/1_000:.0f}k"
    return f"€{v}"


def write_all(ds: Dataset, results: dict, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    windows = results["windows"]
    signings = results["signings"]
    rollups = results["rollups"]

    # ---- windows.csv ----
    with open(out_dir / "windows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["league", "club", "season", "window", "n_signings", "n_starter",
                    "n_rotation", "window_rating", "window_rating_pre_penalty", "problems",
                    "problems_addressed", "problems_unaddressed", "chronic",
                    "problem_resolution", "window_grade"])
        for r in windows:
            w.writerow([_lg(r["league"]), r["club"], r["season_label"], r["window"],
                        r["n_signings"], r["n_starter"], r["n_rotation"],
                        r["window_rating"], r.get("window_rating_raw"), "|".join(r["problems"]),
                        "|".join(r["problems_addressed"]), "|".join(r["problems_unaddressed"]),
                        "|".join(r["chronic_unaddressed"]), r["problem_resolution"],
                        r["window_grade"]])

    # ---- signings.csv ----
    with open(out_dir / "signings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["league", "club", "season", "window", "player", "group", "type",
                    "weight", "successful_seasons", "longevity_mult", "labels", "fee",
                    "mv_at_purchase", "from_club", "sold",
                    "sale_fee", "seasons_eval", "rating",
                    "minutes", "profit_loss", "rating_imp", "efficiency", "mv_growth"])
        for s in signings:
            b = getattr(s, "_breakdown", {}) or {}
            w.writerow([
                _lg(s.league), ds.club_name.get(s.club_id, s.club_id),
                f"{s.season % 100:02d}/{(s.season+1) % 100:02d}", s.window, s.name,
                s.group, "starter" if s.is_starter_signing else "rotation", s.weight,
                s.successful_seasons, s.longevity_multiplier,
                "|".join(s.classification), _eur(s.fee_eur), _eur(s.mv_at_purchase),
                ds.club_name.get(s.from_club_id or "", s.from_club_id or ""),
                getattr(s, "_sold", False), _eur(s.sale_fee_eur), len(s.season_evals),
                s.overall_rating, b.get("minutes"), b.get("profit_loss"),
                b.get("rating"), b.get("efficiency"), b.get("mv_growth")])

    # ---- full JSON (windows with nested signings) ----
    with open(out_dir / "windows.json", "w", encoding="utf-8") as f:
        json.dump(windows, f, ensure_ascii=False, indent=1)
    with open(out_dir / "rollups.json", "w", encoding="utf-8") as f:
        json.dump(rollups, f, ensure_ascii=False, indent=1)

    _write_markdown(ds, results, out_dir / "summary.md")


def _write_markdown(ds: Dataset, results: dict, path: Path) -> None:
    windows = results["windows"]
    rollups = results["rollups"]
    rated = [w for w in windows if w["window_rating"] is not None]
    rated.sort(key=lambda w: -w["window_rating"])

    lines = ["# Transfer-window analysis 2019/20–2025/26", ""]
    lines.append(f"- Windows analysed (with signings): **{len(rated)}**")
    lines.append(f"- Signings scored: **{len(results['signings'])}**")
    lines.append(f"- Overall mean transfer rating: **{rollups['overall_rating']}/10**")
    lines.append(f"- Empirical-Bayes shrinkage k ≈ **{rollups.get('shrinkage_k')}** "
                 "(estimated from variance components; club identity explains little of the "
                 "signing-to-signing variance, so club ratings carry **wide** bootstrap "
                 "intervals — read small leaderboard gaps with caution).")
    lines.append("")

    lines.append("## League averages (weighted transfer rating /10)")
    lines.append("| League | Signings | Rating |")
    lines.append("|---|---:|---:|")
    for r in rollups["by_league"]:
        lines.append(f"| {_lg(r['league'])} | {r['n_signings']} | {r['rating']} |")
    lines.append("")

    lines.append("> Scale note: every incoming transfer is scored, minutes are 60% of the "
                 "weight, and most signings are squad depth — so window/club means sit low "
                 "in absolute terms. Elite single signings reach 8–10; flops sit near 0.")
    lines.append("")

    MIN_N = 3
    sub = [w for w in rated if w["n_signings"] >= MIN_N]
    lines.append(f"## Best 20 windows (≥{MIN_N} signings)")
    lines.append("| League | Club | Season | Window | N | Rating | Problems addressed |")
    lines.append("|---|---|---|---|---:|---:|---|")
    for w in sub[:20]:
        lines.append(f"| {_lg(w['league'])} | {w['club']} | {w['season_label']} | {w['window']} "
                     f"| {w['n_signings']} | {w['window_rating']} "
                     f"| {','.join(w['problems_addressed']) or '-'} |")
    lines.append("")

    lines.append(f"## Worst 20 windows (≥{MIN_N} signings)")
    lines.append("| League | Club | Season | Window | N | Rating | Unaddressed problems |")
    lines.append("|---|---|---|---|---:|---:|---|")
    for w in sub[-20:][::-1]:
        lines.append(f"| {_lg(w['league'])} | {w['club']} | {w['season_label']} | {w['window']} "
                     f"| {w['n_signings']} | {w['window_rating']} "
                     f"| {','.join(w['problems_unaddressed']) or '-'} |")
    lines.append("")

    sg = results["signings"]

    def table(title, items, note=""):
        lines.append(f"## {title}")
        if note:
            lines.append(f"*{note}*")
        lines.append("| Player | Club | Season | Type | Fee | Sold | Sale | Rating |")
        lines.append("|---|---|---|---|---:|:--:|---:|---:|")
        for s in items:
            lines.append(f"| {s.name} | {ds.club_name.get(s.club_id, s.club_id)} "
                         f"| {s.season % 100:02d}/{(s.season+1) % 100:02d} "
                         f"| {'starter' if s.is_starter_signing else 'rotation'} "
                         f"| {_eur(s.fee_eur)} | {'Y' if getattr(s,'_sold',False) else 'N'} "
                         f"| {_eur(s.sale_fee_eur)} | {s.overall_rating} |")
        lines.append("")

    starters = [s for s in sg if s.is_starter_signing]
    paid = [s for s in sg if s.fee_known and (s.fee_eur or 0) >= 25_000_000]
    sold = [s for s in sg if getattr(s, "_sold", False)]

    # tie-break the saturated 10.0s by fee so meaningful signings surface first
    table("Best 25 starter signings", sorted(
        starters, key=lambda s: (-(s.overall_rating or 0), -(s.fee_eur or 0)))[:25])
    table("Best 20 trades (bought, then sold)", sorted(
        sold, key=lambda s: -(s.overall_rating or 0))[:20],
        note="profit/loss realised — minutes still dominate the score")
    table("Worst 20 big-money signings (fee ≥ €25m)", sorted(
        paid, key=lambda s: (s.overall_rating or 0))[:20])

    path.write_text("\n".join(lines), encoding="utf-8")
