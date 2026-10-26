#!/usr/bin/env python3
"""Capture a dated snapshot of the upcoming NFL week's public injury report.

The capture timestamp records when this repository observed the source, not when
the league first published each underlying report.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import sys

import pandas as pd
import requests

SCHEDULE_URLS = [
    "https://github.com/nflverse/nfldata/raw/master/data/games.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
]
INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
OUTPUT_DIR = Path("data/injury_snapshots")
USER_AGENT = {"User-Agent": "sports-betting-model-injury-snapshot/1.0"}


def fetch_csv(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=(10, 45), headers=USER_AGENT)
    response.raise_for_status()
    return pd.read_csv(BytesIO(response.content), low_memory=False)


def main() -> int:
    captured_at = datetime.now(timezone.utc).replace(microsecond=0)
    season = captured_at.year
    today = pd.Timestamp(captured_at.date())

    schedule = None
    errors = []
    for url in SCHEDULE_URLS:
        try:
            candidate = fetch_csv(url)
            needed = {"season", "week", "gameday"}
            if not needed.issubset(candidate.columns):
                errors.append(f"{url}: missing {sorted(needed - set(candidate.columns))}")
                continue
            schedule = candidate
            break
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    if schedule is None:
        print("Could not load schedule. " + " | ".join(errors), file=sys.stderr)
        return 1

    schedule["season"] = pd.to_numeric(schedule["season"], errors="coerce")
    schedule["gameday_parsed"] = pd.to_datetime(schedule["gameday"], errors="coerce", utc=True)
    upcoming = schedule[
        (schedule["season"] == season)
        & schedule["gameday_parsed"].notna()
        & (schedule["gameday_parsed"].dt.date >= today.date())
    ].copy()

    if upcoming.empty:
        print(f"No upcoming {season} games found; skipping snapshot.")
        return 0

    next_date = upcoming["gameday_parsed"].min()
    next_games = upcoming[upcoming["gameday_parsed"].dt.date == next_date.date()]
    week_values = pd.to_numeric(next_games["week"], errors="coerce").dropna()
    if week_values.empty:
        print("Upcoming games found, but their week number is not numeric; skipping snapshot.")
        return 0
    week = int(week_values.iloc[0])

    url = INJURY_URL.format(season=season)
    injuries = fetch_csv(url)
    required = {"week", "team"}
    if not required.issubset(injuries.columns):
        print(f"Injury feed missing required columns: {sorted(required - set(injuries.columns))}", file=sys.stderr)
        return 1

    injuries["week_numeric"] = pd.to_numeric(injuries["week"], errors="coerce")
    target = injuries[injuries["week_numeric"] == week].drop(columns=["week_numeric"]).copy()
    if target.empty:
        print(f"No injury rows returned for {season} Week {week}; no snapshot saved.")
        return 0

    target.insert(0, "snapshot_captured_at_utc", captured_at.isoformat().replace("+00:00", "Z"))
    target.insert(1, "snapshot_source_url", url)
    target.insert(2, "snapshot_season", season)
    target.insert(3, "snapshot_week", week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
    path = OUTPUT_DIR / f"injuries_{season}_week_{week:02d}_{stamp}.csv"
    target.to_csv(path, index=False)
    print(f"Saved {len(target)} injury rows for {season} Week {week}: {path}")
    print(f"Snapshot capture time (UTC): {captured_at.isoformat()}")
    print("Reminder: capture time is not the original publication time of the injury report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
