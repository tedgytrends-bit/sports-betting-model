
import numpy as np
import pandas as pd
import streamlit as st
from datetime import date, timezone, datetime
import json
import hashlib
from model import (
    MODEL_VERSION,
    load_schedule_data,
    load_pbp,
    build_efficiency_model_dataset,
    chronological_backtest,
    baseline_projection,
    add_scoring_baseline_predictions,
    score_prediction_metrics,
    project_upcoming_efficiency,
)

with st.sidebar:
    st.header("Model settings")
    season = st.selectbox("Projection season", [2026, 2025, 2024, 2023, 2022], index=0)
    lookback = st.slider("Recent team games for efficiency", 4, 16, 10)
    show_full_schedule = st.checkbox("Show full remaining season", value=False)
    run_backtest = st.button("Run historical backtest", type="primary")
    use_efficiency_model = st.checkbox(
        "Use efficiency model on board (downloads 2021–2026 play-by-play)",
        value=False,
        help="Leave off for a fast-starting board using the transparent recent-scoring baseline. Turn on to load the larger efficiency-model dataset.",
    )
    st.caption("Default view: games in the next 14 days. Historical backtests and efficiency projections download several seasons of play-by-play.")


@st.cache_data(ttl=1800, show_spinner="Loading NFL schedule and results...")
def get_schedule():
    return load_schedule_data()


@st.cache_data(ttl=3600, show_spinner="Downloading historical NFL play-by-play...")
def get_pbp():
    return load_pbp((2021, 2022, 2023, 2024, 2025, 2026))


try:
    games = get_schedule()
except Exception as e:
    st.error("Could not load the NFL schedule data.")
    st.code(str(e))
    st.stop()

today = pd.Timestamp(date.today())
season_games = games[games["season"] == season].copy()
# The main board uses the efficiency model for projections. Keep the simple
# recent-scoring baseline as a transparent fallback if historical PBP is unavailable.if use_efficiency_model:
    try:
        pbp_for_board = get_pbp()
        feature_data_for_board = build_efficiency_model_dataset(
            games,
            pbp_for_board,
            lookback_games=lookback,
        )
        all_projections = project_upcoming_efficiency(
            feature_data_for_board,
            min_train_games=500,
        )
        if not all_projections.empty:
            all_projections = all_projections[
                pd.to_numeric(all_projections["season"], errors="coerce") == season
            ].copy()
            market_lines = games[["game_id", "spread_line", "total_line"]].drop_duplicates("game_id")
            all_projections = all_projections.merge(
                market_lines, on="game_id", how="left", validate="one_to_one"
            )
            all_projections["market_spread_line"] = pd.to_numeric(
                all_projections["spread_line"], errors="coerce"
            )
            all_projections["predicted_home_margin"] = (
                pd.to_numeric(all_projections["projected_home"], errors="coerce")
                - pd.to_numeric(all_projections["projected_away"], errors="coerce")
            )
            # nflverse convention: positive spread_line means the home team is favored.
            # Positive edge means the model is more favorable to the home team than market.
            all_projections["ats_edge"] = (
                all_projections["predicted_home_margin"] - all_projections["market_spread_line"]
            )
            all_projections["ats_lean"] = np.select(
                [
                    all_projections["market_spread_line"].isna(),
                    all_projections["ats_edge"].isna(),
                    all_projections["ats_edge"] > 0,
                    all_projections["ats_edge"] < 0,
                ],
                ["No market line", "Unavailable", "Home team lean", "Away team lean"],
                default="No edge",
            )
            all_projections["market_total"] = pd.to_numeric(
                all_projections["total_line"], errors="coerce"
            )
            all_projections["total_edge"] = (
                all_projections["projected_total"] - all_projections["market_total"]
            )
        projection_source = "Efficiency model"
    except Exception as projection_error:
        all_projections = baseline_projection(games, season=season, lookback=6)
        projection_source = "Recent-scoring fallback"
        st.warning(
            "The efficiency projection could not be generated, so the board is showing "
            f"the simple recent-scoring baseline instead. Details: {projection_error}"
        )
