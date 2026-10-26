#!/usr/bin/env python3
"""Capture upcoming NFL games within seven calendar days for prospective ATS research."""
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
HEADERS = {"User-Agent": "sports-betting-model-prospective-tracker/1.1"}
HORIZON_DAYS = 7


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
    today_utc = pd.Timestamp(captured.date())
    horizon_date = today_utc + pd.Timedelta(days=HORIZON_DAYS)
    schedule = None
    errors = []
    required = {"game_id", "season", "week", "gameday", "home_team", "away_team", "home_score", "away_score"}
    for url in SCHEDULE_URLS:
        try:
            candidate = fetch_csv(url)
            if required.issubset(candidate.columns):
                schedule = candidate
                break
            errors.append(f"{url}: required columns missing")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    if schedule is None:
        raise RuntimeError("Could not load schedule: " + " | ".join(errors))

    for col in ["season", "week", "home_score", "away_score", "spread_line", "total_line"]:
        if col in schedule:
            schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    if "spread_line" not in schedule:
        schedule["spread_line"] = np.nan
    if "total_line" not in schedule:
        schedule["total_line"] = np.nan
    schedule["gameday"] = pd.to_datetime(schedule["gameday"], errors="coerce", utc=True).dt.tz_convert(None)
    schedule_day = schedule["gameday"].dt.normalize()
    unplayed = schedule["home_score"].isna() | schedule["away_score"].isna()
    upcoming = schedule[
        schedule["gameday"].notna()
        & (schedule_day >= today_utc)
        & (schedule_day <= horizon_date)
        & unplayed
    ].copy()
    if upcoming.empty:
        print(f"No unplayed games scheduled from {today_utc.date()} through {horizon_date.date()}; no snapshot saved.")
        return

    season_values = pd.to_numeric(upcoming["season"], errors="coerce").dropna()
    if season_values.empty:
        print("Upcoming games have no season value; no tracking row saved.")
        return
    season = int(season_values.max())
    upcoming = upcoming[upcoming["season"] == season].copy()
    injury_url = INJURY_URL.format(season=season)
    injury_rows = pd.DataFrame()
    injury_feed_status = "unavailable"
    try:
        fetched_injuries = fetch_csv(injury_url)
        if {"week", "team"}.issubset(fetched_injuries.columns):
            fetched_injuries["week"] = pd.to_numeric(fetched_injuries["week"], errors="coerce")
            injury_rows = fetched_injuries
            injury_feed_status = "loaded"
        else:
            injury_feed_status = "missing_required_columns"
    except Exception as exc:
        print(f"WARNING: injury feed unavailable: {type(exc).__name__}: {exc}")

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
        week_rows = pd.DataFrame()
        if injury_feed_status == "loaded" and pd.notna(week):
            week_rows = injury_rows[injury_rows["week"] == week]
        week_available = not week_rows.empty
        if week_available:
            home_count = int((week_rows["team"].astype(str).str.upper() == home.upper()).sum())
            away_count = int((week_rows["team"].astype(str).str.upper() == away.upper()).sum())
            coverage_status = "week_rows_present"
        elif injury_feed_status == "loaded":
            home_count = away_count = np.nan
            coverage_status = "no_rows_for_week"
        else:
            home_count = away_count = np.nan
            coverage_status = injury_feed_status

        record = {
            "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
            "game_id": game.get("game_id"),
            "season": season,
            "week": week,
            "gameday_utc": game["gameday"].isoformat(),
            "home_team": home,
            "away_team": away,
            "spread_line_source_value": game.get("spread_line", np.nan),
            "spread_value_available": bool(pd.notna(game.get("spread_line", np.nan))),
            "total_line_source_value": game.get("total_line", np.nan),
            "total_value_available": bool(pd.notna(game.get("total_line", np.nan))),
            "baseline_projected_total": round(projected_home + projected_away, 3) if pd.notna(projected_home) and pd.notna(projected_away) else np.nan,
            "baseline_total_edge": round(projected_home + projected_away - float(game.get("total_line")), 3) if pd.notna(projected_home) and pd.notna(projected_away) and pd.notna(game.get("total_line")) else np.nan,
            "baseline_projected_home_points": round(projected_home, 3) if pd.notna(projected_home) else np.nan,
            "baseline_projected_away_points": round(projected_away, 3) if pd.notna(projected_away) else np.nan,
            "baseline_predicted_home_margin": round(predicted_home_margin, 3) if pd.notna(predicted_home_margin) else np.nan,
            "injury_feed_status": injury_feed_status,
            "injury_week_coverage_status": coverage_status,
            "injury_week_has_rows": week_available,
            "home_injury_report_rows": home_count,
            "away_injury_report_rows": away_count,
            "injury_feed_has_source_timestamp": bool("date_modified" in injury_rows.columns) if not injury_rows.empty else False,
            "injury_feed_source": injury_url,
            "note": "Team row counts describe records in the current weekly feed only; zero is not interpreted as no injuries. Reports can omit long-term injuries and current statuses can change. Capture time does not establish source publication time or guarantee capture before kickoff.",
        }
        records.append(record)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ats_market_snapshot_{captured.strftime('%Y%m%dT%H%M%SZ')}.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    print(f"Saved {len(records)} upcoming-game rows for {today_utc.date()} through {horizon_date.date()}: {path}")
    print(f"Capture time UTC: {captured.isoformat()}")
    print("Spread availability: " + str(sum(bool(r["spread_value_available"]) for r in records)) + f"/{len(records)}")
    print("Total availability: " + str(sum(bool(r["total_value_available"]) for r in records)) + f"/{len(records)}")
    print("Injury counts are reported only when the injury feed has rows for that game week; missing feed data is stored as unavailable.")


if __name__ == "__main__":
    main()
