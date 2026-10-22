import pandas as pd
import streamlit as st
from datetime import date
from model import load_schedule_data, load_pbp, build_efficiency_model_dataset, chronological_backtest, baseline_projection

st.set_page_config(page_title="Sports Model | NFL", page_icon="🏈", layout="wide")
st.title("Sports Model")
st.caption("NFL projections • Transparent methodology • Public record")
st.warning(
    "EXPERIMENTAL — This version adds EPA/play and success-rate features and a chronological backtest. "
    "It is not yet a validated betting model. No live odds or injury adjustments are included."
)

with st.sidebar:
    st.header("Model settings")
    season = st.selectbox("Projection season", [2026, 2025, 2024, 2023, 2022], index=0)
    lookback = st.slider("Recent team games for efficiency", 4, 16, 10)
    run_backtest = st.button("Run historical backtest", type="primary")
    st.caption("Backtesting can take a few minutes on first run because historical play-by-play data must download.")

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
projections = baseline_projection(games, season=season, lookback=6)
if not projections.empty:
    projections["gameday"] = pd.to_datetime(projections["gameday"], errors="coerce")
    projections = projections[projections["gameday"] >= today].copy()

a,b,c = st.columns(3)
a.metric("Games in schedule feed", f"{len(season_games):,}")
b.metric("Completed games", f"{int((season_games['home_score'].notna() & season_games['away_score'].notna()).sum()):,}")
c.metric("Upcoming games", f"{len(projections):,}")

st.subheader(f"{season} schedule and baseline projections")
if projections.empty:
    st.info("No upcoming games found for this season.")
else:
    display=projections.copy()
    display["Date"]=pd.to_datetime(display["gameday"],errors="coerce").dt.strftime("%a, %b %d")
    display["Matchup"]=display["away_team"].astype(str)+" at "+display["home_team"].astype(str)
    display["Projected score"]=display["away_team"].astype(str)+" "+display["projected_away"].round(1).astype(str)+" — "+display["home_team"].astype(str)+" "+display["projected_home"].round(1).astype(str)
    display["Model home spread"]=display["model_home_spread"].map(lambda x:f"{x:+.1f}")
    display["Projected total"]=display["projected_total"].map(lambda x:f"{x:.1f}")
    st.dataframe(display[["Date","Matchup","Projected score","Model home spread","Projected total"]],use_container_width=True,hide_index=True)
    choice=st.selectbox("Game breakdown",display["Matchup"].tolist())
    g=display.loc[display["Matchup"]==choice].iloc[0]
    x,y,z=st.columns(3)
    x.metric("Projected score",f'{g["projected_away"]:.1f} – {g["projected_home"]:.1f}')
    y.metric("Model home spread",f'{g["model_home_spread"]:+.1f}')
    z.metric("Projected total",f'{g["projected_total"]:.1f}')

st.divider()
st.subheader("Efficiency model & historical validation")
st.write(
    "This experimental model uses offensive EPA/play, offensive success rate, defensive EPA allowed, "
    "and defensive success rate allowed. Features for each game are built only from earlier games. "
    "A Ridge regression is evaluated in chronological weekly blocks."
)
st.info("First run downloads play-by-play files for 2021–2025. Historical backtest results are model diagnostics, not proof of betting profitability.")

if run_backtest:
    try:
        with st.spinner("Building efficiency features and running chronological backtest..."):
            pbp=get_pbp()
            dataset=build_efficiency_model_dataset(games,pbp,lookback_games=lookback)
            results=chronological_backtest(dataset,min_train_games=500)
        p=results["predictions"]
        m1,m2,m3,m4=st.columns(4)
        m1.metric("Out-of-sample games",f'{results["n"]:,}')
        m2.metric("Home score MAE",f'{results["home_mae"]:.2f} pts')
        m3.metric("Away score MAE",f'{results["away_mae"]:.2f} pts')
        m4.metric("Home score RMSE",f'{results["home_rmse"]:.2f} pts')
        st.metric("Away score RMSE",f'{results["away_rmse"]:.2f} pts')
        st.caption("MAE = average absolute score prediction error; RMSE penalizes larger misses more heavily.")
        st.dataframe(
            p[["gameday","away_team","home_team","pred_away_score","away_score","pred_home_score","home_score"]]
            .tail(50).sort_values("gameday",ascending=False),
            use_container_width=True,hide_index=True
        )
        st.download_button("Download backtest predictions CSV",p.to_csv(index=False).encode("utf-8"),"nfl_backtest_predictions.csv","text/csv")
    except Exception as e:
        st.error("The backtest did not complete. This may be due to a changed data feed or a schema difference.")
        st.code(str(e))

with st.expander("Methodology and limitations"):
    st.markdown("""
    - EPA/play measures expected-points value added per play.
    - Success rate is the share of plays meeting a down-and-distance success threshold as encoded in the source data.
    - Defensive metrics describe efficiency allowed; lower EPA allowed is generally better.
    - The model uses a Ridge regression to reduce overfitting among correlated inputs.
    - Testing is chronological, but the pipeline still needs further auditing for point-in-time integrity and comparison against simple baselines.
    - No betting recommendations or performance record should be published until the model is prospectively tracked with timestamped odds.
    """)
    st.markdown("[nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")
st.caption("Prototype v0.5 • Experimental efficiency model • Not betting advice")