else:
    all_projections = baseline_projection(games, season=season, lookback=6)
    projection_source = "Recent-scoring baseline (fast startup)"
    if not all_projections.empty:
        all_projections["market_spread_line"] = pd.to_numeric(
            all_projections["spread_line"], errors="coerce"
        )
        all_projections["predicted_home_margin"] = (
            pd.to_numeric(all_projections["projected_home"], errors="coerce")
            - pd.to_numeric(all_projections["projected_away"], errors="coerce")
        )
        all_projections["ats_edge"] = (
            all_projections["predicted_home_margin"] - all_projections["market_spread_line"]
        )
        all_projections["ats_lean"] = np.select(
            [
                all_projections["market_spread_line"].isna(),
                all_projections["ats_edge"].isna(),
                all_projections["ats_edge"] > 0,
                all_projections["ats_edge"] < 0,
            ],
            ["No market line", "Unavailable", "Home team lean", "Away team lean"],
            default="No edge",
        )
        all_projections["market_total"] = pd.to_numeric(
            all_projections["total_line"], errors="coerce"
        )
        all_projections["total_edge"] = (
            all_projections["projected_total"] - all_projections["market_total"]
        )

if not all_projections.empty:
    all_projections["gameday"] = pd.to_datetime(all_projections["gameday"], errors="coerce")
    all_projections = all_projections[all_projections["gameday"] >= today].copy()

end_date = today + pd.Timedelta(days=14)
if show_full_schedule:
    projections = all_projections.copy()
else:
    projections = all_projections[
        all_projections["gameday"] < end_date + pd.Timedelta(days=1)
    ].copy()

completed_count = int(
    (season_games["home_score"].notna() & season_games["away_score"].notna()).sum()
)
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
st.caption(
    f"Projection source: {projection_source}. These are analytical estimates, "
    "not instructions to place a bet. Market totals are shown when available. "
    "An Over/Under lean only shows the direction of the model's difference; "
    "it does not establish a profitable edge or account for price, uncertainty, "
    "injuries, or weather. Market lines come from the schedule feed; the app does not "
    "currently verify a live sportsbook quote or provide a line timestamp."
)

if projections.empty:
    st.info(
        "No upcoming games found in this date window. Enable 'Show full remaining season' "
        "in the sidebar to inspect the full schedule."
    )
