"""NFL efficiency features, chronological backtesting, and baseline comparison.

Experimental research utilities. Loads current-season play-by-play when requested and fails loudly on missing seasons. Not a validated betting system.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests
from io import BytesIO
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

MODEL_VERSION = "0.7.0"

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
    """Load a schedule source only if it passes basic integrity checks."""
    errors = []
    required = {
        "game_id", "gameday", "season", "week", "away_team",
        "home_team", "away_score", "home_score", "total_line",
    }

    for url in SCHEDULE_URLS:
        try:
            # Bound network waits so the app cannot spin indefinitely if a source hangs.
            response = requests.get(url, timeout=(5, 20), headers={"User-Agent": "sports-betting-model/1.0"})
            response.raise_for_status()
            df = pd.read_csv(BytesIO(response.content), low_memory=False)
            missing = required - set(df.columns)

            if missing:
                errors.append(f"{url}: missing columns {sorted(missing)}")
                continue

            if df["game_id"].isna().any():
                errors.append(f"{url}: missing game_id values")
                continue

            if df["game_id"].duplicated().any():
                errors.append(f"{url}: duplicate game_id values")
                continue

            normalized = normalize_schedule(df)
            line_count = int(normalized["total_line"].notna().sum())

            if line_count == 0:
                errors.append(f"{url}: no valid total_line values")
                continue


            source_rows = int(len(normalized))

            normalized.attrs["schedule_source_url"] = url
            normalized.attrs["schedule_source_rows"] = source_rows
            normalized.attrs["schedule_total_line_rows"] = line_count
            normalized.attrs["schedule_game_id_unique"] = True

            # Store provenance as columns so it survives cached DataFrame handling.
            normalized["schedule_source_url"] = url
            normalized["schedule_source_rows"] = source_rows
            normalized["schedule_total_line_rows"] = line_count
            normalized["schedule_game_id_unique"] = True

            return normalized


        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    raise RuntimeError(
        "Unable to load a validated schedule source. " + " | ".join(errors)
    )



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
    required = {"game_id", "posteam", "defteam", "play_type"}
    missing = required - set(pbp.columns)
    if missing:
        raise ValueError(f"Play-by-play file is missing required columns: {sorted(missing)}")
    keep = [c for c in PBP_COLUMNS if c in pbp.columns]
    df = pbp.loc[:, keep].copy()
    df["epa"] = pd.to_numeric(df["epa"], errors="coerce") if "epa" in df else np.nan
    df["success"] = pd.to_numeric(df["success"], errors="coerce") if "success" in df else np.nan
    df = df[df["play_type"].isin(["run", "pass"]) & df["posteam"].notna() & df["defteam"].notna()]
    for col in ["qb_kneel", "qb_spike"]:
        if col in df.columns:
            df = df[pd.to_numeric(df[col], errors="coerce").fillna(0) != 1]
    return df


def _binary_indicator(series: pd.Series) -> pd.Series:
    """Normalize a source indicator to 0/1 while preserving genuinely missing data."""
    values = pd.to_numeric(series, errors="coerce")
    # nflverse indicators are 0/1. Clip odd values rather than letting them inflate rates.
    return values.where(values.isna(), values.fillna(0).clip(0, 1))


def _first_usable_indicator(frame: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """Choose a usable indicator; do not mistake an all-null/all-zero field for valid data."""
    for col in candidates:
        if col not in frame.columns:
            continue
        candidate = _binary_indicator(frame[col])
        if candidate.notna().any() and float(candidate.fillna(0).sum()) > 0:
            return candidate.fillna(0)
    # If fields exist but there were no events, an all-zero indicator is plausible only
    # when at least one source column has observed values. Otherwise keep unavailable as NA.
    for col in candidates:
        if col in frame.columns:
            candidate = _binary_indicator(frame[col])
            if candidate.notna().any():
                return candidate.fillna(0)
    return pd.Series(np.nan, index=frame.index, dtype=float)


def build_efficiency_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Build game-level team features from scrimmage play-by-play.

    Red-zone touchdown rate is touchdowns on plays beginning inside the opponent's
    20-yard line divided by red-zone scrimmage plays. It is explicitly a play-level
    proxy, not drive conversion rate. Turnovers use interception indicators/player IDs
    and lost-fumble/recovery fields with fallbacks across nflverse schema variants.
    """
    plays = _get_plays(pbp)
    group_cols = ["game_id", "season", "week", "posteam"]
    off = plays.groupby(group_cols, dropna=False).agg(
        off_epa=("epa", "mean"),
        off_success=("success", "mean"),
        offensive_plays=("play_type", "size"),
    ).reset_index().rename(columns={"posteam": "team"})
    deff = plays.groupby(["game_id", "season", "week", "defteam"], dropna=False).agg(
        def_epa_allowed=("epa", "mean"),
        def_success_allowed=("success", "mean"),
        defensive_plays=("play_type", "size"),
    ).reset_index().rename(columns={"defteam": "team"})
    out = off.merge(deff, on=["game_id", "season", "week", "team"], how="outer")

    extra = plays.copy()
    # Normalize key fields and handle source variants / all-null optional columns.
    for col in ["yardline_100", "touchdown", "pass_touchdown", "rush_touchdown", "return_touchdown",
                "interception", "fumble_lost", "fumble"]:
        if col in extra.columns:
            extra[col] = pd.to_numeric(extra[col], errors="coerce")
    if "yardline_100" in extra.columns and extra["yardline_100"].notna().any():
        extra["red_zone_play"] = extra["yardline_100"].between(1, 20, inclusive="both").astype(float)
    else:
        extra["red_zone_play"] = np.nan

    td_candidates = [c for c in ["touchdown", "pass_touchdown", "rush_touchdown", "return_touchdown"] if c in extra.columns]
    td_indicator = _first_usable_indicator(extra, td_candidates) if td_candidates else pd.Series(np.nan, index=extra.index)
    if extra["red_zone_play"].notna().any() and td_indicator.notna().any():
        extra["red_zone_td_play"] = np.where(
            extra["red_zone_play"].eq(1), td_indicator.fillna(0), 0.0
        )
    else:
        extra["red_zone_td_play"] = np.nan

    int_candidates = [c for c in ["interception"] if c in extra.columns]
    interceptions = _first_usable_indicator(extra, int_candidates) if int_candidates else pd.Series(np.nan, index=extra.index)
    # In some releases the play-level indicator is absent/unusable but the intercepted-player ID is present.
    if (not interceptions.notna().any() or float(interceptions.fillna(0).sum()) == 0) and "interception_player_id" in extra.columns:
        fallback = extra["interception_player_id"].notna().astype(float)
        if fallback.sum() > 0:
            interceptions = fallback

    lost_fumbles = _first_usable_indicator(extra, ["fumble_lost"] if "fumble_lost" in extra.columns else [])
    if (not lost_fumbles.notna().any() or float(lost_fumbles.fillna(0).sum()) == 0) and "fumble" in extra.columns:
        fumbles = _binary_indicator(extra["fumble"])
        if "fumble_recovery_1_team" in extra.columns:
            recovered_by_def = extra["fumble_recovery_1_team"].notna() & (
                extra["fumble_recovery_1_team"].astype(str) == extra["defteam"].astype(str)
            )
            fallback = (fumbles.fillna(0).eq(1) & recovered_by_def).astype(float)
            if fallback.sum() > 0:
                lost_fumbles = fallback

    if interceptions.notna().any() or lost_fumbles.notna().any():
        int_values = interceptions.fillna(0) if interceptions.notna().any() else pd.Series(0.0, index=extra.index)
        fum_values = lost_fumbles.fillna(0) if lost_fumbles.notna().any() else pd.Series(0.0, index=extra.index)
        extra["turnover_play"] = (int_values + fum_values).clip(upper=1).astype(float)
    else:
        extra["turnover_play"] = np.nan

    add = extra.groupby(group_cols, dropna=False).agg(
        off_plays_per_game=("play_type", "size"),
        red_zone_plays=("red_zone_play", lambda x: x.sum(min_count=1)),
        red_zone_td_plays=("red_zone_td_play", lambda x: x.sum(min_count=1)),
        turnovers=("turnover_play", lambda x: x.sum(min_count=1)),
    ).reset_index().rename(columns={"posteam": "team"})
    add["red_zone_td_rate"] = add["red_zone_td_plays"] / add["red_zone_plays"].replace(0, np.nan)
    add["turnovers_per_play"] = add["turnovers"] / add["off_plays_per_game"].replace(0, np.nan)

    # Every turnover play is attributed to the defense on the field for that play.
    def_extra = extra.groupby(["game_id", "season", "week", "defteam"], dropna=False).agg(
        def_takeaways=("turnover_play", lambda x: x.sum(min_count=1)),
        def_opponent_plays=("play_type", "size"),
    ).reset_index().rename(columns={"defteam": "team"})
    def_extra["def_takeaways_per_play"] = def_extra["def_takeaways"] / def_extra["def_opponent_plays"].replace(0, np.nan)

    out = out.merge(add, on=["game_id", "season", "week", "team"], how="left")
    out = out.merge(def_extra[["game_id", "season", "week", "team", "def_takeaways_per_play"]],
                    on=["game_id", "season", "week", "team"], how="left")
    return out

