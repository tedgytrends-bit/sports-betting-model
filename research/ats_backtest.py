import numpy as np
import pandas as pd
import streamlit as st

from model import MODEL_VERSION, load_schedule_data, load_pbp, build_efficiency_model_dataset, chronological_backtest

st.title("NFL ATS Backtest")
st.caption(f"Experimental research page • Model v{MODEL_VERSION}")
st.warning(
    "This is an experimental historical backtest. Results describe how the model's directional picks and edge bands performed "
    "against the recorded spread data; they are evidence to evaluate, not a guarantee of future performance. Simulated ROI assumes -110 odds."
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


@st.cache_data(show_spinner=False)
def cached_efficiency_dataset(games, pbp):
    return build_efficiency_model_dataset(games, pbp, lookback_games=10)


@st.cache_data(show_spinner=False)
def cached_efficiency_backtest(dataset):
    return chronological_backtest(dataset, min_train_games=500)


@st.cache_data(show_spinner=False)
def cached_ats_residual_backtest(dataset, games):
    from model import chronological_ats_residual_backtest
    return chronological_ats_residual_backtest(dataset, games, min_train_games=500)


@st.cache_data(show_spinner=False)
def cached_market_anchored_backtest(dataset, games):
    from model import chronological_market_anchored_ats_backtest
    return chronological_market_anchored_ats_backtest(dataset, games, min_train_games=500)


@st.cache_data(show_spinner=False)
def cached_injury_reports():
    from model import load_injury_reports
    return load_injury_reports((2022, 2023, 2024, 2025, 2026))


def build_injury_coverage_audit(schedule, injuries):
    """Page-local audit avoids dependency on a newly deployed model.py symbol."""
    reports = injuries.copy()
    reports["season"] = pd.to_numeric(reports["season"], errors="coerce")
    reports["week"] = pd.to_numeric(reports["week"], errors="coerce")
    reports["team"] = reports["team"].astype(str).str.upper().str.strip()
    reports["position"] = reports["position"].astype(str).str.upper().str.strip()
    reports["date_modified"] = pd.to_datetime(reports["date_modified"], errors="coerce", utc=True).dt.tz_convert(None)
    if "season_type" not in reports.columns:
        reports["season_type"] = "REG"
    reports["season_type"] = reports["season_type"].fillna("REG").astype(str).str.upper().str.strip()
    reports["season_type"] = reports["season_type"].replace({"REGULAR": "REG", "POSTSEASON": "POST"})
    games = schedule.copy()
    games["season"] = pd.to_numeric(games["season"], errors="coerce")
    games["week"] = pd.to_numeric(games["week"], errors="coerce")
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce").dt.normalize()
    if "game_type" in games.columns:
        games["season_type"] = games["game_type"].astype(str).str.upper().str.strip()
    elif "season_type" in games.columns:
        games["season_type"] = games["season_type"].astype(str).str.upper().str.strip()
    else:
        games["season_type"] = "REG"
    games["season_type"] = games["season_type"].replace({"REGULAR": "REG", "POSTSEASON": "POST"})
    if "gametime" in games.columns:
        local_kickoff = pd.to_datetime(games["gameday"].dt.strftime("%Y-%m-%d") + " " + games["gametime"].astype(str), errors="coerce")
        games["kickoff_utc"] = local_kickoff.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC").dt.tz_localize(None)
    else:
        games["kickoff_utc"] = pd.NaT
    team_slots = []
    for _, game in games.iterrows():
        if pd.isna(game["season"]) or pd.isna(game["week"]) or pd.isna(game["gameday"]):
            continue
        week_reports = reports[(reports["season"] == game["season"]) & (reports["week"] == game["week"]) & (reports["season_type"] == game["season_type"])]
        for team_col in ["home_team", "away_team"]:
            team_rows = week_reports[week_reports["team"] == str(game[team_col]).upper().strip()]
            timestamped = team_rows[team_rows["date_modified"].notna()]
            cutoff = game["kickoff_utc"]
            if pd.notna(cutoff):
                usable = timestamped[timestamped["date_modified"] < cutoff]
            else:
                usable = timestamped[timestamped["date_modified"].dt.normalize() < game["gameday"]]
            qb_rows = usable[usable["position"] == "QB"]
            team_slots.append({"season": int(game["season"]), "Any source row": not team_rows.empty, "Timestamped row": not timestamped.empty, "Usable pre-kickoff row": not usable.empty, "Usable QB row": not qb_rows.empty, "Kickoff time missing": pd.isna(cutoff)})
    slots = pd.DataFrame(team_slots)
    if slots.empty:
        raise ValueError("No scheduled team-games available for injury coverage audit.")
    rows = []
# The ATS backtest begins in 2022; older schedule years are irrelevant here.
    audit_start_season = 2022
    slots = slots[slots["season"] >= audit_start_season].copy()
    reports = reports[reports["season"] >= audit_start_season].copy()
    seasons = sorted(set(reports["season"].dropna().astype(int)) | set(slots["season"].unique()))
    for year in seasons:
        raw, part = reports[reports["season"] == year], slots[slots["season"] == year]
        n = len(part)
        timestamp_columns = (
            raw["source_timestamp_like_columns"].dropna().astype(str).drop_duplicates().tolist()
            if "source_timestamp_like_columns" in raw.columns else []
        )
        raw_nonempty = (
            int(pd.to_numeric(raw["source_date_modified_nonempty"], errors="coerce").max())
            if "source_date_modified_nonempty" in raw.columns and not raw.empty else 0
        )
        raw_parseable = (
            int(pd.to_numeric(raw["source_date_modified_parseable"], errors="coerce").max())
            if "source_date_modified_parseable" in raw.columns and not raw.empty else 0
        )
        raw_examples = (
            raw["source_date_modified_examples"].dropna().astype(str).drop_duplicates().head(1).tolist()
            if "source_date_modified_examples" in raw.columns else []
        )
        rows.append({
            "Season": year,
            "Raw injury rows": len(raw),
            "Source timestamp-like columns": " ; ".join(timestamp_columns) if timestamp_columns else "(not recorded)",
            "Raw date_modified nonempty rows": raw_nonempty,
            "Raw date_modified parseable rows": raw_parseable,
            "date_modified examples": raw_examples[0] if raw_examples else "",
            "Rows missing timestamp after parsing": int(raw["date_modified"].isna().sum()),
            "Scheduled team-games": n,
            "Any report row %": 100 * part["Any source row"].mean() if n else np.nan,
            "Timestamped report %": 100 * part["Timestamped row"].mean() if n else np.nan,
            "Usable pre-kickoff report %": 100 * part["Usable pre-kickoff row"].mean() if n else np.nan,
            "Usable QB report %": 100 * part["Usable QB row"].mean() if n else np.nan,
            "No report row %": 100 * (~part["Any source row"]).mean() if n else np.nan,
            "Reports but none usable %": 100 * (part["Any source row"] & ~part["Usable pre-kickoff row"]).mean() if n else np.nan,
            "Kickoff time missing %": 100 * part["Kickoff time missing"].mean() if n else np.nan
        })
    return pd.DataFrame(rows)

run = st.button("Run ATS backtest", type="primary") or st.session_state.get("ats_backtest_has_run", False)

if run:
    st.session_state["ats_backtest_has_run"] = True
    try:
        with st.spinner("Loading schedule and historical play-by-play..."):
            games = get_schedule()
            pbp = get_play_by_play()
        if "spread_line" not in games.columns:
            st.error("The schedule source has no spread_line field. ATS backtest cannot run.")
            st.stop()

        with st.spinner("Building pregame features and chronological predictions..."):
            dataset = cached_efficiency_dataset(games, pbp)
            results = cached_efficiency_backtest(dataset)
            predictions = results["predictions"].copy()

        # Load experimental functions lazily so an optional model import cannot
        # prevent the entire Streamlit app and its other pages from loading.
        from model import (
            chronological_ats_residual_backtest,
            chronological_market_anchored_ats_backtest,
            load_injury_reports,
            add_pregame_injury_features,
        )

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

        with st.spinner("Testing a direct ATS-residual model..."):
            residual_predictions = cached_ats_residual_backtest(dataset, games)
        backtest = backtest.merge(residual_predictions, on="game_id", how="left", validate="one_to_one")
        backtest["residual_model_edge"] = pd.to_numeric(backtest["predicted_ats_residual"], errors="coerce")

        with st.spinner("Testing the market-anchored ATS model..."):
            anchored_predictions = cached_market_anchored_backtest(dataset, games)
        backtest = backtest.merge(anchored_predictions, on="game_id", how="left", validate="one_to_one")
        backtest["market_anchored_edge"] = backtest["market_anchored_home_margin"] - backtest["spread_line"]

        with st.spinner("Loading free historical injury reports and testing the injury-enhanced model..."):
            injury_reports = cached_injury_reports()
            injury_audit = build_injury_coverage_audit(games, injury_reports)
            injury_dataset = add_pregame_injury_features(dataset, games, injury_reports)
            injury_anchored_predictions = cached_market_anchored_backtest(injury_dataset, games).rename(columns={"market_anchored_home_margin": "injury_anchored_home_margin"})
        backtest = backtest.merge(injury_anchored_predictions, on="game_id", how="left", validate="one_to_one")
        backtest["injury_anchored_edge"] = backtest["injury_anchored_home_margin"] - backtest["spread_line"]

        def grade(frame, edge_col="model_ats_edge"):
            out = frame.copy()
            out["picked_side"] = np.where(out[edge_col] > 0, "Home", "Away")
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
        accuracy.loc[len(accuracy)] = {
            "Reference": "Direct ATS-residual model",
            "Games": int(backtest["residual_model_edge"].notna().sum()),
            "Projected home-margin MAE": (
                backtest.loc[backtest["residual_model_edge"].notna(), "residual_model_edge"]
                .sub(backtest.loc[backtest["residual_model_edge"].notna(), "actual_home_ats_margin"])
                .abs().mean()
            ),
        }
        anchored_valid = backtest.dropna(subset=["market_anchored_home_margin"]).copy()
        accuracy.loc[len(accuracy)] = {
            "Reference": "Market-anchored model",
            "Games": len(anchored_valid),
            "Projected home-margin MAE": (
                anchored_valid["market_anchored_home_margin"] - anchored_valid["actual_home_margin"]
            ).abs().mean(),
        }
        injury_valid = backtest.dropna(subset=["injury_anchored_home_margin"]).copy()
        accuracy.loc[len(accuracy)] = {
            "Reference": "Market-anchored + injuries",
            "Games": len(injury_valid),
            "Projected home-margin MAE": (
                injury_valid["injury_anchored_home_margin"] - injury_valid["actual_home_margin"]
            ).abs().mean(),
        }
        st.dataframe(accuracy.round(2), hide_index=True, use_container_width=True)
        st.caption("The market-anchored model includes the closing spread as an input. The injury-enhanced version adds pregame injury-report counts; reports are used only if updated before kickoff when kickoff time is available, and unavailable reports are treated as missing rather than healthy players.")

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

        st.subheader("Week-by-week record and ROI — efficiency model")
        st.caption("Chronological out-of-sample predictions only. Each threshold is cumulative; one unit risked per bet, wins net 0.909 units at -110, losses -1 unit, pushes 0.")
        weekly_rows = []
        for threshold_value in [3.5, 4.5, 5.5, 6.5, 7.5]:
            selected = backtest[backtest["model_ats_edge"].abs() >= threshold_value].copy()
            selected = grade(selected)
            for (year, week), part in selected.groupby(["season", "week"], dropna=False):
                wins = int(part["result"].eq("Win").sum())
                losses = int(part["result"].eq("Loss").sum())
                pushes = int(part["result"].eq("Push").sum())
                bets = wins + losses + pushes
                net = wins * (100 / 110) - losses
                weekly_rows.append({
                    "Season": int(year) if pd.notna(year) else None,
                    "Week": int(week) if pd.notna(week) else None,
                    "Minimum edge": f"{threshold_value:.1f}+",
                    "Record (W-L-P)": f"{wins}-{losses}-{pushes}",
                    "Bets": bets,
                    "Net units": round(net, 2),
                    "Units risked": bets,
                    "ROI %": round(100 * net / bets, 2) if bets else np.nan,
                })
        weekly_table = pd.DataFrame(weekly_rows)
        if not weekly_table.empty:
            st.dataframe(weekly_table.sort_values(["Season", "Week", "Minimum edge"]), hide_index=True, use_container_width=True)
            st.download_button("Download ATS weekly records CSV", weekly_table.to_csv(index=False).encode("utf-8"), "nfl_ats_weekly_records.csv", "text/csv",
            on_click="ignore"
        )
        else:
            st.info("No completed out-of-sample games met the selected thresholds.")

        st.subheader("Cross-season threshold comparison — ATS")
        st.caption("Same fixed edge thresholds across seasons. Best-week-excluded units are a concentration diagnostic, not a threshold-selection rule.")
        if not weekly_table.empty:
            cross_rows = []
            for (year, edge_label), group in weekly_table.groupby(["Season", "Minimum edge"]):
                group = group.sort_values("Week")
                total_units = float(group["Net units"].sum())
                risked = float(group["Units risked"].sum())
                best = group.loc[group["Net units"].idxmax()]
                worst = group.loc[group["Net units"].idxmin()]
                cross_rows.append({
                    "Season": int(year), "Minimum edge": edge_label,
                    "Bets": int(group["Bets"].sum()), "Net units": round(total_units, 2),
                    "ROI %": round(100 * total_units / risked, 2) if risked else np.nan,
                    "Best week": int(best["Week"]), "Best week units": round(float(best["Net units"]), 2),
                    "Worst week": int(worst["Week"]), "Worst week units": round(float(worst["Net units"]), 2),
                    "Net excluding best week": round(total_units - float(best["Net units"]), 2),
                    "Profitable weeks": int((group["Net units"] > 0).sum()),
                    "Losing weeks": int((group["Net units"] < 0).sum()),
                    "Break-even weeks": int((group["Net units"] == 0).sum()),
                })
            cross_table = pd.DataFrame(cross_rows)
            st.dataframe(cross_table, hide_index=True, use_container_width=True)
            st.download_button("Download cross-season ATS threshold comparison CSV", cross_table.to_csv(index=False).encode("utf-8"), "nfl_ats_cross_season_threshold_comparison.csv", "text/csv", on_click="ignore")

        st.subheader("Weekly concentration by edge threshold — 2025 ATS")
        st.caption("This checks whether a threshold's season result is dominated by one unusually strong week. It is descriptive only; do not choose a threshold solely because it looks best historically.")
        if not weekly_table.empty:
            concentration_source = weekly_table[weekly_table["Season"] == 2025].copy()
            concentration_rows = []
            for edge_label, group in concentration_source.groupby("Minimum edge"):
                group = group.sort_values("Week")
                if group.empty:
                    continue
                total_units = float(group["Net units"].sum())
                best_idx = group["Net units"].idxmax()
                worst_idx = group["Net units"].idxmin()
                best = group.loc[best_idx]
                worst = group.loc[worst_idx]
                concentration_rows.append({
                    "Minimum edge": edge_label,
                    "Bets": int(group["Bets"].sum()),
                    "Record (W-L-P)": "threshold-specific weekly records",
                    "Net units": round(total_units, 2),
                    "ROI %": round(100 * total_units / group["Units risked"].sum(), 2) if group["Units risked"].sum() else np.nan,
                    "Best week": int(best["Week"]),
                    "Best week units": round(float(best["Net units"]), 2),
                    "Worst week": int(worst["Week"]),
                    "Worst week units": round(float(worst["Net units"]), 2),
                    "Net excluding best week": round(total_units - float(best["Net units"]), 2),
                    "Profitable weeks": int((group["Net units"] > 0).sum()),
                    "Losing weeks": int((group["Net units"] < 0).sum()),
                    "Break-even weeks": int((group["Net units"] == 0).sum()),
                })
            concentration_table = pd.DataFrame(concentration_rows)
            if not concentration_table.empty:
                st.dataframe(concentration_table, hide_index=True, use_container_width=True)
                st.download_button("Download 2025 ATS threshold concentration CSV", concentration_table.to_csv(index=False).encode("utf-8"), "nfl_ats_2025_threshold_concentration.csv", "text/csv", on_click="ignore")
            else:
                st.info("No 2025 weekly threshold results are available in this run.")

        st.subheader("Season-by-season ATS robustness — efficiency model")
        st.caption("Fixed thresholds shown by season to reveal whether aggregate results depend heavily on one year. These are historical diagnostics, not proof of future profitability.")
        season_rows = []
        for threshold_value in [3.5, 4.5, 5.5, 6.5, 7.5]:
            selected = backtest[backtest["model_ats_edge"].abs() >= threshold_value].copy()
            selected = grade(selected)
            for year, part in selected.groupby("season", dropna=False):
                wins = int(part["result"].eq("Win").sum())
                losses = int(part["result"].eq("Loss").sum())
                pushes = int(part["result"].eq("Push").sum())
                bets = wins + losses + pushes
                net = wins * (100 / 110) - losses
                season_rows.append({
                    "Season": int(year) if pd.notna(year) else None,
                    "Minimum edge": f"{threshold_value:.1f}+",
                    "Record (W-L-P)": f"{wins}-{losses}-{pushes}",
                    "Bets": bets,
                    "Net units": round(net, 2),
                    "Units risked": bets,
                    "ROI %": round(100 * net / bets, 2) if bets else np.nan,
                })
        season_table = pd.DataFrame(season_rows)
        if not season_table.empty:
            st.dataframe(season_table.sort_values(["Season", "Minimum edge"]), hide_index=True, use_container_width=True)
            st.download_button(
                "Download ATS season-by-season records CSV",
                season_table.to_csv(index=False).encode("utf-8"),
                "nfl_ats_season_records.csv",
                "text/csv",
                on_click="ignore",
            )
        else:
            st.info("No season-by-season results available at these fixed thresholds.")

        st.subheader("Margin calibration and market comparison")
        st.caption("Groups games by the model's predicted home margin. Compare average predicted margin with actual margin, and compare model margin error with the market spread's margin error. All predictions are chronological out-of-sample; this tests calibration, not bet profitability by itself.")
        calibration = backtest.copy()
        calibration["predicted_home_margin"] = pd.to_numeric(calibration["predicted_home_margin"], errors="coerce")
        calibration["actual_home_margin"] = pd.to_numeric(calibration["actual_home_margin"], errors="coerce")
        calibration["model_margin_error_abs"] = (calibration["predicted_home_margin"] - calibration["actual_home_margin"]).abs()
        calibration["market_margin_error_abs"] = (calibration["spread_line"] - calibration["actual_home_margin"]).abs()
        calibration = calibration.dropna(subset=["predicted_home_margin", "actual_home_margin", "spread_line"]).copy()
        calibration["Predicted-margin band"] = pd.cut(
            calibration["predicted_home_margin"],
            bins=[-np.inf, -14, -7, 0, 7, 14, np.inf],
            labels=["Away by 14+", "Away by 7–14", "Away by 0–7", "Home by 0–7", "Home by 7–14", "Home by 14+"],
            right=False,
        )
        calibration_table = calibration.groupby("Predicted-margin band", observed=False).agg(
            Games=("game_id", "count"),
            **{"Average predicted home margin": ("predicted_home_margin", "mean"),
               "Average actual home margin": ("actual_home_margin", "mean"),
               "Model margin MAE": ("model_margin_error_abs", "mean"),
               "Market spread margin MAE": ("market_margin_error_abs", "mean")}
        ).reset_index()
        calibration_table[["Average predicted home margin", "Average actual home margin", "Model margin MAE", "Market spread margin MAE"]] = calibration_table[["Average predicted home margin", "Average actual home margin", "Model margin MAE", "Market spread margin MAE"]].round(2)
        st.dataframe(calibration_table, hide_index=True, use_container_width=True)
        overall_model_mae = calibration["model_margin_error_abs"].mean()
        overall_market_mae = calibration["market_margin_error_abs"].mean()
        delta = overall_market_mae - overall_model_mae
        c1, c2, c3 = st.columns(3)
        c1.metric("Games compared", f"{len(calibration):,}")
        c2.metric("Model home-margin MAE", f"{overall_model_mae:.2f}" if pd.notna(overall_model_mae) else "—")
        c3.metric("Market spread margin MAE", f"{overall_market_mae:.2f}" if pd.notna(overall_market_mae) else "—", delta=f"{delta:+.2f} points vs model")
        st.caption("Lower MAE is better. The market line is a benchmark, not necessarily an executable closing quote in this dataset. A model can have a reasonable score MAE and still fail to beat the spread market.")

        st.subheader("Model-versus-market accuracy by season")
        calibration["market_anchored_margin_error_abs"] = (
            pd.to_numeric(backtest.loc[calibration.index, "market_anchored_home_margin"], errors="coerce")
            - calibration["actual_home_margin"]
        ).abs()
        seasonal_accuracy = calibration.groupby("season", dropna=False).agg(
            Games=("game_id", "count"),
            **{
                "Efficiency model MAE": ("model_margin_error_abs", "mean"),
                "Market spread MAE": ("market_margin_error_abs", "mean"),
                "Market-anchored model MAE": ("market_anchored_margin_error_abs", "mean"),
                "Efficiency model signed error": ("predicted_home_margin", lambda x: float((x - calibration.loc[x.index, "actual_home_margin"]).mean())),
            }
        ).reset_index().rename(columns={"season": "Season"})
        seasonal_accuracy["Market advantage vs efficiency"] = (
            seasonal_accuracy["Efficiency model MAE"] - seasonal_accuracy["Market spread MAE"]
        ).round(2)
        seasonal_accuracy["Anchored improvement vs market"] = (
            seasonal_accuracy["Market spread MAE"] - seasonal_accuracy["Market-anchored model MAE"]
        ).round(2)
        numeric_cols = [
            "Efficiency model MAE", "Market spread MAE", "Market-anchored model MAE",
            "Efficiency model signed error", "Market advantage vs efficiency",
            "Anchored improvement vs market",
        ]
        seasonal_accuracy[numeric_cols] = seasonal_accuracy[numeric_cols].round(2)
        st.dataframe(seasonal_accuracy, hide_index=True, use_container_width=True)
        st.caption("Positive Market advantage means the market spread beats the raw efficiency model. Positive Anchored improvement means the model that also uses the spread beats the market baseline on margin MAE. The market-anchored model is diagnostic and uses the recorded market spread as an input; it is not proof of betting edge.")

        st.subheader("Model audit conclusion")
        pooled_anchored_mae = float(calibration["market_anchored_margin_error_abs"].mean())
        pooled_market_mae = float(calibration["market_margin_error_abs"].mean())
        pooled_efficiency_mae = float(calibration["model_margin_error_abs"].mean())
        anchored_delta = pooled_market_mae - pooled_anchored_mae
        efficiency_delta = pooled_market_mae - pooled_efficiency_mae
        c1, c2, c3 = st.columns(3)
        c1.metric("Efficiency model vs market", f"{efficiency_delta:+.2f} MAE points")
        c2.metric("Market-anchored model vs market", f"{anchored_delta:+.2f} MAE points")
        c3.metric("Anchored model vs raw model", f"{pooled_efficiency_mae - pooled_anchored_mae:+.2f} MAE points")
        if anchored_delta > 0:
            st.info("The market-anchored model has lower pooled margin MAE than the market spread in this historical test. This is a modeling signal to investigate, not evidence of profitable ATS bets.")
        else:
            st.warning("The market-anchored model does not beat the market spread on pooled margin MAE in this historical test. Do not treat its predicted differences as an edge without further validation.")
        st.caption("These are pooled historical comparisons. Seasonal variation and the small observed differences matter; a small MAE improvement can easily be noise and does not imply positive betting ROI.")

        st.subheader("ATS model coverage and edge-size audit")
        st.caption("This separates missing model predictions from models that produce predictions but rarely clear a large edge threshold. Edge thresholds are held fixed for comparison; do not select a threshold based on the best historical ROI.")
        coverage_rows = []
        model_edges = [
            ("Efficiency model", "model_ats_edge"),
            ("Direct ATS residual", "residual_model_edge"),
            ("Market anchored", "market_anchored_edge"),
            ("Market anchored + injuries", "injury_anchored_edge"),
        ]
        for model_label, edge_name in model_edges:
            edge_values = pd.to_numeric(backtest[edge_name], errors="coerce").dropna()
            abs_edges = edge_values.abs()
            coverage_rows.append({
                "Model": model_label,
                "Predictions available": int(edge_values.size),
                "Missing predictions": int(len(backtest) - edge_values.size),
                "Nonzero edges": int((abs_edges > 0).sum()),
                "Median absolute edge": round(float(abs_edges.median()), 3) if not abs_edges.empty else np.nan,
                "90th percentile absolute edge": round(float(abs_edges.quantile(0.90)), 3) if not abs_edges.empty else np.nan,
                "Max absolute edge": round(float(abs_edges.max()), 3) if not abs_edges.empty else np.nan,
                "Picks at 3.5+": int((abs_edges >= 3.5).sum()),
                "Picks at 4.5+": int((abs_edges >= 4.5).sum()),
                "Picks at 5.5+": int((abs_edges >= 5.5).sum()),
                "Picks at 6.5+": int((abs_edges >= 6.5).sum()),
                "Picks at 7.5+": int((abs_edges >= 7.5).sum()),
            })
        st.dataframe(pd.DataFrame(coverage_rows), hide_index=True, use_container_width=True)

        st.subheader("All-model results by fixed edge threshold")
        st.caption("Each model is graded on its own available out-of-sample predictions. One unit risked per pick; -110 assumed. Thresholds are diagnostics, not optimized selections.")
        overall_model_rows = []
        model_edges = [
            ("Efficiency model", "model_ats_edge"),
            ("Direct ATS residual", "residual_model_edge"),
            ("Market anchored", "market_anchored_edge"),
            ("Market anchored + injuries", "injury_anchored_edge"),
        ]
        for model_label, edge_name in model_edges:
            available = backtest.dropna(subset=[edge_name]).copy()
            for minimum_edge in [3.5, 4.5, 5.5, 6.5, 7.5]:
                eligible = available[pd.to_numeric(available[edge_name], errors="coerce").abs() >= minimum_edge].copy()
                eligible = grade(eligible, edge_name)
                summary = summarize(eligible, f"{model_label} {minimum_edge:.1f}+")
                overall_model_rows.append({
                    "Model": model_label,
                    "Minimum edge": f"{minimum_edge:.1f}+",
                    "Predictions available": len(available),
                    "Record (W-L-P)": f"{summary['Wins']}-{summary['Losses']}-{summary['Pushes']}",
                    "Bets": len(eligible),
                    "Net units": round(summary["Net units at -110"], 4),
                    "Units risked": len(eligible),
                    "ROI %": round(summary["ROI"], 4) if pd.notna(summary["ROI"]) else np.nan,
                })
        overall_model_table = pd.DataFrame(overall_model_rows)
        st.dataframe(overall_model_table, hide_index=True, use_container_width=True)
        st.download_button(
            "Download all-model overall ATS results CSV",
            overall_model_table.to_csv(index=False).encode("utf-8"),
            "nfl_ats_all_model_results.csv",
            "text/csv",
            on_click="ignore",
        )

        st.subheader("Season-by-season comparison across ATS models")
        st.caption("Fixed 3.5-point edge threshold, evaluated independently by season for each model. One unit risked per pick; wins net 0.909 units at -110. Use this to check consistency, not to select the best-looking historical model.")
        seasonal_model_rows = []
        for model_label, edge_name in model_edges:
            available = backtest.dropna(subset=[edge_name]).copy()
            eligible = available[pd.to_numeric(available[edge_name], errors="coerce").abs() >= 3.5].copy()
            eligible = grade(eligible, edge_name)
            for year, part in eligible.groupby("season", dropna=False):
                wins = int(part["result"].eq("Win").sum())
                losses = int(part["result"].eq("Loss").sum())
                pushes = int(part["result"].eq("Push").sum())
                bets = wins + losses + pushes
                net = wins * (100 / 110) - losses
                seasonal_model_rows.append({
                    "Season": int(year) if pd.notna(year) else None,
                    "Model": model_label,
                    "Record (W-L-P)": f"{wins}-{losses}-{pushes}",
                    "Bets": bets,
                    "Net units": round(net, 2),
                    "Units risked": bets,
                    "ROI %": round(100 * net / bets, 2) if bets else np.nan,
                })
        seasonal_model_table = pd.DataFrame(seasonal_model_rows)
        if not seasonal_model_table.empty:
            st.dataframe(
                seasonal_model_table.sort_values(["Season", "Model"]),
                hide_index=True,
                use_container_width=True,
            )
            st.download_button(
                "Download season-by-season all-model ATS results CSV",
                seasonal_model_table.to_csv(index=False).encode("utf-8"),
                "nfl_ats_season_model_comparison.csv",
                "text/csv",
                on_click="ignore",
            )
        else:
            st.info("No season-by-season model results met the 3.5-point threshold.")

        st.subheader("All-game weekly ATS record — efficiency model")
        st.caption(
            "Every completed out-of-sample game with a valid efficiency-model edge and spread is graded by the model's predicted side, regardless of edge size. "
            "Exact zero-edge games have no directional pick and are excluded. One unit risked per pick; -110 assumed. This is separate from threshold-filtered records below."
        )
        all_game_ats = backtest.dropna(subset=["model_ats_edge", "spread_line", "actual_home_ats_margin", "season", "week"]).copy()
        all_game_ats["model_ats_edge"] = pd.to_numeric(all_game_ats["model_ats_edge"], errors="coerce")
        all_game_ats = all_game_ats[all_game_ats["model_ats_edge"].abs() > 0].copy()
        all_game_ats = grade(all_game_ats, "model_ats_edge")
        all_game_week_rows = []
        for (year, week), group in all_game_ats.groupby(["season", "week"], dropna=False):
            w = int(group["result"].eq("Win").sum())
            l = int(group["result"].eq("Loss").sum())
            p = int(group["result"].eq("Push").sum())
            bets = w + l + p
            net = w * (100 / 110) - l
            all_game_week_rows.append({
                "Season": int(year), "Week": int(week),
                "Record (W-L-P)": f"{w}-{l}-{p}", "Bets": bets,
                "Net units": round(net, 4), "Units risked": bets,
                "ROI %": round(100 * net / bets, 4) if bets else np.nan,
            })
        all_game_week_table = pd.DataFrame(all_game_week_rows)
        if not all_game_week_table.empty:
            all_game_week_table = all_game_week_table.sort_values(["Season", "Week"])
            all_game_week_table["Cumulative units (season)"] = all_game_week_table.groupby("Season")["Net units"].cumsum().round(4)
            st.dataframe(all_game_week_table, hide_index=True, use_container_width=True)
            focus_year = st.selectbox(
                "Season for weekly ATS breakdown",
                sorted(all_game_week_table["Season"].dropna().unique().tolist(), reverse=True),
                index=(sorted(all_game_week_table["Season"].dropna().unique().tolist(), reverse=True).index(2025)
                       if 2025 in all_game_week_table["Season"].dropna().unique().tolist() else 0),
                key="all_game_ats_focus_season",
            )
            focus_weeks = all_game_week_table[all_game_week_table["Season"] == focus_year].copy()
            if not focus_weeks.empty:
                best_week = focus_weeks.loc[focus_weeks["Net units"].idxmax()]
                worst_week = focus_weeks.loc[focus_weeks["Net units"].idxmin()]
                total_net = float(focus_weeks["Net units"].sum())
                b1, b2, b3, b4 = st.columns(4)
                b1.metric(f"{focus_year} net units", f"{total_net:+.2f}")
                b2.metric("Best week", f"Week {int(best_week['Week'])}: {best_week['Net units']:+.2f}u")
                b3.metric("Worst week", f"Week {int(worst_week['Week'])}: {worst_week['Net units']:+.2f}u")
                b4.metric("Net excluding best week", f"{total_net - float(best_week['Net units']):+.2f}u")
                st.caption(
                    f"Weeks: {(focus_weeks['Net units'] > 0).sum()} profitable, "
                    f"{(focus_weeks['Net units'] < 0).sum()} losing, "
                    f"{(focus_weeks['Net units'] == 0).sum()} break-even. "
                    "The best-week exclusion is a concentration check, not a claim that the week should be discarded."
                )
            st.download_button(
                "Download all-game weekly ATS record CSV",
                all_game_week_table.to_csv(index=False).encode("utf-8"),
                "nfl_ats_all_game_weekly_record.csv",
                "text/csv",
                on_click="ignore",
            )

        st.subheader("Week-by-week comparison across ATS models")
        st.caption("Same completed games where each model has a prediction. One unit risked per pick; -110 assumed. Weekly net units retain precision so they reconcile to overall totals. These are historical simulations, not verified executable prices.")
        weekly_model_rows = []
        model_edges = [
            ("Efficiency model", "model_ats_edge"),
            ("Direct ATS residual", "residual_model_edge"),
            ("Market anchored", "market_anchored_edge"),
            ("Market anchored + injuries", "injury_anchored_edge"),
        ]
        for model_label, edge_name in model_edges:
            available = backtest.dropna(subset=[edge_name]).copy()
            for minimum_edge in [3.5, 4.5, 5.5, 6.5, 7.5]:
                eligible = available[available[edge_name].abs() >= minimum_edge].copy()
                eligible = grade(eligible, edge_name)
                for (year, week), group in eligible.groupby(["season", "week"], dropna=False):
                    w = int(group["result"].eq("Win").sum())
                    l = int(group["result"].eq("Loss").sum())
                    p = int(group["result"].eq("Push").sum())
                    n = w + l + p
                    net_units = w * (100 / 110) - l
                    weekly_model_rows.append({
                        "Season": int(year) if pd.notna(year) else None,
                        "Week": int(week) if pd.notna(week) else None,
                        "Model": model_label,
                        "Minimum edge": f"{minimum_edge:.1f}+",
                        "Record (W-L-P)": f"{w}-{l}-{p}",
                        "Bets": n,
                        "Net units": round(net_units, 6),
                        "Units risked": n,
                        "ROI %": round(100 * net_units / n, 6) if n else np.nan,
                    })
        weekly_model_table = pd.DataFrame(weekly_model_rows)
        if not weekly_model_table.empty:
            st.dataframe(
                weekly_model_table.sort_values(["Season", "Week", "Model", "Minimum edge"]),
                hide_index=True, use_container_width=True
            )
            st.download_button(
                "Download all-model weekly ATS comparison CSV",
                weekly_model_table.to_csv(index=False).encode("utf-8"),
                "nfl_ats_weekly_model_comparison.csv",
                "text/csv",
                on_click="ignore",
            )

        st.subheader("Small-edge diagnostic for residual and market-anchored models")
        st.caption("These lower cutoffs are for diagnosis only, not recommended betting thresholds. We have now examined multiple models and thresholds, so isolated positive rows are especially vulnerable to selection bias. Treat these results as exploratory unless the same pre-specified model and threshold hold up on untouched future games.")
        small_edge_rows = []
        for model_label, edge_name in [
            ("Direct ATS residual", "residual_model_edge"),
            ("Market anchored", "market_anchored_edge"),
            ("Market anchored + injuries", "injury_anchored_edge"),
        ]:
            available = backtest.dropna(subset=[edge_name]).copy()
            for minimum_edge in [0.5, 1.0, 1.5, 2.0, 2.5]:
                eligible = available[pd.to_numeric(available[edge_name], errors="coerce").abs() >= minimum_edge].copy()
                eligible = grade(eligible, edge_name)
                summary = summarize(eligible, f"{model_label} {minimum_edge:.1f}+")
                small_edge_rows.append({
                    "Model": model_label,
                    "Minimum absolute edge": f"{minimum_edge:.1f}+",
                    "Predictions available": len(available),
                    "Record (W-L-P)": f"{summary['Wins']}-{summary['Losses']}-{summary['Pushes']}",
                    "Bets": len(eligible),
                    "Net units": round(summary["Net units at -110"], 4),
                    "Units risked": len(eligible),
                    "ROI %": round(summary["ROI"], 4) if pd.notna(summary["ROI"]) else np.nan,
                })
        small_edge_table = pd.DataFrame(small_edge_rows)
        st.dataframe(small_edge_table, hide_index=True, use_container_width=True)
        st.download_button(
            "Download small-edge ATS diagnostics CSV",
            small_edge_table.to_csv(index=False).encode("utf-8"),
            "nfl_ats_small_edge_diagnostics.csv",
            "text/csv",
            on_click="ignore",
        )

        st.subheader("Historical robustness summary (completed seasons)")
        st.caption("Excludes the current calendar year so partial-season results are not compared with full seasons. Historical ROI is descriptive, not evidence of a durable edge.")
        completed_season_rows = []
        current_calendar_year = pd.Timestamp.now().year
        for model_label, edge_name in [
            ("Direct ATS residual", "residual_model_edge"),
            ("Market anchored", "market_anchored_edge"),
            ("Market anchored + injuries", "injury_anchored_edge"),
        ]:
            available = backtest.dropna(subset=[edge_name]).copy()
            available = available[pd.to_numeric(available["season"], errors="coerce") < current_calendar_year]
            for minimum_edge in [1.0, 1.5]:
                eligible = available[pd.to_numeric(available[edge_name], errors="coerce").abs() >= minimum_edge].copy()
                eligible = grade(eligible, edge_name)
                summary = summarize(eligible, f"{model_label} {minimum_edge:.1f}+")
                profitable_seasons = 0
                seasons_included = 0
                for year, group in eligible.groupby("season", dropna=True):
                    wins = int(group["result"].eq("Win").sum())
                    losses = int(group["result"].eq("Loss").sum())
                    pushes = int(group["result"].eq("Push").sum())
                    net = wins * (100 / 110) - losses
                    seasons_included += 1
                    profitable_seasons += int(net > 0)
                completed_season_rows.append({
                    "Model": model_label,
                    "Minimum edge": f"{minimum_edge:.1f}+",
                    "Seasons included": seasons_included,
                    "Profitable seasons": profitable_seasons,
                    "Bets": len(eligible),
                    "Record (W-L-P)": f"{summary['Wins']}-{summary['Losses']}-{summary['Pushes']}",
                    "Net units": round(summary["Net units at -110"], 4),
                    "ROI %": round(summary["ROI"], 4) if pd.notna(summary["ROI"]) else np.nan,
                })
        completed_season_table = pd.DataFrame(completed_season_rows)
        st.dataframe(completed_season_table, hide_index=True, use_container_width=True)
        st.download_button(
            "Download completed-season robustness summary CSV",
            completed_season_table.to_csv(index=False).encode("utf-8"),
            "nfl_ats_completed_season_robustness.csv",
            "text/csv",
            on_click="ignore",
        )

        st.subheader("Small-edge results by season")
        st.caption("Season splits are a robustness check, not a way to choose the best threshold. Interpret short seasons and small bet counts cautiously.")
        small_edge_season_rows = []
        for model_label, edge_name in [
            ("Direct ATS residual", "residual_model_edge"),
            ("Market anchored", "market_anchored_edge"),
            ("Market anchored + injuries", "injury_anchored_edge"),
        ]:
            available = backtest.dropna(subset=[edge_name]).copy()
            for minimum_edge in [1.0, 1.5]:
                eligible = available[pd.to_numeric(available[edge_name], errors="coerce").abs() >= minimum_edge].copy()
                eligible = grade(eligible, edge_name)
                for year, group in eligible.groupby("season", dropna=True):
                    summary = summarize(group, f"{model_label} {minimum_edge:.1f}+")
                    small_edge_season_rows.append({
                        "Season": int(year),
                        "Model": model_label,
                        "Minimum edge": f"{minimum_edge:.1f}+",
                        "Record (W-L-P)": f"{summary['Wins']}-{summary['Losses']}-{summary['Pushes']}",
                        "Bets": len(group),
                        "Net units": round(summary["Net units at -110"], 4),
                        "ROI %": round(summary["ROI"], 4) if pd.notna(summary["ROI"]) else np.nan,
                    })
        small_edge_season_table = pd.DataFrame(small_edge_season_rows)
        if not small_edge_season_table.empty:
            st.dataframe(
                small_edge_season_table.sort_values(["Model", "Minimum edge", "Season"]),
                hide_index=True, use_container_width=True
            )
            st.download_button(
                "Download small-edge season breakdown CSV",
                small_edge_season_table.to_csv(index=False).encode("utf-8"),
                "nfl_ats_small_edge_by_season.csv",
                "text/csv",
                on_click="ignore",
            )

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

        st.subheader("Direct ATS-residual model")
        st.write("This separately predicts how far the home team's final margin finishes above or below the spread, instead of subtracting two independently predicted scores.")
        residual_games = backtest.dropna(subset=["residual_model_edge"]).copy()
        residual_directional = grade(residual_games[residual_games["residual_model_edge"].abs() > 0], "residual_model_edge")
        residual_all = summarize(residual_directional, "ATS residual: any nonzero edge")
        residual_fixed = grade(residual_games[residual_games["residual_model_edge"].abs() >= threshold], "residual_model_edge")
        residual_fixed_summary = summarize(residual_fixed, "ATS residual: 3.5+ edge")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Directional games", f"{len(residual_directional):,}")
        r2.metric("Correct side", f"{residual_all['Win % (no pushes)']:.1f}%" if pd.notna(residual_all["Win % (no pushes)"]) else "—")
        r3.metric("3.5+ bets", f"{len(residual_fixed):,}")
        r4.metric("3.5+ ROI", f"{residual_fixed_summary['ROI']:+.2f}%" if pd.notna(residual_fixed_summary["ROI"]) else "—")

        residual_seasons = []
        for year, part in residual_games.groupby("season", dropna=True):
            d = grade(part[part["residual_model_edge"].abs() > 0], "residual_model_edge")
            s = grade(part[part["residual_model_edge"].abs() >= threshold], "residual_model_edge")
            dm = summarize(d, "ATS residual: any nonzero edge")
            sm = summarize(s, "ATS residual: 3.5+ edge")
            residual_seasons.append({
                "Season": int(year), "Games": len(part), "Directional games": len(d),
                "Directional win %": dm["Win % (no pushes)"], "3.5+ bets": len(s),
                "3.5+ wins": sm["Wins"], "3.5+ losses": sm["Losses"], "3.5+ pushes": sm["Pushes"],
                "3.5+ net units": sm["Net units at -110"], "3.5+ ROI": sm["ROI"],
            })
        st.dataframe(pd.DataFrame(residual_seasons).round(2), hide_index=True, use_container_width=True)

        st.subheader("Market-anchored ATS model")
        st.write("This model starts with the closing spread and adjusts it using the pregame team-efficiency features. The adjustment is evaluated out of sample; it is not assumed to be valuable just because it produces a different number.")
        anchored_games = backtest.dropna(subset=["market_anchored_edge"]).copy()
        anchored_directional = grade(anchored_games[anchored_games["market_anchored_edge"].abs() > 0], "market_anchored_edge")
        anchored_all = summarize(anchored_directional, "Market anchored: any nonzero edge")
        anchored_fixed = grade(anchored_games[anchored_games["market_anchored_edge"].abs() >= threshold], "market_anchored_edge")
        anchored_fixed_summary = summarize(anchored_fixed, "Market anchored: 3.5+ edge")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Directional games", f"{len(anchored_directional):,}")
        a2.metric("Correct side", f"{anchored_all['Win % (no pushes)']:.1f}%" if pd.notna(anchored_all["Win % (no pushes)"]) else "—")
        a3.metric("3.5+ bets", f"{len(anchored_fixed):,}")
        a4.metric("3.5+ ROI", f"{anchored_fixed_summary['ROI']:+.2f}%" if pd.notna(anchored_fixed_summary["ROI"]) else "—")

        anchored_seasons = []
        for year, part in anchored_games.groupby("season", dropna=True):
            d = grade(part[part["market_anchored_edge"].abs() > 0], "market_anchored_edge")
            s = grade(part[part["market_anchored_edge"].abs() >= threshold], "market_anchored_edge")
            dm = summarize(d, "Market anchored: any nonzero edge")
            sm = summarize(s, "Market anchored: 3.5+ edge")
            anchored_seasons.append({
                "Season": int(year), "Games": len(part), "Directional games": len(d),
                "Directional win %": dm["Win % (no pushes)"], "3.5+ bets": len(s),
                "3.5+ wins": sm["Wins"], "3.5+ losses": sm["Losses"], "3.5+ pushes": sm["Pushes"],
                "3.5+ net units": sm["Net units at -110"], "3.5+ ROI": sm["ROI"],
            })
        st.dataframe(pd.DataFrame(anchored_seasons).round(2), hide_index=True, use_container_width=True)

        st.subheader("Market-anchored model + injuries")
        st.write("This version adds weekly injury-report counts by team and position to the market-anchored model. When kickoff time is available, injury updates are included only if their recorded timestamp is before kickoff; if kickoff time is missing, same-day updates are excluded.")
        injury_directional = grade(injury_valid[injury_valid["injury_anchored_edge"].abs() > 0], "injury_anchored_edge")
        injury_all = summarize(injury_directional, "Market anchored + injuries: any nonzero edge")
        injury_fixed = grade(injury_valid[injury_valid["injury_anchored_edge"].abs() >= threshold], "injury_anchored_edge")
        injury_fixed_summary = summarize(injury_fixed, "Market anchored + injuries: 3.5+ edge")
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Directional games", f"{len(injury_directional):,}")
        i2.metric("Correct side", f"{injury_all['Win % (no pushes)']:.1f}%" if pd.notna(injury_all["Win % (no pushes)"]) else "—")
        i3.metric("3.5+ bets", f"{len(injury_fixed):,}")
        i4.metric("3.5+ ROI", f"{injury_fixed_summary['ROI']:+.2f}%" if pd.notna(injury_fixed_summary["ROI"]) else "—")

        injury_seasons = []
        for year, part in injury_valid.groupby("season", dropna=True):
            d = grade(part[part["injury_anchored_edge"].abs() > 0], "injury_anchored_edge")
            s = grade(part[part["injury_anchored_edge"].abs() >= threshold], "injury_anchored_edge")
            dm = summarize(d, "Market anchored + injuries: any nonzero edge")
            sm = summarize(s, "Market anchored + injuries: 3.5+ edge")
            injury_seasons.append({
                "Season": int(year), "Games": len(part), "Directional games": len(d),
                "Directional win %": dm["Win % (no pushes)"], "3.5+ bets": len(s),
                "3.5+ wins": sm["Wins"], "3.5+ losses": sm["Losses"], "3.5+ pushes": sm["Pushes"],
                "3.5+ net units": sm["Net units at -110"], "3.5+ ROI": sm["ROI"],
            })
        st.dataframe(pd.DataFrame(injury_seasons).round(2), hide_index=True, use_container_width=True)
        st.caption(
            f"Pregame injury report coverage in the feature dataset: home teams {injury_dataset['home_injury_report_available'].mean():.1%}, "
            f"away teams {injury_dataset['away_injury_report_available'].mean():.1%}. Source: free public nflverse weekly injury reports."
        )

        st.subheader("Injury data coverage audit")
        st.write(
            "This separates missing source records from reports that exist but cannot safely be used before kickoff. "
            "QB coverage counts team-games with at least one timestamp-valid quarterback report; it does not mean the starting QB was injured."
        )
        st.dataframe(injury_audit.round(1), hide_index=True, use_container_width=True)
        st.download_button(
            "Download injury coverage audit CSV",
            injury_audit.to_csv(index=False).encode("utf-8"),
            "nfl_injury_coverage_audit.csv",
            "text/csv",
            on_click="ignore"
        
        )


        st.subheader("Edge calibration audit — ATS")
        st.write(
            "This groups every nonzero efficiency-model edge into non-overlapping bands, then grades the model's chosen side "
            "at a flat -110 for comparison. The purpose is to test whether larger predicted edges correspond to better results, "
            "not to declare the best-looking historical band a future betting rule."
        )
        edge_bins = [0, 1, 2, 3.5, 4.5, 5.5, 6.5, 7.5, np.inf]
        edge_labels = ["0–1", "1–2", "2–3.5", "3.5–4.5", "4.5–5.5", "5.5–6.5", "6.5–7.5", "7.5+"]
        calibration = backtest[backtest["model_ats_edge"].abs() > 0].copy()
        calibration["Edge band"] = pd.cut(
            calibration["model_ats_edge"].abs(), bins=edge_bins, labels=edge_labels,
            right=False, include_lowest=True
        )
        calibration = grade(calibration)
        calibration_rows = []
        for band, part in calibration.groupby("Edge band", observed=False):
            wins = int(part["result"].eq("Win").sum())
            losses = int(part["result"].eq("Loss").sum())
            pushes = int(part["result"].eq("Push").sum())
            bets = wins + losses + pushes
            net = wins * (100 / 110) - losses
            decisions = wins + losses
            calibration_rows.append({
                "Edge band (points)": str(band), "Bets": bets, "Wins": wins, "Losses": losses, "Pushes": pushes,
                "Win % (no pushes)": 100 * wins / decisions if decisions else np.nan,
                "Net units": round(net, 2), "ROI %": round(100 * net / bets, 2) if bets else np.nan,
            })
        calibration_table = pd.DataFrame(calibration_rows)
        st.dataframe(calibration_table, hide_index=True, use_container_width=True)
        st.download_button(
            "Download ATS edge calibration CSV",
            calibration_table.to_csv(index=False).encode("utf-8"),
            "nfl_ats_edge_calibration.csv", "text/csv", on_click="ignore"
        )
        st.caption(
            "Bands are disjoint; exact zero-edge games are excluded because they provide no directional pick. "
            "ROI assumes one unit risked and -110 pricing. Read the band totals alongside the season breakdown below."
        )
        calibration_season_rows = []
        for (year, band), part in calibration.groupby(["season", "Edge band"], observed=False, dropna=False):
            wins = int(part["result"].eq("Win").sum())
            losses = int(part["result"].eq("Loss").sum())
            pushes = int(part["result"].eq("Push").sum())
            bets = wins + losses + pushes
            net = wins * (100 / 110) - losses
            decisions = wins + losses
            calibration_season_rows.append({
                "Season": int(year) if pd.notna(year) else None, "Edge band (points)": str(band),
                "Bets": bets, "Wins": wins, "Losses": losses, "Pushes": pushes,
                "Win % (no pushes)": round(100 * wins / decisions, 2) if decisions else np.nan,
                "Net units": round(net, 2), "ROI %": round(100 * net / bets, 2) if bets else np.nan,
            })
        calibration_season_table = pd.DataFrame(calibration_season_rows)
        st.subheader("ATS edge bands by season")
        st.dataframe(calibration_season_table, hide_index=True, use_container_width=True)
        st.download_button(
            "Download ATS edge calibration by season CSV",
            calibration_season_table.to_csv(index=False).encode("utf-8"),
            "nfl_ats_edge_calibration_by_season.csv", "text/csv", on_click="ignore"
        )

        st.subheader("Inspect predictions")
        inspect_cols = ["gameday", "season", "week", "away_team", "home_team", "away_score", "home_score",
                        "spread_line", "pred_away_score", "pred_home_score", "predicted_home_margin",
                        "model_ats_edge", "actual_home_ats_margin", "predicted_ats_residual", "residual_model_edge", "market_anchored_home_margin", "market_anchored_edge", "injury_anchored_home_margin", "injury_anchored_edge"]
        st.dataframe(backtest[[c for c in inspect_cols if c in backtest.columns]].sort_values("gameday", ascending=False).head(100),
                     hide_index=True, use_container_width=True)
        st.download_button("Download ATS backtest CSV", backtest.to_csv(index=False).encode("utf-8"),
                           "nfl_ats_backtest.csv", "text/csv",
            on_click="ignore"
        )
        st.warning(
            "Interpret historical results alongside sample size, season-to-season stability, edge-band performance, and projection accuracy. "
            "A positive ROI in one slice is not enough on its own to establish a repeatable edge."
        )
    except Exception as exc:
        st.error("The ATS backtest did not complete.")
        st.code(f"{type(exc).__name__}: {exc}")
else:
    st.info("Click **Run ATS backtest** to generate the first chronological ATS evaluation.")
