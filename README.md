# Football Transfer-Window Analyzer (2019/20 → 2025/26)

Scrapes **Transfermarkt** (squads, minutes, ages, market values, transfers) and
**SofaScore** (player season ratings) for the top-7 European leagues, detects each
club's problem positions per window, classifies every incoming transfer, scores it
out of 10 across its successive seasons at the club, and aggregates to a grade per
transfer window.

## Quick start

```bash
pip install -r requirements.txt                        # curl_cffi bypasses TLS fingerprinting
python run.py all                                      # scrape everything + score (long!)
# or split the steps:
python run.py collect --leagues GB1 --workers 6        # scrape one league -> data/dataset.pkl
python run.py analyze                                  # score + write data/output/

streamlit run app.py                                   # interactive per-club report
```

## Streamlit app (`app.py`)

`streamlit run app.py` opens an interactive report. Pick a league + club in the
sidebar and you get: average transfer rating (with league rank & vs-league
delta), **best/worst signing**, **best/worst window**, spend / recouped / net
spend, and tabs for —

- **Overview**: rating-by-season trend, signings-by-type, spend-vs-rating scatter.
- **Signings**: every signing with its full sub-score breakdown (sortable).
- **Windows**: window-rating timeline + problem resolution / blended grade.
- **Trading**: profit/loss on players bought and later sold.
- **Squad problems**: flagged vs addressed vs chronic problem positions per window.
- **By position**: rating and spend split by GK/DEF/MID/FWD.

Needs `data/dataset.pkl` (created by `python run.py collect`; bundled in this repo).

## Deploy on Streamlit Community Cloud

The repo is deploy-ready — `app.py` at the root, `requirements.txt`, and the
bundled `data/dataset.pkl` (so no scraping happens in the cloud).

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. **Create app → Deploy a public app from GitHub**.
3. Repository `arulkannank/football-transfer-window-analyzer`, branch `main`,
   main file `app.py`. (Optional: Advanced settings → Python 3.12.)
4. **Deploy.** The first build installs the requirements (a few minutes); the app
   then loads the bundled dataset and runs. You'll get a public
   `*.streamlit.app` URL.

To refresh the data later: `python run.py collect && python run.py analyze`, then
commit the updated `data/dataset.pkl` and push — Streamlit redeploys on push.

Scope is set in [config.py](config.py): `LEAGUES`, `SEASONS` (2019/20–2025/26),
weights and thresholds. The on-disk HTTP cache (`data/cache/`) makes every run
resumable — only cache misses hit the network.

## Outputs (`data/output/`)

| File | Contents |
|---|---|
| `windows.csv` | one row per club-season-window: rating, problems, resolution, grade |
| `signings.csv` | one row per scored transfer with the full sub-score breakdown |
| `windows.json` | the same, nested, with per-season evaluations |
| `rollups.json` | overall / by-league / by-club / by-club-season ratings |
| `summary.md` | best/worst windows, league averages, standout signings |

## How it works

### Data sources (all cached)
- League → clubs, league table (per-club matches → minutes denominator).
- Per club-season **performance** page → minutes, age, position.
- Per club-season **kader** page → historical market value per player.
- Per club-season **transfers** page, filtered by window (`w_s=s/w`) → arrivals &
  departures with fee + market value at the time.
- **SofaScore** season statistics → per-player average rating; minutes-weighted
  league averages per position group are derived from matched players.

### Problem-position detection (diagnosed on the *previous* season)
A position group is **flagged** when no single player reached
`STARTER_MINUTES_SHARE` (65%) of the club's available league minutes. Three
validation layers raise severity / confirm it:
1. **rating** — the group's avg rating trails the league avg for that position;
2. **value** — the group's total market value fell > `DECLINING_VALUE_PCT` YoY;
3. **age** — the most-used player in the group is older than 33 (lightest weight).

### Transfer classification
Labels (a signing can have several): `addresses_problem`, `improves_problem`
(weaker-than-average position), `replaces_sold` (same group as a player sold),
`significant_outlay` (> 1.25× the club's average spend/transfer), `rotation_option`
(> 26 y/o, non-problem area, < 0.5× avg spend). The **rubric bucket** is
*starter-type* (weight **2**) unless the signing is a clear low-investment depth
buy, which is *rotation-type* (weight **1**).

### Per-transfer score (/10)
Evaluated for every season the player is at the club, then averaged.

**Starter — if eventually sold:** minutes 6 · profit/loss 2 · rating-improvement 1
· market-efficiency 0.5 · market-value-growth 0.5.
**Starter — if not sold:** the 2 profit/loss points are redistributed exactly as
specified → minutes 6.5 · rating 1.5 · mv-growth 1.5 · efficiency 0.5.

- **Minutes**: ≥ 90% of available minutes → full; linear below (rotation: ≥ 40%).
- **Profit/Loss** (at sale): sold for ≥ 2.5× cost → full 2/2, linear down through
  break-even (can go negative); 5× / 10× add a +0.25 / +0.5 bonus (rotation: ≥ 1×
  cost → full, proportional below).
- **Rating improvement**: player's season rating − league average for the position;
  +1.0 → full (rotation: ≥ 0 → full), proportional/negative below.
- **Market efficiency**: discount/premium vs market value at purchase (and sale);
  bought ≥ 30% below value → full, paying ≥ 30% over → −full.
- **Market-value growth**: MV at end of each season vs MV at purchase, same
  2.5×/5×/10× structure as profit/loss (rotation: maintained value → full).

Missing components (e.g. no rating match) are dropped and their weight is
redistributed proportionally, so a player isn't penalised for missing data.

### Aggregation
Window rating = weighted mean of its signings (starter ×2, rotation ×1). A
secondary `window_grade` blends recruitment with problem-resolution
(`META_*` weights + a chronic-problem penalty for problems left unaddressed across
consecutive windows). Ratings roll up to club-season, club and league.

## Interpretation decisions (tunable)

The brief left several choices open; these are the defaults chosen, all easy to
change in `config.py` / the scoring module:

- **Minutes denominator** = each club's *actual* league matches × 90 (handles
  COVID-curtailed 2019/20 and Ligue 1's 20→18 resize), not a fixed 38/34.
- **"Available minutes"** counts **league** minutes only (cleanest denominator).
- **Rating baseline for "improvement"** = the league's minutes-weighted average
  rating for that position group that season.
- **Market efficiency cutoff** = ±30% vs market value for full ±credit.
- **Average spend per transfer** = club's total fees ÷ number of incoming
  transfers (frees count as €0), over the whole period.
- **All loan deals**, **players under 18**, and **youth promotions** are excluded
  from scoring (loan-outs also don't count as a sale to be "replaced").
- **Insignificant buys are dropped**: a signing for < 0.2× the club's average
  spend who also played < 10% of available minutes over his spell is treated as
  squad-filler noise and excluded.
- **Cost basis** for profit/loss = the transfer fee; if unknown, market value at
  purchase is used as a proxy.
- A club **relegated out of the top-7** loses data coverage; that player's spell is
  evaluated only over the seasons we can see.
```