def _game_features_for_target(history_eff: pd.DataFrame, home_team: str,
                              away_team: str, target_date: pd.Timestamp,
                              lookback_games: int = 10) -> dict:
    hist = history_eff
    if "gameday" in hist.columns:
        hist = hist[hist["gameday"] < target_date]

    def team_stats(team):
        th = hist[hist["team"] == team].sort_values("gameday").tail(lookback_games)
        if th.empty:
            return None
        def avg(col):
            return float(pd.to_numeric(th[col], errors="coerce").mean()) if col in th else np.nan
        return {
            "off_epa": avg("off_epa"),
            "off_success": avg("off_success"),
            "def_epa_allowed": avg("def_epa_allowed"),
            "def_success_allowed": avg("def_success_allowed"),
            "plays_per_game": avg("off_plays_per_game"),
            "red_zone_td_rate": avg("red_zone_td_rate"),
            "turnovers_per_play": avg("turnovers_per_play"),
            "def_takeaways_per_play": avg("def_takeaways_per_play"),
            "red_zone_opportunities": avg("red_zone_plays"),
        }

    h, a = team_stats(home_team), team_stats(away_team)
    if h is None or a is None:
        return {}
    return {
        "home_off_epa": h["off_epa"], "away_off_epa": a["off_epa"],
        "home_def_epa_allowed": h["def_epa_allowed"], "away_def_epa_allowed": a["def_epa_allowed"],
        "home_off_success": h["off_success"], "away_off_success": a["off_success"],
        "home_def_success_allowed": h["def_success_allowed"], "away_def_success_allowed": a["def_success_allowed"],
        "home_off_minus_away_def": h["off_epa"] - a["def_epa_allowed"],
        "away_off_minus_home_def": a["off_epa"] - h["def_epa_allowed"],
        # Relative matchup features expose offense-vs-defense strength directly.
        "home_success_matchup": h["off_success"] - a["def_success_allowed"],
        "away_success_matchup": a["off_success"] - h["def_success_allowed"],
        "home_plays_per_game": h["plays_per_game"], "away_plays_per_game": a["plays_per_game"],
        "home_red_zone_td_rate": h["red_zone_td_rate"], "away_red_zone_td_rate": a["red_zone_td_rate"],
        "home_turnovers_per_play": h["turnovers_per_play"], "away_turnovers_per_play": a["turnovers_per_play"],
        "home_def_takeaways_per_play": h["def_takeaways_per_play"],
        "away_def_takeaways_per_play": a["def_takeaways_per_play"],
        "home_field": 1.0,
    }


