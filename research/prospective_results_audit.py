from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from model import load_schedule_data

st.title("Prospective Results Audit")
st.caption("Forward-looking snapshot grading • Research only • No claim of sportsbook execution")

SNAPSHOT_DIR = Path("data/prospective_ats_tracking")
SNAPSHOT_PATTERN = "ats_market_snapshot_*.csv"
EDGE_THRESHOLD = 3.5
UNIT_RISK = 1.0
WIN_PROFIT_AT_MINUS_110 = 100 / 110

files = sorted(SNAPSHOT_DIR.glob(SNAPSHOT_PATTERN))
if not files:
    st.info("No saved snapshots found yet. Run the GitHub Actions workflow named 'Capture prospective ATS snapshots'.")
    st.stop()

parts = []
read_errors = []
for path in files:
    try:
        frame = pd.read_csv(path, low_memory=False)
        if not frame.empty:
            frame["snapshot_file"] = path.name
            parts.append(frame)
    except Exception as exc:
        read_errors.append(f"{path.name}: {exc}")

for message in read_errors:
    st.warning(f"Could not read snapshot file — {message}")

if not parts:
    st.info("Snapshot files are empty or could not be read.")
    st.stop()

archive = pd.concat(parts, ignore_index=True, sort=False)
required_snapshot_columns = ["game_id", "captured_at_utc"]
missing_columns = [col for col in required_snapshot_columns if col not in archive.columns]
if missing_columns:
    st.error(f"Snapshot archive is missing required columns: {missing_columns}")
    st.stop()

archive["captured_at_utc"] = pd.to_datetime(archive["captured_at_utc"], errors="coerce", utc=True)
for col in [
    "spread_line_source_value",
    "total_line_source_value",
    "baseline_predicted_home_margin",
    "baseline_projected_total",
]:
    if col not in archive.columns:
        archive[col] = np.nan
    archive[col] = pd.to_numeric(archive[col], errors="coerce")

# Preserve the raw archive, but do not let an early incomplete observation
# permanently disqualify a game. Older collector versions sometimes saved the
# matchup before a line/prediction was available. For each market, select the
# earliest pregame observation containing both its prediction and market line.
# The selection is made independently for ATS and totals; no later result or
# score is used to choose a snapshot.
archive = archive.sort_values(
    ["game_id", "captured_at_utc", "snapshot_file"],
    ascending=[True, True, True],
    na_position="last",
)
unique_game_count = int(archive["game_id"].nunique())
duplicate_observations = int(len(archive) - unique_game_count)
first_snapshot = archive.drop_duplicates("game_id", keep="first").copy()

# Timing classification must be available before choosing market snapshots.
# Use the raw archive to determine whether each observation was captured before
# the scheduled UTC date; exact kickoff/publication timestamps are unavailable.
if "gameday_utc" in archive.columns:
    archive["scheduled_date_utc"] = pd.to_datetime(
        archive["gameday_utc"], errors="coerce", utc=True
    ).dt.floor("D")
elif "gameday" in archive.columns:
    archive["scheduled_date_utc"] = pd.to_datetime(
        archive["gameday"], errors="coerce", utc=True
    ).dt.floor("D")
else:
    archive["scheduled_date_utc"] = pd.NaT
archive["capture_date_utc"] = archive["captured_at_utc"].dt.floor("D")
archive["timing_status"] = np.select(
    [
        archive["captured_at_utc"].isna() | archive["scheduled_date_utc"].isna(),
        archive["capture_date_utc"] < archive["scheduled_date_utc"],
        archive["capture_date_utc"] == archive["scheduled_date_utc"],
        archive["capture_date_utc"] > archive["scheduled_date_utc"],
    ],
    ["Unknown timing", "Definitely before scheduled date", "Same-day timing uncertain", "Captured after scheduled date"],
    default="Unknown timing",
)

try:
    schedule = load_schedule_data()
except Exception as exc:
    st.error(f"Unable to load schedule/final scores: {exc}")
    st.stop()

score_columns = ["game_id", "home_score", "away_score"]
missing_score_columns = [col for col in score_columns if col not in schedule.columns]
if missing_score_columns:
    st.error(f"Schedule source is missing score fields: {missing_score_columns}")
    st.stop()

