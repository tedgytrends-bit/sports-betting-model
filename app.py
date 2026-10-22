import pandas as pd
import streamlit as st
from model import load_schedule_data, build_baseline_projections

st.set_page_config(page_title="Sports Model | NFL", page_icon="🏈", layout="wide")

st.title("Sports Model")
st.caption("NFL projections • Transparent methodology • Public record")

st.warning(
    "EXPERIMENTAL BASELINE — Scores are preliminary estimates based on recent scoring and points allowed. "
    "This is not a validated betting model. Injury adjustments, verified live odds, and out-of-sample "
    "validation are not yet included. Do not treat these estimates as betting advice."
)

with st.sidebar:
    st.header("Projection settings")
    season = st.selectbox("Season", [2026, 2025, 2024, 2023, 2022], index=0)
    lookback = st.slider("Recent completed games per team", 3, 12, 6)
    st.caption("Each projection uses games played before the scheduled matchup.")

@st.cache_data(ttl=1800, show_spinner="Loading NFL schedule and results...")
def get_data():
    return load_schedule_data()

try:
    games = get_data()
except Exception as e:
    st.error("Couldn't load the NFL data feed. Refresh the app in a minute. If it continues, send this error to ChatGPT.")
    st.code(str(e))
    st.markdown("[View nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")
    st.stop()

if games.empty:
    st.error("The data source returned no games.")
    st.stop()

season_games = games[games["season"] == season].copy()
projections = build_baseline_projections(games, season=season, lookback=lookback)

completed_count = int(
    (season_games["home_score"].notna() & season_games["away_score"].notna()).sum()
)
scheduled_count = int(len(season_games))
upcoming_count = int(len(projections))

m1, m2, m3 = st.columns(3)
m1.metric("Games in schedule feed", f"{scheduled_count:,}")
m2.metric("Completed games", f"{completed_count:,}")
m3.metric("Upcoming projections", f"{upcoming_count:,}")

st.caption(
    "These counts describe the data feed, not model performance. We will publish an ATS record only "
    "after every eligible model recommendation is timestamped and graded under documented rules."
)

st.subheader(f"{season} projections")
if projections.empty:
    st.info(
        "No upcoming games could be projected from the current feed for this season. "
        "Check the season selector or refresh the app."
    )
else:
    display = projections.copy()
    display["Date"] = pd.to_datetime(display["gameday"], errors="coerce").dt.strftime("%a, %b %d")
    display["Matchup"] = display["away_team"].astype(str) + " at " + display["home_team"].astype(str)
    display["Projected score"] = (
        display["away_team"].astype(str) + " " + display["projected_away"].round(1).astype(str)
        + " — " + display["home_team"].astype(str) + " " + display["projected_home"].round(1).astype(str)
    )
    display["Model home spread"] = display["model_home_spread"].map(lambda x: f"{x:+.1f}")
    display["Projected total"] = display["projected_total"].map(lambda x: f"{x:.1f}")
    display = display.sort_values("gameday")
    st.dataframe(
        display[["Date", "Matchup", "Projected score", "Model home spread", "Projected total"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date": st.column_config.TextColumn("Date", width="small"),
            "Matchup": st.column_config.TextColumn("Matchup", width="medium"),
            "Projected score": st.column_config.TextColumn("Projected score", width="large"),
            "Model home spread": st.column_config.TextColumn("Model home spread", width="small"),
            "Projected total": st.column_config.TextColumn("Projected total", width="small"),
        },
    )

    st.subheader("Game breakdown")
    matchups = display["Matchup"].tolist()
    selected_matchup = st.selectbox("Select a matchup", matchups)
    g = display.loc[display["Matchup"] == selected_matchup].iloc[0]

    a, b, c = st.columns(3)
    a.metric("Projected score", f'{g["projected_away"]:.1f} – {g["projected_home"]:.1f}')
    b.metric("Model home spread", f'{g["model_home_spread"]:+.1f}')
    c.metric("Projected total", f'{g["projected_total"]:.1f}')

    with st.expander("Why does the baseline project this score?", expanded=True):
        st.write(
            f"For this matchup, the baseline uses each team's average points scored and allowed "
            f"over its last {lookback} completed games available before kickoff. It blends the "
            "away team's scoring average with the home team's points-allowed average, and vice versa. "
            "A fixed 1.5-point home adjustment is currently applied."
        )
        st.write(
            "**Not included yet:** opponent-adjusted EPA/play, success rate, quarterback and other "
            "injury impacts, weather, rest, verified sportsbook lines, calibrated probabilities, "
            "or model uncertainty. The fixed home adjustment and lookback window must be evaluated "
            "using chronological backtests before this baseline is considered useful."
        )

with st.expander("Methodology, data and record policy"):
    st.markdown(
        """
        **Current model:** transparent scoring-average baseline; not yet validated.

        **Data source:** public NFL schedule/results data retrieved from nflverse-related releases.

        **Record policy:** we will not present the raw historical spread tally as the model's record.
        A model record will include only timestamped recommendations made before kickoff, the exact
        line and odds available at publication, final results, pushes, and documented grading rules.

        **Next development steps:** validate the feed, build point-in-time team-efficiency features,
        run chronological walk-forward backtests, add permitted odds and current injury data, and
        preserve a permanent record of every published projection.
        """
    )
    st.markdown("[nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")

st.caption("Prototype v0.3 • Experimental projections • Not betting advice")
