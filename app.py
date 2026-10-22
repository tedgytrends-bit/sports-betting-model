import pandas as pd
import streamlit as st
from datetime import date
from model import (
    load_schedule_data,
    load_pbp,
    build_efficiency_model_dataset,
    chronological_backtest,
    baseline_projection,
    add_scoring_baseline_predictions,
    score_prediction_metrics,
)

st.set_page_config(page_title="Sports Model | NFL", page_icon="🏈", layout="wide")
st.title("Sports Model")
st.caption("NFL projections • Transparent methodology • Public record")
st.warning(
    "EXPERIMENTAL — This version adds a same-game baseline comparison. "
    "It is not a validated betting model. No live odds or injury adjustments are included."
)

with st.sidebar:
    st.header("Model settings")
    season = st.selectbox("Projection season", [2026, 2025, 2024, 2023, 2022], index=0)
    lookback = st.slider("Recent team games for efficiency", 4, 16, 10)
    show_full_schedule = st.checkbox("Show full remaining season", value=False)
    run_backtest = st.button("Run historical backtest", type="primary")
    st.caption("Default view: games in the next 14 days. The backtest downloads several seasons of play-by-play.")

@st.cache_data(ttl=1800, show_spinner="Loading NFL schedule and results...")
def get_schedule():
    return load_schedule_data()

@st.cache_data(ttl=3600, show_spinner="Downloading historical NFL play-by-play...")
def get_pbp():
    return load_pbp((2021, 2022, 2023, 2024, 2025))

try:
    games = get_schedule()
except Exception as e:
    st.error("Could not load the NFL schedule data.")
    st.code(str(e))
    st.stop()

today = pd.Timestamp(date.today())
season_games = games[games["season"] == season].copy()
all_projections = baseline_projection(games, season=season, lookback=6)
if not all_projections.empty:
    all_projections["gameday"] = pd.to_datetime(all_projections["gameday"], errors="coerce")
    all_projections = all_projections[all_projections["gameday"] >= today].copy()

end_date = today + pd.Timedelta(days=14)
if show_full_schedule:
    projections = all_projections.copy()
else:
    projections = all_projections[all_projections["gameday"] < end_date + pd.Timedelta(days=1)].copy()

completed_count = int((season_games["home_score"].notna() & season_games["away_score"].notna()).sum())
scheduled_count = int(len(season_games))
upcoming_count = int(len(all_projections))
window_count = int(len(projections))

m1, m2, m3 = st.columns(3)
m1.metric("Games in schedule feed", f"{scheduled_count:,}")
m2.metric("Completed games", f"{completed_count:,}")
m3.metric("Projections in selected view", f"{window_count:,}")
st.caption(
    "These counts describe the data feed, not model performance. The public ATS record will only include "
    "timestamped recommendations made before kickoff and graded using documented rules."
)

heading = f"{season} projections"
heading += " · Full remaining season" if show_full_schedule else " · Next 14 days"
st.subheader(heading)

if projections.empty:
    st.info("No upcoming games found in this date window. Enable 'Show full remaining season' in the sidebar to inspect the full schedule.")
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
        width="stretch", hide_index=True,
        column_config={
            "Date": st.column_config.TextColumn("Date", width="small"),
            "Matchup": st.column_config.TextColumn("Matchup", width="medium"),
            "Projected score": st.column_config.TextColumn("Projected score", width="large"),
            "Model home spread": st.column_config.TextColumn("Model home spread", width="small"),
            "Projected total": st.column_config.TextColumn("Projected total", width="small"),
        }
    )
    st.subheader("Game breakdown")
    matchup = st.selectbox("Select a matchup", display["Matchup"].tolist())
    g = display.loc[display["Matchup"] == matchup].iloc[0]
    a, b, c = st.columns(3)
    a.metric("Projected score", f'{g["projected_away"]:.1f} – {g["projected_home"]:.1f}')
    b.metric("Model home spread", f'{g["model_home_spread"]:+.1f}')
    c.metric("Projected total", f'{g["projected_total"]:.1f}')
    with st.expander("How the current baseline works", expanded=True):
        st.write(
            "The public projection board uses recent points scored blended with the opponent's recent points allowed. "
            "A fixed 1.5-point home adjustment is applied. This is not yet the efficiency model and is not validated."
        )
        st.write(
            "Not yet included in the public board: current-season opponent-adjusted EPA/play, injuries, weather, rest, "
            "verified sportsbook odds, calibrated probabilities or model uncertainty."
        )

