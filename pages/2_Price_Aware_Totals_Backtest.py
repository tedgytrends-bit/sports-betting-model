
import numpy as np
import pandas as pd
import streamlit as st

from model import (
    MODEL_VERSION,
    load_schedule_data,
    load_pbp,
    build_efficiency_model_dataset,
    chronological_backtest,
    add_scoring_baseline_predictions,
    chronological_market_residual_backtest,
)

st.set_page_config(
    page_title="Price-Aware Totals Backtest",
    page_icon="🏈",
    layout="wide",
)

st.title("Price-Aware NFL Totals Backtest")
st.caption(f"Experimental research page • Model v{MODEL_VERSION}")

st.warning(
    "Historical closing-line simulation only. The schedule feed is the public "
    "nflverse games dataset, which provides closing totals and over/under prices. "
    "These fields are not tied here to a named sportsbook or a timestamp proving "
    "the price was available when a bet could have been placed. Results are not "
    "proof of a profitable live betting strategy."
)

with st.expander("Odds source and limitations"):
    st.markdown(
        "- **Source:** public nflverse schedule dataset (games.csv).\n"
        "- **Market fields:** historical closing total, over price, and under price.\n"
        "- **Not available in this backtest:** a verified sportsbook name and exact "
        "pre-kickoff capture timestamp for each price.\n"
        "- **Interpretation:** useful for exploratory comparison against closing "
        "market numbers, but not a verified simulation of prices actually available "
        "to you at bet time."
    )
    st.markdown(
        "[nflverse schedule data documentation](https://nflreadr.nflverse.com/reference/load_schedules.html)"
    )

st.write(
    "This page compares the efficiency model with the recent-scoring baseline. "
    "It uses each game's recorded over/under price rather than assuming every "
    "bet pays -110. One unit is risked on every bet."
)

threshold = st.slider(
    "Minimum projected-total edge to bet",
    min_value=1.0,
    max_value=6.0,
    value=3.5,
    step=0.5,
    help=(
        "Bet the over when the projected total exceeds the market total by "
        "at least this many points, or the under when it falls short by "
        "at least this many points."
    ),
)

lookback = st.slider(
    "Efficiency model lookback games",
    min_value=4,
    max_value=16,
    value=10,
)

run = st.button("Run Price-Aware Backtest", type="primary")

@st.cache_data(ttl=1800, show_spinner=False)
def get_schedule():
    return load_schedule_data()

@st.cache_data(ttl=3600, show_spinner=False)
def get_play_by_play():
    return load_pbp((2021, 2022, 2023, 2024, 2025, 2026))


def american_profit_per_unit(odds):
    """Profit on a winning bet when exactly one unit is risked."""
    odds = pd.to_numeric(odds, errors="coerce")
    if pd.isna(odds) or odds == 0:
        return np.nan
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


def grade_bets(data, projected_col, threshold_value, strategy_name):
    """Choose totals bets by edge and grade them using recorded prices."""
    out = data.copy()
    out["projected_total"] = out[projected_col]
    out["edge"] = out["projected_total"] - out["total_line"]

    out["bet_side"] = np.select(
        [
            out["edge"] >= threshold_value,
            out["edge"] <= -threshold_value,
        ],
        ["Over", "Under"],
        default="No bet",
    )

    out["bet_odds"] = np.select(
        [
            out["bet_side"].eq("Over"),
            out["bet_side"].eq("Under"),
        ],
        [
            out["over_odds"].fillna(np.nan),
            out["under_odds"].fillna(np.nan),
        ],
        default=np.nan,
    )
    out["bet_odds"] = pd.to_numeric(out["bet_odds"], errors="coerce")

    # Invalid or unavailable prices cannot be simulated.
    valid_price = out["bet_odds"].le(-100) | out["bet_odds"].ge(100)
    out.loc[
        out["bet_side"].ne("No bet") & ~valid_price,
        "bet_side",
    ] = "No bet"

    out["result"] = "No bet"
    selected = out["bet_side"].isin(["Over", "Under"])

    over = out["bet_side"].eq("Over")
    under = out["bet_side"].eq("Under")
    actual = out["actual_total"]
    line = out["total_line"]

    out.loc[over & (actual > line), "result"] = "Win"
    out.loc[over & (actual < line), "result"] = "Loss"
    out.loc[under & (actual < line), "result"] = "Win"
    out.loc[under & (actual > line), "result"] = "Loss"
    out.loc[selected & (actual == line), "result"] = "Push"

    out["units_risked"] = np.where(selected, 1.0, 0.0)
    out["net_units"] = 0.0

    wins = out["result"].eq("Win")
    losses = out["result"].eq("Loss")

    out.loc[wins, "net_units"] = out.loc[wins, "bet_odds"].apply(
        american_profit_per_unit
    )
    out.loc[losses, "net_units"] = -1.0
    out["strategy"] = strategy_name

    return out


