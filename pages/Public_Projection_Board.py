from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "public_snapshots" / "nfl_week_08_public_2026-11-01.csv"

st.set_page_config(page_title="NFL Public Projections", page_icon="🏈", layout="wide")

st.title("NFL Week 8 — Public Projections")
st.caption("Experimental model research • Published for transparency and feedback")

st.warning(
    "**Not intended for betting.** These are experimental research projections, "
    "not betting recommendations. The injury-aware version is being evaluated "
    "against the baseline; its incremental value has not been established."
)

if not SNAPSHOT.exists():
    st.error("The published projection snapshot is unavailable.")
    st.stop()

df = pd.read_csv(SNAPSHOT)
st.dataframe(
    df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Official Bovada Total": st.column_config.TextColumn("Official Bovada Total"),
        "Baseline Total Projection": st.column_config.TextColumn("Baseline Total"),
        "Injury Total Projection": st.column_config.TextColumn("Injury Total"),
    },
)

st.caption(
    "Baseline = model without the current injury-report feature block. "
    "Injury = paired model using the same training data with the injury-report "
    "feature block added. ATS columns show the model's side/line lean; total "
    "columns show projected combined points."
)
st.caption(
    "Model calculation time: November 1, 2026 at 10:54:23 a.m. Central. "
    "The exact public snapshot is stored in the linked GitHub repository; "
    "its commit history provides the publication timestamp and revision record."
)
st.markdown(
    "[View the immutable CSV snapshot](https://github.com/tedgytrends-bit/sports-betting-model/blob/main/data/public_snapshots/nfl_week_08_public_2026-11-01.csv) "
    " · [View its commit history](https://github.com/tedgytrends-bit/sports-betting-model/commits/main/data/public_snapshots/nfl_week_08_public_2026-11-01.csv)"
)
