"""Streamlit app: per-club transfer-window analysis report.

Run:  streamlit run app.py
Needs data/dataset.pkl (build it with `python run.py collect`).
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import config
from ftw import analyze as analyze_mod
from ftw import appdata, collect

st.set_page_config(page_title="Transfer Window Analyzer", page_icon="⚽", layout="wide")

GROUP_NAMES = config.SLOT_NAMES
LEAGUE_NAME = {lg.code: lg.name for lg in config.LEAGUES}


def league_label(codes: str) -> str:
    return ", ".join(LEAGUE_NAME.get(c, c) for c in str(codes).split(", ") if c)


# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading dataset and scoring transfers…")
def load():
    ds = collect.load_dataset()
    if ds is None:
        return None
    results = analyze_mod.analyze(ds, log=lambda *a, **k: None)
    sdf = appdata.signings_df(results, ds)
    wdf = appdata.windows_df(results)
    clubs = appdata.club_index(results, ds)
    if not sdf.empty:
        g = sdf.assign(wr=sdf["rating"] * sdf["weight"]).groupby("league")
        league_avg = (g["wr"].sum() / g["weight"].sum()).round(3).to_dict()
    else:
        league_avg = {}
    return ds, results, sdf, wdf, clubs, league_avg


def fmt_eur(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if abs(v) >= 1e6:
        return f"€{v/1e6:.1f}m"
    if abs(v) >= 1e3:
        return f"€{v/1e3:.0f}k"
    return f"€{v:.0f}"


def weighted_rating(df: pd.DataFrame) -> float | None:
    if df.empty or df["weight"].sum() == 0:
        return None
    return round((df["rating"] * df["weight"]).sum() / df["weight"].sum(), 2)


# ----------------------------------------------------------------------------
data = load()
if data is None:
    st.error("No dataset found. Build it first:  `python run.py collect`")
    st.stop()
ds, results, sdf, wdf, clubs, league_avg = data

st.title("⚽ Transfer Window Analyzer")
st.caption("Top-7 European leagues · 2019/20 – 2025/26 · Transfermarkt + SofaScore")

# ---- sidebar: pick a club --------------------------------------------------
with st.sidebar:
    st.header("Select a club")
    codes = sorted(clubs["leagues"].str.split(", ").explode().unique())
    name_to_code = {LEAGUE_NAME.get(c, c): c for c in codes}
    league_pick = st.selectbox("League", ["All leagues"] + list(name_to_code))
    pool = clubs if league_pick == "All leagues" else \
        clubs[clubs["leagues"].str.contains(name_to_code[league_pick], regex=False)]
    club_names = pool.sort_values("club")["club"].tolist()
    default = club_names.index("Manchester City") if "Manchester City" in club_names else 0
    club_name = st.selectbox("Club", club_names, index=default)
    st.markdown("---")
    st.caption("**Reading the scores:** every signing is scored /10 with minutes "
               "weighted 60%, so club/window means sit low in absolute terms — elite "
               "single signings reach 8–10, flops near 0. Ranking is what matters.")

crow = clubs[clubs["club"] == club_name].iloc[0]
cid = crow["club_id"]
cs = sdf[sdf["club_id"] == cid].copy()
cw = wdf[wdf["club_id"] == cid].copy()
rated_w = cw[cw["window_rating"].notna()]

# ---- header & KPIs ---------------------------------------------------------
st.subheader(f"{club_name}  ·  {league_label(crow['leagues'])}")
n_clubs = len(clubs)
avg = crow["rating"]
spend = cs.loc[cs["fee_eur"].notna(), "fee_eur"].sum()
recouped = cs.loc[cs["sold"], "sale_fee_eur"].fillna(0).sum()

k = st.columns(6)
k[0].metric("Avg transfer rating", f"{avg}/10", help=f"Rank #{int(crow['rank'])} of {n_clubs} clubs")
k[1].metric("Signings scored", int(crow["n_signings"]))
k[2].metric("Starters / Rotation",
            f"{int((cs['type']=='starter').sum())} / {int((cs['type']=='rotation').sum())}")
k[3].metric("Spend on signings", fmt_eur(spend))
k[4].metric("Recouped (sold)", fmt_eur(recouped))
k[5].metric("Net spend", fmt_eur(spend - recouped))

lg = crow["leagues"].split(", ")[0]
if lg in league_avg:
    delta = round(avg - league_avg[lg], 2)
    st.caption(f"{LEAGUE_NAME.get(lg, lg)} average: **{league_avg[lg]}/10** · this club is "
               f"**{'+' if delta>=0 else ''}{delta}** vs league.")

# ---- headline cards --------------------------------------------------------
st.markdown("### Headlines")
c1, c2, c3, c4 = st.columns(4)


def signing_card(col, title, row, good=True):
    with col:
        if row is None:
            col.info(f"**{title}**\n\nn/a")
            return
        emoji = "🟢" if good else "🔴"
        col.markdown(f"**{emoji} {title}**")
        col.markdown(f"### {row['player']}")
        col.markdown(
            f"{row['season_label']} {row['window']} · {row['type']} · "
            f"{GROUP_NAMES.get(row['group'], row['group'])}  \n"
            f"Fee {fmt_eur(row['fee_eur'])}"
            + (f" → sold {fmt_eur(row['sale_fee_eur'])}" if row["sold"] else "")
            + f"  \n**Rating {row['rating']}/10**")


def window_card(col, title, row, good=True):
    with col:
        if row is None:
            col.info(f"**{title}**\n\nn/a")
            return
        emoji = "🟢" if good else "🔴"
        col.markdown(f"**{emoji} {title}**")
        col.markdown(f"### {row['season_label']} {row['window']}")
        probs = row["problems_addressed"] if good else row["problems_unaddressed"]
        col.markdown(
            f"{int(row['n_signings'])} signings · "
            f"{int(row['n_starter'])} starter / {int(row['n_rotation'])} rotation  \n"
            + (f"Addressed: {probs}  \n" if good and probs else "")
            + (f"Unaddressed: {probs}  \n" if (not good) and probs else "")
            + f"**Window rating {row['window_rating']}/10**")


best_sig = cs.loc[cs["rating"].idxmax()] if not cs.empty else None
worst_sig = cs.loc[cs["rating"].idxmin()] if not cs.empty else None
best_win = rated_w.loc[rated_w["window_rating"].idxmax()] if not rated_w.empty else None
worst_win = rated_w.loc[rated_w["window_rating"].idxmin()] if not rated_w.empty else None
signing_card(c1, "Best signing", best_sig, True)
signing_card(c2, "Worst signing", worst_sig, False)
window_card(c3, "Best window", best_win, True)
window_card(c4, "Worst window", worst_win, False)

# ---- tabs ------------------------------------------------------------------
t_over, t_sign, t_win, t_trade, t_prob, t_pos = st.tabs(
    ["📈 Overview", "📋 Signings", "🪟 Windows", "💷 Trading", "🩺 Squad problems", "🧭 By position"])

with t_over:
    a, b = st.columns(2)
    # rating by season
    if not cs.empty:
        per_season = (cs.assign(wr=cs["rating"] * cs["weight"])
                      .groupby(["season", "season_label"], as_index=False)
                      .agg(wr=("wr", "sum"), weight=("weight", "sum"),
                           signings=("rating", "size")))
        per_season["rating"] = per_season["wr"] / per_season["weight"]
        line = alt.Chart(per_season).mark_line(point=True).encode(
            x=alt.X("season_label:O", title="Season"),
            y=alt.Y("rating:Q", title="Avg rating /10", scale=alt.Scale(domain=[0, 10])),
            tooltip=["season_label", alt.Tooltip("rating:Q", format=".2f"), "signings"])
        a.markdown("**Average transfer rating by season**")
        a.altair_chart(line, width='stretch')

        type_counts = cs["type"].value_counts().rename_axis("type").reset_index(name="n")
        bar = alt.Chart(type_counts).mark_bar().encode(
            x=alt.X("type:N", title=None), y=alt.Y("n:Q", title="Signings"),
            color=alt.Color("type:N", legend=None),
            tooltip=["type", "n"])
        b.markdown("**Signings by type**")
        b.altair_chart(bar, width='stretch')

    # spend vs rating
    paid = cs[cs["fee_m"] > 0]
    if not paid.empty:
        st.markdown("**Spend vs. rating** (each point a signing; hover for detail)")
        scatter = alt.Chart(paid).mark_circle(opacity=0.7).encode(
            x=alt.X("fee_m:Q", title="Fee (€m)"),
            y=alt.Y("rating:Q", title="Rating /10", scale=alt.Scale(domain=[0, 10])),
            color=alt.Color("type:N", title="Type"),
            size=alt.Size("mv_m:Q", title="MV at purchase (€m)", legend=None),
            tooltip=["player", "season_label", "window", "type",
                     alt.Tooltip("fee_m:Q", title="Fee €m", format=".1f"),
                     alt.Tooltip("rating:Q", format=".2f"), "sold"])
        st.altair_chart(scatter, width='stretch')

with t_sign:
    cols = ["season_label", "window", "player", "group", "type", "labels",
            "fee_eur", "mv_at_purchase", "sold", "sale_fee_eur", "seasons_evaluated",
            "rating", "sc_minutes", "sc_profit_loss", "sc_rating", "sc_efficiency",
            "sc_mv_growth"]
    show = cs[cols].sort_values("rating", ascending=False).rename(columns={
        "season_label": "Season", "window": "Window", "player": "Player",
        "group": "Pos", "type": "Type", "labels": "Classification",
        "fee_eur": "Fee", "mv_at_purchase": "MV in", "sold": "Sold",
        "sale_fee_eur": "Sale fee", "seasons_evaluated": "Seasons",
        "rating": "Rating", "sc_minutes": "minutes", "sc_profit_loss": "P/L",
        "sc_rating": "rating⁺", "sc_efficiency": "effic.", "sc_mv_growth": "mv↑"})
    st.dataframe(
        show, width='stretch', hide_index=True,
        column_config={
            "Fee": st.column_config.NumberColumn(format="€%d"),
            "MV in": st.column_config.NumberColumn(format="€%d"),
            "Sale fee": st.column_config.NumberColumn(format="€%d"),
            "Rating": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.2f"),
        })
    st.caption("Sub-score columns (minutes/P&L/rating⁺/efficiency/mv↑) are the points "
               "earned out of that component's max; they sum to the rating.")

with t_win:
    timeline = rated_w.sort_values("order")
    if not timeline.empty:
        bar = alt.Chart(timeline).mark_bar().encode(
            x=alt.X("order:O", axis=alt.Axis(labels=False, title="Window (time →)")),
            y=alt.Y("window_rating:Q", title="Window rating /10", scale=alt.Scale(domain=[0, 10])),
            color=alt.Color("window:N", title="Window"),
            tooltip=["season_label", "window", "n_signings",
                     alt.Tooltip("window_rating:Q", format=".2f"),
                     "problems_addressed", "problems_unaddressed"])
        st.markdown("**Window ratings over time**")
        st.altair_chart(bar, width='stretch')
    wshow = cw.sort_values("order")[[
        "season_label", "window", "n_signings", "window_rating", "problems",
        "problems_addressed", "problems_unaddressed", "chronic",
        "problem_resolution", "window_grade"]].rename(columns={
            "season_label": "Season", "window": "Window", "n_signings": "N",
            "window_rating": "Rating", "problems": "Flagged",
            "problems_addressed": "Addressed", "problems_unaddressed": "Unaddressed",
            "chronic": "Chronic", "problem_resolution": "Prob.resolution",
            "window_grade": "Blended grade"})
    st.dataframe(wshow, width='stretch', hide_index=True)

with t_trade:
    sold = cs[cs["sold"]].copy()
    if sold.empty:
        st.info("No tracked signings have been sold yet.")
    else:
        sold["profit_m"] = sold["sale_m"] - sold["fee_m"]
        tot_in = sold["fee_m"].sum()
        tot_out = sold["sale_m"].sum()
        m = st.columns(3)
        m[0].metric("Bought for (sold players)", fmt_eur(tot_in * 1e6))
        m[1].metric("Sold for", fmt_eur(tot_out * 1e6))
        m[2].metric("Trading profit", fmt_eur((tot_out - tot_in) * 1e6))
        chart = alt.Chart(sold).mark_bar().encode(
            x=alt.X("profit_m:Q", title="Profit on resale (€m)"),
            y=alt.Y("player:N", sort="-x", title=None),
            color=alt.condition(alt.datum.profit_m >= 0, alt.value("#2e7d32"), alt.value("#c62828")),
            tooltip=["player", "season_label",
                     alt.Tooltip("fee_m:Q", title="Bought €m", format=".1f"),
                     alt.Tooltip("sale_m:Q", title="Sold €m", format=".1f"),
                     alt.Tooltip("profit_m:Q", title="Profit €m", format=".1f"),
                     alt.Tooltip("rating:Q", format=".2f")])
        st.altair_chart(chart, width='stretch')

with t_prob:
    psum = appdata.club_problem_summary(wdf, cid)
    m = st.columns(3)
    m[0].metric("Problem-positions flagged", psum["flagged"])
    m[1].metric("Addressed via signings", psum["addressed"])
    m[2].metric("Chronic (left unaddressed)", psum["chronic"])
    st.caption("A position is flagged when no single player reached 65% of available "
               "minutes the prior season; validated by below-average rating, market-value "
               "decline, or an ageing (>33) key player.")
    probrows = cw[cw["problems"] != ""].sort_values("order")[[
        "season_label", "window", "problems", "problems_addressed",
        "problems_unaddressed", "chronic"]].rename(columns={
            "season_label": "Season", "window": "Window", "problems": "Flagged",
            "problems_addressed": "Addressed", "problems_unaddressed": "Unaddressed",
            "chronic": "Chronic"})
    if probrows.empty:
        st.info("No flagged problem positions in range.")
    else:
        st.dataframe(probrows, width='stretch', hide_index=True)

with t_pos:
    if not cs.empty:
        grp = (cs.assign(wr=cs["rating"] * cs["weight"])
               .groupby("group", as_index=False)
               .agg(signings=("rating", "size"), wr=("wr", "sum"),
                    weight=("weight", "sum"), spend_m=("fee_m", "sum")))
        grp["avg_rating"] = (grp["wr"] / grp["weight"]).round(2)
        grp["spend_m"] = grp["spend_m"].round(1)
        grp["position"] = grp["group"].map(GROUP_NAMES)
        a, b = st.columns(2)
        a.markdown("**Average rating by position**")
        a.altair_chart(alt.Chart(grp).mark_bar().encode(
            x=alt.X("position:N", sort=list(GROUP_NAMES.values()), title=None),
            y=alt.Y("avg_rating:Q", title="Avg rating /10", scale=alt.Scale(domain=[0, 10])),
            color=alt.Color("position:N", legend=None),
            tooltip=["position", "avg_rating", "signings"]), width='stretch')
        b.markdown("**Spend by position**")
        b.altair_chart(alt.Chart(grp).mark_bar().encode(
            x=alt.X("position:N", sort=list(GROUP_NAMES.values()), title=None),
            y=alt.Y("spend_m:Q", title="Spend (€m)"),
            color=alt.Color("position:N", legend=None),
            tooltip=["position", alt.Tooltip("spend_m:Q", format=".1f"), "signings"]),
            width='stretch')
        st.dataframe(grp[["position", "signings", "avg_rating", "spend_m"]].rename(
            columns={"position": "Position", "signings": "Signings",
                     "avg_rating": "Avg rating", "spend_m": "Spend €m"}),
            width='stretch', hide_index=True)
