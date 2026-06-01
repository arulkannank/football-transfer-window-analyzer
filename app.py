"""Streamlit app: transfer-window analysis.

Three views: a per-club report, a league-wide leaderboard (with market-efficiency
-by-position and an external-validity check), and a club-vs-club comparison.

Run:  streamlit run app.py   (needs data/dataset.pkl from `python run.py collect`)
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import config
from ftw import analyze as analyze_mod
from ftw import appdata, collect, validity

st.set_page_config(page_title="Transfer Window Analyzer", page_icon="⚽", layout="wide")

SLOT_NAMES = config.SLOT_NAMES
LEAGUE_NAME = {lg.code: lg.name for lg in config.LEAGUES}


def league_label(codes) -> str:
    return ", ".join(LEAGUE_NAME.get(c, c) for c in str(codes).split(", ") if c)


@st.cache_resource(show_spinner="Loading dataset and scoring transfers…")
def load():
    ds = collect.load_dataset()
    if ds is None:
        return None
    results = analyze_mod.analyze(ds, log=lambda *a, **k: None)
    sdf = appdata.signings_df(results, ds)
    wdf = appdata.windows_df(results)
    clubs = appdata.club_index(results, ds)
    val = validity.run(ds, results, log=lambda *a, **k: None)
    return ds, results, sdf, wdf, clubs, val


def fmt_eur(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if abs(v) >= 1e6:
        return f"€{v/1e6:.1f}m"
    if abs(v) >= 1e3:
        return f"€{v/1e3:.0f}k"
    return f"€{v:.0f}"


# ----------------------------------------------------------------------------
data = load()
if data is None:
    st.error("No dataset found. Build it first:  `python run.py collect`")
    st.stop()
ds, results, sdf, wdf, clubs, val = data
priors = results.get("league_priors", {})

st.title("⚽ Transfer Window Analyzer")
st.caption("Top-7 European leagues · 2019/20 – 2025/26 · Transfermarkt + SofaScore")

with st.expander("ℹ️ Column guide — what every column means and why it matters"):
    st.markdown("""
**Scope.** Every incoming transfer is scored **/10**. Excluded: loans, under-18s,
youth & own-academy promotions, players with no rating, and insignificant buys
(< 0.2× avg spend who barely played). Minutes are 60% of the score, so club/window
means sit low in absolute terms — **ranking** is what matters. The **Recruitment
report** (Club view) auto-summarises each club's strengths and weaknesses.

##### Headline metrics (Club report)
| Metric | Meaning / significance |
|---|---|
| **Avg transfer rating** | Weighted mean /10 of the club's signings (starter ×2, rotation ×1, × longevity), **shrunk** toward the league mean. The club rank is by this. |
| **Signings scored** | Number of transfers evaluated after the exclusions above. |
| **Starters / Rotation** | Split by classification (starters carry double weight). |
| **Spend on signings** | Total disclosed fees paid for the scored signings. |
| **Recouped (sold)** | Sale fees received for those later sold. |
| **Net spend** | Spend − Recouped. |

##### Signings table
| Column | Meaning / significance |
|---|---|
| **Season / Window** | When the player was bought (summer or winter window). |
| **Pos** | Formation slot: GK · RB · LB · CB · MID · W (wingers) · CF. |
| **Type** | *starter* (weight 2) or *rotation* (weight 1) in the aggregates. |
| **Classification** | Why it's a starter/rotation: `addresses_problem` (bought into a flagged weak slot), `improves_problem` (slot rated below league), `replaces_sold` (a sold regular), `significant_outlay` (> 1.25× avg spend), `rotation_option` (depth), `squad_addition`. |
| **Fee / MV in** | Fee paid vs Transfermarkt market value at purchase. |
| **Fee conf.** | *known* = disclosed; *estimated* = undisclosed, so P&L & efficiency use a market-value proxy (lower confidence). |
| **Sold / Sale fee** | Whether later sold by the club, and for how much. |
| **Seasons** | Seasons the player was evaluated at the club. |
| **Good szns** | "Successful" seasons (≥ 40% of available minutes). |
| **Longevity×** | Weight multiplier for sustained success: ×1 (one good season) → ×2.5 (four+). Lasting signings count more than one-season hits. |
| **Value×** | Weight multiplier (up to ×2) that amplifies **cheap successes** and **expensive flops** — fee judged vs the club+league average spend — so finding gems lifts the club's rating and overpaying for flops drags it harder. |
| **Rating** | The transfer's /10 score (sum of the sub-scores below). |
| **minutes** | Share of available league minutes, averaged across seasons (max **6**, or 6.5 if never sold). The dominant component. |
| **P/L** | Profit/loss at sale: ≥ 2.5× cost → full **2**; bonuses at 5×/10×; blank (redistributed) if not sold. |
| **rating⁺** | SofaScore rating minus the league **starter** average for that slot (max **1**, or 1.5 if not sold). |
| **effic.** | Fee vs market value at purchase/sale — bought ≥ 30% below value → full **0.5**; overpaying is negative. |
| **mv↑** | Market-value growth vs purchase (max **0.5**, or 1.5 if not sold). |

