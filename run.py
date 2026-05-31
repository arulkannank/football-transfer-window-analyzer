"""CLI for the football transfer-window analyzer.

Usage:
  python run.py collect [--leagues GB1,ES1] [--workers 6]   # scrape -> data/dataset.pkl
  python run.py analyze                                      # score + write data/output/*
  python run.py all     [--leagues ...] [--workers 6]        # collect then analyze

Resumable: collect uses an on-disk HTTP cache, so re-running continues where it
left off. Output lands in data/output/ (windows.csv, signings.csv, *.json,
summary.md).
"""
from __future__ import annotations

import argparse
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json

import config
from ftw import analyze as analyze_mod
from ftw import collect, report, sensitivity, validity
from ftw.http import DATA_DIR


def _write_validity(ds, results):
    out = validity.run(ds, results)
    (DATA_DIR / "output").mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "output" / "validity.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def _leagues(arg: str | None):
    if not arg:
        return config.LEAGUES
    codes = {c.strip().upper() for c in arg.split(",")}
    return [lg for lg in config.LEAGUES if lg.code in codes]


def cmd_collect(args):
    leagues = _leagues(args.leagues)
    print(f"Collecting {[lg.code for lg in leagues]} with {args.workers} workers...")
    collect.build_dataset(leagues, workers=args.workers)


def cmd_analyze(args):
    ds = collect.load_dataset()
    if ds is None:
        print("No dataset found — run `python run.py collect` first.")
        return
    t0 = time.time()
    results = analyze_mod.analyze(ds)
    report.write_all(ds, results)
    _write_validity(ds, results)
    print(f"Wrote data/output/ in {time.time()-t0:.1f}s. "
          f"Overall mean rating: {results['rollups']['overall_rating']}/10")


def cmd_all(args):
    leagues = _leagues(args.leagues)
    ds = collect.build_dataset(leagues, workers=args.workers)
    results = analyze_mod.analyze(ds)
    report.write_all(ds, results)
    _write_validity(ds, results)
    print(f"Done. Overall mean rating: {results['rollups']['overall_rating']}/10")


def cmd_sensitivity(args):
    ds = collect.load_dataset()
    if ds is None:
        print("No dataset found — run `python run.py collect` first.")
        return
    print("Running sensitivity analysis (re-scores at perturbed thresholds)...")
    result = sensitivity.run(ds)
    sensitivity.write_report(result, DATA_DIR / "output" / "sensitivity.md")
    print("Wrote data/output/sensitivity.md")


def cmd_validity(args):
    ds = collect.load_dataset()
    if ds is None:
        print("No dataset found — run `python run.py collect` first.")
        return
    out = _write_validity(ds, None)
    print(f"corr(recruitment, league position)   = {out['corr_recruitment_vs_position']} "
          f"(negative = better recruitment → better finish)")
    print(f"corr(recruitment, position improved) = {out['corr_recruitment_vs_improvement']} "
          f"(positive = better recruitment → bigger improvement); n={out['n']}")


def main():
    p = argparse.ArgumentParser(description="Football transfer-window analyzer")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--leagues", help="comma-separated codes (default: all)")
        sp.add_argument("--workers", type=int, default=6)
    sub.add_parser("analyze")
    sub.add_parser("sensitivity")
    sub.add_parser("validity")
    args = p.parse_args()
    {"collect": cmd_collect, "analyze": cmd_analyze, "all": cmd_all,
     "sensitivity": cmd_sensitivity, "validity": cmd_validity}[args.cmd](args)


if __name__ == "__main__":
    main()
