"""NFL efficiency-based baseline and chronological backtesting utilities.

This is an educational, experimental model. It is not a validated betting system.
All features for a game are constructed using games dated strictly before kickoff.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

SCHEDULE_URLS = [
    "https://github.com/nflverse/nfldata/raw/master/data/games.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
]
PBP_URLS = [
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2024.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2023.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2022.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2021.csv",
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

def load_pbp(seasons=(2021, 2022, 2023, 2024, 2025)) -> pd.DataFrame:
    """Load play-by-play files, failing clearly if none are available."""
    frames, errors = [], []
    for season in seasons:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv"
        try:
            frame = pd.read_csv(url, low_memory=False)
            if "season" not in frame.columns:
                frame["season"] = season
            frames.append(frame)
        except Exception as exc:
            errors.append(f"{season}: {exc}")
    if not frames:
        raise RuntimeError("Unable to load play-by-play data. " + " | ".join(errors))
    return pd.concat(frames, ignore_index=True)

def _get_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Filter to offensive scrimmage plays and required fields."""
    df = pbp.copy()
    required = {"game_id", "posteam", "defteam", "epa", "success", "play_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Play-by-play file is missing required columns: {sorted(missing)}")
    df["epa"] = pd.to_numeric(df["epa"], errors="coerce")
    df["success"] = pd.to_numeric(df["success"], errors="coerce")
    df = df[df["play_type"].isin(["run", "pass"]) & df["posteam"].notna() & df["defteam"].notna()]
    df = df[df["epa"].notna() & df["success"].notna()]
    if "qb_kneel" in df.columns:
        df = df[df["qb_kneel"].fillna(0) != 1]
    if "qb_spike" in df.columns:
        df = df[df["qb_spike"].fillna(0) != 1]
    return df

def build_team_game_efficiency(pbp: pd.DataFrame) -> pd.DataFrame:
    """One row per team/game: offense and defense EPA/play and success rate."""
    df = _get_plays(pbp)
    grouped = df.groupby(["game_id", "season", "week", "posteam", "defteam"], dropna=False).agg(
        off_epa=("epa", "mean"),
        off_success=("success", "mean"),
        offensive_plays=("epa", "size"),
    ).reset_index()
    offense = grouped.rename(columns={"posteam": "team", "defteam": "opponent"})
    defense = grouped.rename(columns={
        "posteam": "opponent",
        "defteam": "team",
        "off_epa": "def_epa_allowed",
        "off_success": "def_success_allowed",
        "offensive_plays": "defensive_plays",
    })
    return pd.concat([
        offense[["game_id","season","week","team","opponent","off_epa","off_success","offensive_plays"]],
        defense[["game_id","season","week","team","opponent","def_epa_allowed","def_success_allowed","defensive_plays"]]
    ], ignore_index=True, sort=False)