def _feature_frame(schedule: pd.DataFrame, efficiency: pd.DataFrame, lookback_games=10):
    game_meta = schedule[["game_id", "gameday"]].copy()
    eff = efficiency.merge(game_meta, on="game_id", how="left")
    rows = []
    for _, g in schedule.sort_values("gameday").iterrows():
        if pd.isna(g["gameday"]):
            continue
        hist_eff = eff[eff["gameday"] < g["gameday"]]
        f = _game_features_for_target(hist_eff, g["home_team"], g["away_team"], g["gameday"], lookback_games)
        if not f:
            continue
        # Rest-day features use only schedule dates strictly before this game.
        prior_games = schedule[(schedule["gameday"] < g["gameday"]) &
                               (schedule["home_score"].notna()) & (schedule["away_score"].notna())]
        def rest_days(team):
            played = prior_games[(prior_games["home_team"] == team) | (prior_games["away_team"] == team)]
            if played.empty:
                return 7.0
            last_date = pd.to_datetime(played["gameday"], errors="coerce").max()
            return float(np.clip((g["gameday"] - last_date).days, 0, 30))
        f["home_rest_days"] = rest_days(g["home_team"])
        f["away_rest_days"] = rest_days(g["away_team"])
        f["rest_days_diff"] = f["home_rest_days"] - f["away_rest_days"]
        f.update({
            "game_id": g["game_id"], "gameday": g["gameday"], "season": g["season"], "week": g["week"],
            "home_team": g["home_team"], "away_team": g["away_team"],
            "home_score": g["home_score"], "away_score": g["away_score"],
        })
        rows.append(f)
    return pd.DataFrame(rows)