##### Windows table
| Column | Meaning / significance |
|---|---|
| **N** | Signings made that window. |
| **Pre-pen. → Rating** | Window rating before → after the **chronic penalty** (−0.75 per slot left unaddressed ≥ 2 consecutive windows). |
| **Shrunk** | Rating pulled toward the club's own level (tames 1-signing noise); used for best/worst-window ranking. |
| **Flagged / Addressed / Unaddressed** | Problem slots that window and whether a signing addressed them. |
| **Chronic** | Slots unaddressed for ≥ 2 consecutive windows (each triggers the penalty). |
| **Prob.res** | Problem-resolution sub-score /10 (share of validated problems fixed, minus chronic). |
| **Grade** | Blended recruitment (70%) + problem-resolution (30%). |

##### League leaderboard
| Column | Meaning / significance |
|---|---|
| **Raw → Rating** | Unshrunk weighted rating → **shrunk** rating (toward league mean, by an empirical-Bayes *k* estimated from the data). Rank is by the shrunk value. |
| **95% CI** | Bootstrap confidence interval on the rating. |
| **Rank CI** | Bootstrap 95% interval on the club's league rank — **wide intervals mean clubs aren't statistically separable** (club identity explains only ~3% of signing variance). |
| **Hit rate** | Share of signings scoring ≥ 5/10 — a steadier "how often do they get it right" read of a zero-inflated score. |
| **Median** | Median signing rating. |

##### Market efficiency by position
*Avg discount vs MV (%)* — mean (market value − fee) ÷ market value; **negative = clubs pay above** Transfermarkt value. *Rating per €10m* — average rating bought per €10m of fee (value for money by position).