st.divider()
st.subheader("Efficiency model & historical validation")
st.write(
    "The historical efficiency model uses offensive EPA/play, offensive success rate, defensive EPA allowed, "
    "and defensive success rate allowed. It is evaluated chronologically by weekly blocks."
)
st.info(
    "The backtest compares the efficiency model with a simple recent-scoring baseline on the same test games. "
    "The first run downloads play-by-play data for 2021–2025 and may take several minutes."
)

if run_backtest:
    try:
        with st.spinner("Loading data, building features, and comparing models..."):
            pbp = get_pbp()
            dataset = build_efficiency_model_dataset(games, pbp, lookback_games=lookback)
            results = chronological_backtest(dataset, min_train_games=500)
            efficiency_pred = results["predictions"].copy()
            compared = add_scoring_baseline_predictions(efficiency_pred, games, lookback=6)
            metrics = score_prediction_metrics(compared, "pred_home_score", "pred_away_score")
            baseline_metrics = score_prediction_metrics(compared, "baseline_home_score", "baseline_away_score")
        st.subheader("Overall model comparison")
        st.caption(
            f"{len(compared):,} games with both models' predictions. Lower MAE/RMSE is better. "
            "This evaluates score prediction, not betting profitability."
        )
        comparison = pd.DataFrame([
            {"Model": "EPA / efficiency model", **metrics},
            {"Model": "Recent scoring baseline", **baseline_metrics},
        ])
        st.dataframe(comparison, width="stretch", hide_index=True)
        st.subheader("Efficiency model summary")
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Out-of-sample games", f'{results["n"]:,}')
        x2.metric("Home score MAE", f'{results["home_mae"]:.2f} pts')
        x3.metric("Away score MAE", f'{results["away_mae"]:.2f} pts')
        x4.metric("Home score RMSE", f'{results["home_rmse"]:.2f} pts')
        st.metric("Away score RMSE", f'{results["away_rmse"]:.2f} pts')
        st.caption("MAE is average absolute score error; RMSE penalizes large misses more heavily. Neither is ATS performance.")

        st.subheader("Season-by-season comparison")
        season_rows = []
        for yr, part in compared.groupby("season", dropna=False):
            em = score_prediction_metrics(part, "pred_home_score", "pred_away_score")
            bm = score_prediction_metrics(part, "baseline_home_score", "baseline_away_score")
            season_rows.append({
                "Season": int(yr),
                "Games": len(part),
                "Efficiency home MAE": round(em["Home MAE"], 2),
                "Baseline home MAE": round(bm["Home MAE"], 2),
                "Efficiency away MAE": round(em["Away MAE"], 2),
                "Baseline away MAE": round(bm["Away MAE"], 2),
            })
        st.dataframe(pd.DataFrame(season_rows), width="stretch", hide_index=True)

        with st.expander("Inspect latest predictions"):
            cols = ["gameday", "season", "away_team", "home_team", "pred_away_score",
                    "away_score", "pred_home_score", "home_score", "baseline_away_score", "baseline_home_score"]
            st.dataframe(compared[cols].tail(50).sort_values("gameday", ascending=False), width="stretch", hide_index=True)
        st.download_button(
            "Download comparison predictions CSV",
            compared.to_csv(index=False).encode("utf-8"),
            "nfl_backtest_comparison.csv",
            "text/csv"
        )
        st.warning(
            "Audit note: historical efficiency features are derived from 2021–2025 play-by-play. "
            "2026 rows therefore do not incorporate 2026 game-level efficiency data. Also, a better score MAE does not "
            "prove positive betting ROI; market-line testing is a separate stage."
        )
    except Exception as e:
        st.error("The backtest comparison did not complete. The dashboard should remain available.")
        st.code(f"{type(e).__name__}: {e}")

with st.expander("Methodology, data and record policy"):
    st.markdown("""
    - EPA/play measures expected-points value added per offensive play.
    - Success rate measures the share of plays meeting the source's down-and-distance success definition.
    - Defensive metrics describe EPA and success rate allowed.
    - Ridge regression reduces overfitting among correlated features.
    - The historical test is chronological, but must still be audited for data leakage and compared with simple baselines.
    - No betting record should be published until picks are prospectively timestamped with the line and odds available at publication.
    """)
    st.markdown("[nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")

st.caption("Prototype v0.5.3 • Model comparison audit • Not betting advice")
