"""Tedgy Trends complete Injury directional results, preserving original prospective grades.

The exact-market Week8 IND@JAX tie was resolved *retrospectively* from an
existing published Baseline Over projection. Display as derived Injury-series
Over/Win, NEVER suggest the original Injury release picked Over.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"data"/"public_results"
RAW=DIR/"nfl_2026_graded_games.csv"
FULL=DIR/"nfl_2026_full_directional_games.csv"
SUMMARY=DIR/"nfl_2026_full_directional_summary.csv"
POLICY=DIR/"nfl_2026_full_directional_policy.json"
URL="https://github.com/tedgytrends-bit/sports-betting-model/blob/main/data/public_results/"

st.title("Tedgy Trends — Overall Injury Model Record")
st.caption("2026 · Week 8 onward · ATS and totals · grades updated after completed game days")

if any(not p.exists() for p in [RAW,FULL,SUMMARY,POLICY]):
    st.error("Results source is incomplete. Records cannot be inferred.")
    st.stop()
original=pd.read_csv(RAW,keep_default_na=False)
games=pd.read_csv(FULL,keep_default_na=False)
summary=pd.read_csv(SUMMARY,dtype={"week":str},keep_default_na=False)
published=original.loc[original.model.eq("injury") & original.record_class.eq("PUBLIC_PUBLISHED")]
if len(games)!=len(published) or games.game_id.nunique()!=len(games):
    st.error("Derived results are missing one or more original published games.")
    st.stop()
if (not games.model.eq("injury").all()
    or not games.record_class.eq("DERIVED_DIRECTIONAL_TIEBREAK").all()
    or not games.total_pick.isin(["Over","Under"]).all()
    or not games.total_result.isin(["Win","Loss","Push","Pending"]).all()
    or not games.score_status.isin(["FINAL","PENDING"]).all()):
    st.error("Results contain an invalid model, pick, or final-status value.")
    st.stop()
old_by_game=published.set_index("game_id")
for row in games.itertuples(index=False):
    if row.game_id not in old_by_game.index:
        st.error("A new game has no original Injury forecast.")
        st.stop()
    old=old_by_game.loc[row.game_id]
    if any(str(getattr(row,key))!=str(old[key]) for key in
           ("actual_away","actual_home","ats_pick","ats_result","projected_total",
            "bovada_total","score_status")):
        st.error("A historical result or market value differs from the published archive.")
        st.stop()
    if old["total_result"]=="No lean":
        if row.selection_provenance!="POSTHOC_POLICY_USING_PREEXISTING_PREGAME_BASELINE":
            st.error("An exact-market tie has no disclosed pre-existing tiebreaker.")
            st.stop()
    elif row.total_result!=old["total_result"] or row.total_pick!=old["total_pick"]:
        st.error("Non-tied published Injury results cannot be rewritten.")
        st.stop()
fix=games.loc[games.game_id.eq("2026_08_IND_JAX")]
if len(fix)!=1 or fix.iloc[0].total_pick!="Over" or fix.iloc[0].total_result!="Win" or str(fix.iloc[0].fallback_projected_total)!="46.9":
    st.error("Week 8 source-backed Over tiebreak cannot be verified.")
    st.stop()

def get_summary(week):
    rec=summary.loc[summary.week.eq(str(week)) & summary.model.eq("injury")
                    & summary.record_class.eq("DERIVED_DIRECTIONAL_TIEBREAK")]
    if len(rec)!=1:raise ValueError("Missing exact Injury model summary")
    return rec.iloc[0]

def record(row,kind):
    prefix="ats_" if kind=="ATS" else "totals_"
    w,l,p=(int(row[prefix+x]) for x in ["wins","losses","pushes"])
    return f"{w}–{l}"+(f"–{p}" if p else "")

def roi(row,kind):
    key="illustrative_flat_110_"+("ats" if kind=="ATS" else "totals")+"_roi_pct"
    return f"{float(row[key]):+.1f}%" if str(row[key]).strip() else "—"

overall=get_summary("ALL")
finals=int(games.score_status.eq("FINAL").sum())
pending=int(games.score_status.eq("PENDING").sum())
st.info(
    f"**Overall Injury model directional record:** {finals} completed games, {pending} pending. "
    "For the Week 8 Indianapolis–Jacksonville exact-market total, the previously "
    "published Baseline forecast breaks the tie: **Over 46 — Win**. "
    "That tiebreaker was assigned retrospectively; it was not the original Injury pick. "
    "The original published record is retained unchanged."
)
left,right=st.columns(2)
for column,kind in [(left,"ATS"),(right,"Totals")]:
    with column:
        st.metric("Overall Injury "+kind+" Record",record(overall,kind))
        rate=overall["ats_win_pct" if kind=="ATS" else "totals_win_pct"]
        st.caption(f"{float(rate):.1f}% win rate · {roi(overall,kind)} illustrative -110 ROI")
        if kind=="Totals":st.caption("Includes one retrospective Baseline directional tiebreaker.")
        if pending:st.caption(f"{pending} game pending")

st.subheader("Week-by-week performance")
weeks=sorted([int(x) for x in summary.week.unique() if str(x).isdigit()],reverse=True)
rows=[]
for week in weeks:
    val=get_summary(week)
    rows.append({
        "Week":week,"Injury ATS":record(val,"ATS"),
        "Injury totals":record(val,"Totals")+(" †" if week==8 else ""),
        "Final / games":f"{int(val.games_final)}/{int(val.games_expected)}",
        "ATS ROI*":roi(val,"ATS"),"Totals ROI*":roi(val,"Totals"),
    })
st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
st.caption("† Week8 Indianapolis–Jacksonville Over uses a retrospectively adopted tiebreaker from a pre-existing Baseline projection. *ROI is theoretical, not actual betting returns.")

st.subheader("Game-by-game results")
c1,c2=st.columns(2)
with c1:which=st.selectbox("Week",["All weeks"]+["Week "+str(x) for x in weeks])
with c2:day=st.selectbox("Game day",["All game days","Thursday","Sunday","Monday"])
subset=games
if which!="All weeks":
    subset=subset.loc[pd.to_numeric(subset.week,errors="coerce").eq(int(which.split()[-1]))]
if day!="All game days":subset=subset.loc[subset.day.eq(day)]
table=[]
for item in subset.itertuples(index=False):
    final=item.score_status=="FINAL"
    actual=int(item.actual_away)+int(item.actual_home) if final else None
    line=float(item.bovada_total)
    actual_result=("Push" if actual==line else "Over" if actual>line else "Under") if final else "Pending"
    home=float(item.home_favored_spread)
    favorite=item.home_team if home>0 else item.away_team
    market=(f"{favorite} -{abs(home):g}" if home else "PK")+f" / {line:g}"
    fallback=item.selection_provenance=="POSTHOC_POLICY_USING_PREEXISTING_PREGAME_BASELINE"
    table.append({
        "Week":int(item.week),"Day":item.day,
        "Matchup":f"{item.away_team} @ {item.home_team}",
        "Final":(f"{item.away_team} {int(item.actual_away)} – {item.home_team} {int(item.actual_home)}" if final else "Pending"),
        "Bovada":market,
        "Injury ATS":f"{item.ats_pick} — {item.ats_result}",
        "Injury total":f"{item.total_pick} {line:g} — {item.total_result}"+(" † Retrospective tiebreak" if fallback else ""),
        "Actual total":(f"{actual} · {actual_result}" if final else "Pending"),
        "Forecast source":Path(item.forecast_file).name,
        "_kickoff":item.kickoff_utc
    })
table.sort(key=lambda x:(x["Week"],x["_kickoff"],x["Matchup"]),reverse=True)
if table:
    st.dataframe(pd.DataFrame(table).drop(columns=["_kickoff"]),hide_index=True,width="stretch",height=560)
else:
    st.info("No games match that filter.")

st.caption(
    "A total is a PUSH only when the actual game's points equal the sportsbook total. "
    "For IND @ JAX, the model and Bovada both had 46, but the game finished at 49: "
    "Over 46 won. The original Injury forecast of exactly 46 had no directional pick; "
    "its retrospective tiebreaker is disclosed above."
)
st.markdown(
    "[Complete directional record]("+URL+"nfl_2026_full_directional_games.csv) · "
    "[Original unmodified Injury record]("+URL+"nfl_2026_graded_games.csv)"
)
st.page_link("pages/Week_10_Projection_Board.py",
    label="View Week 10 projections",icon=":material/sports_football:")