else:
    display = projections.copy()
    display["Date"] = pd.to_datetime(display["gameday"], errors="coerce").dt.strftime("%a, %b %d")
    display["Matchup"] = (
        display["away_team"].astype(str) + " at " + display["home_team"].astype(str)
    )
    display["Projected score"] = (
        display["away_team"].astype(str)
        + " "
        + display["projected_away"].round(1).astype(str)
        + " — "
        + display["home_team"].astype(str)
        + " "
        + display["projected_home"].round(1).astype(str)
    )
    display["Model home spread"] = display["model_home_spread"].map(lambda x: f"{x:+.1f}")
    display["Projected total"] = display["projected_total"].map(lambda x: f"{x:.1f}")
    if "market_spread_line" in display.columns:
        display["Market spread"] = pd.to_numeric(
            display["market_spread_line"], errors="coerce"
        ).map(lambda x: f"{x:+.1f}" if pd.notna(x) else "Not available yet")
        display["ATS edge"] = pd.to_numeric(
            display["ats_edge"], errors="coerce"
        ).map(lambda x: f"{x:+.1f}" if pd.notna(x) else "Not available")
        display["ATS lean"] = display["ats_lean"]
    if "market_total" in display.columns:
        display["Market total"] = pd.to_numeric(
            display["market_total"], errors="coerce"
        ).map(lambda x: f"{x:.1f}" if pd.notna(x) else "Not available yet")
        display["Total lean"] = pd.to_numeric(
            display["total_edge"], errors="coerce"
        ).map(
            lambda x: "Over lean" if pd.notna(x) and x > 0
            else ("Under lean" if pd.notna(x) and x < 0 else "No market line")
        )
        display["Model vs market"] = pd.to_numeric(
            display["total_edge"], errors="coerce"
        ).map(lambda x: f"{x:+.1f}" if pd.notna(x) else "Not available")
    display = display.sort_values("gameday")

    # Keep the main board compact: the projected score already identifies
    # both teams, and the score margin is not yet a validated ATS model.
    table_columns = ["Date", "Projected score", "Projected total"]
    if "Market spread" in display.columns:
        table_columns += ["Market spread", "ATS edge", "ATS lean"]
    if "Market total" in display.columns:
        table_columns += ["Market total", "Model vs market", "Total lean"]
    st.dataframe(
        display[table_columns],
        width="stretch",
        hide_index=True,
        column_config={
            "Date": st.column_config.TextColumn("Date", width="small"),
            "Projected score": st.column_config.TextColumn("Projected score", width="large"),
            "Projected total": st.column_config.TextColumn("Model total", width="small"),
            "Market spread": st.column_config.TextColumn("Spread", width="small"),
            "ATS edge": st.column_config.TextColumn("ATS edge", width="small"),
            "ATS lean": st.column_config.TextColumn("ATS lean", width="medium"),
            "Market total": st.column_config.TextColumn("Total market", width="small"),
            "Model vs market": st.column_config.TextColumn("Difference", width="small"),
            "Total lean": st.column_config.TextColumn("Total lean", width="small"),
        },
    )

    st.subheader("Game breakdown")
    matchup = st.selectbox("Select a matchup", display["Matchup"].tolist())
    g = display.loc[display["Matchup"] == matchup].iloc[0]

    a, b, c = st.columns(3)
    a.metric("Projected score", f'{g["projected_away"]:.1f} – {g["projected_home"]:.1f}')
    b.metric("Model home spread", f'{g["model_home_spread"]:+.1f}')
    c.metric("Projected total", f'{g["projected_total"]:.1f}')
    if "market_total" in g.index and pd.notna(g["market_total"]):
        d, e = st.columns(2)
        d.metric("Market total", f'{g["market_total"]:.1f}')
        edge_value = g.get("total_edge", np.nan)
        e.metric("Model vs market", f'{edge_value:+.1f} pts' if pd.notna(edge_value) else "Unavailable")

    with st.expander("How the current projection works", expanded=True):
        st.write(
            "The primary board fits the historical efficiency model on completed games and projects scheduled games "
            "using pregame team features. It is experimental and has not demonstrated a durable betting edge."
        )
        st.write(
            "The model does not automatically ingest current injury reports, weather, or verified live sportsbook prices. "
            "or sportsbook odds. Use the manual QB adjustment preview below when the starting-quarterback situation is known."
        )

    st.markdown("**Manual injury and severe-weather adjustment preview**")
    st.caption(
        "These controls adjust only the selected matchup preview; they do not change historical backtest results. "
        "The point values are conservative starting heuristics, not fitted or validated injury coefficients. "
        "Enter missing players by position group; do not count the QB twice."
    )

    qb_penalties = {
        "Expected starter": 0.0,
        "Questionable / limited": 1.5,
        "Backup starting": 5.0,
        "Emergency / third-string": 8.0,
    }
    qb1, qb2 = st.columns(2)
    with qb1:
        away_qb = st.selectbox(
            f"{g['away_team']} QB status",
            list(qb_penalties),
            key=f"away_qb_{g['game_id']}",
        )
    with qb2:
        home_qb = st.selectbox(
            f"{g['home_team']} QB status",
            list(qb_penalties),
            key=f"home_qb_{g['game_id']}",
        )

    injury_weights = {
        "Offensive line": 0.65,
        "WR / TE": 0.60,
        "Running back": 0.30,
        "Defensive front / LB": 0.50,
        "Secondary": 0.50,
        "Kicker": 0.25,
    }
    injury_key = f"injuries_{g['game_id']}"
    if injury_key not in st.session_state:
        st.session_state[injury_key] = pd.DataFrame({
            "Position group": list(injury_weights.keys()),
            "Away OUT": [0] * len(injury_weights),
            "Away questionable": [0] * len(injury_weights),
            "Home OUT": [0] * len(injury_weights),
            "Home questionable": [0] * len(injury_weights),
        })

    injuries = st.data_editor(
        st.session_state[injury_key],
        key=f"injury_editor_{g['game_id']}",
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        disabled=["Position group"],
        column_config={
            "Position group": st.column_config.TextColumn("Position group"),
            "Away OUT": st.column_config.NumberColumn(
                f"{g['away_team']} OUT", min_value=0, max_value=5, step=1
            ),
            "Away questionable": st.column_config.NumberColumn(
                f"{g['away_team']} Q", min_value=0, max_value=5, step=1
            ),
            "Home OUT": st.column_config.NumberColumn(
                f"{g['home_team']} OUT", min_value=0, max_value=5, step=1
            ),
            "Home questionable": st.column_config.NumberColumn(
                f"{g['home_team']} Q", min_value=0, max_value=5, step=1
            ),
        },
    )
    st.session_state[injury_key] = injuries

    away_off_penalty = 0.0
    home_off_penalty = 0.0
    away_def_penalty = 0.0
    home_def_penalty = 0.0

    for _, injury in injuries.iterrows():
        group = injury["Position group"]
        weight = injury_weights[group]
        away_load = float(injury["Away OUT"] or 0) + 0.4 * float(injury["Away questionable"] or 0)
        home_load = float(injury["Home OUT"] or 0) + 0.4 * float(injury["Home questionable"] or 0)

        if group in ["Defensive front / LB", "Secondary"]:
            away_def_penalty += weight * away_load
            home_def_penalty += weight * home_load
        else:
            away_off_penalty += weight * away_load
            home_off_penalty += weight * home_load

    weather = st.selectbox(
        "Expected game conditions",
        ["Normal / roofed", "Heavy rain", "Snow / icy field", "Sustained high wind", "Extreme cold"],
        key=f"weather_{g['game_id']}",
        help="Use only when the forecast known before kickoff supports it. This is a small total-scoring adjustment, not a weather forecast.",
    )
    weather_total_penalty = {
        "Normal / roofed": 0.0,
        "Heavy rain": 1.5,
        "Snow / icy field": 2.0,
        "Sustained high wind": 2.5,
        "Extreme cold": 1.0,
    }[weather]

    # Offense injuries reduce that team's scoring; defensive injuries increase the opponent's scoring.
    adjusted_away = max(
        0.0,
        float(g["projected_away"]) - qb_penalties[away_qb] - away_off_penalty + home_def_penalty,
    )
    adjusted_home = max(
        0.0,
        float(g["projected_home"]) - qb_penalties[home_qb] - home_off_penalty + away_def_penalty,
    )
    adjusted_away = max(0.0, adjusted_away - weather_total_penalty / 2)
    adjusted_home = max(0.0, adjusted_home - weather_total_penalty / 2)

    q1, q2, q3 = st.columns(3)
    q1.metric(
        "Adjusted score preview",
        f"{g['away_team']} {adjusted_away:.1f} – {g['home_team']} {adjusted_home:.1f}",
    )
    q2.metric("Adjusted total", f"{adjusted_away + adjusted_home:.1f}")
    q3.metric(
        "Change vs baseline",
        f"{(adjusted_away + adjusted_home) - float(g['projected_total']):+.1f} pts",
    )
    st.caption(
        f"Estimated own-offense deductions: {g['away_team']} {away_off_penalty:.1f} pts, "
        f"{g['home_team']} {home_off_penalty:.1f} pts. "
        f"Defensive injury allowances to opponent: {g['away_team']} defense {away_def_penalty:.1f} pts, "
        f"{g['home_team']} defense {home_def_penalty:.1f} pts. "
        f"Weather adjustment: -{weather_total_penalty:.1f} total points."
    )

