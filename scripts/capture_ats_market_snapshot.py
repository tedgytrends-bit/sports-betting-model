#!/usr/bin/env python3
"""Record pregame schedule, market spread, simple baseline prediction, and injury-feed coverage."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SCHEDULE_URLS = [
    "https://github.com/nflverse/nfldata/raw/master/data/games.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
]
INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
OUT = Path("data/prospective_ats_tracking")
HEADERS = {"User-Agent": "sports-betting-model-prospective-tracker/1.0"}


def fetch_csv(url):
    response = requests.get(url, timeout=(10, 45), headers=HEADERS)
    response.raise_for_status()
    return pd.read_csv(BytesIO(response.content), low_memory=False)


def team_points_history(games, team, before_date, lookback=6):
    history = games[
        (games["gameday"] < before_date)
        & games["home_score"].notna()
        & games["away_score"].notna()
        & ((games["home_team"] == team) | (games["away_team"] == team))
    ].sort_values("gameday").tail(lookback)
    if history.empty:
        return None
    at_home = history["home_team"].eq(team)
    scored = np.where(at_home, history["home_score"], history["away_score"]).astype(float)
    allowed = np.where(at_home, history["away_score"], history["home_score"]).astype(float)
    return float(scored.mean()), float(allowed.mean())


def main():
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    schedule = None
    errors = []
    for url in SCHEDULE_URLS:
        try:
            schedule = fetch_csv(url)
            if {"game_id", "season", "week", "gameday", "home_team", "away_team", "home_score", "away_score"}.issubset(schedule.columns):
                break
            schedule = None
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    if schedule is None:
        raise RuntimeError("Could not load schedule: " + " | ".join(errors))

    for col in ["season", "week", "home_score", "away_score", "spread_line"]:
        if col in schedule:
            schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    if "spread_line" not in schedule:
        schedule["spread_line"] = np.nan
    schedule["gameday"] = pd.to_datetime(schedule["gameday"], errors="coerce", utc=True).dt.tz_convert(None)
    now = pd.Timestamp(captured.replace(tzinfo=None))
    upcoming = schedule[
        schedule["gameday"].notna()
        & (schedule["gameday"] > now)
        & (schedule["home_score"].isna() | schedule["away_score"].isna())
    ].copy()
    if upcoming.empty:
        print("No future unplayed games in schedule; no tracking row saved.")
        return

    season_values = pd.to_numeric(upcoming["season"], errors="coerce").dropna()
    if season_values.empty:
        print("Upcoming games have no season value; no tracking row saved.")
        return
    season = int(season_values.max())
    upcoming = upcoming[upcoming["season"] == season].copy()
    injury_rows = pd.DataFrame()
    injury_url = INJURY_URL.format(season=season)
    try:
        injury_rows = fetch_csv(injury_url)
    except Exception as exc:
        print(f"WARNING: injury feed unavailable: {type(exc).__name__}: {exc}")

    if not injury_rows.empty and {"week", "team"}.issubset(injury_rows.columns):
        injury_rows["week"] = pd.to_numeric(injury_rows["week"], errors="coerce")
    else:
        injury_rows = pd.DataFrame()

    records = []
    for _, game in upcoming.iterrows():
        home, away = str(game["home_team"]), str(game["away_team"])
        home_hist = team_points_history(schedule, home, game["gameday"])
        away_hist = team_points_history(schedule, away, game["gameday"])
        if home_hist and away_hist:
            projected_home = max(0.0, 0.5 * home_hist[0] + 0.5 * away_hist[1] + 1.5)
            projected_away = max(0.0, 0.5 * away_hist[0] + 0.5 * home_hist[1])
            predicted_home_margin = projected_home - projected_away
        else:
            projected_home = projected_away = predicted_home_margin = np.nan
        week = int(game["week"]) if pd.notna(game["week"]) else np.nan
        if not injury_rows.empty and pd.notna(week):
            week_rows = injury_rows[injury_rows["week"] == week]
            home_injuries = int((week_rows["team"].astype(str).str.upper() == home.upper()).sum())
            away_injuries = int((week_rows["team"].astype(str).str.upper() == away.upper()).sum())
        else:
            home_injuries = away_injuries = np.nan
        record = {
            "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
            "game_id": game.get("game_id"),
            "season": season,
            "week": week,
            "gameday_utc": game["gameday"].isoformat(),
            "home_team": home,
            "away_team": away,
            "spread_line_source_value": game.get("spread_line", np.nan),
            "baseline_projected_home_points": round(projected_home, 3) if pd.notna(projected_home) else np.nan,
            "baseline_projected_away_points": round(projected_away, 3) if pd.notna(projected_away) else np.nan,
            "baseline_predicted_home_margin": round(predicted_home_margin, 3) if pd.notna(predicted_home_margin) else np.nan,
            "home_injury_rows_in_current_feed": home_injuries,
            "away_injury_rows_in_current_feed": away_injuries,
            "injury_feed_has_source_timestamp": bool("date_modified" in injury_rows.columns) if not injury_rows.empty else False,
            "injury_feed_source": injury_url,
            "note": "Capture time is when this workflow observed the feed; source report publication time may be earlier and is not established here.",
        }
        records.append(record)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ats_market_snapshot_{captured.strftime('%Y%m%dT%H%M%SZ')}.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    print(f"Saved {len(records)} upcoming-game tracking rows: {path}")
    print(f"Capture time UTC: {captured.isoformat()}")
    print("Contains market spread field as published by schedule feed and a simple points-based baseline, not the full efficiency ATS model.")


if __name__ == "__main__":
    main()
