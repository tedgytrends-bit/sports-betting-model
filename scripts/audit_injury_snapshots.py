#!/usr/bin/env python3
"""Audit immutable nflverse injury-feed snapshots without assuming feed completeness.

Capture time is when this repository observed the feed, not the league's original
publication time. Feed membership changes are observations, not confirmed report
additions/removals. Structural validation is deliberately separate from coverage:
a team with no rows may simply have no listed players in this export.
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
QUALITY_COLUMNS = [
    "snapshot_file", "snapshot_captured_at_utc", "snapshot_season", "snapshot_week",
    "row_count", "unique_player_ids", "missing_player_ids", "duplicate_player_ids",
    "teams_observed", "teams_present", "structural_status", "comparison_eligible",
    "quality_note",
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


def validate_snapshot(df: pd.DataFrame, snapshot_file: str = "") -> dict:
    """Return structural diagnostics; do not equate team coverage with completeness."""
    ids = df["gsis_id"].astype("string").str.strip()
    missing_ids = int(ids.isna().sum() + ids.eq("").fillna(False).sum())
    valid_ids = ids[ids.notna() & ids.ne("")]
    duplicate_ids = int(valid_ids.duplicated(keep=False).sum())
    teams = df["team"].astype("string").str.strip().str.upper()
    teams = teams[teams.notna() & teams.ne("")]
    invalid_team_rows = int(len(df) - len(teams))
    issues = []
    if missing_ids:
        issues.append(f"{missing_ids} rows have missing player IDs")
    if duplicate_ids:
        issues.append(f"{duplicate_ids} rows belong to duplicated player IDs")
    if invalid_team_rows:
        issues.append(f"{invalid_team_rows} rows have missing team")
    structurally_valid = not issues and len(df) > 0
    if len(df) == 0:
        issues.append("snapshot contains zero rows")
    return {
        "snapshot_file": snapshot_file,
        "row_count": int(len(df)),
        "unique_player_ids": int(valid_ids.nunique()),
        "missing_player_ids": missing_ids,
        "duplicate_player_ids": duplicate_ids,
        "teams_observed": int(teams.nunique()),
        "teams_present": ";".join(sorted(teams.unique().tolist())),
        "structural_status": "valid_structure" if structurally_valid else "invalid_structure",
        "comparison_eligible": bool(structurally_valid),
        "quality_note": "; ".join(issues) if issues else (
            "Structure valid; team/player coverage is not certified by this check"
        ),
    }


def compare_snapshot_pair(previous: pd.DataFrame, current: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """Return observed player-level transitions between two snapshots for one team/week."""
    prev = previous.set_index("gsis_id")
    curr = current.set_index("gsis_id")
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
    frames, quality = [], []
    for path in files:
        df = pd.read_csv(path, dtype={"gsis_id": "string"}, low_memory=False)
        required = set(KEY + ["snapshot_captured_at_utc"] + COMPARE)
        if not required.issubset(df.columns):
            raise ValueError(f"{path} missing columns: {sorted(required - set(df.columns))}")
        df["snapshot_file"] = path.name
        df["snapshot_captured_at_utc"] = pd.to_datetime(
            df["snapshot_captured_at_utc"], utc=True, errors="coerce"
        )
        diagnostic = validate_snapshot(df, path.name)
        diagnostic["snapshot_captured_at_utc"] = (
            df["snapshot_captured_at_utc"].dropna().iloc[0].isoformat()
            if df["snapshot_captured_at_utc"].notna().any() else ""
        )
        diagnostic["snapshot_season"] = int(df["snapshot_season"].dropna().iloc[0]) if df["snapshot_season"].notna().any() else None
        diagnostic["snapshot_week"] = int(df["snapshot_week"].dropna().iloc[0]) if df["snapshot_week"].notna().any() else None
        quality.append(diagnostic)
        frames.append(df)

    quality_df = pd.DataFrame(quality, columns=QUALITY_COLUMNS)
    quality_lookup = quality_df.set_index("snapshot_file")["comparison_eligible"].to_dict()
    all_rows = pd.concat(frames, ignore_index=True)
    all_rows = all_rows.dropna(subset=["snapshot_captured_at_utc"])
    schedule = load_schedule()
    kickoff_lookup = build_kickoff_lookup(schedule)
    events = []
    skipped_pairs = 0

    for (season, week, team), group in all_rows.groupby(
        ["snapshot_season", "snapshot_week", "team"], dropna=False
    ):
        snapshots = sorted(group["snapshot_captured_at_utc"].unique())
        for previous_time, current_time in zip(snapshots, snapshots[1:]):
            prev_rows = group[group["snapshot_captured_at_utc"].eq(previous_time)]
            curr_rows = group[group["snapshot_captured_at_utc"].eq(current_time)]
            prev_file = str(prev_rows["snapshot_file"].iloc[0])
            curr_file = str(curr_rows["snapshot_file"].iloc[0])
            if not quality_lookup.get(prev_file, False) or not quality_lookup.get(curr_file, False):
                skipped_pairs += 1
                continue
            # Duplicate IDs and missing IDs are excluded at snapshot level above;
            # therefore no silent drop_duplicates() is needed here.
            prev = prev_rows.set_index("gsis_id")
            curr = curr_rows.set_index("gsis_id")
            changes = compare_snapshot_pair(prev_rows, curr_rows)
            kickoff = kickoff_lookup.get((int(season), int(week), str(team)))
            hours = (kickoff - pd.Timestamp(current_time)).total_seconds() / 3600 if kickoff is not None else None
            for player_id, field, before, after in changes:
                source = curr if player_id in curr.index else prev
                events.append({
                    "season": int(season), "week": int(week), "team": str(team),
                    "player_id": player_id, "player_name": str(source.at[player_id, "full_name"]),
                    "position": str(source.at[player_id, "position"]),
                    "change_type": field, "previous_value": before, "current_value": after,
                    "previous_snapshot_at_utc": pd.Timestamp(previous_time).isoformat(),
                    "current_snapshot_at_utc": pd.Timestamp(current_time).isoformat(),
                    "hours_before_team_kickoff": hours,
                    "timing_note": "Repository capture time; not original publication time",
                    "interpretation_note": (
                        "Feed membership changed; absence is not proof of official report removal"
                        if field == "feed_membership" else "Observed field change between captured feed versions"
                    ),
                    "previous_snapshot_file": prev_file, "current_snapshot_file": curr_file,
                    "pregame_publication_verified": False,
                })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    quality_df.to_csv(OUTPUT_DIR / "snapshot_quality.csv", index=False)
    out = pd.DataFrame(events)
    if out.empty:
        out = pd.DataFrame(columns=[
            "season","week","team","player_id","player_name","position","change_type",
            "previous_value","current_value","previous_snapshot_at_utc","current_snapshot_at_utc",
            "hours_before_team_kickoff","timing_note","interpretation_note",
            "previous_snapshot_file","current_snapshot_file","pregame_publication_verified"
        ])
    out.to_csv(OUTPUT_DIR / "snapshot_changes.csv", index=False)
    summary = (out.groupby(["season", "week", "team", "change_type"], dropna=False)
               .size().rename("change_count").reset_index()) if not out.empty else pd.DataFrame(
                   columns=["season","week","team","change_type","change_count"])
    summary.to_csv(OUTPUT_DIR / "snapshot_change_summary.csv", index=False)
    invalid = int((~quality_df["comparison_eligible"]).sum())
    print(f"Audited {len(files)} snapshots; {invalid} structurally invalid; skipped {skipped_pairs} adjacent team comparisons; wrote {len(out)} observed changes.")
    print("Structural validity does not certify source completeness or original publication timing.")


if __name__ == "__main__":
    main()
