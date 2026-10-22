import pandas as pd
import streamlit as st
from model import load_schedule_data, build_baseline_projections, summarize_record

st.set_page_config(page_title="Sports Model | NFL", page_icon="🏈", layout="wide")

st.title("Sports Model")
st.caption("NFL projections • Transparent methodology • Public record")

st.warning(
    "Experimental baseline only. These projections use historical team scoring averages, "
    "not a validated betting model. No injury adjustments or live sportsbook odds are included. "
    "Do not treat these outputs as betting advice."
)

with st.sidebar:
    st.header("Model settings")
    season = st.selectbox("Season", [2026, 2025, 2024, 2023, 2022], index=0)
    lookback = st.slider("Recent games used per team", min_value=3, max_value=12, value=6)
    st.caption("The baseline uses completed games before each matchup. Future game results are excluded.")

@st.cache_data(ttl=1800, show_spinner="Loading public NFL schedule and results...")
def get_data():
    return load_schedule_data()

try:
    games = get_data()
except Exception as e:
    st.error("Couldn't load the public NFL schedule data. Try refreshing the app in a minute.")
    st.code(str(e))
    st.markdown("[Open the nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")
    st.stop()

if games.empty:
    st.error("The data source returned no games.")
    st.stop()

projections = build_baseline_projections(games, season=season, lookback=lookback)

# Grade a simple closing-spread baseline only where a spread exists in the data.
graded = games[
    games["home_score"].notna()
    & games["away_score"].notna()
    & games["spread_line"].notna()
].copy()
if not graded.empty:
    graded["home_margin"] = graded["home_score"] - graded["away_score"]
    # nflverse spread_line convention: positive value means home team favored.
    graded["home_cover_margin"] = graded["home_margin"] - graded["spread_line"]
    graded["ats_result"] = graded["home_cover_margin"].apply(
        lambda x: "W" if x > 0 else ("L" if x < 0 else "P")
    )
    rec = summarize_record(graded["ats_result"].tolist())
else:
    rec = {"W": 0, "L": 0, "P": 0}

c1, c2, c3 = st.columns(3)
c1.metric("Historical games with a listed spread", f"{len(graded):,}")
c2.metric("Market result sample", f'{rec["W"]}-{rec["L"]}-{rec["P"]}')
c3.metric("Projection status", "Baseline / unvalidated")

st.caption(
    "The historical ATS sample above describes recorded game outcomes against the spread_line field "
    "in the data source. It is not the model's record and should not be interpreted as its performance."
)

st.subheader(f"{season} schedule and score projections")
if projections.empty:
    st.info("No upcoming games found for this season in the current schedule feed.")
else:
    display = projections.copy()
    display["Projected away score"] = display["projected_away"].round(1)
    display["Projected home score"] = display["projected_home"].round(1)
    display["Model home spread"] = display["model_home_spread"].round(1)
    display["Projected total"] = display["projected_total"].round(1)
    cols = ["gameday", "away_team", "home_team", "Projected away score",
            "Projected home score", "Model home spread", "Projected total"]
    if "spread_line" in display.columns:
        cols.append("spread_line")
    if "total_line" in display.columns:
        cols.append("total_line")
    st.dataframe(display[cols], use_container_width=True, hide_index=True)

    display["matchup"] = display["away_team"] + " at " + display["home_team"]
    choice = st.selectbox("Game breakdown", display["matchup"].tolist())
    g = display.loc[display["matchup"] == choice].iloc[0]
    st.markdown("### " + choice)
    a, b, c = st.columns(3)
    a.metric("Projected score", f'{g["projected_away"]:.1f} – {g["projected_home"]:.1f}')
    b.metric("Model home spread", f'{g["model_home_spread"]:+.1f}')
    c.metric("Projected total", f'{g["projected_total"]:.1f}')
    st.markdown("**How this baseline works**")
    st.write(
        f"The model averages each team's points scored and points allowed over its last "
        f"{lookback} completed games before this matchup, then blends the team's offense "
        "with the opponent's points-allowed average. A small home-field adjustment is included. "
        "This is a transparent starting benchmark, not the final model."
    )
    st.write(
        "Not yet included: EPA/play, success rate, quarterback or other injuries, weather, "
        "rest adjustments, point-in-time odds, uncertainty estimates, or trained model weights."
    )

with st.expander("Data source and methodology"):
    st.markdown(
        """
        - **Data source:** nflverse public NFL schedule/results data.
        - **Projection:** recent points scored blended with recent points allowed.
        - **Home field:** fixed small baseline adjustment, which must be estimated and tested.
        - **Important:** a simple scoring-average model can be weak and is not evidence of a betting edge.
        - **Validation still required:** chronological walk-forward testing, no future-data leakage,
          odds timestamping, prospective tracking, and comparison with a market baseline.
        """
    )
    st.markdown("[nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")
    st.markdown("[nflverse data update documentation](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)")

st.caption("Version 0.2 • Experimental baseline • All projections should be timestamped before kickoff.")
