from pathlib import Path
import json
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "four_model_week08" / "week08_four_model_comparison.csv"
SUMMARY = ROOT / "data" / "four_model_week08" / "week08_four_model_summary.json"

st.set_page_config(page_title="NFL Four-Model Comparison", page_icon="🏈", layout="wide")
st.title("NFL Week 8 — Four-Model Comparison")
st.caption("A transparent comparison of four research model variants. Not betting advice.")

st.info(
    "The original Baseline and Injury projections below are preserved from the November 1 public snapshot. "
    "Efficiency and Combined are chronological reconstructions using only pregame information. "
    "Bears–Seahawks is included in this same Week 8 comparison and clearly labeled as a late-added forecast."
)

if not DATA.exists():
    st.warning("The Week 8 four-model comparison has not been generated yet.")
    st.stop()

df = pd.read_csv(DATA)
if SUMMARY.exists():
    with SUMMARY.open(encoding="utf-8") as f:
        report = json.load(f)
    omitted = report.get("schedule_games_not_on_original_board", [])
    if omitted:
        st.caption(
            "Week 8 schedule games not included in the frozen November 1 public board "
            f"(not projected or counted here): {', '.join(omitted)}."
        )
original = df[df["publication_status"].eq("Original Nov. 1 public snapshot")].copy()
late = df[df["publication_status"].str.startswith("Late-added", na=False)].copy()

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
    graded = part[part[col].isin(["Win", "Loss"])]
    wins = int((graded[col] == "Win").sum())
    losses = int((graded[col] == "Loss").sum())
    pushes = int((part[col] == "Push").sum())
    pending = int((part[col] == "Pending").sum())
    decided = wins + losses
    pct = f" · {wins / decided:.0%}" if decided else ""
    suffix = f" · {pushes} push" if pushes else ""
    if pending:
        suffix += f" · {pending} pending"
    return f"{wins}-{losses}{suffix}{pct}"


def display_table(part: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in part.sort_values(["date", "matchup"]).iterrows():
        actual = "Pending"
        if pd.notna(r.get("actual_away_score")) and pd.notna(r.get("actual_home_score")):
            actual = (
                f'{r["away_team"]} {r["actual_away_score"]:g} — '
                f'{r["home_team"]} {r["actual_home_score"]:g}'
            )
        item = {
            "Date": r.get("date", ""),
            "Matchup": r["matchup"],
            "Publication": "Late-added" if str(r.get("publication_status", "")).startswith("Late-added") else "Original board",
            "Final": actual,
        }
        for model, label in MODEL_LABELS:
            away_score = float(r[f"{model}_away_score"])
            home_score = float(r[f"{model}_home_score"])
            score = f'{r["away_team"]} {away_score:.1f} — {r["home_team"]} {home_score:.1f}'
            total = float(r[f"{model}_projected_total"])
            total_pick = str(r[f"{model}_total_pick"])
            total_text = f"{total_pick} {total:.1f}"
            ats = str(r[f"{model}_ats_pick"])
            ats_result = str(r.get(f"{model}_ats_result", ""))
            total_result = str(r.get(f"{model}_total_result", ""))
            item[label] = (
                f"{score}\n{ats} · {ats_result}\n{total_text} · {total_result}"
            )
        rows.append(item)
    return pd.DataFrame(rows)


def summary_block(part: pd.DataFrame, heading: str) -> None:
    st.subheader(heading)
    cols = st.columns(4)
    for col, (model, label) in zip(cols, MODEL_LABELS):
        with col:
            st.markdown(f"**{label}**")
            st.metric("ATS", record(part, model, "ats"))
            st.metric("Totals", record(part, model, "total"))


all_week8 = pd.concat([original, late], ignore_index=True)
summary_block(all_week8, "Week 8 results · All 13 included matchups")
st.caption(
    "All Week 8 matchups appear together below. The Publication column distinguishes the 12 games "
    "on the original November 1 board from Bears–Seahawks, which was added November 2 before kickoff. "
    "Each model cell shows projected score, ATS pick/result, then total direction and projected points/result. "
    "ATS grading uses the displayed pick; totals are graded against the recorded Bovada total."
)
st.dataframe(
    display_table(all_week8),
    hide_index=True,
    use_container_width=True,
    column_config={
        "Date": st.column_config.TextColumn("Date", width="small"),
        "Matchup": st.column_config.TextColumn("Matchup", width="small"),
        "Publication": st.column_config.TextColumn("Publication", width="small"),
        "Final": st.column_config.TextColumn("Final score", width="medium"),
        "Baseline": st.column_config.TextColumn("Baseline", width="large"),
        "Injury": st.column_config.TextColumn("Injury", width="large"),
        "Efficiency": st.column_config.TextColumn("Efficiency", width="large"),
        "Combined": st.column_config.TextColumn("Combined", width="large"),
    },
)

with st.expander("Methodology and publication history"):
    st.markdown(
        """
        - **Baseline:** the exact score, ATS, and total projections published in the November 1 snapshot.
        - **Injury:** the exact injury-aware score, ATS, and total projections published in that same snapshot.
        - **Efficiency:** reconstructed chronologically for the Week 8 test week, using training games strictly before that week's first game.
        - **Combined:** the same chronological process with the passing/rushing efficiency and injury feature blocks.
        - **Bears–Seahawks:** included in the Week 8 comparison as a late-added November 2 pregame forecast; the Publication label distinguishes it from the original November 1 board. It is not retroactively represented as part of that original publication.
        - The comparison is research transparency, not proof of profitability. No official prospective record or production model is changed.
        """
    )
    st.markdown(
        "[Original immutable Week 8 public snapshot](https://github.com/tedgytrends-bit/sports-betting-model/blob/main/data/public_snapshots/nfl_week_08_public_2026-11-01.csv)"
    )