def summarize(data, group_columns=None):
    """Summarize graded bets; excludes no-bets from the betting record."""
    if group_columns is None:
        group_columns = []

    bets = data[data["bet_side"].isin(["Over", "Under"])].copy()

    if bets.empty:
        return pd.DataFrame(
            columns=group_columns + [
                "Bets", "Wins", "Losses", "Pushes",
                "Win rate %", "Net units", "ROI %",
            ]
        )

    if group_columns:
        groups = bets.groupby(group_columns, dropna=False)
    else:
        groups = [(None, bets)]

    rows = []
    for key, part in groups:
        wins = int(part["result"].eq("Win").sum())
        losses = int(part["result"].eq("Loss").sum())
        pushes = int(part["result"].eq("Push").sum())
        total_bets = len(part)
        decisions = wins + losses
        risked = float(part["units_risked"].sum())
        profit = float(part["net_units"].sum())

        row = {
            "Bets": total_bets,
            "Wins": wins,
            "Losses": losses,
            "Pushes": pushes,
            "Win rate %": round(100 * wins / decisions, 2) if decisions else np.nan,
            "Net units": round(profit, 2),
            "ROI %": round(100 * profit / risked, 2) if risked else np.nan,
        }

        if group_columns:
            if len(group_columns) == 1:
                row[group_columns[0]] = key
            else:
                row.update(dict(zip(group_columns, key)))

        rows.append(row)

    result = pd.DataFrame(rows)
    return result[group_columns + [
        "Bets", "Wins", "Losses", "Pushes",
        "Win rate %", "Net units", "ROI %",
    ]]


if run:
    try:
        with st.spinner(
            "Loading historical data and generating chronological predictions..."
        ):
            games = get_schedule()
            pbp = get_play_by_play()

            dataset = build_efficiency_model_dataset(
                games,
                pbp,
                lookback_games=lookback,
            )
            results = chronological_backtest(
                dataset,
                min_train_games=500,
            )

            predictions = results["predictions"].copy()
            compared = add_scoring_baseline_predictions(
                predictions,
                games,
                lookback=6,
            )

            residual_predictions = chronological_market_residual_backtest(
                dataset,
                games,
                min_train_games=500,
            )
            compared = compared.merge(
                residual_predictions,
                on="game_id",
                how="left",
                validate="one_to_one",
            )

            required_odds = ["over_odds", "under_odds"]
            missing_odds = [
                col for col in required_odds if col not in games.columns
            ]
            if missing_odds:
                st.error(
                    "The schedule feed is missing required odds fields: "
                    + ", ".join(missing_odds)
                )
                st.stop()

            schedule_columns = [
                "game_id", "total_line", "over_odds", "under_odds"
            ]
            schedule_prices = games[schedule_columns].copy()

            for col in ["total_line", "over_odds", "under_odds"]:
                schedule_prices[col] = pd.to_numeric(
                    schedule_prices[col], errors="coerce"
                )

            if schedule_prices["game_id"].duplicated().any():
                st.error(
                    "Duplicate game IDs were found in the schedule data. "
                    "Stopping to avoid duplicate or incorrect grading."
                )
                st.stop()

            data = compared.merge(
                schedule_prices,
                on="game_id",
                how="left",
                validate="one_to_one",
            )

            data["actual_total"] = (
                pd.to_numeric(data["home_score"], errors="coerce")
                + pd.to_numeric(data["away_score"], errors="coerce")
            )

            data["efficiency_projected_total"] = (
                data["pred_home_score"] + data["pred_away_score"]
            )
            data["baseline_projected_total"] = (
                data["baseline_home_score"] + data["baseline_away_score"]
            )

            data["market_residual_projected_total"] = (
                data["total_line"] + data["pred_market_residual"]
            )

            data = data.dropna(
                subset=[
                    "season",
                    "total_line",
                    "actual_total",
                    "efficiency_projected_total",
                    "baseline_projected_total",
                ]
            ).copy()

            # Only include games where both recorded prices are in a
            # conventional American-odds range for this comparison.
            valid_over = data["over_odds"].le(-100) | data["over_odds"].ge(100)
            valid_under = data["under_odds"].le(-100) | data["under_odds"].ge(100)
            data["has_valid_prices"] = valid_over & valid_under

            st.session_state["price_aware_data"] = data
            st.session_state["price_aware_threshold"] = threshold
            st.session_state["price_aware_lookback"] = lookback

    except Exception as exc:
        st.error(f"Backtest failed: {exc}")
        st.stop()


