"""Research-only prospective shadow comparison: frozen baseline vs passing features.

Writes immutable, timestamped projections to a separate folder. It does not
modify production model files, official prospective records, or user bet logs.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from research.efficiency_feature_experiments import (
    ALPHA,
    MIN_TRAIN_GAMES,
    _feature_sets,
    _pregame_split_features,
    _team_split_history,
)

OUT = ROOT / "data" / "prospective_passing_shadow"
MODEL_VERSION = "0.8.0"
CANDIDATE_NAME = "baseline_plus_all_passing"


def _predict(train: pd.DataFrame, future: pd.DataFrame, features: list[str], label: str) -> pd.DataFrame:
    active = [c for c in features if c in train.columns and train[c].notna().any()]
    if not active:
        raise RuntimeError(f"No active training features for {label}.")
    medians = train[active].median(numeric_only=True).fillna(0)
    x_train = train[active].fillna(medians).fillna(0)
    x_future = future[active].fillna(medians).fillna(0)
    out = future[["game_id", "gameday", "season", "week", "away_team", "home_team"]].copy()
    for target, col in (("home_score", "projected_home"), ("away_score", "projected_away")):
        estimator = Ridge(alpha=ALPHA)
        estimator.fit(x_train, train[target])
        out[col] = estimator.predict(x_future)
    out["projected_total"] = out["projected_home"] + out["projected_away"]
    out["predicted_home_margin"] = out["projected_home"] - out["projected_away"]
    out["training_games"] = len(train)
    out["active_feature_count"] = len(active)
    return out


def main() -> None:
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    print("Loading schedule and play-by-play...")
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    split_history = _team_split_history(pbp, schedule)
    split_features = _pregame_split_features(schedule, split_history)

    baseline_columns = list(baseline.columns)
    experimental_columns = [c for c in split_features.columns if c != "game_id"]
    data = baseline.merge(split_features, on="game_id", how="left", validate="one_to_one")
    variants = _feature_sets(data, baseline_columns, experimental_columns)

    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce", utc=True)
    now = pd.Timestamp(captured)
    completed = data.dropna(subset=["gameday", "home_score", "away_score"]).copy()
    future = data[
        data["gameday"].notna()
        & (data["gameday"] > now)
        & (data["home_score"].isna() | data["away_score"].isna())
    ].copy()
    if len(completed) < MIN_TRAIN_GAMES:
        raise RuntimeError(f"Only {len(completed)} completed games; need {MIN_TRAIN_GAMES}.")
    if future.empty:
        print("No unplayed future games; no shadow file written.")
        return

    # Market values are included only as separately labeled reference fields.
    market = schedule[["game_id", "spread_line", "total_line"]].drop_duplicates("game_id")
    future = future.merge(market, on="game_id", how="left", validate="one_to_one")

    baseline_pred = _predict(completed, future, variants["baseline_frozen_features"], "baseline")
    passing_pred = _predict(completed, future, variants[CANDIDATE_NAME], "passing_candidate")
    result = baseline_pred.rename(columns={
        "projected_home": "baseline_projected_home",
        "projected_away": "baseline_projected_away",
        "projected_total": "baseline_projected_total",
        "predicted_home_margin": "baseline_predicted_home_margin",
        "training_games": "baseline_training_games",
        "active_feature_count": "baseline_active_feature_count",
    }).merge(
        passing_pred.rename(columns={
            "projected_home": "passing_projected_home",
            "projected_away": "passing_projected_away",
            "projected_total": "passing_projected_total",
            "predicted_home_margin": "passing_predicted_home_margin",
            "training_games": "passing_training_games",
            "active_feature_count": "passing_active_feature_count",
        }).drop(columns=["gameday", "season", "week", "away_team", "home_team"]),
        on="game_id", how="inner", validate="one_to_one",
    )
    result = result.merge(
        future[["game_id", "spread_line", "total_line"]].drop_duplicates("game_id"),
        on="game_id", how="left", validate="one_to_one",
    )
    result["baseline_ats_edge"] = result["baseline_predicted_home_margin"] - result["spread_line"]
    result["passing_ats_edge"] = result["passing_predicted_home_margin"] - result["spread_line"]
    result["baseline_total_edge"] = result["baseline_projected_total"] - result["total_line"]
    result["passing_total_edge"] = result["passing_projected_total"] - result["total_line"]
    result["captured_at_utc"] = captured.isoformat().replace("+00:00", "Z")
    result["baseline_model_version"] = MODEL_VERSION
    result["candidate_name"] = CANDIDATE_NAME
    result["candidate_alpha"] = ALPHA
    result["status"] = "RESEARCH_ONLY_SHADOW_NOT_OFFICIAL"
    result["line_source"] = "nflverse schedule feed; not verified sportsbook quote"
    result["note"] = (
        "Research-only side-by-side projection. Candidate adds passing EPA, success, "
        "volume and matchup features to the frozen baseline feature set. Schedule lines "
        "are not verified Bovada/DraftKings quotes. No production or official record changes."
    )
    columns = [
        "captured_at_utc", "game_id", "season", "week", "gameday", "away_team", "home_team",
        "spread_line", "total_line",
        "baseline_projected_home", "baseline_projected_away", "baseline_predicted_home_margin",
        "baseline_projected_total", "baseline_ats_edge", "baseline_total_edge",
        "passing_projected_home", "passing_projected_away", "passing_predicted_home_margin",
        "passing_projected_total", "passing_ats_edge", "passing_total_edge",
        "baseline_training_games", "passing_training_games",
        "baseline_active_feature_count", "passing_active_feature_count",
        "baseline_model_version", "candidate_name", "candidate_alpha", "status", "line_source", "note",
    ]
    result = result[columns].sort_values(["gameday", "away_team", "home_team"])
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    path = OUT / f"passing_shadow_projection_{stamp}.csv"
    result.to_csv(path, index=False)
    print(f"Saved {len(result)} paired shadow projections to {path}")
    print(f"Completed training games: {len(completed)}")
    print(f"Baseline features: {len(variants['baseline_frozen_features'])}; passing candidate features: {len(variants[CANDIDATE_NAME])}")
    print(result[["away_team", "home_team", "baseline_predicted_home_margin", "passing_predicted_home_margin", "baseline_projected_total", "passing_projected_total"]].to_string(index=False))


if __name__ == "__main__":
    main()