##### Does recruitment track results?
*β recruitment → position* — regression of league finish on recruitment rating, controlling for spend & prior-season position, cluster-robust by club. **Negative ⇒ better recruitment → better finish.** *β within-club (fixed effects)* — same, differencing out club quality (does a club finish higher in years it recruits better than its own norm?).
""")

view = st.sidebar.radio("View", ["🏟️ Club report", "🏆 League leaderboard", "⚖️ Compare clubs"])
st.sidebar.markdown("---")
st.sidebar.caption("**Reading the scores:** every signing is scored /10 with minutes "
                   "weighted 60%, so club/window means sit low in absolute terms — elite "
                   "single signings reach 8–10, flops near 0. Ranking is what matters. "
                   "Club/window ratings are **shrunk** toward the league mean to tame small "
                   "samples.")


# ============================================================ CLUB REPORT ===
def render_club():
    with st.sidebar:
        codes = sorted(clubs["leagues"].str.split(", ").explode().unique())
        name_to_code = {LEAGUE_NAME.get(c, c): c for c in codes}
        league_pick = st.selectbox("League", ["All leagues"] + list(name_to_code))
        pool = clubs if league_pick == "All leagues" else \
            clubs[clubs["leagues"].str.contains(name_to_code[league_pick], regex=False)]
        names = pool.sort_values("club")["club"].tolist()
        default = names.index("Manchester City") if "Manchester City" in names else 0
        club_name = st.selectbox("Club", names, index=default)

    crow = clubs[clubs["club"] == club_name].iloc[0]
    cid = crow["club_id"]
    cs = sdf[sdf["club_id"] == cid].copy()
    cw = wdf[wdf["club_id"] == cid].copy()
    rated_w = cw[cw["window_rating_shrunk"].notna()]

    st.subheader(f"{club_name}  ·  {league_label(crow['leagues'])}")
    spend = cs.loc[cs["fee_eur"].notna(), "fee_eur"].sum()
    recouped = cs.loc[cs["sold"], "sale_fee_eur"].fillna(0).sum()
    k = st.columns(6)
    ci_txt = (f"; 95% CI {crow['lo']:.1f}–{crow['hi']:.1f}" if pd.notna(crow.get("lo")) else "")
    k[0].metric("Avg transfer rating", f"{crow['rating']}/10",
                help=f"Rank #{int(crow['rank'])} of {len(clubs)} (shrunk rating{ci_txt}). "
                     f"Hit rate {crow.get('hit_rate')} · median {crow.get('median')}")
    k[1].metric("Signings scored", int(crow["n_signings"]))
    k[2].metric("Starters / Rotation",
                f"{int((cs['type']=='starter').sum())} / {int((cs['type']=='rotation').sum())}")
    k[3].metric("Spend on signings", fmt_eur(spend))
    k[4].metric("Recouped (sold)", fmt_eur(recouped))
    k[5].metric("Net spend", fmt_eur(spend - recouped))

    lg = crow["leagues"].split(", ")[0]
    if lg in priors:
        d = round(crow["rating"] - priors[lg], 2)
        st.caption(f"{LEAGUE_NAME.get(lg, lg)} average: **{priors[lg]}/10** · this club is "
                   f"**{'+' if d>=0 else ''}{d}** vs league.")

    st.markdown("### Headlines")
    c1, c2, c3, c4 = st.columns(4)
    best_sig = cs.loc[cs["rating"].idxmax()] if not cs.empty else None
    worst_sig = cs.loc[cs["rating"].idxmin()] if not cs.empty else None
    best_win = rated_w.loc[rated_w["window_rating_shrunk"].idxmax()] if not rated_w.empty else None
    worst_win = rated_w.loc[rated_w["window_rating_shrunk"].idxmin()] if not rated_w.empty else None
    _signing_card(c1, "Best signing", best_sig, True)
    _signing_card(c2, "Worst signing", worst_sig, False)
    _window_card(c3, "Best window", best_win, True)
    _window_card(c4, "Worst window", worst_win, False)

    _strengths_weaknesses(cs, cw, crow)

    t = st.tabs(["📈 Overview", "📋 Signings", "🪟 Windows", "💷 Trading",
                 "🩺 Squad problems", "🧭 By position"])
    with t[0]:
        _overview(cs)
    with t[1]:
        _signings_table(cs)
    with t[2]:
        _windows_tab(cw, rated_w)
    with t[3]:
        _trading_tab(cs)
    with t[4]:
        _problems_tab(cid)
    with t[5]:
        _byposition_tab(cs)


def _compute_sw(cs, cw, prior, blended, by_pos):
    """Return (strengths, weaknesses) bullet strings — dense and data-driven."""
    S, W = [], []
    if cs.empty:
        return S, W
    # position strength / weakness vs the global per-slot average
    grp = (cs.assign(wr=cs["rating"] * cs["weight"]).groupby("group")
           .agg(wr=("wr", "sum"), wt=("weight", "sum"), n=("rating", "size")))
    grp["avg"] = grp["wr"] / grp["wt"]
    best = worst = None
    for slot, r in grp.iterrows():
        if r["n"] >= 3 and slot in by_pos:
            d = r["avg"] - by_pos[slot]
            if best is None or d > best[1]:
                best = (slot, d, r["avg"], r["n"])
            if worst is None or d < worst[1]:
                worst = (slot, d, r["avg"], r["n"])
    if best and best[1] >= 0.6:
        S.append(f"Recruits **{SLOT_NAMES[best[0]]}** well ({best[2]:.1f} vs "
                 f"{by_pos[best[0]]:.1f} league-wide, n={int(best[3])})")
    if worst and worst[1] <= -0.6:
        W.append(f"Struggles in **{SLOT_NAMES[worst[0]]}** ({worst[2]:.1f} vs "
                 f"{by_pos[worst[0]]:.1f}, n={int(worst[3])})")
    # value: cheap successes vs expensive flops
    if blended:
        paid = cs[cs["fee_eur"].notna()]
        gems = paid[(paid["fee_eur"] < blended) & (paid["rating"] >= prior + 2.0)]
        if len(gems) >= 2:
            ex = gems.sort_values("rating", ascending=False).iloc[0]
            S.append(f"**Finds value**: {len(gems)} cheap signings well above par "
                     f"(e.g. {ex['player']} {fmt_eur(ex['fee_eur'])} → {ex['rating']})")
        flops = paid[(paid["fee_eur"] >= 1.5 * blended)
                     & (paid["rating"] <= max(2.5, prior - 1.0))]
        if len(flops) >= 1:
            ex = flops.sort_values("rating").iloc[0]
            W.append(f"**Costly flops**: {len(flops)} big buys underperformed "
                     f"(e.g. {ex['player']} {fmt_eur(ex['fee_eur'])} → {ex['rating']}; "
                     f"€{flops['fee_m'].sum():.0f}m total)")
    # trading
    sold = cs[cs["sold"]]
    if not sold.empty:
        profit = (sold["sale_m"] - sold["fee_m"]).sum()
        if profit >= 20:
            t = sold.assign(p=sold["sale_m"] - sold["fee_m"]).sort_values("p", ascending=False).iloc[0]
            S.append(f"**Trades at a profit**: +€{profit:.0f}m on {len(sold)} resales "
                     f"(e.g. {t['player']} {fmt_eur(t['fee_eur'])}→{fmt_eur(t['sale_fee_eur'])})")
        elif profit <= -20:
            W.append(f"**Loses on resale**: −€{abs(profit):.0f}m across {len(sold)} sales")
    # chronic problems
    chronic = set()
    for c in cw["chronic"].dropna():
        chronic.update(x for x in c.split(", ") if x)
    if chronic:
        W.append("**Never fixed**: " + ", ".join(SLOT_NAMES.get(g, g) for g in sorted(chronic))
                 + " left unaddressed across windows")
    # consistency
    hit = (cs["rating"] >= 5).mean()
    if hit >= 0.45:
        S.append(f"**Consistent**: {hit:.0%} of signings land (≥5/10)")
    elif hit <= 0.25:
        W.append(f"**Hit-and-miss**: only {hit:.0%} of signings land (≥5/10)")
    return S, W


def _strengths_weaknesses(cs, cw, crow):
    lg = crow["leagues"].split(", ")[0]
    prior = priors.get(lg) or results["rollups"]["overall_rating"] or 3.0
    club_avg = cs.loc[cs["fee_eur"].notna(), "fee_eur"].mean()
    league_avg = sdf.loc[(sdf["league"] == lg) & sdf["fee_eur"].notna(), "fee_eur"].mean()
    avgs = [x for x in (club_avg, league_avg) if pd.notna(x) and x > 0]
    blended = (sum(avgs) / len(avgs)) if avgs else None
    by_pos = {p["slot"]: p["avg_rating"] for p in results["rollups"]["by_position"]
              if p["avg_rating"] is not None}
    S, W = _compute_sw(cs, cw, prior, blended, by_pos)
    st.markdown("### 📋 Recruitment report")
    a, b = st.columns(2)
    a.markdown("**💪 Strengths**\n\n" + ("\n".join(f"- {x}" for x in S)
               if S else "- _No standout strengths in range._"))
    b.markdown("**⚠️ Weaknesses**\n\n" + ("\n".join(f"- {x}" for x in W)
               if W else "- _No glaring weaknesses in range._"))


def _signing_card(col, title, row, good):
    with col:
        if row is None:
            col.info(f"**{title}**\n\nn/a")
            return
        col.markdown(f"**{'🟢' if good else '🔴'} {title}**")
        col.markdown(f"### {row['player']}")
        conf = "" if row["fee_confidence"] == "known" else " *(fee est.)*"
        col.markdown(
            f"{row['season_label']} {row['window']} · {row['type']} · "
            f"{SLOT_NAMES.get(row['group'], row['group'])}  \n"
            f"Fee {fmt_eur(row['fee_eur'])}{conf}"
            + (f" → sold {fmt_eur(row['sale_fee_eur'])}" if row["sold"] else "")
            + f"  \n**Rating {row['rating']}/10**")


def _window_card(col, title, row, good):
    with col:
        if row is None:
            col.info(f"**{title}**\n\nn/a")
            return
        col.markdown(f"**{'🟢' if good else '🔴'} {title}**")
        col.markdown(f"### {row['season_label']} {row['window']}")
        probs = row["problems_addressed"] if good else row["problems_unaddressed"]
        col.markdown(
            f"{int(row['n_signings'])} signings · "
            f"{int(row['n_starter'])} starter / {int(row['n_rotation'])} rotation  \n"
            + (f"Addressed: {probs}  \n" if good and probs else "")
            + (f"Unaddressed: {probs}  \n" if (not good) and probs else "")
            + f"**Window rating {row['window_rating_shrunk']}/10**")


def _overview(cs):
    a, b = st.columns(2)
    if not cs.empty:
        ps = (cs.assign(wr=cs["rating"] * cs["weight"])
              .groupby(["season", "season_label"], as_index=False)
              .agg(wr=("wr", "sum"), weight=("weight", "sum"), signings=("rating", "size")))
        ps["rating"] = ps["wr"] / ps["weight"]
        a.markdown("**Average transfer rating by season**")
        a.altair_chart(alt.Chart(ps).mark_line(point=True).encode(
            x=alt.X("season_label:O", title="Season"),
            y=alt.Y("rating:Q", title="Avg rating /10", scale=alt.Scale(domain=[0, 10])),
            tooltip=["season_label", alt.Tooltip("rating:Q", format=".2f"), "signings"]),
            width="stretch")
        tc = cs["type"].value_counts().rename_axis("type").reset_index(name="n")
        b.markdown("**Signings by type**")
        b.altair_chart(alt.Chart(tc).mark_bar().encode(
            x=alt.X("type:N", title=None), y=alt.Y("n:Q", title="Signings"),
            color=alt.Color("type:N", legend=None), tooltip=["type", "n"]), width="stretch")
    paid = cs[cs["fee_m"] > 0]
    if not paid.empty:
        st.markdown("**Spend vs. rating** (hover for detail)")
        st.altair_chart(alt.Chart(paid).mark_circle(opacity=0.7).encode(
            x=alt.X("fee_m:Q", title="Fee (€m)"),
            y=alt.Y("rating:Q", title="Rating /10", scale=alt.Scale(domain=[0, 10])),
            color=alt.Color("type:N", title="Type"),
            size=alt.Size("mv_m:Q", legend=None),
            tooltip=["player", "season_label", "type",
                     alt.Tooltip("fee_m:Q", title="Fee €m", format=".1f"),
                     alt.Tooltip("rating:Q", format=".2f"), "sold"]), width="stretch")


def _signings_table(cs):
    cols = ["season_label", "window", "player", "group", "type", "labels", "fee_eur",
            "fee_confidence", "mv_at_purchase", "sold", "sale_fee_eur",
            "seasons_evaluated", "successful_seasons", "longevity_multiplier",
            "value_multiplier", "rating", "sc_minutes", "sc_profit_loss", "sc_rating",
            "sc_efficiency", "sc_mv_growth"]
    show = cs[cols].sort_values("rating", ascending=False).rename(columns={
        "season_label": "Season", "window": "Window", "player": "Player", "group": "Pos",
        "type": "Type", "labels": "Classification", "fee_eur": "Fee",
        "fee_confidence": "Fee conf.", "mv_at_purchase": "MV in", "sold": "Sold",
        "sale_fee_eur": "Sale fee", "seasons_evaluated": "Seasons",
        "successful_seasons": "Good szns", "longevity_multiplier": "Longevity×",
        "value_multiplier": "Value×", "rating": "Rating", "sc_minutes": "minutes",
        "sc_profit_loss": "P/L", "sc_rating": "rating⁺", "sc_efficiency": "effic.",
        "sc_mv_growth": "mv↑"})
    st.dataframe(show, width="stretch", hide_index=True, column_config={
        "Fee": st.column_config.NumberColumn(format="€%d"),
        "MV in": st.column_config.NumberColumn(format="€%d"),
        "Sale fee": st.column_config.NumberColumn(format="€%d"),
        "Rating": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.2f")})
    st.caption("Sub-scores (minutes/P&L/rating⁺/efficiency/mv↑) are points earned out of "
               "each component's max; they sum to the rating. *Fee conf. = estimated* means "
               "the fee was undisclosed and P&L/efficiency use a market-value proxy. "
               "**Longevity×** weights multi-season successes more (×1 for one good season → "
               "×2.5 for four). **Value×** amplifies cheap successes and expensive flops "
               "(relative to league + club spend), so finding gems / wasting money on flops "
               "moves the club's rating more.")


def _windows_tab(cw, rated_w):
    tl = rated_w.sort_values("order")
    if not tl.empty:
        st.markdown("**Window ratings over time** (shrunk toward league mean)")
        st.altair_chart(alt.Chart(tl).mark_bar().encode(
            x=alt.X("order:O", axis=alt.Axis(labels=False, title="Window (time →)")),
            y=alt.Y("window_rating_shrunk:Q", title="Rating /10", scale=alt.Scale(domain=[0, 10])),
            color=alt.Color("window:N", title="Window"),
            tooltip=["season_label", "window", "n_signings",
                     alt.Tooltip("window_rating:Q", title="raw", format=".2f"),
                     alt.Tooltip("window_rating_shrunk:Q", title="shrunk", format=".2f"),
                     "problems_addressed", "problems_unaddressed"]), width="stretch")
    show = cw.sort_values("order")[[
        "season_label", "window", "n_signings", "window_rating_raw", "window_rating",
        "window_rating_shrunk", "problems", "problems_addressed", "problems_unaddressed",
        "chronic", "problem_resolution", "window_grade"]].rename(columns={
            "season_label": "Season", "window": "Window", "n_signings": "N",
            "window_rating_raw": "Pre-pen.", "window_rating": "Rating",
            "window_rating_shrunk": "Shrunk", "problems": "Flagged",
            "problems_addressed": "Addressed", "problems_unaddressed": "Unaddressed",
            "chronic": "Chronic", "problem_resolution": "Prob.res", "window_grade": "Grade"})
    st.dataframe(show, width="stretch", hide_index=True)
    st.caption("**Rating** = recruitment rating after a **chronic penalty** (−0.75 per slot "
               "left unaddressed for ≥2 consecutive windows); **Pre-pen.** is before it.")


def _trading_tab(cs):
    sold = cs[cs["sold"]].copy()
    if sold.empty:
        st.info("No tracked signings have been sold yet.")
        return
    sold["profit_m"] = sold["sale_m"] - sold["fee_m"]
    m = st.columns(3)
    m[0].metric("Bought for (sold players)", fmt_eur(sold["fee_m"].sum() * 1e6))
    m[1].metric("Sold for", fmt_eur(sold["sale_m"].sum() * 1e6))
    m[2].metric("Trading profit", fmt_eur((sold["sale_m"].sum() - sold["fee_m"].sum()) * 1e6))
    st.altair_chart(alt.Chart(sold).mark_bar().encode(
        x=alt.X("profit_m:Q", title="Profit on resale (€m)"),
        y=alt.Y("player:N", sort="-x", title=None),
        color=alt.condition(alt.datum.profit_m >= 0, alt.value("#2e7d32"), alt.value("#c62828")),
        tooltip=["player", "season_label",
                 alt.Tooltip("fee_m:Q", title="Bought €m", format=".1f"),
                 alt.Tooltip("sale_m:Q", title="Sold €m", format=".1f"),
                 alt.Tooltip("profit_m:Q", title="Profit €m", format=".1f"),
                 alt.Tooltip("rating:Q", format=".2f")]), width="stretch")


def _problems_tab(cid):
    psum = appdata.club_problem_summary(wdf, cid)
    m = st.columns(3)
    m[0].metric("Problem-positions flagged", psum["flagged"])
    m[1].metric("Addressed via signings", psum["addressed"])
    m[2].metric("Chronic (left unaddressed)", psum["chronic"])
    st.caption("A slot is flagged when fewer than the required starters (e.g. 2 centre-backs) "
               "reached 65% of minutes the prior season; validated by below-average rating, "
               "market-value decline, or an ageing (>33) key player.")
    sub = wdf[(wdf["club_id"] == cid) & (wdf["problems"] != "")].sort_values("order")
    pr = sub[["season_label", "window", "problems", "problems_addressed",
              "problems_unaddressed", "chronic"]].rename(columns={
                  "season_label": "Season", "window": "Window", "problems": "Flagged",
                  "problems_addressed": "Addressed", "problems_unaddressed": "Unaddressed",
                  "chronic": "Chronic"})
    st.dataframe(pr, width="stretch", hide_index=True) if not pr.empty else \
        st.info("No flagged problem positions in range.")


def _byposition_tab(cs):
    if cs.empty:
        return
    grp = (cs.assign(wr=cs["rating"] * cs["weight"]).groupby("group", as_index=False)
           .agg(signings=("rating", "size"), wr=("wr", "sum"), weight=("weight", "sum"),
                spend_m=("fee_m", "sum")))
    grp["avg_rating"] = (grp["wr"] / grp["weight"]).round(2)
    grp["spend_m"] = grp["spend_m"].round(1)
    grp["position"] = grp["group"].map(SLOT_NAMES)
    order = list(SLOT_NAMES.values())
    a, b = st.columns(2)
    a.markdown("**Average rating by position**")
    a.altair_chart(alt.Chart(grp).mark_bar().encode(
        x=alt.X("position:N", sort=order, title=None),
        y=alt.Y("avg_rating:Q", title="Avg rating /10", scale=alt.Scale(domain=[0, 10])),
        color=alt.Color("position:N", legend=None),
        tooltip=["position", "avg_rating", "signings"]), width="stretch")
    b.markdown("**Spend by position**")
    b.altair_chart(alt.Chart(grp).mark_bar().encode(
        x=alt.X("position:N", sort=order, title=None),
        y=alt.Y("spend_m:Q", title="Spend (€m)"), color=alt.Color("position:N", legend=None),
        tooltip=["position", alt.Tooltip("spend_m:Q", format=".1f"), "signings"]), width="stretch")


# ====================================================== LEAGUE LEADERBOARD ==
def _board_chart(sub, n=25, color_league=True):
    top = sub.sort_values("rating_shrunk", ascending=False).head(n)
    base = alt.Chart(top)
    color = alt.Color("League:N", legend=None) if color_league else alt.value("#4c78a8")
    bars = base.mark_bar().encode(
        x=alt.X("rating_shrunk:Q", title="Shrunk rating /10"),
        y=alt.Y("club:N", sort="-x", title=None), color=color,
        tooltip=["club", "League", "n_signings",
                 alt.Tooltip("rating:Q", title="raw"),
                 alt.Tooltip("rating_shrunk:Q", title="shrunk"),
                 alt.Tooltip("lo:Q", title="CI low"), alt.Tooltip("hi:Q", title="CI high"),
                 alt.Tooltip("rank_lo:Q", title="rank ≥"), alt.Tooltip("rank_hi:Q", title="rank ≤")])
    err = base.mark_rule(color="#444").encode(y=alt.Y("club:N", sort="-x"), x="lo:Q", x2="hi:Q")
    return bars + err


def _board_table(sub, within_rank=False):
    t = sub.sort_values("rating_shrunk", ascending=False).copy()
    if within_rank:
        t.insert(0, "#", range(1, len(t) + 1))
    t["95% CI"] = t.apply(lambda r: f"{r['lo']:.1f}–{r['hi']:.1f}"
                          if pd.notna(r["lo"]) else "—", axis=1)
    t["Rank CI"] = t.apply(lambda r: f"{int(r['rank_lo'])}–{int(r['rank_hi'])}"
                           if pd.notna(r["rank_lo"]) else "—", axis=1)
    cols = (["#"] if within_rank else []) + [
        "club", "League", "n_signings", "rating", "rating_shrunk", "95% CI",
        "Rank CI", "hit_rate", "median"]
    t = t[cols].rename(columns={
        "club": "Club", "n_signings": "N", "rating": "Raw", "rating_shrunk": "Rating",
        "hit_rate": "Hit rate", "median": "Median"})
    st.dataframe(t, width="stretch", hide_index=True, column_config={
        "Rating": st.column_config.ProgressColumn(min_value=0, max_value=6, format="%.2f"),
        "Hit rate": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0f%%")})


def render_leaderboard():
    with st.sidebar:
        layout = st.radio("Leaderboard layout", ["Combined", "By league"])
        min_n = st.slider("Min. signings", 1, 40, 10)
        codes_all = sorted(clubs["leagues"].str.split(", ").explode().unique())
        if layout == "Combined":
            n2c = {LEAGUE_NAME.get(c, c): c for c in codes_all}
            pick = st.selectbox("League", ["All leagues"] + list(n2c))
        else:
            topn = st.slider("Top clubs per league", 5, 25, 10)
    pool = clubs[clubs["n_signings"] >= min_n].copy()
    pool["League"] = pool["leagues"].map(league_label)

    shrink_note = (f"Clubs ranked by **shrunk** weighted rating (empirical-Bayes k≈"
                   f"{results.get('shrinkage_k')}). Bars show the 95% bootstrap CI — note how "
                   "wide they are: most clubs are **not** statistically separable.")

    if layout == "Combined":
        sub = pool if pick == "All leagues" else \
            pool[pool["leagues"].str.contains(n2c[pick], regex=False)]
        st.subheader("🏆 Recruitment leaderboard")
        st.caption(shrink_note)
        st.altair_chart(_board_chart(sub, 25), width="stretch")
        _board_table(sub)
        st.caption("**Hit rate** = share of signings scoring ≥5/10; **Rank CI** = 95% "
                   "bootstrap interval on league rank.")
    else:
        st.subheader("🏆 Recruitment leaderboards — by league")
        st.caption("Each league ranked on its own (" + shrink_note[0].lower() + shrink_note[1:] + ")")
        present = sorted([c for c in codes_all], key=lambda c: -(priors.get(c) or 0))
        la = pd.DataFrame([{"League": LEAGUE_NAME.get(c, c), "avg": priors.get(c)}
                           for c in present if priors.get(c) is not None])
        st.markdown("**League averages** (weighted transfer rating /10)")
        st.altair_chart(alt.Chart(la).mark_bar().encode(
            x=alt.X("avg:Q", title="League avg /10"), y=alt.Y("League:N", sort="-x", title=None),
            color=alt.Color("League:N", legend=None),
            tooltip=["League", alt.Tooltip("avg:Q", format=".3f")]), width="stretch")
        for c in present:
            subc = pool[pool["leagues"].str.contains(c, regex=False)]
            if subc.empty:
                continue
            st.markdown(f"#### {LEAGUE_NAME.get(c, c)}  ·  league avg "
                        f"{priors.get(c, '—')}/10  ·  {len(subc)} clubs")
            st.altair_chart(_board_chart(subc, topn, color_league=False), width="stretch")
            with st.expander(f"{LEAGUE_NAME.get(c, c)} — full table"):
                _board_table(subc, within_rank=True)

    st.markdown("---")
    st.subheader("🧭 Market efficiency by position")
    pos = pd.DataFrame(results["rollups"]["by_position"])
    c1, c2 = st.columns(2)
    c1.markdown("**Fee vs. market value** (negative = paid above TM value)")
    c1.altair_chart(alt.Chart(pos).mark_bar().encode(
        x=alt.X("avg_premium_pct:Q", title="Avg discount vs MV (%)"),
        y=alt.Y("position:N", sort="x", title=None),
        color=alt.condition(alt.datum.avg_premium_pct >= 0, alt.value("#2e7d32"), alt.value("#c62828")),
        tooltip=["position", "n_signings", "avg_premium_pct", "avg_fee_m"]), width="stretch")
    c2.markdown("**Rating return per €10m spent**")
    c2.altair_chart(alt.Chart(pos[pos["rating_per_10m"].notna()]).mark_bar().encode(
        x=alt.X("rating_per_10m:Q", title="Rating per €10m"),
        y=alt.Y("position:N", sort="-x", title=None),
        color=alt.Color("position:N", legend=None),
        tooltip=["position", "avg_rating", "avg_fee_m", "rating_per_10m"]), width="stretch")

    st.markdown("---")
    st.subheader("📊 Does recruitment track results?")
    vd = pd.DataFrame(val["data"])
    cp = val["corr_recruitment_vs_position"]
    ci = val["corr_recruitment_vs_improvement"]
    reg = val.get("regression", {})
    st.caption(
        f"Across **{val['n']}** club-seasons: recruitment ↔ league-position Spearman ρ = "
        f"**{cp}** (negative ⇒ better recruitment, better finish); ↔ position-improvement ρ = "
        f"**{ci}**.")
    if reg:
        c = st.columns(2)
        c[0].metric("β recruitment → position (controlled)", reg.get("pooled_beta"),
                    help=f"OLS controlling for spend + prior position, cluster-robust by club. "
                         f"t={reg.get('pooled_t')}, SE={reg.get('pooled_se')}. Negative & "
                         f"significant ⇒ better recruitment → better finish.")
        c[1].metric("β within-club (fixed effects)", reg.get("fe_beta"),
                    help=f"Club fixed effects: in years a club recruits better than its own "
                         f"norm, does it finish higher? t={reg.get('fe_t')}, SE={reg.get('fe_se')}, "
                         f"n={reg.get('n')}.")
        sig = "significant (t<−2)" if (reg.get("fe_t") or 0) < -2 else "weak"
        st.caption(f"Even differencing out club quality (fixed effects), the recruitment "
                   f"effect is **{sig}**: a +1 rating point ≈ **{abs(reg.get('fe_beta',0)):.2f}** "
                   f"places better in the table.")
    if not vd.empty:
        vd["League"] = vd["league"].map(LEAGUE_NAME).fillna(vd["league"])
        st.altair_chart(alt.Chart(vd).mark_circle(opacity=0.55).encode(
            x=alt.X("recruitment:Q", title="Recruitment rating /10"),
            y=alt.Y("position:Q", title="League position (1 = top)",
                    scale=alt.Scale(reverse=True)),
            color=alt.Color("League:N"), size=alt.Size("n_signings:Q", legend=None),
            tooltip=["club", "season", "League", "recruitment", "position", "pos_change"]),
            width="stretch")


# ========================================================= COMPARE CLUBS ====
def render_compare():
    names = clubs.sort_values("club")["club"].tolist()
    pre = [n for n in ["Brighton & Hove Albion", "Manchester United"] if n in names]
    picks = st.sidebar.multiselect("Clubs (2–4)", names, default=pre or names[:2], max_selections=4)
    if len(picks) < 2:
        st.info("Pick at least two clubs in the sidebar to compare.")
        return
    rows = []
    for nm in picks:
        cr = clubs[clubs["club"] == nm].iloc[0]
        cid = cr["club_id"]
        cc = sdf[sdf["club_id"] == cid]
        spend = cc.loc[cc["fee_eur"].notna(), "fee_eur"].sum()
        recoup = cc.loc[cc["sold"], "sale_fee_eur"].fillna(0).sum()
        best = cc.loc[cc["rating"].idxmax()] if not cc.empty else None
        rows.append({
            "Club": nm, "League": league_label(cr["leagues"]),
            "Rating": cr["rating"], "Rank": int(cr["rank"]), "Signings": int(cr["n_signings"]),
            "Spend": fmt_eur(spend), "Net spend": fmt_eur(spend - recoup),
            "Best signing": (f"{best['player']} ({best['rating']})" if best is not None else "—"),
        })
    st.subheader("⚖️ Club comparison")
    st.dataframe(pd.DataFrame(rows).set_index("Club"), width="stretch")

    sub = sdf[sdf["club_id"].isin(clubs[clubs["club"].isin(picks)]["club_id"])].copy()
    sub["Club"] = sub["club"]
    grp = (sub.assign(wr=sub["rating"] * sub["weight"]).groupby(["Club", "group"], as_index=False)
           .agg(wr=("wr", "sum"), weight=("weight", "sum")))
    grp["avg_rating"] = grp["wr"] / grp["weight"]
    grp["position"] = grp["group"].map(SLOT_NAMES)
    st.markdown("**Average rating by position**")
    st.altair_chart(alt.Chart(grp).mark_bar().encode(
        x=alt.X("position:N", sort=list(SLOT_NAMES.values()), title=None),
        xOffset="Club:N",
        y=alt.Y("avg_rating:Q", title="Avg rating /10", scale=alt.Scale(domain=[0, 10])),
        color=alt.Color("Club:N"),
        tooltip=["Club", "position", alt.Tooltip("avg_rating:Q", format=".2f")]), width="stretch")

    ps = (sub.assign(wr=sub["rating"] * sub["weight"])
          .groupby(["Club", "season_label"], as_index=False)
          .agg(wr=("wr", "sum"), weight=("weight", "sum")))
    ps["rating"] = ps["wr"] / ps["weight"]
    st.markdown("**Rating by season**")
    st.altair_chart(alt.Chart(ps).mark_line(point=True).encode(
        x=alt.X("season_label:O", title="Season"),
        y=alt.Y("rating:Q", title="Avg rating /10", scale=alt.Scale(domain=[0, 10])),
        color=alt.Color("Club:N"),
        tooltip=["Club", "season_label", alt.Tooltip("rating:Q", format=".2f")]), width="stretch")


if view.startswith("🏟"):
    render_club()
elif view.startswith("🏆"):
    render_leaderboard()
else:
    render_compare()
