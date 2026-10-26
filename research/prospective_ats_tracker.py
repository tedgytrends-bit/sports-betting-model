from pathlib import Path

import pandas as pd
import streamlit as st

st.title("Prospective ATS Tracker")
st.caption("Forward-looking records • Research only • Not a validated betting system")

st.write(
    "The collector now focuses on unplayed games scheduled within the next seven calendar days. "
    "It records the schedule-feed spread, a simple points-based baseline, capture time, and whether injury-feed "
    "records were available for that week."
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
data["spread_value_available"] = data.get("spread_value_available", data["spread_line_source_value"].notna()).fillna(False).astype(bool)
data["injury_week_has_rows"] = data.get("injury_week_has_rows", pd.Series(False, index=data.index)).fillna(False).astype(bool)
data = data.sort_values(["gameday_utc", "captured_at_utc"], ascending=[True, False])

a, b, c, d = st.columns(4)
a.metric("Snapshot files", int(data["snapshot_file"].nunique()))
b.metric("Game observations", len(data))
c.metric("Rows with a spread", int(data["spread_value_available"].sum()))
d.metric("Snapshots with injury-week rows", int(data["injury_week_has_rows"].sum()))

st.subheader("Upcoming game observations")
columns = [
    "captured_at_utc", "gameday_utc", "season", "week", "away_team", "home_team",
    "spread_line_source_value", "baseline_predicted_home_margin", "spread_value_available",
    "injury_feed_status", "injury_week_coverage_status", "home_injury_report_rows",
    "away_injury_report_rows", "injury_feed_has_source_timestamp", "snapshot_file",
]
visible = data[[col for col in columns if col in data.columns]].copy()
visible = visible.rename(columns={
    "captured_at_utc": "Captured at (UTC)",
    "gameday_utc": "Scheduled date (UTC from feed)",
    "season": "Season",
    "week": "Week",
    "away_team": "Away",
    "home_team": "Home",
    "spread_line_source_value": "Schedule spread field",
    "baseline_predicted_home_margin": "Baseline projected home margin",
    "spread_value_available": "Spread available",
    "injury_feed_status": "Injury feed status",
    "injury_week_coverage_status": "Injury week coverage",
    "home_injury_report_rows": "Home report rows",
    "away_injury_report_rows": "Away report rows",
    "injury_feed_has_source_timestamp": "Source has date_modified",
    "snapshot_file": "Snapshot file",
})
st.dataframe(visible, hide_index=True, use_container_width=True)

st.caption(
    "The spread is from the public schedule feed, not verified as a live/executable sportsbook line. "
    "The prediction is a simple points-for/against baseline, not the full ATS efficiency model. "
    "Injury row counts describe records in the current feed, not confirmed current absences or full injury status. "
    "A player with a long-term injury may not appear in the weekly report, and statuses can change. "
    "Missing rows are shown as unavailable rather than being treated as zero injuries. "
    "The workflow capture time does not prove when the source first published the information or guarantee capture before kickoff."
)

st.subheader("Download raw observations")
st.download_button(
    "Download prospective ATS tracking CSV",
    data.to_csv(index=False).encode("utf-8"),
    "prospective_ats_tracking.csv",
    "text/csv",
)