def build_efficiency_model_dataset(schedule: pd.DataFrame, pbp: pd.DataFrame, lookback_games=10) -> pd.DataFrame:
    efficiency = build_efficiency_table(pbp)
    return _feature_frame(schedule, efficiency, lookback_games=lookback_games)


def project_upcoming_efficiency(
    dataset: pd.DataFrame,
    min_train_games: int = 500,
) -> pd.DataFrame:
    """Fit on completed games and project scheduled games with missing scores."""
    data = dataset.copy()
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    completed = data.dropna(subset=["home_score", "away_score", "gameday"]).copy()
    upcoming = data[
        data["gameday"].notna()
        & (data["home_score"].isna() | data["away_score"].isna())
    ].copy()
    if len(completed) < min_train_games:
        raise ValueError(
            f"Need at least {min_train_games} completed games; found {len(completed)}."
        )
    exclude = {
        "game_id", "gameday", "season", "week", "home_team", "away_team",
        "home_score", "away_score",
    }
    features = [
        c for c in data.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(data[c])
    ]
    active_features = [c for c in features if completed[c].notna().any()]
    if not active_features:
        raise ValueError("No usable numeric features for upcoming projections.")
    medians = completed[active_features].median(numeric_only=True).fillna(0)
    X_train = completed[active_features].fillna(medians).fillna(0)
    predictions = upcoming[["game_id", "gameday", "season", "week", "away_team", "home_team"]].copy()
    X_future = upcoming[active_features].fillna(medians).fillna(0)
    for target, output in [
        ("home_score", "projected_home"),
        ("away_score", "projected_away"),
    ]:
        estimator = Ridge(alpha=10.0)
        estimator.fit(X_train, completed[target])
        predictions[output] = estimator.predict(X_future)
    predictions["projected_total"] = predictions["projected_home"] + predictions["projected_away"]
    predictions["model_home_spread"] = predictions["projected_away"] - predictions["projected_home"]
    predictions["training_games"] = len(completed)
    return predictions


def chronological_backtest(dataset: pd.DataFrame, min_train_games=500) -> dict:
    data = dataset.dropna(subset=["home_score", "away_score"]).sort_values("gameday").copy()
    exclude = {"game_id", "gameday", "season", "week", "home_team", "away_team", "home_score", "away_score"}
    features = [c for c in data.columns if c not in exclude and pd.api.types.is_numeric_dtype(data[c])]
    if len(data) <= min_train_games:
        raise ValueError(f"Need more than {min_train_games} completed games; found {len(data)}.")
    preds = []
    data["test_block"] = data["gameday"].dt.to_period("W").astype(str)
    for block in data["test_block"].drop_duplicates().tolist():
        test = data[data["test_block"] == block]
        train = data[data["gameday"] < test["gameday"].min()]
        if len(train) < min_train_games:
            continue
        # Train-window-only feature availability and imputation: a feature that is
        # entirely absent in training is excluded, not silently converted into zeros.
        active_features = [c for c in features if train[c].notna().any()]
        if not active_features:
            continue
        train_medians = train[active_features].median(numeric_only=True).fillna(0)
        X_train = train[active_features].fillna(train_medians).fillna(0)
        X_test = test[active_features].fillna(train_medians).fillna(0)
        test = test.copy()
        test["n_active_features"] = len(active_features)
        for target in ["home_score", "away_score"]:
            estimator = Ridge(alpha=10.0)
            estimator.fit(X_train, train[target])
            test[f"pred_{target}"] = estimator.predict(X_test)
        preds.append(test)
    if not preds:
        raise ValueError("No test predictions were generated; check history and minimum training size.")
    result = pd.concat(preds, ignore_index=True).drop_duplicates(subset=["game_id"])
    metrics = score_prediction_metrics(result, "pred_home_score", "pred_away_score")
    return {
        "predictions": result,
        "n": len(result),
        "home_mae": metrics["Home MAE"],
        "away_mae": metrics["Away MAE"],
        "home_rmse": metrics["Home RMSE"],
        "away_rmse": metrics["Away RMSE"],
    }


