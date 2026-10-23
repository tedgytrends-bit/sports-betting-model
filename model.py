"""NFL efficiency features, chronological backtesting, and baseline comparison.

Experimental research utilities. Loads current-season play-by-play when requested and fails loudly on missing seasons. Not a validated betting system.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

MODEL_VERSION = "0.6.3"

SCHEDULE_URLS = [
    "https://github.com/nflverse/nfldata/raw/master/data/games.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
]

# Only columns used by the feature pipeline are downloaded, reducing memory use.
PBP_COLUMNS = [
    "game_id", "season", "week", "posteam", "defteam", "epa", "success",
    "play_type", "qb_kneel", "qb_spike", "yardline_100", "touchdown",
    "pass_touchdown", "rush_touchdown", "return_touchdown", "interception",
    "interception_player_id", "fumble_lost", "fumble", "fumble_recovery_1_team",
    "fumble_recovery_2_team", "fixed_drive", "drive", "game_seconds_remaining",
]


def load_schedule_data() -> pd.DataFrame:
    errors = []
    for url in SCHEDULE_URLS:
        try:
            df = pd.read_csv(url, low_memory=False)
            required = {"season", "away_team", "home_team", "away_score", "home_score"}
            if required.issubset(df.columns):
                return normalize_schedule(df)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("Unable to load compatible schedule data. " + " | ".join(errors))


def normalize_schedule(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["season", "week", "away_score", "home_score", "spread_line", "total_line"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "gameday" in df.columns:
        df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce", utc=True).dt.tz_convert(None)
    else:
        df["gameday"] = pd.NaT
    for col in ["spread_line", "total_line"]:
        if col not in df.columns:
            df[col] = np.nan
    return df.sort_values(["gameday", "season", "week"], na_position="last").reset_index(drop=True)


def load_pbp(seasons=(2021, 2022, 2023, 2024, 2025, 2026)) -> pd.DataFrame:
    """Load only fields needed for the model; fall back if a source lacks optional columns."""
    frames, errors = [], []
    for season in seasons:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv"
        try:
            try:
                frame = pd.read_csv(url, usecols=lambda c: c in PBP_COLUMNS, low_memory=False)
            except Exception:
                # A fallback for source/schema changes; still reduce to known required columns after loading.
                frame = pd.read_csv(url, low_memory=False)
                frame = frame[[c for c in PBP_COLUMNS if c in frame.columns]]
            if "season" not in frame.columns:
                frame["season"] = season
            required = {"game_id", "posteam", "defteam", "epa", "success", "play_type"}
            missing = required - set(frame.columns)
            if missing:
                raise ValueError(f"missing required columns: {sorted(missing)}")
            frames.append(frame)
        except Exception as exc:
            errors.append(f"{season}: {exc}")
    if errors:
        # Fail loudly instead of silently using stale/incomplete seasons in a backtest.
        raise RuntimeError("Unable to load all requested play-by-play seasons: " + " | ".join(errors))
    if not frames:
        raise RuntimeError("Unable to load play-by-play data; no requested seasons were loaded.")
    combined = pd.concat(frames, ignore_index=True)
    loaded = set(pd.to_numeric(combined["season"], errors="coerce").dropna().astype(int).unique())
    missing_seasons = sorted(set(int(s) for s in seasons) - loaded)
    if missing_seasons:
        raise RuntimeError(f"Play-by-play data did not contain requested season(s): {missing_seasons}")
    return combined


def _get_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Return scrimmage plays without dropping rows just because a metric is missing.

    EPA/success averages ignore missing values naturally, but red-zone and turnover
    indicators must still be calculated from the underlying play even if EPA is null.
    """
