"""Tedgy Trends official published NFL results, auto-graded after each game day.

Use exactly the same data as the GitHub Pages Results tab. The underlying
GitHub Actions run never changes frozen pregame forecasts or historical grades
after outcomes have been verified. Research and missing games are explicit.
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

st.title("Tedgy Trends — Model Results")
st.caption("2026 NFL Week 8 onward · ATS and totals · Updated after Thursday, Sunday and Monday game days")

if not RESULTS.exists() or not SUMMARY.exists():
    st.error("Public grading files have not been published yet. Existing archived Week 8/9 grades remain unchanged.")
    st.stop()
df=pd.read_csv(RESULTS,dtype={"game_id":str,"model":str,"record_class":str,"score_status":str},keep_default_na=False)
summary=pd.read_csv(SUMMARY,dtype={"week":str,"model":str,"record_class":str},keep_default_na=False)
required={"game_id","season","week","model","record_class","score_status","ats_result","total_result","actual_away","actual_home","home_favored_spread","bovada_total","away_team","home_team","day","score_source_url","forecast_file"}
if not required.issubset(df.columns):
    st.error("Public grading file is missing required fields.")
    st.stop()
if df.duplicated(["game_id","model"]).any() or not set(df.score_status).issubset(STATES):
    st.error("Results contain a duplicate model/game or invalid final status.")
    st.stop()
if not set(df.ats_result).issubset(OUTCOMES) or not set(df.total_result).issubset(OUTCOMES):
    st.error("Invalid result category in archived grades.")
    st.stop()
if any(df.loc[df.score_status.eq("PENDING"),c].ne("Pending").any() for c in ("ats_result","total_result")):
    st.error("A game was graded before its final result.")
    st.stop()
for week,count in ((8,14),(9,15),(10,14)):
    subset=df.loc[pd.to_numeric(df.week,errors="coerce").eq(week)]
    if len(subset)!=count*2 or subset.game_id.nunique()!=count:
        st.error(f"Week {week} archive is incomplete; will not display a partial cumulative record.")
        st.stop()

def get_summary(week,model,klass="PUBLIC_PUBLISHED"):
    matches=summary.loc[
        summary.week.eq(str(week)) &
        summary.model.eq(model) &
        summary.record_class.eq(klass)
    ]
    if len(matches)!=1:
        raise ValueError(f"Missing unique {model} {klass} summary for Week {week}")
    return matches.iloc[0]

def record(row,kind):
    prefix="ats_" if kind=="ATS" else "totals_"
    w,l,p=(int(row[prefix+x]) for x in ("wins","losses","pushes"))
    no=int(row[prefix+"no_lean"])
    return f"{w}–{l}"+(f"–{p}" if p else "")+(f" ({no} no lean)" if no else "")

def roi(row,kind):
    k="illustrative_flat_110_"+("ats" if kind=="ATS" else "totals")+"_roi_pct"
    v=row[k]
    return f"{float(v):+.1f}%" if str(v).strip() else "—"

model_order=(("baseline","Baseline"),("injury","Injury"))
st.info(
    f"**{df.loc[df.score_status.eq('FINAL'),'game_id'].nunique()} completed NFL games graded**, "
    f"{df.loc[df.score_status.eq('PENDING'),'game_id'].nunique()} awaiting final scores. "
    "Week 9's Baseline is a retrospective research comparator, excluded from the published "
    "cumulative Baseline record. Miami's rookie QB adjustment is flagged as uncalibrated."
)

cols=st.columns(4)
for col,(model,name),kind in zip(cols,
        (model_order[0],model_order[1],model_order[0],model_order[1]),
        ("ATS","ATS","Totals","Totals")):
    row=get_summary("ALL",model)
    with col:
        st.metric(name+" "+kind,record(row,kind))
        pct=row["ats_win_pct" if kind=="ATS" else "totals_win_pct"]
        st.caption(
            f"{float(pct):.1f}% decisive wins · {roi(row,kind)} illustrative -110 ROI"
            if str(pct).strip() else "No graded decisive games"
        )
        st.caption(f"{int(row.games_final)} completed · {int(row.games_pending)} pending")

st.subheader("Week-by-week performance")
weekly=[]
weeks=sorted((int(x) for x in summary.week.unique() if str(x).isdigit()),reverse=True)
for w in weeks:
    b=get_summary(w,"baseline","RESEARCH_COMPARATOR" if w==9 else "PUBLIC_PUBLISHED")
    i=get_summary(w,"injury")
    weekly.append({
        "Week":w,
        "Baseline ATS":record(b,"ATS")+("*" if w==9 else ""),
        "Injury ATS":record(i,"ATS"),
        "Baseline totals":record(b,"Totals")+("*" if w==9 else ""),
        "Injury totals":record(i,"Totals"),
        "Graded / Games":f"{int(i.games_final)}/{int(i.games_expected)}",
        "Injury ATS ROI*":roi(i,"ATS"),
        "Injury totals ROI*":roi(i,"Totals"),
    })
st.dataframe(pd.DataFrame(weekly),hide_index=True,width="stretch")
st.caption(
    "*Week 9 Baseline is retrospective research and not included in the cumulative "
    "published Baseline record. ROI figures assume a theoretical flat -110 price "
    "for every directional lean; they are not actual betting returns."
)

st.subheader("Game-by-game results")
col_week,col_day=st.columns(2)
with col_week:
    chosen=st.selectbox("Week",options=["All weeks"]+["Week "+str(w) for w in weeks])
with col_day:
    day=st.selectbox("Game day",options=["All game days","Thursday","Sunday","Monday"])
view=df.copy()
if chosen!="All weeks":
    view=view.loc[pd.to_numeric(view.week,errors="coerce").eq(int(chosen.split()[-1]))]
if day!="All game days":
    view=view.loc[view.day.eq(day)]
game_rows=[]
by_game=view.groupby("game_id",sort=False)
for game,group in by_game:
    if len(group)!=2 or set(group.model)!={"injury","baseline"}:
        st.error(f"Missing model pair for {game}")
        st.stop()
    injury=group.loc[group.model.eq("injury")].iloc[0]
    baseline=group.loc[group.model.eq("baseline")].iloc[0]
    if injury.score_status!=baseline.score_status:
        st.error(f"Model status discrepancy for {game}")
        st.stop()
    status=injury.score_status
    spread=float(injury.home_favored_spread)
    favorite=injury.home_team if spread>0 else injury.away_team
    market=(f"{favorite} -{abs(spread):g}" if spread else "PK")+f" / {float(injury.bovada_total):g}"
    final=(f"{injury.away_team} {int(injury.actual_away)} – "
           f"{injury.home_team} {int(injury.actual_home)}") if status=="FINAL" else "Pending"
    research=" [research]" if baseline.record_class=="RESEARCH_COMPARATOR" else ""
    unreliable=" · uncalibrated QB" if "NOT CALIBRATED" in injury.source_warning else ""
    game_rows.append({
        "Week":int(injury.week),
        "Day":injury.day,
        "Matchup":f"{injury.away_team} @ {injury.home_team}",
        "Final":final,
        "Bovada":market,
        "Baseline ATS / totals":f"{baseline.ats_result} / {baseline.total_result}{research}",
        "Injury ATS / totals":f"{injury.ats_result} / {injury.total_result}{unreliable}",
        "Injury forecast version":Path(injury.forecast_file).name,
        "Final score source":injury.score_source_url if status=="FINAL" else "",
        "_kickoff":injury.kickoff_utc,
    })
game_rows.sort(key=lambda r:(r["Week"],r["_kickoff"],r["Matchup"]),reverse=True)
if game_rows:
    show=pd.DataFrame(game_rows).drop(columns=["_kickoff"])
    st.dataframe(show,hide_index=True,width="stretch",height=560)
else:
    st.info("No published games match the selected filters.")

st.caption(
    "The grader chooses the latest separately archived model forecast captured "
    "before each kickoff, together with the latest archived user-provided Bovada "
    "line before kickoff. No result is graded until the public scoreboard marks "
    "it FINAL. Previous graded final scores, market lines and selected model "
    "versions cannot be silently overwritten."
)
st.markdown(
    "[View complete audited model results]("+MARKET+"nfl_2026_graded_games.csv) · "
    "[View weekly and cumulative summary]("+MARKET+"nfl_2026_results_summary.csv)"
)
st.page_link("pages/Week_10_Projection_Board.py",label="View Week 10 projections",icon=":material/sports_football:")
