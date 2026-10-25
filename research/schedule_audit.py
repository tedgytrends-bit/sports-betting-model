
import pandas as pd
import streamlit as st
from model import load_schedule_data

st.title("Schedule Data Audit")
st.write(
    "Check historical game coverage and inspect whether over/under odds "
    "look like usable American betting prices."
)

if st.button("Run Data Audit", type="primary"):
    st.cache_data.clear()

    with st.spinner("Loading schedule data..."):
        try:
            games = load_schedule_data()
        except Exception as exc:
            st.error(f"Could not load schedule data: {exc}")
            st.stop()

    required = [
        "season", "game_id", "home_score", "away_score", "total_line"
    ]
    missing = [col for col in required if col not in games.columns]

    if missing:
        st.error(f"Required columns are missing: {missing}")
        st.stop()

    df = games.copy()

    numeric_columns = [
        "season", "week", "home_score", "away_score",
        "total_line", "over_odds", "under_odds",
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Completed"] = df["home_score"].notna() & df["away_score"].notna()
    df["Has closing total"] = df["total_line"].notna()

    has_odds_columns = (
        "over_odds" in df.columns and "under_odds" in df.columns
    )

    if has_odds_columns:
        df["Has both odds"] = (
            df["over_odds"].notna() & df["under_odds"].notna()
        )
    else:
        df["Has both odds"] = False

    df["Completed with total"] = (
        df["Completed"] & df["Has closing total"]
    )
    df["Completed with both odds"] = (
        df["Completed"] & df["Has both odds"]
    )

    # ATS data audit: spread_line is treated as the home team's handicap
    # only for diagnostics. The sign convention is explicitly surfaced below
    # and must be confirmed before any ATS model is trusted.
    if "spread_line" in df.columns:
        df["spread_line"] = pd.to_numeric(df["spread_line"], errors="coerce")
    else:
        df["spread_line"] = float("nan")
    df["Has spread line"] = df["spread_line"].notna()
    df["Completed with spread"] = df["Completed"] & df["Has spread line"]
    df["Actual home margin"] = df["home_score"] - df["away_score"]
    df["Home ATS margin (assumes home spread)"] = (
        df["Actual home margin"] + df["spread_line"]
    )

    report = (
        df.groupby("season")
        .agg(
            Scheduled_games=("game_id", "size"),
            Completed_games=("Completed", "sum"),
            Completed_with_total=("Completed with total", "sum"),
            Completed_with_both_odds=("Completed with both odds", "sum"),
        )
        .reset_index()
        .sort_values("season")
    )

    count_columns = [
        "Scheduled_games",
        "Completed_games",
        "Completed_with_total",
        "Completed_with_both_odds",
    ]
    report[count_columns] = report[count_columns].astype(int)

    st.subheader("Coverage by season")
    st.dataframe(report, hide_index=True, use_container_width=True)

    a, b, c = st.columns(3)
    a.metric("Completed games", f"{int(df['Completed'].sum()):,}")
    b.metric(
        "Completed games with totals",
        f"{int(df['Completed with total'].sum()):,}",
    )
    c.metric(
        "Completed games with both odds",
        f"{int(df['Completed with both odds'].sum()):,}",
    )

    st.subheader("ATS spread-data audit")

    spread_report = (
        df.groupby("season")
        .agg(
            Scheduled_games=("game_id", "size"),
            Completed_games=("Completed", "sum"),
            Games_with_spread=("Has spread line", "sum"),
            Completed_with_spread=("Completed with spread", "sum"),
        )
        .reset_index()
        .sort_values("season")
    )
    for col in [
        "Scheduled_games", "Completed_games", "Games_with_spread",
        "Completed_with_spread",
    ]:
        spread_report[col] = spread_report[col].astype(int)

    total_completed = df[df["Completed"]]
    completed_with_spread = total_completed[
        total_completed["spread_line"].notna()
    ].copy()
    x, y, z = st.columns(3)
    x.metric("Completed games", f"{len(total_completed):,}")
    y.metric("Completed games with spread", f"{len(completed_with_spread):,}")
    z.metric(
        "Spread coverage",
        f"{len(completed_with_spread) / len(total_completed) * 100:.1f}%"
        if len(total_completed) else "—",
    )
    st.dataframe(spread_report, hide_index=True, use_container_width=True)

    st.caption(
        "For the diagnostic below only, we test the convention that spread_line "
        "is the home team's handicap: home ATS margin = home score − away score "
        "+ spread_line. This convention must be confirmed against the source "
        "documentation and known games before grading ATS results. The schedule "
        "feed does not establish a sportsbook, price, or line timestamp."
    )

    if completed_with_spread.empty:
        st.warning("No completed games have spread_line values; ATS backtesting cannot proceed from this feed.")
    else:
        margin = completed_with_spread["Home ATS margin (assumes home spread)"]
        graded = margin.dropna()
        q1, q2, q3 = st.columns(3)
        q1.metric("Assumed home covers", f"{int((graded > 0).sum()):,}")
        q2.metric("Assumed away covers", f"{int((graded < 0).sum()):,}")
        q3.metric("Assumed pushes", f"{int((graded == 0).sum()):,}")

        st.write("Example completed games for sign-convention review")
        example_cols = [
            "season", "week", "gameday", "game_id", "away_team", "home_team",
            "away_score", "home_score", "spread_line", "Actual home margin",
            "Home ATS margin (assumes home spread)",
        ]
        st.dataframe(
            completed_with_spread[
                [c for c in example_cols if c in completed_with_spread.columns]
            ].sort_values(["season", "week"]).tail(30),
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("Odds field availability")

    if not has_odds_columns:
        st.error(
            "The schedule feed does not contain both over_odds and "
            "under_odds. We cannot inspect historical prices from this feed."
        )
    else:
        completed = df[df["Completed"]].copy()
        both_odds = completed[
            completed["over_odds"].notna()
            & completed["under_odds"].notna()
        ].copy()

        st.write(
            f"Both odds fields are populated for {len(both_odds):,} "
            f"of {len(completed):,} completed games."
        )

        if both_odds.empty:
            st.warning("There are no completed games with both odds populated.")
        else:
            # Basic checks for values that resemble American odds.
            # Typical American odds are <= -100 or >= +100.
            for col in ["over_odds", "under_odds"]:
                values = both_odds[col]
                both_odds[f"{col}_looks_like_american"] = (
                    values.le(-100) | values.ge(100)
                )

            over_valid = int(
                both_odds["over_odds_looks_like_american"].sum()
            )
            under_valid = int(
                both_odds["under_odds_looks_like_american"].sum()
            )

            x, y = st.columns(2)
            x.metric(
                "Over prices in typical American-odds format",
                f"{over_valid:,} / {len(both_odds):,}",
            )
            y.metric(
                "Under prices in typical American-odds format",
                f"{under_valid:,} / {len(both_odds):,}",
            )

            st.caption(
                "This is only a format check. It does not prove that the "
                "prices are correctly sourced, closing prices, or prices "
                "that were available at the time of a bet."
            )

            st.subheader("Odds value summary")

            summary_rows = []
            for col in ["over_odds", "under_odds"]:
                values = both_odds[col].dropna()
                summary_rows.append(
                    {
                        "Field": col,
                        "Non-missing values": int(values.size),
                        "Unique values": int(values.nunique()),
                        "Minimum": values.min() if not values.empty else None,
                        "25th percentile": (
                            values.quantile(0.25) if not values.empty else None
                        ),
                        "Median": (
                            values.median() if not values.empty else None
                        ),
                        "75th percentile": (
                            values.quantile(0.75) if not values.empty else None
                        ),
                        "Maximum": values.max() if not values.empty else None,
                        "Outside typical American format": int(
                            (~(values.le(-100) | values.ge(100))).sum()
                        ),
                    }
                )

            st.dataframe(
                pd.DataFrame(summary_rows),
                hide_index=True,
                use_container_width=True,
            )

            st.subheader("Most common odds values")

            left, right = st.columns(2)
            with left:
                st.write("**Over odds**")
                st.dataframe(
                    both_odds["over_odds"]
                    .value_counts()
                    .head(15)
                    .rename_axis("Odds")
                    .reset_index(name="Games"),
                    hide_index=True,
                    use_container_width=True,
                )

            with right:
                st.write("**Under odds**")
                st.dataframe(
                    both_odds["under_odds"]
                    .value_counts()
                    .head(15)
                    .rename_axis("Odds")
                    .reset_index(name="Games"),
                    hide_index=True,
                    use_container_width=True,
                )

            st.subheader("Example games")

            preferred_columns = [
                "season", "week", "gameday", "game_id",
                "away_team", "home_team", "away_score", "home_score",
                "total_line", "over_odds", "under_odds",
            ]
            display_columns = [
                col for col in preferred_columns if col in both_odds.columns
            ]

            examples = both_odds.sort_values(
                ["season", "week"] if "week" in both_odds.columns else ["season"]
            ).tail(30)

            st.dataframe(
                examples[display_columns],
                hide_index=True,
                use_container_width=True,
            )

            suspicious = both_odds[
                ~both_odds["over_odds_looks_like_american"]
                | ~both_odds["under_odds_looks_like_american"]
            ]

            if not suspicious.empty:
                st.warning(
                    f"{len(suspicious):,} completed games have at least one "
                    "odds value outside the typical American-odds format. "
                    "Review these before using the prices in a backtest."
                )
                st.dataframe(
                    suspicious[display_columns].head(50),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.success(
                    "All populated over/under odds values pass the basic "
                    "American-odds format check."
                )

            st.download_button(
                "Download completed games with odds",
                both_odds[display_columns].to_csv(index=False).encode("utf-8"),
                "completed_games_with_odds.csv",
                "text/csv",
            )

    st.subheader("What this audit does—and does not—prove")
    st.write(
        "- Adds season-by-season coverage for historical spread_line values and an assumed home-spread sign check.\n"
        "- The spread sign convention must be verified before ATS results are graded.\n"
        "- The schedule feed does not verify sportsbook, line timestamp, or ATS odds; any ROI at assumed -110 would be illustrative only.\n"
        "- Confirms how many completed games have totals and both odds fields.\n"
        "- Shows the actual values and checks whether they resemble American odds.\n"
        "- Does not verify the sportsbook, the timing of the prices, or whether "
        "the prices are genuine historical closing odds.\n"
        "- Does not change the model, backtest, or betting recommendations."
    )

    st.download_button(
        "Download coverage report",
        report.to_csv(index=False).encode("utf-8"),
        "schedule_coverage_report.csv",
        "text/csv",
    )
