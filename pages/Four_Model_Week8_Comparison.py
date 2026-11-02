from pathlib import Path
import json
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "four_model_week08" / "week08_four_model_comparison.csv"
SUMMARY = ROOT / "data" / "four_model_week08" / "week08_four_model_summary.json"

st.set_page_config(page_title="NFL Week 8 Model Comparison", page_icon="🏈", layout="wide")
st.title("NFL Week 8 — Four-Model Comparison")
st.caption("All 14 games · One Bovada market board · Four model versions")

if not DATA.exists():
    st.warning("The Week 8 comparison data has not been generated yet. Run the Four-Model Comparison workflow.")
    st.stop()

df = pd.read_csv(DATA)
required = {"matchup", "market_favorite", "market_spread_points", "market_total"}
if not required.issubset(df.columns):
    st.error("The comparison file is missing required market fields.")
    st.stop()

MODEL_LABELS = [
    ("baseline", "Baseline"),
    ("injury", "Injury"),
    ("efficiency", "Efficiency"),
    ("combined", "Combined"),
]

def record(part: pd.DataFrame, model: str, market: str) -> str:
    col = f"{model}_{market}_result"
    if col not in part:
        return "—"
    wins = int((part[col] == "Win").sum())
    losses = int((part[col] == "Loss").sum())
    pushes = int((part[col] == "Push").sum())
    pending = int((part[col] == "Pending").sum())
    decided = wins + losses
    result = f"{wins}-{losses}"
    if pushes:
        result += f" · {pushes} push"
    if pending:
        result += f" · {pending} pending"
    if decided:
        result += f" · {wins / decided:.1%}"
    return result

def display_table(part: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in part.sort_values(["date", "matchup"]).iterrows():
        actual = "Pending"
        if pd.notna(r.get("actual_away_score")) and pd.notna(r.get("actual_home_score")):
            actual = f'{r["away_team"]} {r["actual_away_score"]:g} — {r["home_team"]} {r["actual_home_score"]:g}'
        favorite = str(r["market_favorite"])
        spread = float(r["market_spread_points"])
        dog = r["away_team"] if favorite == r["home_team"] else r["home_team"]
        market = f'{favorite} -{spread:g} / {dog} +{spread:g} · O/U {float(r["market_total"]):g}'
        item = {"Date": r.get("date", ""), "Matchup": r["matchup"], "Bovada": market, "Final": actual}
        for model, label in MODEL_LABELS:
            away_score = float(r[f"{model}_away_score"])
            home_score = float(r[f"{model}_home_score"])
            projected_total = float(r[f"{model}_projected_total"])
            ats = str(r[f"{model}_ats_pick"])
            total_pick = str(r[f"{model}_total_pick"])
            ats_result = str(r.get(f"{model}_ats_result", ""))
            total_result = str(r.get(f"{model}_total_result", ""))
            item[label] = (
                f'{r["away_team"]} {away_score:.1f} — {r["home_team"]} {home_score:.1f}\n'
                f'{ats} ({ats_result})\n'
                f'{total_pick} {projected_total:.1f} ({total_result})'
            )
        rows.append(item)
    return pd.DataFrame(rows)

# A strict completeness check prevents a partial slate from looking finished.
matchups = set(df["matchup"].astype(str))
if len(df) != 14 or len(matchups) != 14:
    st.error(f"Expected 14 unique Week 8 games; found {len(df)} rows and {len(matchups)} unique matchups.")
    st.dataframe(df[["matchup"]], hide_index=True)
    st.stop()

st.subheader("Weekly results")
summary_cols = st.columns(4)
for col, (model, label) in zip(summary_cols, MODEL_LABELS):
    with col:
        st.markdown(f"**{label}**")
        st.metric("ATS", record(df, model, "ats"))
        st.metric("Totals", record(df, model, "total"))

st.subheader("All 14 games")
st.caption("Each model cell shows projected score, ATS lean and result, then projected total direction and points with result. Bovada lines are the same user-verified lines for every model.")
st.dataframe(
    display_table(df),
    hide_index=True,
    use_container_width=True,
    column_config={
        "Date": st.column_config.TextColumn("Date", width="small"),
        "Matchup": st.column_config.TextColumn("Game", width="small"),
        "Bovada": st.column_config.TextColumn("Bovada line", width="medium"),
        "Final": st.column_config.TextColumn("Final score", width="medium"),
        "Baseline": st.column_config.TextColumn("Baseline", width="large"),
        "Injury": st.column_config.TextColumn("Injury", width="large"),
        "Efficiency": st.column_config.TextColumn("Efficiency", width="large"),
        "Combined": st.column_config.TextColumn("Combined", width="large"),
    },
)

with st.expander("How to read this comparison"):
    st.markdown(
        """
        - **Baseline:** original model feature set.
        - **Injury:** baseline plus the injury feature block.
        - **Efficiency:** baseline plus passing/rushing efficiency features.
        - **Combined:** efficiency and injury features together.
        - Each model's score is shown as away team points — home team points.
        - ATS results grade the displayed ATS lean against the Bovada spread shown in the same row.
        - Total results grade the displayed Over/Under direction against that row's Bovada total.
        - Original Baseline and Injury projections are preserved from the frozen public snapshot where available. Games missing from that snapshot are chronological research reconstructions. Bears-Seahawks uses its saved pregame four-model forecast.
        - This is a research comparison, not betting advice or a change to the official prospective record.
        """
    )
    st.markdown("[Frozen original Week 8 public snapshot](https://github.com/tedgytrends-bit/sports-betting-model/blob/main/data/public_snapshots/nfl_week_08_public_2026-11-01.csv)")
