"""Collection orchestration: scrape Transfermarkt + SofaScore into a Dataset.

Resumable via the HTTP disk cache (only cache misses hit the network). Per-club
work is fanned out over a small thread pool, each thread owning its own Client.
The Dataset is mutated only on the main thread.
"""
from __future__ import annotations

import pickle
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config
from . import sofa, tm, util
from .dataset import Dataset
from .http import DATA_DIR
from .problems import GROUPS

# Season ranges per data type (start years). Windows scored: 2019..2025.
CLUB_SEASONS = list(range(2017, 2026))    # club lists + tables (incl. MV baselines)
PERF_SEASONS = set(range(2018, 2026))     # minutes/age/position (Y-1 baseline..spell)
KADER_SEASONS = set(range(2017, 2026))    # market value (incl. Y-2 decline baseline)
TRANSFER_SEASONS = set(range(2019, 2026)) # transfer windows scored
RATING_SEASONS = set(range(2018, 2026))   # SofaScore ratings

WINDOW_SEASONS = list(range(2019, 2026))
DATASET_PATH = DATA_DIR / "dataset.pkl"

_local = threading.local()


def _client() -> "tm.Client":
    c = getattr(_local, "tm", None)
    if c is None:
        from .http import Client
        c = Client("tm", referer="https://www.transfermarkt.com/", verbose=False)
        _local.tm = c
    return c


def _scrape_club(league, season: int, club: dict) -> dict:
    c = _client()
    cid, slug = club["club_id"], club["slug"]
    res: dict = {"club": club, "league": league.code, "season": season}
    if season in PERF_SEASONS:
        res["roster"] = tm.club_performance(c, league, cid, slug, season)
    if season in KADER_SEASONS:
        res["squad_mv"] = tm.club_squad_values(c, cid, slug, season)
    if season in TRANSFER_SEASONS:
        res["transfers"] = {
            w: tm.club_transfers(c, league, cid, slug, season, window=w)
            for w in config.WINDOWS
        }
    return res


def _store_club(ds: Dataset, res: dict) -> None:
    club, season = res["club"], res["season"]
    cid = club["club_id"]
    ds.club_name[cid] = club["name"]
    ds.club_slug[cid] = club["slug"]
    ds.club_league[(cid, season)] = res["league"]
    if "roster" in res:
        ds.rosters[(cid, season)] = res["roster"]
    if "squad_mv" in res:
        ds.squad_mv[(cid, season)] = res["squad_mv"]
    if "transfers" in res:
        for w, tr in res["transfers"].items():
            ds.transfers[(cid, season, w)] = tr
            for d in tr.get("departures", []):
                ds.departures_by_pid.setdefault(d["pid"], []).append({
                    "club_id": cid, "season": season, "window": w,
                    "fee_eur": d["fee"].get("eur"), "fee_known": d["fee"].get("known"),
                    "is_loan": d["fee"].get("loan"), "mv": d.get("mv_at"),
                    "group": d.get("group"),
                    "to_club_id": d.get("counterpart_club_id"),
                })


def _compute_pos_rating_avg(ds: Dataset, league_code: str, season: int) -> None:
    """Minutes-weighted league average rating per position group."""
    acc: dict[str, list[float]] = {g: [0.0, 0.0] for g in GROUPS}  # [num, den]
    for (cid, s), roster in ds.rosters.items():
        if s != season or ds.club_league.get((cid, s)) != league_code:
            continue
        cname = ds.club_name.get(cid, "")
        for p in roster:
            if p.minutes <= 0:
                continue
            r = ds.rating(league_code, season, p.name, cname)
            if r is None:
                continue
            acc[p.group][0] += r * p.minutes
            acc[p.group][1] += p.minutes
    for g, (num, den) in acc.items():
        if den > 0:
            ds.pos_rating_avg[(league_code, season, g)] = round(num / den, 3)


def build_dataset(leagues=None, *, workers: int = 4, save: bool = True,
                  log=print) -> Dataset:
    leagues = leagues or config.LEAGUES
    ds = Dataset(seasons=WINDOW_SEASONS)
    sofa_client = sofa.make_client(verbose=False)
    t0 = time.time()

    for league in leagues:
        log(f"\n=== {league.name} ({league.code}) ===")
        # ---- league lists + tables + ratings per season ----
        season_clubs: dict[int, list[dict]] = {}
        lc = _client()
        for season in CLUB_SEASONS:
            clubs = tm.league_clubs(lc, league, season)
            season_clubs[season] = clubs
            ds.clubs[(league.code, season)] = clubs
            ds.matches.update({(cid, season): m
                               for cid, m in tm.league_matches(lc, league, season).items()})
            if season in RATING_SEASONS:
                sid = sofa.tournament_season_id(sofa_client, league.sofa_tournament_id, season)
                if sid:
                    ratings = sofa.league_ratings(sofa_client, league.sofa_tournament_id, sid)
                    ds.ratings_index[(league.code, season)] = sofa.build_rating_index(ratings)
            log(f"  {util.season_label(season)}: "
                f"{len(clubs)} clubs"
                + ("" if season not in RATING_SEASONS else
                   f", {len(ds.ratings_index.get((league.code, season), {}))} rated"))

        # ---- per-club fan-out ----
        tasks = [(league, season, club)
                 for season in CLUB_SEASONS for club in season_clubs[season]]
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_scrape_club, lg, s, cl): (s, cl) for lg, s, cl in tasks}
            for fut in as_completed(futs):
                res = fut.result()
                _store_club(ds, res)
                done += 1
                if done % 25 == 0:
                    log(f"  scraped {done}/{len(tasks)} club-seasons "
                        f"({time.time()-t0:.0f}s)")

        # ---- league position-rating averages ----
        for season in RATING_SEASONS:
            _compute_pos_rating_avg(ds, league.code, season)

        if save:
            save_dataset(ds)
            log(f"  checkpoint saved ({time.time()-t0:.0f}s elapsed)")

    log(f"\nCollection complete in {time.time()-t0:.0f}s. "
        f"Clubs:{len(ds.club_name)} rosters:{len(ds.rosters)} "
        f"transfers:{len(ds.transfers)} ratings:{len(ds.ratings_index)}")
    if save:
        save_dataset(ds)
    return ds


def save_dataset(ds: Dataset, path: Path = DATASET_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(ds, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)


def load_dataset(path: Path = DATASET_PATH) -> Dataset | None:
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)
