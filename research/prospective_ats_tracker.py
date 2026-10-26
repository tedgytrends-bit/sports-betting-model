from pathlib import Path

import pandas as pd
import streamlit as st

st.title("Prospective ATS Tracker")
st.caption("Forward-looking records • Research only • Not a validated betting system")

st.write(
    "This page displays scheduled-game snapshots captured by GitHub Actions. Each row records when the workflow "
    "observed the schedule/injury feed, the schedule-feed spread value, a simple points-based baseline prediction, "
    "and injury-row counts if the public feed has them. The baseline is not the full efficiency ATS model."
)

folder = Path("data/prospective_ats_tracking")
files = sorted(folder.glob("ats_market_snapshot_*.csv")) if folder.exists() else []
if not files:
    st.info("No prospective ATS tracking files yet. Run the GitHub Actions workflow named 'Capture prospective ATS snapshots', then refresh this page.")
    st.stop()

frames = []
for file in files:
    try:
        df = pd.read_csv(file, low_memory=False)
        if not df.empty:
            df["snapshot_file"] = file.name
            frames.append(df)
    except Exception as exc:
        st.warning(f"Could not read {file.name}: {exc}")

if not frames:
    st.info("Tracking files exist but contain no readable rows.")
    st.stop()

data = pd.concat(frames, ignore_index=True, sort=False)
data["captured_at_utc"] = pd.to_datetime(data["captured_at_utc"], errors="coerce", utc=True)
data["gameday_utc"] = pd.to_datetime(data["gameday_utc"], errors="coerce", utc=True)
data = data.sort_values(["gameday_utc", "captured_at_utc"], ascending=[True, False])

a, b, c = st.columns(3)
a.metric("Snapshot files", int(data["snapshot_file"].nunique()))
b.metric("Game observations", len(data))
c.metric("Distinct capture times", int(data["captured_at_utc"].nunique()))

st.subheader("Upcoming game observations")
columns = [
    "captured_at_utc", "gameday_utc", "season", "week", "away_team", "home_team",
    "spread_line_source_value", "baseline_predicted_home_margin",
    "home_injury_rows_in_current_feed", "away_injury_rows_in_current_feed",
    "injury_feed_has_source_timestamp", "snapshot_file",
]
visible = data[[col for col in columns if col in data.columns]].copy()
visible = visible.rename(columns={
    "captured_at_utc": "Captured at (UTC)",
    "gameday_utc": "Scheduled kickoff/date (UTC from feed)",
    "season": "Season",
    "week": "Week",
    "away_team": "Away",
    "home_team": "Home",
    "spread_line_source_value": "Schedule spread field",
    "baseline_predicted_home_margin": "Baseline projected home margin",
    "home_injury_rows_in_current_feed": "Home injury rows",
    "away_injury_rows_in_current_feed": "Away injury rows",
    "injury_feed_has_source_timestamp": "Source has date_modified",
    "snapshot_file": "Snapshot file",
})
st.dataframe(visible, hide_index=True, use_container_width=True)

st.caption(
    "Important: the spread is from the public schedule feed, not verified as a live/executable sportsbook line. "
    "The prediction is a simple points-for/against baseline, not the full ATS efficiency model. "
    "A workflow capture timestamp does not prove when the source first published its injury information. "
    "Do not use these rows as proof of a betting edge."
)

st.subheader("Download raw observations")
st.download_button(
    "Download prospective ATS tracking CSV",
    data.to_csv(index=False).encode("utf-8"),
    "prospective_ats_tracking.csv",
    "text/csv",
)
