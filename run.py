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

import config
from ftw import analyze as analyze_mod
from ftw import collect, report


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
    print(f"Wrote data/output/ in {time.time()-t0:.1f}s. "
          f"Overall mean rating: {results['rollups']['overall_rating']}/10")


def cmd_all(args):
    leagues = _leagues(args.leagues)
    ds = collect.build_dataset(leagues, workers=args.workers)
    results = analyze_mod.analyze(ds)
    report.write_all(ds, results)
    print(f"Done. Overall mean rating: {results['rollups']['overall_rating']}/10")


def main():
    p = argparse.ArgumentParser(description="Football transfer-window analyzer")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--leagues", help="comma-separated codes (default: all)")
        sp.add_argument("--workers", type=int, default=6)
    sub.add_parser("analyze")
    args = p.parse_args()
    {"collect": cmd_collect, "analyze": cmd_analyze, "all": cmd_all}[args.cmd](args)


if __name__ == "__main__":
    main()