def chronological_direct_total_backtest(
    dataset: pd.DataFrame,
    min_train_games: int = 500,
) -> pd.DataFrame:
    """Predict actual combined score directly using chronological training.

    Each weekly test block is trained only on completed games dated before
    that block. Identifier fields and scores are excluded from predictors.
    """
    data = dataset.dropna(
        subset=["gameday", "home_score", "away_score"]
    ).sort_values("gameday").copy()
    data["actual_total"] = (
        pd.to_numeric(data["home_score"], errors="coerce")
        + pd.to_numeric(data["away_score"], errors="coerce")
    )
    data = data.dropna(subset=["actual_total"]).copy()
    exclude = {
        "game_id", "gameday", "season", "week", "home_team", "away_team",
        "home_score", "away_score", "actual_total",
    }
    features = [
        c for c in data.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(data[c])
    ]
    if len(data) <= min_train_games:
        raise ValueError(
            f"Need more than {min_train_games} completed games; found {len(data)}."
        )

    data["test_block"] = data["gameday"].dt.to_period("W").astype(str)
    predictions = []
    for block in data["test_block"].drop_duplicates().tolist():
        test = data[data["test_block"] == block].copy()
        train = data[data["gameday"] < test["gameday"].min()].copy()
        if len(train) < min_train_games:
            continue
        active_features = [c for c in features if train[c].notna().any()]
        if not active_features:
            continue
        medians = train[active_features].median(numeric_only=True).fillna(0)
        X_train = train[active_features].fillna(medians).fillna(0)
        X_test = test[active_features].fillna(medians).fillna(0)
        model = Ridge(alpha=10.0)
        model.fit(X_train, train["actual_total"])
        test["direct_total_prediction"] = model.predict(X_test)
        predictions.append(test[["game_id", "direct_total_prediction"]])

    if not predictions:
        raise ValueError("No chronological direct-total predictions were generated.")
    return pd.concat(predictions, ignore_index=True).drop_duplicates("game_id")


def chronological_market_residual_backtest(
    dataset: pd.DataFrame,
    schedule: pd.DataFrame,
    min_train_games: int = 500,
) -> pd.DataFrame:
    """Predict actual game-total residual versus the market using chronological training.

    Target = actual combined score minus the recorded market total.
    Each weekly test block is predicted only from games dated before that block.
    Market totals are targets/benchmarks, not model input features.
    """
    lines = schedule[["game_id", "total_line"]].copy()
    lines["total_line"] = pd.to_numeric(lines["total_line"], errors="coerce")
    data = dataset.merge(lines, on="game_id", how="left", validate="one_to_one")
    data["actual_total"] = (
        pd.to_numeric(data["home_score"], errors="coerce")
        + pd.to_numeric(data["away_score"], errors="coerce")
    )
    data["market_residual"] = data["actual_total"] - data["total_line"]
    data = data.dropna(
        subset=["gameday", "actual_total", "total_line", "market_residual"]
    ).sort_values("gameday").copy()

    exclude = {
        "game_id", "gameday", "season", "week", "home_team", "away_team",
        "home_score", "away_score", "total_line", "actual_total",
        "market_residual",
        # Absolute rest-day values are capped at 30, making offseason games
        # indistinguishable from a long rest/bye. Keep only relative rest.
        "home_rest_days", "away_rest_days",
    }
    features = [
        c for c in data.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(data[c])
    ]
    if len(data) <= min_train_games:
        raise ValueError(
            f"Need more than {min_train_games} games with market totals; found {len(data)}."
        )

    data["test_block"] = data["gameday"].dt.to_period("W").astype(str)
    predictions = []
    for block in data["test_block"].drop_duplicates().tolist():
        test = data[data["test_block"] == block].copy()
        train = data[data["gameday"] < test["gameday"].min()].copy()
        if len(train) < min_train_games:
            continue
        active_features = [c for c in features if train[c].notna().any()]
        if not active_features:
            continue
        medians = train[active_features].median(numeric_only=True).fillna(0)
        X_train = train[active_features].fillna(medians).fillna(0)
        X_test = test[active_features].fillna(medians).fillna(0)
        model = Ridge(alpha=10.0)
        model.fit(X_train, train["market_residual"])
        test["pred_market_residual"] = model.predict(X_test)
        predictions.append(test[["game_id", "pred_market_residual"]])

    if not predictions:
        raise ValueError("No chronological market-residual predictions were generated.")
    return pd.concat(predictions, ignore_index=True).drop_duplicates("game_id")


