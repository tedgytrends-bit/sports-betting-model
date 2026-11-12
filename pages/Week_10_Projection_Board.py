"""2026 Week 10 public board: immutable initial models, latest saved Bovada prices.

Displays exactly two model views: Baseline and Injury (QB provisional). The
initial model snapshot is not rewritten by Saturday/Sunday line updates.
Week 8 and 9 archives remain separate historical records.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
SNAP=ROOT/"data"/"public_snapshots"/"nfl_week10_initial_projections_2026-11-12.csv"
MARKET=ROOT/"data"/"bovada_lines.csv"
SOURCE="https://github.com/tedgytrends-bit/sports-betting-model/blob/main/"
SEASON=2026
WEEK=10


def team(x):
    t=str(x).upper().strip()
    return "LA" if t=="LAR" else t


def num(value):
    return float(value)


def fmt_price(value):
    if pd.isna(value):
        return "price unavailable"
    p=int(float(value))
    return f"+{p}" if p>0 else str(p)


def format_side(favored,home,away,market):
    s=num(favored)
    if market=="display":
        if s>0:
            return f"{home} -{abs(s):g}"
        if s<0:
            return f"{away} -{abs(s):g}"
        return "Pick'em"
    raise ValueError("Unsupported format type")


def decode(row,quote):
    h,a,t=(num(row[k]) for k in ("projected_home","projected_away","projected_total"))
    s=num(quote["home_favorite_spread"])
    total=num(quote["total_line"])
    edge=(h-a)-s
    te=t-total
    away,home=team(row["away_team"]),team(row["home_team"])
    ats=home if edge>0 else away if edge<0 else "Even"
    ats_line=-s if edge>0 else s
    price=(quote["home_spread_price"] if edge>0 else quote["away_spread_price"]) if edge!=0 else float("nan")
    over=te>0
    price_t=quote["over_price"] if over else quote["under_price"]
    local=pd.to_datetime(row["kickoff_utc"],utc=True).tz_convert("America/Chicago")
    return {
        "_time":local,
        "Kickoff (CT)":local.strftime("%a %b %-d · %-I:%M %p"),
        "Game":f"{away} @ {home}",
        "Bovada":f"{format_side(s,home,away,'display')} · O/U {total:g}",
        "Projected score":f"{away} {a:.1f} – {home} {h:.1f}",
        "Projected total":round(t,1),
        "ATS lean":f"{ats} {ats_line:+g} ({fmt_price(price)})" if ats!="Even" else "No ATS edge",
        "ATS difference":round(abs(edge),1),
        "Total lean":f"{'Over' if over else 'Under' if te<0 else 'Even'} {total:g} ({fmt_price(price_t)})",
        "Total difference":round(abs(te),1),
        "QB information":(
            f"{row['away_qb_name']} / {row['home_qb_name']}"
            if row["model"]=="injury" else "Baseline · no QB overlay"
        ),
        "QB verification":(
            "Includes provisional starters"
            if row["model"]=="injury" else "Not applicable"
        ),
    }


st.title("NFL Week 10 — Projections")
st.caption(
    "All 14 games, ordered by kickoff · Initial November 12 pregame Baseline and Injury "
    "forecasts · User-provided Bovada lines"
)
if not SNAP.exists() or not MARKET.exists():
    st.error("Week 10 public archive is incomplete. Scores are withheld rather than fabricated.")
    st.stop()

df=pd.read_csv(SNAP,low_memory=False)
quotes=pd.read_csv(MARKET,low_memory=False)
required={
    "published_at_utc","publication_status","game_id","season","week",
    "kickoff_utc","away_team","home_team","model","projected_away",
    "projected_home","projected_total",
}
if not required.issubset(df.columns) or len(df)!=28 or df.game_id.nunique()!=14:
    st.error("Week 10 forecast does not contain exactly 14 unique model pairs.")
    st.stop()
if df.duplicated(["game_id","model"]).any() or set(df.model)!={"baseline","injury"}:
    st.error("Malformed Week 10 Baseline/Injury archive.")
    st.stop()
if not df.publication_status.eq("INITIAL_PUBLIC_PREGAME_2026_WEEK10_PROVISIONAL_QB").all():
    st.error("Week 10 publication status failed validation.")
    st.stop()
if len(df.published_at_utc.unique())!=1:
    st.error("Week 10 initial publication timestamp is inconsistent.")
    st.stop()
df["kickoff"]=pd.to_datetime(df.kickoff_utc,utc=True,errors="coerce")
df["published"]=pd.to_datetime(df.published_at_utc,utc=True,errors="coerce")
if df[["kickoff","published"]].isna().any().any() or not (df.published<df.kickoff).all():
    st.error("An initial forecast could not be verified as predating kickoff.")
    st.stop()
for key in ("projected_away","projected_home","projected_total"):
    df[key]=pd.to_numeric(df[key],errors="coerce")
if df[["projected_away","projected_home","projected_total"]].isna().any().any() or (
    (df.projected_home+df.projected_away-df.projected_total).abs().gt(.02)
).any():
    st.error("Projected points failed a consistency check.")
    st.stop()

quotes=quotes.loc[
    pd.to_numeric(quotes.season,errors="coerce").eq(SEASON)
    & pd.to_numeric(quotes.week,errors="coerce").eq(WEEK)
].copy()
quotes["key"]=quotes.away_team.map(team)+"@"+quotes.home_team.map(team)
quotes["captured_at_utc"]=pd.to_datetime(quotes.captured_at_utc,utc=True,errors="coerce")
market=quotes.dropna(subset=["captured_at_utc"]).sort_values("captured_at_utc").drop_duplicates(
    "key",keep="last"
).set_index("key")
if len(market)!=14 or market["total_line"].isna().any():
    st.error("Week 10 Bovada archive is incomplete; refusing to calculate leans.")
    st.stop()
if len(market)!=df.game_id.nunique():
    st.error("Week 10 model and price game counts do not match.")
    st.stop()

published=df.published.iloc[0].tz_convert("America/Chicago").strftime("%b %-d, %-I:%M %p CT")
market_time=quotes.captured_at_utc.max().tz_convert("America/Chicago").strftime("%b %-d, %-I:%M %p CT")
st.info(
    f"Initial model published **{published}**. Latest saved user-supplied Bovada "
    f"reference **{market_time}**. This is an initial forecast; injury statuses and QB "
    "identities may change before kickoff. No Week 8/9 forecasts were replaced."
)

selection=st.radio(
    "Model view",
    options=["Injury · QB provisional","Baseline"],
    index=0,
    horizontal=True,
)
model="injury" if selection.startswith("Injury") else "baseline"
chosen=df[df.model.eq(model)].sort_values(["kickoff","game_id"]).copy()
rows=[]
for _,row in chosen.iterrows():
    key=team(row.away_team)+"@"+team(row.home_team)
    if key not in market.index:
        st.error(f"No archived Bovada quote for {key}.")
        st.stop()
    quote=market.loc[key]
    if isinstance(quote,pd.DataFrame):
        st.error(f"Duplicate market game {key}.")
        st.stop()
    rows.append(decode(row,quote))
out=pd.DataFrame(rows).sort_values("_time").drop(columns=["_time"])
if len(out)!=14:
    st.error("Week 10 board is missing games.")
    st.stop()
st.dataframe(out,hide_index=True,width="stretch",height=530)
st.caption(
    "ATS and total differences are directional comparisons, not betting recommendations. "
    "The Injury model currently relies on largely provisional starting-QB identities; "
    "Saturday/Sunday pregame updates must be captured separately."
)
st.link_button(
    "View frozen first-public Week 10 data",
    SOURCE+"data/public_snapshots/nfl_week10_initial_projections_2026-11-12.csv",
)
st.page_link("pages/Week_09_Projection_Board.py",label="View archived Week 9 projections",icon=":material/history:")
