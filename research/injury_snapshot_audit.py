from pathlib import Path

import pandas as pd
import streamlit as st

from model import load_schedule_data

st.title("NFL Injury Snapshot Audit")
st.caption("Prospective data collection • Research only")

st.markdown(
    "This page checks the injury snapshots saved by GitHub Actions and whether each snapshot was captured "
    "before the scheduled game date. To avoid timezone ambiguity, same-calendar-day captures are marked "
    "unverified rather than assumed to be pregame."
)

snapshot_dir = Path("data/injury_snapshots")
files = sorted(snapshot_dir.glob("injuries_*.csv")) if snapshot_dir.exists() else []

if not files:
    st.info("No saved injury snapshots found in this deployment yet. Run the GitHub Actions workflow and refresh this page.")
    st.stop()

frames = []
for path in files:
    try:
        df = pd.read_csv(path, low_memory=False)
        if not df.empty:
            df["snapshot_file"] = path.name
            frames.append(df)
    except Exception as exc:
        st.warning(f"Could not read {path.name}: {exc}")

if not frames:
    st.info("Snapshot files exist, but none contained readable rows.")
    st.stop()

snapshots = pd.concat(frames, ignore_index=True, sort=False)
snapshots["snapshot_captured_at_utc"] = pd.to_datetime(
    snapshots.get("snapshot_captured_at_utc"), errors="coerce", utc=True
)
snapshots["snapshot_season"] = pd.to_numeric(snapshots.get("snapshot_season"), errors="coerce")
snapshots["snapshot_week"] = pd.to_numeric(snapshots.get("snapshot_week"), errors="coerce")

unique_files = snapshots.drop_duplicates("snapshot_file").copy()
unique_files["Capture time (UTC)"] = unique_files["snapshot_captured_at_utc"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
unique_files["Rows"] = unique_files["snapshot_file"].map(snapshots.groupby("snapshot_file").size())
unique_files["Season"] = unique_files["snapshot_season"]
unique_files["Week"] = unique_files["snapshot_week"]
unique_files["Source timestamp in original report"] = (
    snapshots.groupby("snapshot_file").apply(
        lambda x: "Yes" if any("date_modified" in str(c).lower() for c in x.columns) else "No",
        include_groups=False,
    ).reindex(unique_files["snapshot_file"]).to_numpy()
)

st.subheader("Collection summary")
col1, col2, col3 = st.columns(3)
col1.metric("Snapshot files", int(snapshots["snapshot_file"].nunique()))
col2.metric("Total captured rows", len(snapshots))
col3.metric("Distinct capture times", int(snapshots["snapshot_captured_at_utc"].nunique()))

st.subheader("Saved snapshots")
summary = unique_files[[
    "snapshot_file", "Capture time (UTC)", "Season", "Week", "Rows", "Source timestamp in original report"
]].sort_values("Capture time (UTC)", ascending=False)
st.dataframe(summary, hide_index=True, use_container_width=True)

st.subheader("Pregame usability check")
try:
    schedule = load_schedule_data()
    if "gameday" not in schedule.columns or "season" not in schedule.columns or "week" not in schedule.columns:
        st.warning("Schedule feed is missing season/week/gameday fields; pregame date check unavailable.")
    else:
        schedule["season"] = pd.to_numeric(schedule["season"], errors="coerce")
        schedule["week"] = pd.to_numeric(schedule["week"], errors="coerce")
        schedule["gameday_date"] = pd.to_datetime(schedule["gameday"], errors="coerce").dt.date
        check = snapshots[[
            "snapshot_file", "snapshot_captured_at_utc", "snapshot_season", "snapshot_week"
        ]].drop_duplicates()
        check = check.merge(
            schedule[["season", "week", "gameday_date"]].dropna().drop_duplicates(),
            left_on=["snapshot_season", "snapshot_week"],
            right_on=["season", "week"],
            how="left",
        )
        captured_date = check["snapshot_captured_at_utc"].dt.date
        check["Date-based status"] = "Unverified: same-day or missing date"
        check.loc[
            check["gameday_date"].notna() & (captured_date < check["gameday_date"]),
            "Date-based status"
        ] = "Captured before game date"
        check.loc[
            check["gameday_date"].notna() & (captured_date > check["gameday_date"]),
            "Date-based status"
        ] = "After game date — exclude"
        check["Capture time (UTC)"] = check["snapshot_captured_at_utc"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        check["Season"] = check["snapshot_season"]
        check["Week"] = check["snapshot_week"]
        check = check[[
            "snapshot_file", "Capture time (UTC)", "Season", "Week", "gameday_date", "Date-based status"
        ]].rename(columns={"snapshot_file": "Snapshot file", "gameday_date": "Scheduled game date"})
        st.dataframe(check, hide_index=True, use_container_width=True)

        st.subheader("Team coverage by snapshot")
        team_columns = {"home_team", "away_team"}
        if team_columns.issubset(schedule.columns) and "team" in snapshots.columns:
            team_schedule = schedule.copy()
            team_schedule["season"] = pd.to_numeric(team_schedule["season"], errors="coerce")
            team_schedule["week"] = pd.to_numeric(team_schedule["week"], errors="coerce")
            coverage_rows = []
            for (snap_file, snap_season, snap_week), snap_rows in snapshots.groupby(
                ["snapshot_file", "snapshot_season", "snapshot_week"], dropna=False
            ):
                scheduled = team_schedule[
                    (team_schedule["season"] == snap_season)
                    & (team_schedule["week"] == snap_week)
                ]
                expected_teams = set(
                    scheduled["home_team"].dropna().astype(str).str.upper()
                ) | set(scheduled["away_team"].dropna().astype(str).str.upper())
                observed_teams = set(snap_rows["team"].dropna().astype(str).str.upper())
                absent_teams = sorted(expected_teams - observed_teams)
                extra_teams = sorted(observed_teams - expected_teams)
                coverage_rows.append({
                    "Snapshot file": snap_file,
                    "Season": snap_season,
                    "Week": snap_week,
                    "Scheduled teams": len(expected_teams),
                    "Teams with player rows": len(expected_teams & observed_teams),
                    "Teams with no rows in feed": ", ".join(absent_teams) if absent_teams else "None",
                    "Unexpected team codes": ", ".join(extra_teams) if extra_teams else "None",
                })
            if coverage_rows:
                st.dataframe(
                    pd.DataFrame(coverage_rows).sort_values(
                        ["Season", "Week", "Snapshot file"], ascending=[False, False, False]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption(
                    "A team with no player rows is not automatically a missing report: the source may have no listed players for that team at capture time. "
                    "This checks team codes against the schedule, not whether each team's report was complete or final."
                )
        else:
            st.info("Team coverage comparison unavailable: schedule must include home_team/away_team and the snapshot must include team.")

        st.caption(
            "Conservative screen only: a snapshot captured before the game date is potentially usable, not proof of report publication time. "
            "Same-day snapshots require kickoff-time verification before use. A snapshot after the game date must be excluded."
        )
except Exception as exc:
    st.warning(f"Could not complete the schedule comparison: {type(exc).__name__}: {exc}")

st.subheader("Inspect a snapshot")
chosen = st.selectbox("Choose a saved snapshot", sorted(snapshots["snapshot_file"].dropna().unique(), reverse=True))
sample = snapshots[snapshots["snapshot_file"] == chosen].copy()
st.caption(f"{len(sample)} rows in {chosen}")
st.dataframe(sample, hide_index=True, use_container_width=True)