def build_efficiency_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Return team-game efficiency rows with offense and defense metrics combined."""
    plays = _get_plays(pbp)
    off = plays.groupby(["game_id","season","week","posteam"]).agg(
        off_epa=("epa","mean"),
        off_success=("success","mean"),
        offensive_plays=("epa","size"),
    ).reset_index().rename(columns={"posteam":"team"})
    deff = plays.groupby(["game_id","season","week","defteam"]).agg(
        def_epa_allowed=("epa","mean"),
        def_success_allowed=("success","mean"),
        defensive_plays=("epa","size"),
    ).reset_index().rename(columns={"defteam":"team"})
    out = off.merge(deff, on=["game_id","season","week","team"], how="outer")
    return out

def _game_features_for_target(history_eff: pd.DataFrame, schedule_history: pd.DataFrame,
                              home_team: str, away_team: str, target_date: pd.Timestamp,
                              lookback_games: int = 10) -> dict:
    hist = history_eff.copy()
    if "gameday" in hist.columns:
        hist = hist[hist["gameday"] < target_date]
    # Most recent team-game rows available before target kickoff date.
    def team_stats(team):
        th = hist[hist["team"] == team].sort_values(["gameday"] if "gameday" in hist.columns else ["season","week"]).tail(lookback_games)
        if th.empty:
            return None
        def avg(col):
            return float(pd.to_numeric(th[col], errors="coerce").mean()) if col in th else np.nan
        return {
            "off_epa": avg("off_epa"),
            "off_success": avg("off_success"),
            "def_epa_allowed": avg("def_epa_allowed"),
            "def_success_allowed": avg("def_success_allowed"),
        }
    h, a = team_stats(home_team), team_stats(away_team)
    if h is None or a is None:
        return {}
    # Directional features. Negative defensive EPA allowed means the defense suppresses efficiency.
    return {
        "home_off_epa": h["off_epa"], "away_off_epa": a["off_epa"],
        "home_def_epa_allowed": h["def_epa_allowed"], "away_def_epa_allowed": a["def_epa_allowed"],
        "home_off_success": h["off_success"], "away_off_success": a["off_success"],
        "home_def_success_allowed": h["def_success_allowed"], "away_def_success_allowed": a["def_success_allowed"],
        "home_off_minus_away_def": h["off_epa"] - a["def_epa_allowed"],
        "away_off_minus_home_def": a["off_epa"] - h["def_epa_allowed"],
        "home_field": 1.0,
    }

def _feature_frame(schedule: pd.DataFrame, efficiency: pd.DataFrame, lookback_games=10):
    # Map game_id to date/teams and attach date to team-game efficiency rows.
    game_meta = schedule[["game_id","gameday","season","week","home_team","away_team","home_score","away_score"]].copy()
    eff = efficiency.merge(game_meta[["game_id","gameday"]], on="game_id", how="left")
    rows = []
    feature_cols = None
    for _, g in schedule.sort_values("gameday").iterrows():
        if pd.isna(g["gameday"]):
            continue
        # For each target, only include historical games before target date.
        hist_eff = eff[eff["gameday"] < g["gameday"]]
        f = _game_features_for_target(hist_eff, schedule, g["home_team"], g["away_team"], g["gameday"], lookback_games)
        if not f:
            continue
        f.update({
            "game_id": g["game_id"], "gameday": g["gameday"], "season": g["season"], "week": g["week"],
            "home_team": g["home_team"], "away_team": g["away_team"],
            "home_score": g["home_score"], "away_score": g["away_score"],
        })
        rows.append(f)
    return pd.DataFrame(rows)

def build_efficiency_model_dataset(schedule: pd.DataFrame, pbp: pd.DataFrame, lookback_games=10) -> pd.DataFrame:
    eff = build_efficiency_table(pbp)
    return _feature_frame(schedule, eff, lookback_games=lookback_games)

def chronological_backtest(dataset: pd.DataFrame, min_train_games=500) -> dict:
    """Chronological expanding-window Ridge regression predicting home/away scores."""
    data = dataset.dropna(subset=["home_score","away_score"]).sort_values("gameday").copy()
    exclude = {"game_id","gameday","season","week","home_team","away_team","home_score","away_score"}
    features = [c for c in data.columns if c not in exclude and pd.api.types.is_numeric_dtype(data[c])]
    if len(data) <= min_train_games:
        raise ValueError(f"Need more than {min_train_games} completed games; found {len(data)}.")
    preds = []
    # Test in chronological blocks by week, fitting only on earlier rows.
    data["test_block"] = data["gameday"].dt.to_period("W").astype(str)
    for block in data["test_block"].drop_duplicates().tolist():
        test = data[data["test_block"] == block]
        train = data[data["gameday"] < test["gameday"].min()]
        if len(train) < min_train_games:
            continue
        X_train, X_test = train[features].fillna(0), test[features].fillna(0)
        for target in ["home_score","away_score"]:
            model = Ridge(alpha=10.0)
            model.fit(X_train, train[target])
            test = test.copy()
            test[f"pred_{target}"] = model.predict(X_test)
        preds.append(test)
    if not preds:
        raise ValueError("No test predictions were generated; check history and minimum training size.")
    result = pd.concat(preds, ignore_index=True).drop_duplicates(subset=["game_id"])
    return {
        "predictions": result,
        "n": len(result),
        "home_mae": float(mean_absolute_error(result["home_score"], result["pred_home_score"])),
        "away_mae": float(mean_absolute_error(result["away_score"], result["pred_away_score"])),
        "home_rmse": float(np.sqrt(mean_squared_error(result["home_score"], result["pred_home_score"]))),
        "away_rmse": float(np.sqrt(mean_squared_error(result["away_score"], result["pred_away_score"]))),
    }

def baseline_projection(games: pd.DataFrame, season: int, lookback: int = 6) -> pd.DataFrame:
    """Recent points-for/against baseline for future scheduled games."""
    season_games = games[games["season"] == season].copy()
    if season_games.empty:
        return pd.DataFrame()
    output = []
    for _, game in season_games.iterrows():
        if pd.notna(game["home_score"]) and pd.notna(game["away_score"]):
            continue
        game_date = game.get("gameday", pd.NaT)
        if pd.isna(game_date):
            continue
        history = games[games["gameday"] < game_date]
        def stats(team):
            prior = history[
                ((history["home_team"] == team) | (history["away_team"] == team))
                & history["home_score"].notna() & history["away_score"].notna()
            ].sort_values("gameday").tail(lookback)
            if prior.empty:
                return None
            scored, allowed = [], []
            for _, row in prior.iterrows():
                if row["home_team"] == team:
                    scored.append(float(row["home_score"])); allowed.append(float(row["away_score"]))
                else:
                    scored.append(float(row["away_score"])); allowed.append(float(row["home_score"]))
            return sum(scored)/len(scored), sum(allowed)/len(allowed)
        h, a = stats(str(game["home_team"])), stats(str(game["away_team"]))
        if h is None or a is None:
            continue
        home_points = 0.5*h[0] + 0.5*a[1] + 1.5
        away_points = 0.5*a[0] + 0.5*h[1]
        item = game.to_dict()
        item["projected_home"] = max(0.0, home_points)
        item["projected_away"] = max(0.0, away_points)
        item["model_home_spread"] = -(home_points-away_points)
        item["projected_total"] = home_points+away_points
        output.append(item)
    return pd.DataFrame(output)
