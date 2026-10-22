import pandas as pd
import streamlit as st
from model import GameProjection

st.set_page_config(page_title="Sports Model | NFL", page_icon="🏈", layout="wide")

st.title("Sports Model")
st.caption("NFL projections • Transparent methodology • Public record")

st.info(
    "Prototype dashboard only. The games below are fictional examples used to test "
    "the layout; they are not current predictions and must not be used as betting advice."
)

c1, c2, c3 = st.columns(3)
c1.metric("ATS record", "—", help="Will populate from the audited game ledger.")
c2.metric("Units", "—", help="Will use a documented stake and odds convention.")
c3.metric("ROI", "—", help="Will populate only after results and prices are recorded.")

st.subheader("Weekly projections")
st.write("Select a game to see the score projection, market comparison, and explanation.")

# Fictional display examples, deliberately labeled and not tied to real fixtures.
sample_games = [
    {
        "Away": "Example Away Team",
        "Home": "Example Home Team",
        "Away score": 21.4,
        "Home score": 24.8,
        "Market home spread": -3.5,
        "Market total": 45.5,
        "Status": "Fictional example",
    },
    {
        "Away": "Sample University",
        "Home": "Demo State",
        "Away score": 27.1,
        "Home score": 23.6,
        "Market home spread": 2.5,
        "Market total": 49.0,
        "Status": "Fictional example",
    },
]
df = pd.DataFrame(sample_games)
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("Game breakdown preview")
choice = st.selectbox("Choose a sample game", df["Away"] + " at " + df["Home"])
row = df.loc[(df["Away"] + " at " + df["Home"]) == choice].iloc[0]
projection = GameProjection(
    away_team=row["Away"],
    home_team=row["Home"],
    away_points=float(row["Away score"]),
    home_points=float(row["Home score"]),
    market_home_spread=float(row["Market home spread"]),
    market_total=float(row["Market total"]),
)

a, b, c = st.columns(3)
a.metric("Projected score", f"{projection.away_points:.1f} – {projection.home_points:.1f}")
b.metric("Model home spread", f"{projection.model_home_spread:+.1f}")
c.metric("Projected total", f"{projection.projected_total:.1f}")

st.markdown("#### Why the model likes this side")
st.write(
    "This section will explain the actual model inputs after the data pipeline is connected: "
    "offensive efficiency, defensive efficiency, opponent adjustment, injuries, rest, "
    "weather where relevant, and market context. No explanation should be generated unless "
    "it can be traced to measured inputs."
)

st.caption(
    "Recommended pick will be a model output, not an instruction to bet. "
    "Every published projection should be timestamped and preserved for public grading."
)

with st.expander("Model methodology and record rules"):
    st.markdown(
        """
        - Projections must be generated from information available before kickoff.
        - The market line and its timestamp must be saved alongside each projection.
        - Backtests and live prospective results must be reported separately.
        - The public record must include wins, losses, pushes, passes/no-bets, and sample size.
        - ROI must account for the actual odds and documented staking rules.
        """
    )