scores = schedule[score_columns].copy()
scores["home_score"] = pd.to_numeric(scores["home_score"], errors="coerce")
scores["away_score"] = pd.to_numeric(scores["away_score"], errors="coerce")
scores = scores.drop_duplicates("game_id", keep="first")
graded = first_snapshot.merge(scores, on="game_id", how="left", validate="one_to_one")
graded["final_available"] = graded["home_score"].notna() & graded["away_score"].notna()
graded["actual_margin"] = graded["home_score"] - graded["away_score"]
graded["actual_total"] = graded["home_score"] + graded["away_score"]
graded["ats_edge"] = graded["baseline_predicted_home_margin"] - graded["spread_line_source_value"]
graded["total_edge"] = graded["baseline_projected_total"] - graded["total_line_source_value"]

# Select earliest complete pregame observation separately for each market.
# Incomplete early rows remain visible in the raw archive, but do not block a
# later valid pregame observation from being evaluated.
def first_complete_market_snapshot(edge_col, line_col):
    candidates = archive[
        archive["timing_status"].eq("Definitely before scheduled date")
        & archive[edge_col].notna()
        & archive[line_col].notna()
    ].copy()
    return candidates.drop_duplicates("game_id", keep="first")

ats_selected = first_complete_market_snapshot("ats_edge", "spread_line_source_value")
totals_selected = first_complete_market_snapshot("total_edge", "total_line_source_value")
ats_game_ids = set(ats_selected["game_id"])
totals_game_ids = set(totals_selected["game_id"])
ats_population = graded[graded["game_id"].isin(ats_game_ids)].copy()
totals_population = graded[graded["game_id"].isin(totals_game_ids)].copy()
ats_population = ats_population.drop(columns=["captured_at_utc", "snapshot_file"], errors="ignore").merge(
    ats_selected[["game_id", "captured_at_utc", "snapshot_file", "timing_status"]].drop_duplicates("game_id"),
    on="game_id", how="left", validate="one_to_one", suffixes=("", "_selected")
)
totals_population = totals_population.drop(columns=["captured_at_utc", "snapshot_file"], errors="ignore").merge(
    totals_selected[["game_id", "captured_at_utc", "snapshot_file", "timing_status"]].drop_duplicates("game_id"),
    on="game_id", how="left", validate="one_to_one", suffixes=("", "_selected")
)
timing_uncertain_count = int(first_snapshot["timing_status"].isin(["Same-day timing uncertain", "Unknown timing"]).sum())
late_capture_count = int(first_snapshot["timing_status"].eq("Captured after scheduled date").sum())
pregame = graded[graded["timing_status"] == "Definitely before scheduled date"].copy()


def grade_market(frame, edge_col, actual_col, line_col):
    market = frame.copy()
    market["line_available"] = market[line_col].notna()
    market["prediction_available"] = market[edge_col].notna()
    market["eligible_edge"] = market[edge_col].abs() >= EDGE_THRESHOLD
    eligible = market[
        market["final_available"]
        & market["line_available"]
        & market["prediction_available"]
        & market["eligible_edge"]
    ].copy()

    # Positive spread_line means home favored in the nflverse schedule convention.
    # Therefore actual home margin minus spread_line is the home ATS cover margin.
    eligible["actual_margin_vs_line"] = eligible[actual_col] - eligible[line_col]
    eligible["result"] = np.select(
        [
            eligible["actual_margin_vs_line"].eq(0),
            eligible["actual_margin_vs_line"] * np.sign(eligible[edge_col]) > 0,
        ],
        ["Push", "Win"],
        default="Loss",
    )
    eligible["units_risked"] = UNIT_RISK
    eligible["net_units"] = np.select(
        [eligible["result"].eq("Win"), eligible["result"].eq("Loss")],
        [WIN_PROFIT_AT_MINUS_110, -UNIT_RISK],
        default=0.0,
    )
    return market, eligible


ats_population, ats = grade_market(ats_population, "ats_edge", "actual_margin", "spread_line_source_value")
totals_population, totals = grade_market(totals_population, "total_edge", "actual_total", "total_line_source_value")

