"""Tedgy Trends public results: ONE overall Injury model and every completed game.

The original pregame forecasts and saved Week8 zero-edge 'No bet' stay immutable.
A market-side winner is NOT retroactively a model pick when the model had no edge.
Baseline research stays in GitHub but is intentionally hidden from this public page.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/"data"/"public_results"/"nfl_2026_graded_games.csv"
SUMMARY=ROOT/"data"/"public_results"/"nfl_2026_results_summary.csv"
MARKET="https://github.com/tedgytrends-bit/sports-betting-model/blob/main/data/public_results/"
STATES={"FINAL","PENDING"}
OUTCOMES={"Win","Loss","Push","No lean","Pending"}

st.title("Tedgy Trends — Overall Model Record")
st.caption("2026 Injury model · Week 8 onward · ATS and totals · Updated after Thursday, Sunday and Monday game days")

if not RESULTS.exists() or not SUMMARY.exists():
    st.error("Public grading files are not available; cannot infer a record.")
    st.stop()

source=pd.read_csv(RESULTS,dtype={"game_id":str,"model":str,"record_class":str,"score_status":str},keep_default_na=False)
summary=pd.read_csv(SUMMARY,dtype={"week":str,"model":str,"record_class":str},keep_default_na=False)
required={"game_id","season","week","model","record_class","score_status","ats_result",
          "total_result","actual_away","actual_home","home_favored_spread","bovada_total",
          "away_team","home_team","day","score_source_url","forecast_file",
          "ats_pick","total_pick"}
if not required.issubset(source.columns):
    st.error("Public results data is missing required fields.")
    st.stop()
if source.duplicated(["game_id","model"]).any() or not set(source.score_status).issubset(STATES):
    st.error("Invalid public results: duplicate model/game or final state.")
    st.stop()
if not set(source.ats_result).issubset(OUTCOMES) or not set(source.total_result).issubset(OUTCOMES):
    st.error("Invalid result category in saved public grades.")
    st.stop()
if any(source.loc[source.score_status.eq("PENDING"),c].ne("Pending").any()
       for c in ("ats_result","total_result")):
    st.error("A game was graded before its final score.")
    st.stop()
for week,count in ((8,14),(9,15),(10,14)):
    subset=source.loc[pd.to_numeric(source.week,errors="coerce").eq(week)]
    if len(subset)!=count*2 or subset.game_id.nunique()!=count:
        st.error(f"Week {week} public record incomplete. Results withheld.")
        st.stop()

df=source.loc[source.model.eq("injury") & source.record_class.eq("PUBLIC_PUBLISHED")].copy()
if len(df)!=source.game_id.nunique():
    st.error("Every published game needs one official Injury model record.")
    st.stop()
if (df.loc[df.score_status.eq("FINAL"),"score_source_url"].astype(str).eq("")).any():
    st.error("Missing source for an officially completed game.")
    st.stop()

def get_summary(week):
    subset=summary.loc[
        summary.week.eq(str(week)) & summary.model.eq("injury")
        & summary.record_class.eq("PUBLIC_PUBLISHED")
    ]
    if len(subset)!=1:
        raise ValueError(f"Expected one official Injury summary for {week}")
    return subset.iloc[0]

def record(row,kind):
    prefix="ats_" if kind=="ATS" else "totals_"
    w,l,p=(int(row[prefix+x]) for x in ("wins","losses","pushes"))
    return f"{w}–{l}"+(f"–{p}" if p else "")

def roi(row,kind):
    k="illustrative_flat_110_"+("ats" if kind=="ATS" else "totals")+"_roi_pct"
    return f"{float(row[k]):+.1f}%" if str(row[k]).strip() else "—"

all_record=get_summary("ALL")
final_count=df.loc[df.score_status.eq("FINAL"),"game_id"].nunique()
pending_count=df.loc[df.score_status.eq("PENDING"),"game_id"].nunique()
st.info(
    f"**Overall Injury model record — {final_count} completed games, {pending_count} pending.** "
    "Results update after games are officially final. Each completed matchup also shows "
    "the actual market total outcome, including games where the model projected exactly "
    "the bookmaker's number. No hypothetical bets are recorded as placed bets."
)

c_ats,c_totals=st.columns(2)
for col,kind in ((c_ats,"ATS"),(c_totals,"Totals")):
    with col:
        st.metric("Overall Injury "+kind+" record",record(all_record,kind))
        pct=all_record["ats_win_pct" if kind=="ATS" else "totals_win_pct"]
        neutral=int(all_record["ats_no_lean" if kind=="ATS" else "totals_no_lean"])
        graded=final_count-neutral
        st.caption(
            f"{graded} graded directions · {float(pct):.1f}% decisive win rate · "
            f"{roi(all_record,kind)} illustrative flat -110 ROI"
            if str(pct).strip() else "No decisive graded games"
        )
        if neutral:
            st.caption(
                f"{neutral} completed game with a pregame projection exactly equal to "
                "the market: its actual outcome is shown below, but it is not a model win."
            )
        if pending_count:
            st.caption(f"{pending_count} future or unfinished game pending")

st.subheader("Week-by-week performance")
weeks=sorted((int(x) for x in summary.week.unique() if str(x).isdigit()),reverse=True)
week_rows=[]
for wk in weeks:
    r=get_summary(wk)
    neutral=int(r.totals_no_lean)
    week_rows.append({
        "Week":wk,
        "Injury ATS":record(r,"ATS"),
        "Injury totals":record(r,"Totals")+(f" ({neutral} exact-market projection)" if neutral else ""),
        "Final / Games":f"{int(r.games_final)}/{int(r.games_expected)}",
        "ATS ROI*":roi(r,"ATS"),
        "Totals ROI*":roi(r,"Totals"),
    })
st.dataframe(pd.DataFrame(week_rows),hide_index=True,width="stretch")
st.caption("*Illustrative flat -110 ROI assumes wagering every directional model lean; not actual betting returns.")

st.subheader("Game-by-game results")
left,right=st.columns(2)
with left:
    chosen=st.selectbox("Week",options=["All weeks"]+["Week "+str(w) for w in weeks])
with right:
    day=st.selectbox("Game day",options=["All game days","Thursday","Sunday","Monday"])
view=df.copy()
if chosen!="All weeks":
    view=view.loc[pd.to_numeric(view.week,errors="coerce").eq(int(chosen.split()[-1]))]
if day!="All game days":
    view=view.loc[view.day.eq(day)]
game_rows=[]
for _,g in view.iterrows():
    final=g.score_status=="FINAL"
    actual_total=int(g.actual_away)+int(g.actual_home) if final else None
    line=float(g.bovada_total)
    outcome=(
        ("Market total Push" if actual_total==line
         else "Market Over won" if actual_total>line else "Market Under won")
        if final else "Pending"
    )
    spread=float(g.home_favored_spread)
    favorite=g.home_team if spread>0 else g.away_team
    market=(f"{favorite} -{abs(spread):g}" if spread else "PK")+f" / {line:g}"
    ats_result=f"{g.ats_pick}: {g.ats_result}"
    if g.total_result=="No lean":
        total_grade=f"No pregame pick — {outcome}" if final else "No pregame pick — pending"
    else:
        total_grade=f"{g.total_pick}: {g.total_result}"
    first_start=" · uncalibrated QB" if "NOT CALIBRATED" in g.source_warning else ""
    final_score=(
        f"{g.away_team} {int(g.actual_away)} – {g.home_team} {int(g.actual_home)}"
        if final else "Pending"
    )
    game_rows.append({
        "Week":int(g.week),"Day":g.day,
        "Matchup":f"{g.away_team} @ {g.home_team}",
        "Final score":final_score,
        "Archived Bovada":market,
        "Injury ATS pick / grade":ats_result,
        "Injury totals pick / grade":total_grade+first_start,
        "Actual total outcome":f"{actual_total} points · {outcome}" if final else "Pending",
        "Forecast archive":Path(g.forecast_file).name,
        "_kickoff":g.kickoff_utc,
    })
game_rows.sort(key=lambda r:(r["Week"],r["_kickoff"],r["Matchup"]),reverse=True)
if game_rows:
    st.dataframe(pd.DataFrame(game_rows).drop(columns=["_kickoff"]),hide_index=True,width="stretch",height=560)
else:
    st.info("No games match those filters.")

st.caption(
    "Week 8 IND @ JAX: the Injury model total was 46.0, identical to Bovada 46.0. "
    "The actual game totaled 49, so market Over won, but no pregame model total was picked. "
    "Historical records are not rewritten to retroactively create a model win."
)
st.markdown(
    "[Audited game-by-game data]("+MARKET+"nfl_2026_graded_games.csv) · "
    "[Weekly and overall record]("+MARKET+"nfl_2026_results_summary.csv)"
)
st.page_link("pages/Week_10_Projection_Board.py",label="View Week 10 projections",icon=":material/sports_football:")
