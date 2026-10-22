"""Transparent, experimental NFL score baseline using public schedule/results data."""
from __future__ import annotations
import pandas as pd

SCHEDULE_URLS = [
    "https://github.com/nflverse/nfldata/raw/master/data/games.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
]

def load_schedule_data() -> pd.DataFrame:
    errors = []
    df = None
    for url in SCHEDULE_URLS:
        try:
            candidate = pd.read_csv(url, low_memory=False)
            if {"season", "away_team", "home_team", "away_score", "home_score"}.issubset(candidate.columns):
                df = candidate
                break
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    if df is None:
        raise RuntimeError("Could not load a compatible schedule CSV. " + " | ".join(errors))

    for col in ["season", "week", "away_score", "home_score", "spread_line", "total_line"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "gameday" in df.columns:
        df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce")
    else:
        df["gameday"] = pd.NaT
    if "spread_line" not in df.columns:
        df["spread_line"] = float("nan")
    if "total_line" not in df.columns:
        df["total_line"] = float("nan")
    return df.sort_values(["season", "week", "gameday"], na_position="last").reset_index(drop=True)

def summarize_record(results: list[str]) -> dict[str, int]:
    return {key: sum(1 for result in results if result == key) for key in ["W", "L", "P"]}

def _team_recent_stats(history: pd.DataFrame, team: str, before_date, lookback: int):
    prior = history[
        (history["gameday"] < before_date)
        & (
            (history["home_team"] == team) | (history["away_team"] == team)
        )
        & history["home_score"].notna()
        & history["away_score"].notna()
    ].sort_values("gameday").tail(lookback)

    if prior.empty:
        return None
    scored, allowed = [], []
    for _, row in prior.iterrows():
        if row["home_team"] == team:
            scored.append(float(row["home_score"]))
            allowed.append(float(row["away_score"]))
        else:
            scored.append(float(row["away_score"]))
            allowed.append(float(row["home_score"]))
    return {"scored": sum(scored) / len(scored), "allowed": sum(allowed) / len(allowed), "n": len(prior)}

def build_baseline_projections(games: pd.DataFrame, season: int, lookback: int = 6) -> pd.DataFrame:
    season_games = games[games["season"] == season].copy()
    if season_games.empty:
        return pd.DataFrame()
    # Use all prior seasons plus completed games earlier than each fixture in this season.
    output = []
    for _, game in season_games.iterrows():
        if pd.notna(game["home_score"]) and pd.notna(game["away_score"]):
            continue
        game_date = game.get("gameday", pd.NaT)
        if pd.isna(game_date):
            continue
        history = games[games["gameday"] < game_date]
        away = _team_recent_stats(history, str(game["away_team"]), game_date, lookback)
        home = _team_recent_stats(history, str(game["home_team"]), game_date, lookback)
        if away is None or home is None:
            continue
        # Blend each team's recent scoring with its opponent's recent points allowed.
        away_points = 0.5 * away["scored"] + 0.5 * home["allowed"]
        home_points = 0.5 * home["scored"] + 0.5 * away["allowed"] + 1.5
        item = game.to_dict()
        item["projected_away"] = max(0.0, away_points)
        item["projected_home"] = max(0.0, home_points)
        item["model_home_spread"] = -(item["projected_home"] - item["projected_away"])
        item["projected_total"] = item["projected_home"] + item["projected_away"]
        output.append(item)
    return pd.DataFrame(output)