st.divider()
st.subheader("Efficiency model & historical validation")
st.write(
    "The historical efficiency model now tests offensive/defensive EPA and success rate, offense-versus-defense matchup differences, "
    "plays per game as a pace proxy, red-zone touchdown rate when available, turnovers per play when available, and rest-day differences. "
    "It is evaluated chronologically by weekly blocks. Optional PBP fields are used only when present."
)
st.info(
    "The backtest compares the efficiency model with a simple recent-scoring baseline on the same test games. "
    "The first run downloads play-by-play data for 2021–2026 and may take several minutes."
)

if run_backtest:
    run_started_utc = datetime.now(timezone.utc)
    run_id = run_started_utc.strftime("%Y%m%dT%H%M%SZ")

    try:
        with st.spinner("Loading data, building features, and comparing models..."):
            pbp = get_pbp()
            loaded_seasons = sorted(
                pd.to_numeric(pbp["season"], errors="coerce").dropna().astype(int).unique().tolist()
            )
            st.caption(
                "Play-by-play seasons loaded: "
                + ", ".join(map(str, loaded_seasons))
                + ". Features for each game use only earlier-dated games."
            )

            dataset = build_efficiency_model_dataset(games, pbp, lookback_games=lookback)
            results = chronological_backtest(dataset, min_train_games=500)

            diagnostics = [
                c for c in [
                    "home_red_zone_td_rate",
                    "away_red_zone_td_rate",
                    "home_turnovers_per_play",
                    "away_turnovers_per_play",
                    "home_def_takeaways_per_play",
                    "away_def_takeaways_per_play",
                ]
                if c in dataset.columns
            ]

            if diagnostics:
                st.subheader("Feature availability audit")
                diag_rows = []
                broken_features = []

                for col in diagnostics:
                    valid = dataset[col].dropna()
                    row = {
                        "Feature": col,
                        "Non-missing rows": int(valid.size),
                        "Missing %": round(float(dataset[col].isna().mean() * 100), 1),
                        "Unique values": int(valid.nunique()),
                        "Min": round(float(valid.min()), 4) if not valid.empty else np.nan,
                        "Max": round(float(valid.max()), 4) if not valid.empty else np.nan,
                    }
                    diag_rows.append(row)

                    if valid.empty or valid.nunique() <= 1:
                        broken_features.append(col)

                st.dataframe(pd.DataFrame(diag_rows), width="stretch", hide_index=True)

                if broken_features:
                    st.error(
                        "These metrics are missing or constant and therefore cannot add useful predictive information: "
                        + ", ".join(broken_features)
                        + ". Check source-field availability before interpreting the model comparison."
                    )
                else:
                    st.success(
                        "All audited red-zone and turnover features have non-missing variation in the dataset."
                    )

            if "n_active_features" in dataset.columns:
                st.caption(
                    "The training pipeline excludes features that are entirely missing in each training window "
                    "and imputes other missing values using that training window only."
                )

            efficiency_pred = results["predictions"].copy()
            compared = add_scoring_baseline_predictions(efficiency_pred, games, lookback=6)
            metrics = score_prediction_metrics(compared, "pred_home_score", "pred_away_score")
            baseline_metrics = score_prediction_metrics(
                compared, "baseline_home_score", "baseline_away_score"
            )

            # Reproducibility metadata is attached to every exported prediction row.
            excluded_feature_cols = {
                "game_id",
                "gameday",
                "season",
                "week",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "test_block",
                "n_active_features",
                "pred_home_score",
                "pred_away_score",
            }
            model_feature_columns = [
                c for c in dataset.columns
                if c not in excluded_feature_cols and pd.api.types.is_numeric_dtype(dataset[c])
            ]

            # Validate provenance before building the run manifest.
            provenance_columns = [
                "schedule_source_url",
                "schedule_source_rows",
                "schedule_total_line_rows",
                "schedule_game_id_unique",
            ]
            missing_provenance = [
                col for col in provenance_columns if col not in games.columns
            ]

            if games.empty or missing_provenance:
                raise RuntimeError(
                    "Schedule provenance is missing. "
                    f"Empty schedule: {games.empty}; "
                    f"missing columns: {missing_provenance}"
                )

            schedule_source_url = games["schedule_source_url"].iloc[0]
            if pd.isna(schedule_source_url) or not str(schedule_source_url).strip():
                raise RuntimeError("Schedule source URL is missing.")

            schedule_source_rows = int(games["schedule_source_rows"].iloc[0])
            schedule_total_line_rows = int(games["schedule_total_line_rows"].iloc[0])
            schedule_game_id_unique = bool(games["schedule_game_id_unique"].iloc[0])

            run_metadata = {
                "run_id": run_id,
                "run_started_utc": run_started_utc.isoformat(),
                "model_version": MODEL_VERSION,
                "schedule_source_url": schedule_source_url,
                "schedule_source_rows": schedule_source_rows,
                "schedule_total_line_rows": schedule_total_line_rows,
                "schedule_game_id_unique": schedule_game_id_unique,
                "min_train_games": 500,
                "lookback_games": int(lookback),
                "baseline_lookback_games": 6,
                "requested_pbp_seasons": json.dumps([2021, 2022, 2023, 2024, 2025, 2026]),
                "loaded_pbp_seasons": json.dumps(loaded_seasons),
                "dataset_rows": int(len(dataset)),
                "efficiency_prediction_rows": int(results["n"]),
                "comparison_prediction_rows": int(len(compared)),
                "feature_columns_json": json.dumps(model_feature_columns),
            }

            for key, value in run_metadata.items():
                compared[key] = value

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
        st.caption(
            "MAE is average absolute score error; RMSE penalizes large misses more heavily. "
            "Neither is ATS performance."
        )

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
            cols = [
                "gameday",
                "season",
                "away_team",
                "home_team",
                "pred_away_score",
                "away_score",
                "pred_home_score",
                "home_score",
                "baseline_away_score",
                "baseline_home_score",
            ]
            st.dataframe(
                compared[cols].tail(50).sort_values("gameday", ascending=False),
                width="stretch",
                hide_index=True,
            )

        st.download_button(
            "Download comparison predictions CSV",
            compared.to_csv(index=False).encode("utf-8"),
            "nfl_backtest_comparison.csv",
            "text/csv",
        )

        # Totals evaluation: join out-of-sample predictions to the schedule's recorded total line.
        st.divider()
        st.subheader("Historical totals backtest")
        st.write(
            "This section compares each model's projected combined score with the recorded NFLverse total line. "
            "The schedule's total_line is treated as the recorded closing market number; it is not a specific sportsbook quote."
        )

        line_cols = ["game_id", "total_line"]
        if "total_line" not in games.columns:
            st.error("The schedule feed does not include total_line, so the totals backtest cannot run.")
        else:
            lines = games[line_cols].drop_duplicates(subset=["game_id"])
            totals = compared.merge(lines, on="game_id", how="left")
            totals["actual_total"] = totals["home_score"] + totals["away_score"]
            totals["efficiency_projected_total"] = (
                totals["pred_home_score"] + totals["pred_away_score"]
            )
            totals["baseline_projected_total"] = (
                totals["baseline_home_score"] + totals["baseline_away_score"]
            )
            totals = totals.dropna(
                subset=[
                    "total_line",
                    "actual_total",
                    "efficiency_projected_total",
                    "baseline_projected_total",
                ]
            ).copy()

            # Preserve exact run provenance and final row counts in the downloadable CSV.
            totals["totals_export_rows"] = int(len(totals))

            if totals["game_id"].isna().any():
                raise RuntimeError(
                    "Integrity check failed: totals export contains missing game_id values."
                )

            if totals["game_id"].duplicated().any():
                duplicates = (
                    totals.loc[totals["game_id"].duplicated(keep=False), "game_id"]
                    .astype(str)
                    .unique()
                    .tolist()
                )
                raise RuntimeError(
                    "Integrity check failed: totals export contains duplicate game_id values: "
                    + ", ".join(duplicates[:10])
                )

            if len(totals) > len(compared):
                raise RuntimeError(
                    f"Integrity check failed: totals export has {len(totals)} rows but only "
                    f"{len(compared)} comparison predictions exist."
                )

            totals["efficiency_total_error"] = (
                totals["efficiency_projected_total"] - totals["actual_total"]
            ).abs()
            totals["baseline_total_error"] = (
                totals["baseline_projected_total"] - totals["actual_total"]
            ).abs()
            totals["efficiency_edge"] = (
                totals["efficiency_projected_total"] - totals["total_line"]
            )
            totals["baseline_edge"] = (
                totals["baseline_projected_total"] - totals["total_line"]
            )

            total_accuracy = pd.DataFrame([
                {
                    "Model": "EPA / efficiency model",
                    "Games": len(totals),
                    "Total MAE": totals["efficiency_total_error"].mean(),
                    "Average projection minus line": totals["efficiency_edge"].mean(),
                },
                {
                    "Model": "Recent scoring baseline",
                    "Games": len(totals),
                    "Total MAE": totals["baseline_total_error"].mean(),
                    "Average projection minus line": totals["baseline_edge"].mean(),
                },
            ])
            st.caption(
                f"{len(totals):,} historical games with both model predictions and a recorded total line."
            )
            st.dataframe(total_accuracy.round(2), width="stretch", hide_index=True)

            def grade_totals(frame, edge_col, threshold):
                # At threshold zero, require a nonzero edge.
                edge_size = frame[edge_col].abs()
                mask = edge_size > 0 if threshold == 0 else edge_size >= threshold
                bets = frame[mask].copy()
                threshold_label = (
                    "Any nonzero edge" if threshold == 0 else f"{threshold:.1f}+ pts"
                )

                if bets.empty:
                    return {
                        "Edge threshold": threshold_label,
                        "Bets": 0,
                        "Over": 0,
                        "Under": 0,
                        "Wins": 0,
                        "Losses": 0,
                        "Pushes": 0,
                        "Win % (no pushes)": np.nan,
                        "Net units at -110": 0.0,
                        "ROI": np.nan,
                    }

                bets["side"] = np.where(bets[edge_col] > 0, "Over", "Under")
                bets["result"] = np.where(
                    bets["actual_total"] == bets["total_line"],
                    "Push",
                    np.where(
                        (
                            (bets["side"] == "Over")
                            & (bets["actual_total"] > bets["total_line"])
                        )
                        | (
                            (bets["side"] == "Under")
                            & (bets["actual_total"] < bets["total_line"])
                        ),
                        "Win",
                        "Loss",
                    ),
                )

                wins = int((bets["result"] == "Win").sum())
                losses = int((bets["result"] == "Loss").sum())
                pushes = int((bets["result"] == "Push").sum())
                net_units = wins * (100 / 110) - losses
                decided = wins + losses

                return {
                    "Edge threshold": threshold_label,
                    "Bets": len(bets),
                    "Over": int((bets["side"] == "Over").sum()),
                    "Under": int((bets["side"] == "Under").sum()),
                    "Wins": wins,
                    "Losses": losses,
                    "Pushes": pushes,
                    "Win % (no pushes)": (100 * wins / decided) if decided else np.nan,
                    "Net units at -110": net_units,
                    # Pushes remain in total handle and ROI denominator.
                    "ROI": (net_units / len(bets) * 100) if len(bets) else np.nan,
                }

            st.markdown("**EPA / efficiency model: simulated totals record**")
            efficiency_grades = pd.DataFrame([
                grade_totals(totals, "efficiency_edge", t)
                for t in (0, 1.5, 2.5, 3.5, 4.5)
            ])
            efficiency_grades["Win % (no pushes)"] = efficiency_grades[
                "Win % (no pushes)"
            ].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            efficiency_grades["Net units at -110"] = efficiency_grades[
                "Net units at -110"
            ].map(lambda x: f"{x:+.2f}")
            efficiency_grades["ROI"] = efficiency_grades["ROI"].map(
                lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
            )
            st.dataframe(efficiency_grades, width="stretch", hide_index=True)

            st.markdown("**Recent-scoring baseline: simulated totals record**")
            baseline_grades = pd.DataFrame([
                grade_totals(totals, "baseline_edge", t)
                for t in (0, 1.5, 2.5, 3.5, 4.5)
            ])
            baseline_grades["Win % (no pushes)"] = baseline_grades[
                "Win % (no pushes)"
            ].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            baseline_grades["Net units at -110"] = baseline_grades[
                "Net units at -110"
            ].map(lambda x: f"{x:+.2f}")
            baseline_grades["ROI"] = baseline_grades["ROI"].map(
                lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
            )
            st.dataframe(baseline_grades, width="stretch", hide_index=True)

            st.markdown("**Season-by-season totals results**")
            st.caption(
                "Each row is evaluated independently by season, model, and edge threshold. ROI is net units divided by all bets placed, "
                "including pushes in the denominator; win percentage excludes pushes. Small seasonal samples can be very noisy."
            )

            seasonal_rows = []
            model_edge_cols = [
                ("EPA / efficiency model", "efficiency_edge"),
                ("Recent scoring baseline", "baseline_edge"),
            ]

            for yr, season_part in totals.groupby("season", dropna=True):
                for model_name, edge_col in model_edge_cols:
                    for threshold in (0, 1.5, 2.5, 3.5, 4.5):
                        graded = grade_totals(season_part, edge_col, threshold)
                        seasonal_rows.append({
                            "Season": int(yr),
                            "Model": model_name,
                            "Edge threshold": graded["Edge threshold"],
                            "Bets": graded["Bets"],
                            "Wins": graded["Wins"],
                            "Losses": graded["Losses"],
                            "Pushes": graded["Pushes"],
                            "Win % (no pushes)": graded["Win % (no pushes)"],
                            "Net units at -110": graded["Net units at -110"],
                            "ROI": graded["ROI"],
                        })

            seasonal_table = pd.DataFrame(seasonal_rows)
            seasonal_display = seasonal_table.copy()
            seasonal_display["Win % (no pushes)"] = seasonal_display[
                "Win % (no pushes)"
            ].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            seasonal_display["Net units at -110"] = seasonal_display[
                "Net units at -110"
            ].map(lambda x: f"{x:+.2f}")
            seasonal_display["ROI"] = seasonal_display["ROI"].map(
                lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
            )
            st.dataframe(seasonal_display, width="stretch", hide_index=True)

            st.download_button(
                "Download season-by-season totals results CSV",
                seasonal_table.to_csv(index=False).encode("utf-8"),
                "nfl_totals_season_results.csv",
                "text/csv",
            )

            with st.expander("Inspect every totals prediction"):
                inspect = totals[
                    [
                        "gameday",
                        "season",
                        "week",
                        "away_team",
                        "home_team",
                        "actual_total",
                        "total_line",
                        "efficiency_projected_total",
                        "efficiency_edge",
                        "baseline_projected_total",
                        "baseline_edge",
                    ]
                ].copy()
                inspect = inspect.rename(columns={
                    "gameday": "Date",
                    "season": "Season",
                    "week": "Week",
                    "away_team": "Away",
                    "home_team": "Home",
                    "actual_total": "Actual total",
                    "total_line": "Market total",
                    "efficiency_projected_total": "Efficiency projected total",
                    "efficiency_edge": "Efficiency edge",
                    "baseline_projected_total": "Baseline projected total",
                    "baseline_edge": "Baseline edge",
                })
                st.dataframe(
                    inspect.sort_values("Date", ascending=False),
                    width="stretch",
                    hide_index=True,
                )

            st.download_button(
                "Download historical totals backtest CSV",
                totals.to_csv(index=False).encode("utf-8"),
                "nfl_totals_backtest.csv",
                "text/csv",
            )

            export_manifest = {
                **run_metadata,
                "totals_export_rows": int(len(totals)),
                "total_line_nonmissing_rows": (
                    int(games["total_line"].notna().sum())
                    if "total_line" in games
                    else 0
                ),
                "exported_game_ids_sha256": hashlib.sha256(
                    "\n".join(totals["game_id"].astype(str).tolist()).encode("utf-8")
                ).hexdigest(),
                "notes": [
                    "CSV rows are generated from this run's chronological_backtest predictions.",
                    "Rows can be fewer than efficiency_prediction_rows because baseline and market-line joins can drop rows.",
                    "Historical total_line is the schedule-feed value, not a verified sportsbook quote.",
                ],
            }

            st.download_button(
                "Download backtest run manifest (JSON)",
                json.dumps(export_manifest, indent=2).encode("utf-8"),
                "nfl_backtest_run_manifest.json",
                "application/json",
            )

            st.caption(
                "Simulated betting assumptions: 1 unit risked per bet, -110 odds, +0.909 units per win, -1 unit per loss, "
                "0 units on pushes. ROI is net units divided by all bets placed (including pushes); win percentage excludes pushes. "
                "A zero-edge game is not counted as a bet in the 'Any nonzero edge' row. Edge thresholds are exploratory, "
                "not proven optimal. Historical recorded lines are not guaranteed to match the price you could have bet at."
            )

        st.warning(
            "Audit note: the backtest requests 2021–2026 play-by-play. Features for each target game are filtered to games dated "
            "strictly before that target date, so completed 2026 games can inform later 2026 predictions without using "
            "the target game or future games. If any requested season fails to load, the loader reports an error rather "
            "than silently running with stale data. The total-line comparison is not proof of a repeatable betting edge."
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
    - Red-zone touchdown rate is a play-level proxy (touchdown on plays starting inside the opponent's 20), not a drive conversion rate.
    - Turnovers use interception and lost-fumble indicators with schema fallbacks; defensive takeaways are assigned to the defense on that play.
    - Features entirely absent from a training window are excluded; other missing values are imputed using that training window only.
    - The historical test is chronological, but must still be audited for data leakage and compared with simple baselines.
    - No betting record should be published until picks are prospectively timestamped with the line and odds available at publication.
    """)
    st.markdown("[nflverse data releases](https://github.com/nflverse/nflverse-data/releases)")

st.caption(f"Prototype v{MODEL_VERSION} • Reproducible exports and run manifest • Not betting advice")
