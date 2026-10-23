
import pandas as pd
import streamlit as st
from model import load_schedule_data

st.set_page_config(
    page_title="Schedule Data Audit",
    page_icon="🏈",
    layout="wide",
)

st.title("NFL Schedule Data Audit")
st.write(
    "This page checks whether historical schedule data contains "
    "completed results, closing totals, and actual over/under odds."
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

    if "over_odds" not in games.columns or "under_odds" not in games.columns:
        st.warning(
            "The schedule feed does not contain both over_odds and "
            "under_odds. This source alone cannot support price-specific "
            "historical returns. We need to find a historical odds source."
        )

    df = games.copy()

    for col in [
        "home_score", "away_score", "total_line",
        "over_odds", "under_odds",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Completed"] = df["home_score"].notna() & df["away_score"].notna()
    df["Has closing total"] = df["total_line"].notna()

    if "over_odds" in df.columns and "under_odds" in df.columns:
        df["Has both odds"] = (
            df["over_odds"].notna() & df["under_odds"].notna()
        )
    else:
        df["Has both odds"] = False

    completed = df["Completed"]
    df["Completed with total"] = completed & df["Has closing total"]
    df["Completed with both odds"] = completed & df["Has both odds"]

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

    completed_count = int(df["Completed"].sum())
    completed_total_count = int(df["Completed with total"].sum())
    completed_odds_count = int(df["Completed with both odds"].sum())

    a, b, c = st.columns(3)
    a.metric("Completed games", f"{completed_count:,}")
    b.metric("Completed games with totals", f"{completed_total_count:,}")
    c.metric("Completed games with both odds", f"{completed_odds_count:,}")

    st.subheader("What this means")

    if completed_odds_count > 0:
        st.write(
            f"The feed contains both over and under odds for "
            f"{completed_odds_count:,} completed games. Next, we need to "
            "check how many overlap with the model's backtest predictions "
            "and whether the prices represent usable historical betting odds."
        )
    else:
        st.write(
            "No completed games have both over and under odds in this feed. "
            "We need another historical odds source before calculating "
            "price-specific betting returns."
        )

    st.caption(
        "Having both odds recorded is a first check, not proof that the "
        "prices were available before kickoff or that they represent "
        "the sportsbook you would have used."
    )

    st.download_button(
        "Download coverage report",
        report.to_csv(index=False).encode("utf-8"),
        "schedule_coverage_report.csv",
        "text/csv",
    )
