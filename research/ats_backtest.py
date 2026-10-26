import numpy as np
import pandas as pd
import streamlit as st

from model import MODEL_VERSION, load_schedule_data, load_pbp, build_efficiency_model_dataset, chronological_backtest

st.title("NFL ATS Backtest")
st.caption(f"Experimental research page • Model v{MODEL_VERSION}")
st.warning(
    "This is a research backtest, not a validated betting system. Historical spread lines come from the public "
    "nflverse schedule feed; the exact sportsbook and time the line was available are not verified. Simulated ROI assumes -110 odds."
)
st.markdown(
    "This page tests whether the existing EPA/efficiency score model can identify ATS value. It is separate from the totals research. "
    "All eligible games are evaluated directionally; a fixed 3.5-point model edge is used for the illustrative betting record."
)
with st.expander("How to read the spread"):
    st.markdown(
        "- Positive spread_line means the home team is favored; negative means home underdog.\n"
        "- Model projected home margin = projected home score minus projected away score.\n"
        "- ATS edge = model projected home margin minus closing spread.\n"
        "- Positive edge leans home; negative edge leans away.\n"
        "- Actual home ATS margin = actual home margin minus closing spread. Positive means home covered; negative means away covered; zero is a push.\n"
        "- The rolling weekly backtest trains on games dated before each test week."
    )
    st.markdown("[nflverse schedule data documentation](https://nflreadr.nflverse.com/reference/load_schedules.html)")

@st.cache_data(ttl=1800, show_spinner=False)
def get_schedule():
    return load_schedule_data()

@st.cache_data(ttl=3600, show_spinner=False)
def get_play_by_play():
    return load_pbp((2021, 2022, 2023, 2024, 2025, 2026))

run = st.button("Run ATS backtest", type="primary")

