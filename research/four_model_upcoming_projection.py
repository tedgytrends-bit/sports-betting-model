"""Research-only four-model projection for a specified upcoming NFL game.

Fits each variant only on completed games strictly before the target game's date.
Does not modify production projections, Bovada archives, or prospective records.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from injury_model import add_injury_features, injury_coverage_diagnostics, load_injury_reports
from research.efficiency_feature_experiments import _team_split_history, _pregame_split_features
from research.four_model_comparison import _feature_columns

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
MIN_TRAIN_GAMES = 500
ALPHA = 10.0
TARGET_SEASON = 2026
TARGET_WEEK = 8
TARGET_AWAY = "CHI"
TARGET_HOME = "SEA"
OUT = ROOT / "data" / "four_model_upcoming"


def predict_variant(data: pd.DataFrame, target: pd.Series, features: list[str]) -> dict:
    target_date = pd.Timestamp(target["gameday"])
    train = data[
        data["gameday"].notna()
        & (data["gameday"] < target_date)
        & data["home_score"].notna()
        & data["away_score"].notna()
    ].copy()
    if len(train) < MIN_TRAIN_GAMES:
        raise RuntimeError(f"Only {len(train)} pregame training games; need {MIN_TRAIN_GAMES}.")
    active = [c for c in features if c in train.columns and train[c].notna().any()]
    if not active:
        raise RuntimeError("No active training features.")
    medians = train[active].median(numeric_only=True).fillna(0)
    x_train = train[active].fillna(medians).fillna(0)
    x_target = target[active].to_frame().T.fillna(medians).fillna(0)
    scores = {}
    for source, output in (("home_score", "projected_home"), ("away_score", "projected_away")):
        model = Ridge(alpha=ALPHA)
        model.fit(x_train, train[source])
        scores[output] = float(model.predict(x_target)[0])
    scores["projected_total"] = scores["projected_home"] + scores["projected_away"]
    scores["projected_home_margin"] = scores["projected_home"] - scores["projected_away"]
    scores["fair_home_spread"] = -scores["projected_home_margin"]
    scores["training_games"] = int(len(train))
    scores["active_features"] = int(len(active))
    return scores


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading schedule, PBP, and injury feed...")
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)

    target_rows = schedule[
        pd.to_numeric(schedule["season"], errors="coerce").eq(TARGET_SEASON)
        & pd.to_numeric(schedule["week"], errors="coerce").eq(TARGET_WEEK)
        & schedule["away_team"].astype(str).str.upper().eq(TARGET_AWAY)
        & schedule["home_team"].astype(str).str.upper().eq(TARGET_HOME)
    ].copy()
    if len(target_rows) != 1:
        raise RuntimeError(f"Expected one target game {TARGET_AWAY}@{TARGET_HOME}; found {len(target_rows)}.")
    target_game_id = target_rows.iloc[0]["game_id"]

    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    injury_frame = add_injury_features(baseline, schedule, reports)
    split_history = _team_split_history(pbp, schedule)
    split_features = _pregame_split_features(schedule, split_history)

    injury_cols = [
        c for c in injury_frame.columns
        if c.startswith(("home_injury_", "away_injury_", "home_inj_", "away_inj_",
                         "home_qb_", "away_qb_", "home_ol_", "away_ol_",
                         "home_skill_", "away_skill_", "home_defense_", "away_defense_"))
    ]
    passing_cols = [c for c in split_features.columns if c != "game_id"]
    data = baseline.merge(split_features, on="game_id", how="left", validate="one_to_one")
    data = data.merge(injury_frame[["game_id"] + injury_cols], on="game_id",
                      how="left", validate="one_to_one")
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    variants = _feature_columns(data, list(baseline.columns), passing_cols, injury_cols)
    target = data[data["game_id"].eq(target_game_id)]
    if len(target) != 1:
        raise RuntimeError("Target feature row missing or duplicated.")
    target = target.iloc[0]

    results = {}
    for name, features in variants.items():
        print(f"Projecting {name} ({len(features)} candidate features)...")
        results[name] = predict_variant(data, target, features)

    diagnostic = injury_coverage_diagnostics(target_rows, reports).iloc[0].to_dict()
    injury_inputs = {
        col: (None if pd.isna(target[col]) else float(target[col]))
        for col in injury_cols if col in target.index and pd.api.types.is_numeric_dtype(data[col])
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": {
            "game_id": str(target_game_id), "season": TARGET_SEASON, "week": TARGET_WEEK,
            "away_team": TARGET_AWAY, "home_team": TARGET_HOME,
            "gameday": str(pd.Timestamp(target["gameday"]).date()),
        },
        "training_policy": "Completed games strictly before the target game's calendar date; same-day games excluded.",
        "estimator": "Ridge alpha=10; training-window medians; same four controlled feature sets as historical comparison.",
        "models": results,
        "injury_inputs": injury_inputs,
        "injury_coverage_diagnostic": diagnostic,
        "cautions": [
            "Research-only single-game forecasts; not a validated prospective four-model board.",
            "The 2025-2026 undated weekly injury rows rely on the user's official-report deadline assumption, not row-level timestamps.",
            "The four variants are historical research candidates; injury features have not demonstrated incremental predictive value.",
            "Market prices are not embedded in this forecast; compare against the user's current Bovada line.",
        ],
    }
    path = OUT / f"four_model_upcoming_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