def score_prediction_metrics(data: pd.DataFrame, home_pred: str, away_pred: str) -> dict:
    return {
        "Home MAE": float(mean_absolute_error(data["home_score"], data[home_pred])),
        "Away MAE": float(mean_absolute_error(data["away_score"], data[away_pred])),
        "Home RMSE": float(np.sqrt(mean_squared_error(data["home_score"], data[home_pred]))),
        "Away RMSE": float(np.sqrt(mean_squared_error(data["away_score"], data[away_pred]))),
    }


def add_scoring_baseline_predictions(predictions: pd.DataFrame, schedule: pd.DataFrame, lookback: int = 6) -> pd.DataFrame:
    """Add a recent points-for/against baseline for the same historical test games.

    Every baseline prediction uses only completed games dated strictly before the target date.
    """
    games = schedule.copy()
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce")
    output = predictions.copy()
    home_preds, away_preds = [], []

    for _, game in output.iterrows():
        target_date = pd.to_datetime(game["gameday"], errors="coerce")
        history = games[
            (games["gameday"] < target_date)
            & games["home_score"].notna()
            & games["away_score"].notna()
        ]

        def stats(team):
            prior = history[
                (history["home_team"] == team) | (history["away_team"] == team)
            ].sort_values("gameday").tail(lookback)
            if prior.empty:
                return None
            home_mask = prior["home_team"] == team
            scored = np.where(home_mask, prior["home_score"], prior["away_score"]).astype(float)
            allowed = np.where(home_mask, prior["away_score"], prior["home_score"]).astype(float)
            return float(scored.mean()), float(allowed.mean())

        h = stats(game["home_team"])
        a = stats(game["away_team"])
        if h is None or a is None:
            home_preds.append(np.nan)
            away_preds.append(np.nan)
            continue
        home_score = 0.5 * h[0] + 0.5 * a[1] + 1.5
        away_score = 0.5 * a[0] + 0.5 * h[1]
        home_preds.append(max(0.0, home_score))
        away_preds.append(max(0.0, away_score))

    output["baseline_home_score"] = home_preds
    output["baseline_away_score"] = away_preds
    return output.dropna(subset=["baseline_home_score", "baseline_away_score"]).copy()


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
            home_mask = prior["home_team"] == team
            scored = np.where(home_mask, prior["home_score"], prior["away_score"]).astype(float)
            allowed = np.where(home_mask, prior["away_score"], prior["home_score"]).astype(float)
            return float(scored.mean()), float(allowed.mean())
        h, a = stats(str(game["home_team"])), stats(str(game["away_team"]))
        if h is None or a is None:
            continue
        home_points = 0.5 * h[0] + 0.5 * a[1] + 1.5
        away_points = 0.5 * a[0] + 0.5 * h[1]
        item = game.to_dict()
        item["projected_home"] = max(0.0, home_points)
        item["projected_away"] = max(0.0, away_points)
        item["model_home_spread"] = -(home_points - away_points)
        item["projected_total"] = home_points + away_points
        output.append(item)
    return pd.DataFrame(output)