st.subheader("Snapshot coverage and data quality")
a, b, c, d = st.columns(4)
a.metric("Unique games in archive", f"{unique_game_count:,}")
b.metric("Repeated observations not re-graded", f"{duplicate_observations:,}")
c.metric("Games with final scores", f"{int(graded['final_available'].sum()):,}")
d.metric("Definitely pregame snapshots", f"{len(pregame):,}")

st.write(
    f"Timing not sufficiently certain for primary grading: **{timing_uncertain_count:,}** games. "
    f"Captured after the scheduled UTC date: **{late_capture_count:,}** games."
)
st.caption(
    "Because the archive does not establish the exact source publication time or exact kickoff timestamp, "
    "same-day captures are excluded from primary performance figures rather than assumed to be pregame."
)


def report(title, population, bets, line_col, edge_col):
    st.subheader(title)
    missing_line = int(population[line_col].isna().sum())
    missing_prediction = int(population[edge_col].isna().sum())
    missing_final = int((~population["final_available"]).sum())
    edge_candidates = population[population[edge_col].notna() & (population[edge_col].abs() >= EDGE_THRESHOLD)]
    no_line_among_candidates = int(edge_candidates[line_col].isna().sum())

    x, y, z = st.columns(3)
    x.metric("Missing market lines", f"{missing_line:,}")
    y.metric("Missing predictions", f"{missing_prediction:,}")
    z.metric("Eligible-edge games missing lines", f"{no_line_among_candidates:,}")

    wins = int(bets["result"].eq("Win").sum())
    losses = int(bets["result"].eq("Loss").sum())
    pushes = int(bets["result"].eq("Push").sum())
    net = float(bets["net_units"].sum())
    risked = float(bets["units_risked"].sum())
    roi = 100 * net / risked if risked else np.nan

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Record (W-L-P)", f"{wins}-{losses}-{pushes}")
    m2.metric("Bets", f"{len(bets):,}")
    m3.metric("Net units", f"{net:+.2f}")
    m4.metric("Units risked", f"{risked:.2f}")
    m5.metric("ROI at assumed -110", f"{roi:+.2f}%" if risked else "—")

    if bets.empty:
        st.info("No games currently meet the data, timing, and fixed 3.5-point edge requirements.")
        return

    cols = [
        "game_id", "captured_at_utc", "scheduled_date_utc", "away_team", "home_team",
        line_col, edge_col, "actual_margin", "actual_total", "result", "net_units",
        "timing_status", "snapshot_file",
    ]
    st.dataframe(
        bets[[col for col in cols if col in bets.columns]].sort_values("captured_at_utc", ascending=False),
        hide_index=True,
        use_container_width=True,
    )


st.caption(
    f"Fixed absolute model-edge threshold: {EDGE_THRESHOLD:.1f} points. One unit risked per bet; wins earn "
    f"{WIN_PROFIT_AT_MINUS_110:.3f} units at assumed -110, losses lose one unit, pushes earn zero. "
    "This convention is illustrative because schedule-feed prices are not verified sportsbook prices."
)
report("ATS results", ats_population, ats, "spread_line_source_value", "ats_edge")
report("Totals results", totals_population, totals, "total_line_source_value", "total_edge")

st.warning(
    "Important limitations: the saved line fields come from a public schedule feed and are not verified executable "
    "sportsbook prices or odds. The audit grades the first saved snapshot per game and never overwrites it with a later "
    "capture. Same-day/unknown timing is excluded from primary results. Injury-feed coverage is descriptive only; "
    "this page does not establish that the model had complete or actionable injury information."
)

st.subheader("Download audit data")
st.download_button(
    "Download raw snapshot audit archive (all observations)",
    data=archive.to_csv(index=False).encode("utf-8"),
    file_name="prospective_results_audit.csv",
    mime="text/csv",
)
st.download_button(
    "Download eligible ATS bets",
    data=ats.to_csv(index=False).encode("utf-8"),
    file_name="prospective_ats_graded.csv",
    mime="text/csv",
)
st.download_button(
    "Download eligible totals bets",
    data=totals.to_csv(index=False).encode("utf-8"),
    file_name="prospective_totals_graded.csv",
    mime="text/csv",
)