if run:
    try:
        with st.spinner("Loading schedule and historical play-by-play..."):
            games = get_schedule()
            pbp = get_play_by_play()
        if "spread_line" not in games.columns:
            st.error("The schedule source has no spread_line field. ATS backtest cannot run.")
            st.stop()

        with st.spinner("Building pregame features and chronological predictions..."):
            dataset = build_efficiency_model_dataset(games, pbp, lookback_games=10)
            results = chronological_backtest(dataset, min_train_games=500)
            predictions = results["predictions"].copy()

        spread_cols = ["game_id", "gameday", "season", "week", "home_team", "away_team", "home_score", "away_score", "spread_line"]
        lines = games[[c for c in spread_cols if c in games.columns]].drop_duplicates("game_id")
        keep_meta = ["game_id", "pred_home_score", "pred_away_score"]
        backtest = lines.merge(predictions[keep_meta], on="game_id", how="inner", validate="one_to_one")
        for col in ["home_score", "away_score", "spread_line", "pred_home_score", "pred_away_score"]:
            if col in backtest.columns:
                backtest[col] = pd.to_numeric(backtest[col], errors="coerce")
        backtest = backtest.dropna(subset=["gameday", "home_score", "away_score", "spread_line", "pred_home_score", "pred_away_score"]).copy()
        if backtest.empty:
            st.error("No completed out-of-sample games with spread lines were available.")
            st.stop()

        backtest["actual_home_margin"] = backtest["home_score"] - backtest["away_score"]
        backtest["predicted_home_margin"] = backtest["pred_home_score"] - backtest["pred_away_score"]
        backtest["actual_home_ats_margin"] = backtest["actual_home_margin"] - backtest["spread_line"]
        backtest["model_ats_edge"] = backtest["predicted_home_margin"] - backtest["spread_line"]
        backtest["market_margin_error"] = (backtest["spread_line"] - backtest["actual_home_margin"]).abs()
        backtest["model_margin_error"] = (backtest["predicted_home_margin"] - backtest["actual_home_margin"]).abs()

        def grade(frame):
            out = frame.copy()
            out["picked_side"] = np.where(out["model_ats_edge"] > 0, "Home", "Away")
            out["result"] = np.where(
                out["actual_home_ats_margin"] == 0, "Push",
                np.where(
                    ((out["picked_side"] == "Home") & (out["actual_home_ats_margin"] > 0))
                    | ((out["picked_side"] == "Away") & (out["actual_home_ats_margin"] < 0)),
                    "Win", "Loss"
                )
            )
            return out

        def summarize(frame, label):
            wins = int((frame["result"] == "Win").sum())
            losses = int((frame["result"] == "Loss").sum())
            pushes = int((frame["result"] == "Push").sum())
            net = wins * (100 / 110) - losses
            n = len(frame)
            decided = wins + losses
            return {
                "Strategy": label, "Games / bets": n, "Wins": wins, "Losses": losses, "Pushes": pushes,
                "Win % (no pushes)": 100 * wins / decided if decided else np.nan,
                "Net units at -110": net, "ROI": 100 * net / n if n else np.nan,
            }

        st.subheader("Out-of-sample projection accuracy")
        st.caption(f"{len(backtest):,} completed games with chronological predictions and a recorded spread. Lower margin MAE is better.")
        accuracy = pd.DataFrame([
            {"Reference": "Efficiency model", "Games": len(backtest), "Projected home-margin MAE": backtest["model_margin_error"].mean()},
            {"Reference": "Closing spread", "Games": len(backtest), "Projected home-margin MAE": backtest["market_margin_error"].mean()},
        ])
        st.dataframe(accuracy.round(2), hide_index=True, use_container_width=True)

        st.subheader("All-game directional results")
        st.write("This grades the side the model favors on every game with a nonzero edge. It is a diagnostic, not a claim that each game is a worthwhile bet.")
        directional = grade(backtest[backtest["model_ats_edge"].abs() > 0].copy())
        if directional.empty:
            st.info("No nonzero ATS edges were produced.")
        else:
            all_dir = summarize(directional, "Any nonzero edge")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Directional games", f"{len(directional):,}")
            c2.metric("Correct side (excluding pushes)", f"{all_dir['Win % (no pushes)']:.1f}%")
            c3.metric("Net units at -110", f"{all_dir['Net units at -110']:+.2f}")
            c4.metric("Illustrative ROI", f"{all_dir['ROI']:+.2f}%")

        st.subheader("Fixed-threshold betting simulation")
        threshold = 3.5
        selected = grade(backtest[backtest["model_ats_edge"].abs() >= threshold].copy())
        fixed = summarize(selected, "3.5+ point edge")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Bets", f"{len(selected):,}")
        c2.metric("Win rate", f"{fixed['Win % (no pushes)']:.1f}%" if pd.notna(fixed["Win % (no pushes)"]) else "—")
        c3.metric("Net units", f"{fixed['Net units at -110']:+.2f}")
        c4.metric("ROI", f"{fixed['ROI']:+.2f}%" if pd.notna(fixed["ROI"]) else "—")
        st.caption("The 3.5-point threshold is fixed for this first test, not selected as optimal. One unit risked per bet; wins earn 0.909 units; losses lose one unit; pushes return zero.")

        st.subheader("Results by season")
        season_rows = []
        for year, part in backtest.groupby("season", dropna=True):
            d = grade(part[part["model_ats_edge"].abs() > 0].copy())
            s = grade(part[part["model_ats_edge"].abs() >= threshold].copy())
            dm = summarize(d, "Any nonzero edge")
            sm = summarize(s, "3.5+ point edge")
            season_rows.append({
                "Season": int(year), "Games with predictions": len(part), "Directional games": len(d),
                "Directional win %": dm["Win % (no pushes)"], "3.5+ bets": len(s),
                "3.5+ wins": sm["Wins"], "3.5+ losses": sm["Losses"], "3.5+ pushes": sm["Pushes"],
                "3.5+ net units": sm["Net units at -110"], "3.5+ ROI": sm["ROI"],
            })
        st.dataframe(pd.DataFrame(season_rows).round(2), hide_index=True, use_container_width=True)

        st.subheader("Inspect predictions")
        inspect_cols = ["gameday", "season", "week", "away_team", "home_team", "away_score", "home_score",
                        "spread_line", "pred_away_score", "pred_home_score", "predicted_home_margin",
                        "model_ats_edge", "actual_home_ats_margin"]
        st.dataframe(backtest[[c for c in inspect_cols if c in backtest.columns]].sort_values("gameday", ascending=False).head(100),
                     hide_index=True, use_container_width=True)
        st.download_button("Download ATS backtest CSV", backtest.to_csv(index=False).encode("utf-8"),
                           "nfl_ats_backtest.csv", "text/csv")
        st.warning(
            "Closing-line spread coverage is useful for research, but the feed does not prove the line was available at a particular "
            "sportsbook or timestamp. A positive ROI is not enough on its own; look for stable later-season results and prospective tracking."
        )
    except Exception as exc:
        st.error("The ATS backtest did not complete.")
        st.code(f"{type(exc).__name__}: {exc}")
else:
    st.info("Click **Run ATS backtest** to generate the first chronological ATS evaluation.")