if "price_aware_data" in st.session_state:
    data = st.session_state["price_aware_data"].copy()
    used_threshold = st.session_state["price_aware_threshold"]
    used_lookback = st.session_state["price_aware_lookback"]

    # The settings used for the last run are shown explicitly.
    st.caption(
        f"Last run: minimum edge {used_threshold:.1f} points; "
        f"efficiency lookback {used_lookback} games."
    )

    price_data = data[data["has_valid_prices"]].copy()

    st.subheader("Data coverage")

    a, b, c, d = st.columns(4)
    a.metric("Model comparison games", f"{len(data):,}")
    b.metric("Games with valid prices", f"{len(price_data):,}")
    c.metric(
        "Games missing usable prices",
        f"{len(data) - len(price_data):,}",
    )
    d.metric(
        "Seasons represented",
        f"{price_data['season'].nunique():,}",
    )

    if price_data.empty:
        st.warning("No games have usable over and under prices.")
        st.stop()

    efficiency_bets = grade_bets(
        price_data,
        "efficiency_projected_total",
        used_threshold,
        "Efficiency model",
    )
    baseline_bets = grade_bets(
        price_data,
        "baseline_projected_total",
        used_threshold,
        "Recent scoring baseline",
    )
    residual_bets = grade_bets(
        price_data,
        "market_residual_projected_total",
        used_threshold,
        "Market residual model",
    )

    graded = pd.concat(
        [efficiency_bets, baseline_bets, residual_bets],
        ignore_index=True,
    )

    st.subheader("Overall results")

    overall = summarize(graded, ["strategy"])
    st.dataframe(
        overall.sort_values("strategy"),
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "ROI = net units divided by total units risked. Win rate excludes "
        "pushes. Each bet risks one unit; winning profit uses the recorded "
        "American odds. No-bets are excluded from the record."
    )

    st.subheader("Season-by-season results")

    season_results = summarize(graded, ["strategy", "season"])
    if not season_results.empty:
        season_results["season"] = season_results["season"].astype(int)
        season_results = season_results.sort_values(["season", "strategy"])
        st.dataframe(
            season_results,
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("Model-versus-market validation")

    # These diagnostics evaluate whether the model's disagreement with the
    # closing total contains information about the final total. They are
    # descriptive only; thresholds must not be selected from these same rows
    # and then presented as an independent test.
    edge_data = price_data.copy()
    edge_data["market_error"] = (
        pd.to_numeric(edge_data["actual_total"], errors="coerce")
        - pd.to_numeric(edge_data["total_line"], errors="coerce")
    )
    edge_data["model_edge"] = (
        pd.to_numeric(edge_data["efficiency_projected_total"], errors="coerce")
        - pd.to_numeric(edge_data["total_line"], errors="coerce")
    )
    edge_data = edge_data.dropna(subset=["market_error", "model_edge"]).copy()
    edge_data["direction_correct"] = (
        np.sign(edge_data["model_edge"]) == np.sign(edge_data["market_error"])
    ) & edge_data["market_error"].ne(0) & edge_data["model_edge"].ne(0)

    corr = edge_data["model_edge"].corr(edge_data["market_error"])
    eligible = edge_data[edge_data["model_edge"].abs() >= used_threshold].copy()
    eligible = eligible[eligible["market_error"].ne(0)]
    direction_accuracy = (
        100 * eligible["direction_correct"].mean()
        if not eligible.empty else np.nan
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Edge / market-error correlation", f"{corr:.3f}" if pd.notna(corr) else "N/A")
    m2.metric(
        f"Direction correct (edge ≥ {used_threshold:.1f})",
        f"{direction_accuracy:.1f}%" if pd.notna(direction_accuracy) else "N/A",
    )
    m3.metric("Games in direction check", f"{len(eligible):,}")

    st.caption(
        "Market error = actual total minus closing total. Model edge = projected "
        "total minus closing total. A positive correlation means the model edge "
        "tends to point in the same direction as the market's eventual error. "
        "This is a diagnostic on the displayed historical sample, not proof of "
        "future profitability."
    )

    edge_bins = [
        (0.0, 1.0, "0 to <1"),
        (1.0, 2.0, "1 to <2"),
        (2.0, 3.5, "2 to <3.5"),
        (3.5, 5.0, "3.5 to <5"),
        (5.0, 7.5, "5 to <7.5"),
        (7.5, np.inf, "7.5+"),
    ]
    bin_rows = []
    for lower, upper, label in edge_bins:
        part = edge_data[
            (edge_data["model_edge"].abs() >= lower)
            & (edge_data["model_edge"].abs() < upper)
            & edge_data["market_error"].ne(0)
        ].copy()
        if part.empty:
            bin_rows.append({
                "Absolute model edge (points)": label,
                "Games": 0,
                "Direction correct %": np.nan,
                "Mean absolute market error (points)": np.nan,
            })
            continue
        bin_rows.append({
            "Absolute model edge (points)": label,
            "Games": len(part),
            "Direction correct %": round(100 * part["direction_correct"].mean(), 1),
            "Mean absolute market error (points)": round(part["market_error"].abs().mean(), 2),
        })
    st.dataframe(pd.DataFrame(bin_rows), hide_index=True, use_container_width=True)

    season_rows = []
    for season, part in edge_data.groupby("season"):
        selected = part[
            (part["model_edge"].abs() >= used_threshold)
            & part["market_error"].ne(0)
        ]
        season_rows.append({
            "Season": int(season),
            "Games with edge": len(selected),
            "Direction correct %": (
                round(100 * selected["direction_correct"].mean(), 1)
                if not selected.empty else np.nan
            ),
            "Edge / market-error correlation": round(part["model_edge"].corr(part["market_error"]), 3),
        })
    st.caption("Season split uses the same fixed edge threshold as the backtest above.")
    st.dataframe(pd.DataFrame(season_rows), hide_index=True, use_container_width=True)

    st.subheader("Over/under performance by season")

    # Keep the original 3.5-point threshold fixed. This table diagnoses whether
    # the over/under difference survives the later-season period; it is not used
    # to optimize a new threshold.
    side_season_rows = []
    for strategy_name, strategy_data in graded.groupby("strategy"):
        for season, season_data in strategy_data.groupby("season"):
            for side in ["Over", "Under"]:
                part = season_data[season_data["bet_side"] == side]
                wins = int(part["result"].eq("Win").sum())
                losses = int(part["result"].eq("Loss").sum())
                pushes = int(part["result"].eq("Push").sum())
                risked = float(part["units_risked"].sum())
                profit = float(part["net_units"].sum())
                decisions = wins + losses
                side_season_rows.append({
                    "Strategy": strategy_name,
                    "Season": int(season),
                    "Side": side,
                    "Bets": len(part),
                    "Wins": wins,
                    "Losses": losses,
                    "Pushes": pushes,
                    "Win rate %": round(100 * wins / decisions, 2) if decisions else np.nan,
                    "Net units": round(profit, 2),
                    "ROI %": round(100 * profit / risked, 2) if risked else np.nan,
                })
    side_season = pd.DataFrame(side_season_rows)
    if not side_season.empty:
        st.dataframe(
            side_season.sort_values(["Strategy", "Season", "Side"]),
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("Over/under performance: earlier vs. later seasons")
    side_season["period"] = np.where(
        pd.to_numeric(side_season["Season"], errors="coerce") <= 2024,
        "Earlier period (2022–2024)",
        "Later holdout (2025–2026)",
    )
    period_rows = []
    for (strategy_name, period, side), part in side_season.groupby(
        ["Strategy", "period", "Side"], dropna=False
    ):
        wins = int(part["Wins"].sum())
        losses = int(part["Losses"].sum())
        pushes = int(part["Pushes"].sum())
        bets = int(part["Bets"].sum())
        risked = float(bets)
        profit = float(part["Net units"].sum())
        decisions = wins + losses
        period_rows.append({
            "Strategy": strategy_name,
            "Period": period,
            "Side": side,
            "Bets": bets,
            "Wins": wins,
            "Losses": losses,
            "Pushes": pushes,
            "Win rate %": round(100 * wins / decisions, 2) if decisions else np.nan,
            "Net units": round(profit, 2),
            "ROI %": round(100 * profit / risked, 2) if risked else np.nan,
        })
    st.dataframe(
        pd.DataFrame(period_rows).sort_values(["Strategy", "Period", "Side"]),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "The threshold is unchanged from the main backtest. Empty side/season "
        "cells indicate no qualifying bets. Use the later period as a stress test, "
        "not as proof of future performance."
    )

    st.subheader("Fixed chronological holdout")

    st.write(
        "For a more conservative check, this section separates earlier seasons "
        "(2022–2024) from later seasons (2025–2026). The 3.5-point threshold is "
        "kept fixed rather than optimized separately for each period. Because "
        "the odds source and exact pre-kickoff availability are unverified, this "
        "remains a historical diagnostic, not a live-betting result."
    )
    holdout = graded.copy()
    holdout["period"] = np.where(
        pd.to_numeric(holdout["season"], errors="coerce") <= 2024,
        "Earlier period (2022–2024)",
        "Later holdout (2025–2026)",
    )
    holdout_summary = summarize(holdout, ["strategy", "period"])
    if not holdout_summary.empty:
        holdout_summary = holdout_summary.sort_values(["strategy", "period"])
        st.dataframe(
            holdout_summary,
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No eligible bets were available for the period comparison.")

    st.subheader("Projection accuracy vs. market")

    accuracy = price_data.copy()
    accuracy["efficiency_abs_error"] = (
        accuracy["efficiency_projected_total"] - accuracy["actual_total"]
    ).abs()
    accuracy["baseline_abs_error"] = (
        accuracy["baseline_projected_total"] - accuracy["actual_total"]
    ).abs()
    accuracy["market_abs_error"] = (
        accuracy["total_line"] - accuracy["actual_total"]
    ).abs()
    accuracy["efficiency_signed_error"] = (
        accuracy["efficiency_projected_total"] - accuracy["actual_total"]
    )
    accuracy["baseline_signed_error"] = (
        accuracy["baseline_projected_total"] - accuracy["actual_total"]
    )

    accuracy_summary = pd.DataFrame([
        {
            "Forecast": "Efficiency model",
            "Games": len(accuracy),
            "Mean absolute error (points)": round(accuracy["efficiency_abs_error"].mean(), 2),
            "Mean signed error (points)": round(accuracy["efficiency_signed_error"].mean(), 2),
        },
        {
            "Forecast": "Recent scoring baseline",
            "Games": len(accuracy),
            "Mean absolute error (points)": round(accuracy["baseline_abs_error"].mean(), 2),
            "Mean signed error (points)": round(accuracy["baseline_signed_error"].mean(), 2),
        },
        {
            "Forecast": "Closing market total",
            "Games": len(accuracy),
            "Mean absolute error (points)": round(accuracy["market_abs_error"].mean(), 2),
            "Mean signed error (points)": round((accuracy["total_line"] - accuracy["actual_total"]).mean(), 2),
        },
        {
            "Forecast": "Market residual model",
            "Games": int(accuracy["market_residual_projected_total"].notna().sum()),
            "Mean absolute error (points)": round(
                (accuracy["market_residual_projected_total"] - accuracy["actual_total"]).abs().mean(), 2
            ),
            "Mean signed error (points)": round(
                (accuracy["market_residual_projected_total"] - accuracy["actual_total"]).mean(), 2
            ),
        },
    ])
    st.dataframe(accuracy_summary, hide_index=True, use_container_width=True)
    st.caption(
        "Mean absolute error (MAE) is lower-is-better. Signed error is forecast "
        "minus actual total; positive values mean overprojection and negative "
        "values mean underprojection. The market comparison uses closing totals "
        "from the same unverified historical source."
    )

    st.subheader("Over/under results by side")
    side_rows = []
    for strategy_name, strategy_data in graded.groupby("strategy"):
        selected = strategy_data[strategy_data["bet_side"].isin(["Over", "Under"])]
        for side in ["Over", "Under"]:
            part = selected[selected["bet_side"] == side]
            wins = int(part["result"].eq("Win").sum())
            losses = int(part["result"].eq("Loss").sum())
            pushes = int(part["result"].eq("Push").sum())
            risked = float(part["units_risked"].sum())
            profit = float(part["net_units"].sum())
            decisions = wins + losses
            side_rows.append({
                "Strategy": strategy_name,
                "Side": side,
                "Bets": len(part),
                "Wins": wins,
                "Losses": losses,
                "Pushes": pushes,
                "Win rate %": round(100 * wins / decisions, 2) if decisions else np.nan,
                "Net units": round(profit, 2),
                "ROI %": round(100 * profit / risked, 2) if risked else np.nan,
            })
    st.dataframe(pd.DataFrame(side_rows), hide_index=True, use_container_width=True)
    st.caption(
        "Side results use the fixed threshold from this run and the recorded "
        "over/under prices. They are descriptive diagnostics, not a basis for "
        "choosing a side-specific threshold after seeing results."
    )

    st.subheader("Bet-level results")

    strategy_choice = st.selectbox(
        "Choose model to inspect",
        ["Efficiency model", "Recent scoring baseline", "Market residual model"],
    )
    bet_details = graded[
        (graded["strategy"] == strategy_choice)
        & graded["bet_side"].isin(["Over", "Under"])
    ].copy()

    display_columns = [
        "gameday",
        "season",
        "week",
        "away_team",
        "home_team",
        "actual_total",
        "total_line",
        "projected_total",
        "edge",
        "bet_side",
        "bet_odds",
        "result",
        "net_units",
    ]
    display_columns = [
        col for col in display_columns if col in bet_details.columns
    ]

    st.dataframe(
        bet_details[display_columns].sort_values(
            ["season", "gameday"]
        ),
        hide_index=True,
        use_container_width=True,
    )

    # Carry odds provenance with every exported row so results are not detached
    # from the limitations of the historical schedule-price source.
    graded["odds_source"] = "nflverse public games.csv schedule dataset"
    graded["odds_type"] = "Historical closing total and over/under prices"
    graded["sportsbook_verified"] = False
    graded["pre_kickoff_price_timestamp_verified"] = False

    st.caption(
        "Export provenance is included: source dataset, closing-price classification, "
        "and explicit flags that sportsbook identity and exact bet-time availability "
        "have not been verified."
    )
    st.download_button(
        "Download all price-aware bet results",
        graded.to_csv(index=False).encode("utf-8"),
        "nfl_price_aware_totals_backtest.csv",
        "text/csv",
    )

    st.subheader("Interpretation")
    st.write(
        "Use this page to compare the efficiency model against the recent-scoring "
        "baseline under the same price and edge rules. Do not choose a threshold "
        "solely because it produced the best historical ROI; different thresholds "
        "can produce very different sample sizes and results."
    )
    st.write(
        "The historical schedule prices are closing-line fields from nflverse. "
        "Their exact sportsbook and capture time are not attached to this backtest, "
        "so the ROI should be treated as exploratory market-close research—not as "
        "proof that the same bets could have been placed at those prices."
    )
else:
    st.info(
        "Choose your minimum edge and lookback, then click "
        "'Run Price-Aware Backtest'. The page will generate predictions and "
        "grade eligible bets using the recorded over/under prices."
    )
