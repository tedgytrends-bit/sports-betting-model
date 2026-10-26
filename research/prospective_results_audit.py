import glob
import numpy as np
import pandas as pd
import streamlit as st
from model import load_schedule_data

st.title("Prospective Results Audit")
st.caption("Forward-looking snapshot grading • Research only")

files = sorted(glob.glob("data/prospective_ats_tracking/ats_market_snapshot_*.csv"))
if not files:
    st.info("No saved snapshots found yet. Run the Capture prospective ATS snapshots workflow.")
    st.stop()

parts = []
for path in files:
    df = pd.read_csv(path, low_memory=False)
    if not df.empty:
        df["snapshot_file"] = path.rsplit("/", 1)[-1]
        parts.append(df)
if not parts:
    st.info("Snapshot files are empty.")
    st.stop()

data = pd.concat(parts, ignore_index=True, sort=False)
data["captured_at_utc"] = pd.to_datetime(data["captured_at_utc"], errors="coerce", utc=True)
for col in ["spread_line_source_value", "total_line_source_value", "baseline_predicted_home_margin", "baseline_projected_total"]:
    if col not in data:
        data[col] = np.nan
    data[col] = pd.to_numeric(data[col], errors="coerce")

# Grade each game once using its latest saved snapshot, never a postgame prediction.
data = data.sort_values("captured_at_utc").drop_duplicates("game_id", keep="last")
try:
    scores = load_schedule_data()[["game_id", "home_score", "away_score"]]
except Exception as exc:
    st.error(f"Unable to load final scores: {exc}")
    st.stop()

data = data.merge(scores, on="game_id", how="left", suffixes=("", "_final"))
data["final_available"] = data["home_score"].notna() & data["away_score"].notna()
data["actual_margin"] = data["home_score"] - data["away_score"]
data["actual_total"] = data["home_score"] + data["away_score"]
data["ats_edge"] = data["baseline_predicted_home_margin"] - data["spread_line_source_value"]
data["total_edge"] = data["baseline_projected_total"] - data["total_line_source_value"]

def grade(edge_col, actual_col, line_col):
    d = data[data["final_available"] & data[edge_col].notna() & data[actual_col].notna() & data[line_col].notna()].copy()
    d = d[d[edge_col].abs() >= 3.5]
    d["actual_margin_vs_line"] = d[actual_col] - d[line_col]
    d["result"] = np.where(d["actual_margin_vs_line"] == 0, "Push",
        np.where(d["actual_margin_vs_line"] * np.sign(d[edge_col]) > 0, "Win", "Loss"))
    d["net_units"] = np.select([d.result.eq("Win"), d.result.eq("Loss")], [100/110, -1.0], default=0.0)
    return d

ats = grade("ats_edge", "actual_margin", "spread_line_source_value")
totals = grade("total_edge", "actual_total", "total_line_source_value")

st.metric("Games in snapshot archive", len(data))
st.metric("Games with final scores", int(data.final_available.sum()))
st.caption("Fixed 3.5-point model-edge filter; one unit risked at assumed -110 odds. This is a research convention, not a tuned recommendation.")

def report(title, df):
    st.subheader(title)
    n = len(df)
    wins = int(df.result.eq("Win").sum()) if n else 0
    losses = int(df.result.eq("Loss").sum()) if n else 0
    pushes = int(df.result.eq("Push").sum()) if n else 0
    net = float(df.net_units.sum()) if n else 0.0
    st.write(f"Record: {wins}-{losses}-{pushes} • {n} bets • Net: {net:+.2f} units")
    st.write(f"ROI: {100*net/n:.1f}%" if n else "No graded bets meet the threshold yet.")
    if n:
        cols = ["captured_at_utc", "away_team", "home_team", "spread_line_source_value", "baseline_predicted_home_margin", "ats_edge", "total_line_source_value", "baseline_projected_total", "total_edge", "actual_margin", "actual_total", "result", "net_units", "snapshot_file"]
        st.dataframe(df[[c for c in cols if c in df]].sort_values("captured_at_utc", ascending=False), hide_index=True, use_container_width=True)

report("ATS results (3.5+ point edge)", ats)
report("Totals results (3.5+ point edge)", totals)
st.warning("Schedule-feed lines are not verified sportsbook prices, and capture time does not prove a line was available before kickoff. Latest-snapshot grading is a research audit, not proof of a profitable strategy.")
st.download_button("Download graded snapshot archive", data.to_csv(index=False).encode("utf-8"), "prospective_results_audit.csv", "text/csv")
