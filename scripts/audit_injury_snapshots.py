#!/usr/bin/env python3
"""Build an event-level comparison of immutable nflverse injury-feed snapshots.

Snapshot capture time means this repository observed the feed at that time. It is
not the league's original publication timestamp. Missing players are described as
feed-membership changes, not confirmed removals from an official injury report.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

SNAPSHOT_DIR = Path("data/injury_snapshots")
OUTPUT_DIR = Path("data/injury_snapshot_audits")
SCHEDULE_URLS = [
    "https://github.com/nflverse/nfldata/raw/master/data/games.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
]
KEY = ["snapshot_season", "snapshot_week", "team", "gsis_id"]
COMPARE = [
    "position", "full_name", "report_primary_injury", "report_secondary_injury",
    "report_status", "practice_primary_injury", "practice_secondary_injury",
    "practice_status",
]


def load_schedule() -> pd.DataFrame:
    errors = []
    for url in SCHEDULE_URLS:
        try:
            df = pd.read_csv(url, low_memory=False)
            needed = {"season", "week", "gameday", "gametime", "home_team", "away_team"}
            if needed.issubset(df.columns):
                return df
            errors.append(f"{url}: missing {sorted(needed - set(df.columns))}")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("Could not load schedule: " + " | ".join(errors))


def build_kickoff_lookup(schedule: pd.DataFrame) -> dict[tuple[int, int, str], pd.Timestamp]:
    s = schedule.copy()
    s["season"] = pd.to_numeric(s["season"], errors="coerce")
    s["week"] = pd.to_numeric(s["week"], errors="coerce")
    lookup = {}
    for row in s.itertuples(index=False):
        try:
            date = pd.Timestamp(str(row.gameday)).date()
            clock = str(row.gametime)[:5]
            local = pd.Timestamp(f"{date} {clock}").tz_localize(
                ZoneInfo("America/New_York"), ambiguous="raise", nonexistent="raise"
            )
            kickoff = local.tz_convert("UTC")
            for team in (str(row.home_team), str(row.away_team)):
                key = (int(row.season), int(row.week), team)
                lookup[key] = min(lookup.get(key, kickoff), kickoff)
        except (TypeError, ValueError, OverflowError):
            continue
    return lookup


def compare_snapshot_pair(previous: pd.DataFrame, current: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """Return player-level transitions between two snapshots for one team/week."""
    prev = previous.drop_duplicates("gsis_id").set_index("gsis_id")
    curr = current.drop_duplicates("gsis_id").set_index("gsis_id")
    prev_ids, curr_ids = set(prev.index), set(curr.index)
    changes: list[tuple[str, str, str, str]] = []
    for player_id in sorted(curr_ids - prev_ids):
        changes.append((player_id, "feed_membership", "not_present", "present"))
    for player_id in sorted(prev_ids - curr_ids):
        changes.append((player_id, "feed_membership", "present", "not_present"))
    for player_id in sorted(prev_ids & curr_ids):
        for field in COMPARE:
            before, after = prev.at[player_id, field], curr.at[player_id, field]
            before = "" if pd.isna(before) else str(before).strip()
            after = "" if pd.isna(after) else str(after).strip()
            if before != after:
                changes.append((player_id, field, before, after))
    return changes


def main() -> None:
    files = sorted(SNAPSHOT_DIR.glob("injuries_*_week_*_*.csv"))
    if not files:
        print("No snapshots found; audit skipped.")
        return
    frames = []
    for path in files:
        df = pd.read_csv(path, dtype={"gsis_id": "string"}, low_memory=False)
        required = set(KEY + ["snapshot_captured_at_utc"] + COMPARE)
        if not required.issubset(df.columns):
            raise ValueError(f"{path} missing columns: {sorted(required - set(df.columns))}")
        df["snapshot_file"] = path.name
        df["snapshot_captured_at_utc"] = pd.to_datetime(
            df["snapshot_captured_at_utc"], utc=True, errors="coerce"
        )
        frames.append(df)
    all_rows = pd.concat(frames, ignore_index=True)
    all_rows = all_rows.dropna(subset=["snapshot_captured_at_utc"])
    schedule = load_schedule()
    kickoff_lookup = build_kickoff_lookup(schedule)
    events = []

    for (season, week, team), group in all_rows.groupby(
        ["snapshot_season", "snapshot_week", "team"], dropna=False
    ):
        snapshots = sorted(group["snapshot_captured_at_utc"].unique())
        for previous_time, current_time in zip(snapshots, snapshots[1:]):
            prev_rows = group[group["snapshot_captured_at_utc"].eq(previous_time)].drop_duplicates("gsis_id")
            curr_rows = group[group["snapshot_captured_at_utc"].eq(current_time)].drop_duplicates("gsis_id")
            prev = prev_rows.set_index("gsis_id")
            curr = curr_rows.set_index("gsis_id")
            changes = compare_snapshot_pair(prev_rows, curr_rows)
            kickoff = kickoff_lookup.get((int(season), int(week), str(team)))
            hours = (kickoff - pd.Timestamp(current_time)).total_seconds() / 3600 if kickoff is not None else None
            for player_id, field, before, after in changes:
                name = ""
                position = ""
                if player_id in curr.index:
                    name = str(curr.at[player_id, "full_name"])
                    position = str(curr.at[player_id, "position"])
                elif player_id in prev.index:
                    name = str(prev.at[player_id, "full_name"])
                    position = str(prev.at[player_id, "position"])
                events.append({
                    "season": int(season), "week": int(week), "team": str(team),
                    "player_id": player_id, "player_name": name, "position": position,
                    "change_type": field, "previous_value": before, "current_value": after,
                    "previous_snapshot_at_utc": pd.Timestamp(previous_time).isoformat(),
                    "current_snapshot_at_utc": pd.Timestamp(current_time).isoformat(),
                    "hours_before_team_kickoff": hours,
                    "timing_note": "Repository capture time; not original publication time",
                    "interpretation_note": (
                        "Feed membership changed; absence is not proof of official report removal"
                        if field == "feed_membership" else "Observed field change between captured feed versions"
                    ),
                    "previous_snapshot_file": str(prev.loc[player_id, "snapshot_file"]) if player_id in prev.index else "",
                    "current_snapshot_file": str(curr.loc[player_id, "snapshot_file"]) if player_id in curr.index else "",
                })
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(events)
    if out.empty:
        out = pd.DataFrame(columns=[
            "season","week","team","player_id","player_name","position","change_type",
            "previous_value","current_value","previous_snapshot_at_utc","current_snapshot_at_utc",
            "hours_before_team_kickoff","timing_note","interpretation_note",
            "previous_snapshot_file","current_snapshot_file"
        ])
    out.to_csv(OUTPUT_DIR / "snapshot_changes.csv", index=False)
    summary = (out.groupby(["season", "week", "team", "change_type"], dropna=False)
               .size().rename("change_count").reset_index()) if not out.empty else pd.DataFrame(
                   columns=["season","week","team","change_type","change_count"])
    summary.to_csv(OUTPUT_DIR / "snapshot_change_summary.csv", index=False)
    print(f"Compared {len(files)} snapshots; wrote {len(out)} observed changes.")
    print("All timing fields refer to repository capture timestamps, not source publication timestamps.")


if __name__ == "__main__":
    main()
