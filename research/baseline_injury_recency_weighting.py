"""Research-only recency-weighting experiment for Baseline vs Injury ATS.

Tests whether exponential time-decay weighting improves chronological ATS performance
without discarding older observations. Decay schemes are frozen before evaluation:
- equal_weight: no recency weighting
- half_life_4_seasons: gentle decay
- half_life_2_seasons: moderate decay
- half_life_1_season: aggressive decay

Weights are normalized to mean 1 within every fold so decay does not implicitly alter
the effective Ridge penalty. The existing 500-game minimum training-history rule is
preserved. No production files or official prospective records are modified.
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
from injury_model import add_injury_features, load_injury_reports
from research.injury_recent_regime_training_window import (
    _apply_market_policy,
    _grade,
    _numeric_feature_columns,
    _paired_injury_delta,
    _record,
)

OUT = ROOT / "data" / "four_model_2026_weeks01_08" / "recency_weighting"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
EVAL_SEASONS = (2023, 2024, 2025, 2026)
ALPHA = 10.0
MIN_TRAIN_GAMES = 500
DAYS_PER_SEASON = 365.25
DECAYS = {
    "equal_weight": None,
    "half_life_4_seasons": 4.0,
    "half_life_2_seasons": 2.0,
    "half_life_1_season": 1.0,
}
EXCLUDED = {
    "game_id", "gameday", "season", "week", "home_team", "away_team",
    "home_score", "away_score", "spread_line", "total_line",
    "market_spread_line", "market_source",
}


def _weights_for_fold(train: pd.DataFrame, test_date: pd.Timestamp, half_life_seasons: float | None) -> np.ndarray:
    if half_life_seasons is None:
        return np.ones(len(train), dtype=float)
    age_days = (test_date - train["gameday"]).dt.total_seconds().to_numpy(dtype=float) / 86400.0
    age_days = np.maximum(age_days, 0.0)
    half_life_days = float(half_life_seasons) * DAYS_PER_SEASON
    weights = np.power(0.5, age_days / half_life_days)
    mean_w = float(np.mean(weights))
    if not np.isfinite(mean_w) or mean_w <= 0:
        raise RuntimeError("Invalid recency-weight mean.")
    return weights / mean_w


def _effective_sample_size(weights: np.ndarray) -> float:
    denom = float(np.sum(np.square(weights)))
    if denom <= 0:
        return 0.0
    return float(np.square(np.sum(weights)) / denom)


def _fit_weekly_weighted(
    data: pd.DataFrame,
    features: list[str],
    model_name: str,
    decay_name: str,
    half_life_seasons: float | None,
) -> pd.DataFrame:
    work = data.dropna(subset=["gameday", "home_score", "away_score"]).copy()
    work["gameday"] = pd.to_datetime(work["gameday"], errors="coerce")
    work = work.dropna(subset=["gameday"]).sort_values("gameday")
    work["calendar_test_week"] = work["gameday"].dt.to_period("W").astype(str)
    predictions: list[pd.DataFrame] = []

    for fold in work["calendar_test_week"].drop_duplicates():
        test = work[work["calendar_test_week"].eq(fold)].copy()
        if test.empty:
            continue
        test_date = test["gameday"].min()
        train = work[work["gameday"] < test_date].copy()
        if len(train) < MIN_TRAIN_GAMES:
            continue

        active = [c for c in features if c in train.columns and train[c].notna().any()]
        if not active:
            continue
        medians = train[active].median(numeric_only=True).fillna(0)
        x_train = train[active].fillna(medians).fillna(0)
        x_test = test[active].fillna(medians).fillna(0)
        weights = _weights_for_fold(train, test_date, half_life_seasons)

        for target, output in (("home_score", "pred_home"), ("away_score", "pred_away")):
            reg = Ridge(alpha=ALPHA)
            reg.fit(x_train, train[target], sample_weight=weights)
            test[output] = reg.predict(x_test)

        test["training_games"] = int(len(train))
        test["effective_training_games"] = round(_effective_sample_size(weights), 3)
        test["training_first_season"] = int(pd.to_numeric(train["season"], errors="coerce").min())
        test["training_last_season"] = int(pd.to_numeric(train["season"], errors="coerce").max())
        test["oldest_game_weight"] = round(float(np.min(weights)), 6)
        test["newest_game_weight"] = round(float(np.max(weights)), 6)
        test["model"] = model_name
        test["decay_scheme"] = decay_name
        test["half_life_seasons"] = half_life_seasons
        predictions.append(test)

    if not predictions:
        return pd.DataFrame()
    return pd.concat(predictions, ignore_index=True).drop_duplicates("game_id")


def _common_ids(preds: pd.DataFrame) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for season in EVAL_SEASONS:
        s = preds[pd.to_numeric(preds["season"], errors="coerce").eq(season)].copy()
        sets: list[set[str]] = []
        for decay_name in DECAYS:
            for model_name in ("baseline", "injury"):
                sets.append(set(s[(s["decay_scheme"] == decay_name) & (s["model"] == model_name)]["game_id"]))
        result[season] = set.intersection(*sets) if sets else set()
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading data and building baseline/injury features...")
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)
    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    injury_frame = add_injury_features(baseline, schedule, reports)

    injury_cols = [
        c for c in injury_frame.columns
        if c.startswith(("home_injury_", "away_injury_", "home_inj_", "away_inj_",
                         "home_qb_", "away_qb_", "home_ol_", "away_ol_",
                         "home_skill_", "away_skill_", "home_defense_", "away_defense_"))
    ]
    data = injury_frame.merge(
        schedule[["game_id", "spread_line", "total_line"]],
        on="game_id", how="left", validate="one_to_one",
    )
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    data = _apply_market_policy(data)

    baseline_features = _numeric_feature_columns(data, list(baseline.columns))
    injury_features = list(dict.fromkeys(baseline_features + _numeric_feature_columns(data, injury_cols)))
    if not baseline_features or len(injury_features) <= len(baseline_features):
        raise RuntimeError("Could not build distinct baseline and injury feature sets.")

    all_preds: list[pd.DataFrame] = []
    for decay_name, half_life in DECAYS.items():
        for model_name, features in (("baseline", baseline_features), ("injury", injury_features)):
            print(f"Fitting {model_name} with {decay_name} ({len(features)} features)...")
            pred = _fit_weekly_weighted(data, features, model_name, decay_name, half_life)
            if pred.empty:
                raise RuntimeError(f"No predictions for {model_name}/{decay_name}")
            all_preds.append(_grade(pred))

    preds = pd.concat(all_preds, ignore_index=True)
    preds = preds[pd.to_numeric(preds["season"], errors="coerce").isin(EVAL_SEASONS)].copy()
    preds = preds[(preds["season"] != 2026) | pd.to_numeric(preds["week"], errors="coerce").between(1, 8)].copy()

    common_ids_by_season = _common_ids(preds)
    common_all = set().union(*common_ids_by_season.values())
    eval_preds = preds[preds["game_id"].isin(common_all)].copy()

    season_report: dict[str, dict] = {}
    summary_rows: list[dict] = []
    for season in EVAL_SEASONS:
        ids = common_ids_by_season[season]
        season_slice = eval_preds[eval_preds["game_id"].isin(ids)].copy()
        season_report[str(season)] = {}
        for decay_name in DECAYS:
            season_report[str(season)][decay_name] = {}
            pair: dict[str, pd.DataFrame] = {}
            for model_name in ("baseline", "injury"):
                f = season_slice[(season_slice["decay_scheme"] == decay_name) & (season_slice["model"] == model_name)].copy()
                rec = _record(f)
                pair[model_name] = f
                season_report[str(season)][decay_name][model_name] = rec
                summary_rows.append({"season": season, "decay_scheme": decay_name, "model": model_name, **rec})
            season_report[str(season)][decay_name]["injury_incremental_vs_baseline"] = _paired_injury_delta(pair["baseline"], pair["injury"])

    regime_defs = {
        "2023_2024": (2023, 2024),
        "2025_only": (2025,),
        "2026_weeks_1_8": (2026,),
        "2025_2026_combined": (2025, 2026),
    }
    regime_report: dict[str, dict] = {}
    for regime_name, seasons in regime_defs.items():
        ids = set().union(*[common_ids_by_season[s] for s in seasons])
        regime_report[regime_name] = {}
        for decay_name in DECAYS:
            regime_report[regime_name][decay_name] = {}
            pair: dict[str, pd.DataFrame] = {}
            for model_name in ("baseline", "injury"):
                f = eval_preds[
                    eval_preds["game_id"].isin(ids)
                    & eval_preds["decay_scheme"].eq(decay_name)
                    & eval_preds["model"].eq(model_name)
                ].copy()
                regime_report[regime_name][decay_name][model_name] = _record(f)
                pair[model_name] = f
            regime_report[regime_name][decay_name]["injury_incremental_vs_baseline"] = _paired_injury_delta(pair["baseline"], pair["injury"])

    all_scope: dict[str, dict] = {}
    for decay_name in DECAYS:
        all_scope[decay_name] = {}
        pair: dict[str, pd.DataFrame] = {}
        for model_name in ("baseline", "injury"):
            f = eval_preds[(eval_preds["decay_scheme"] == decay_name) & (eval_preds["model"] == model_name)].copy()
            all_scope[decay_name][model_name] = _record(f)
            pair[model_name] = f
        all_scope[decay_name]["injury_incremental_vs_baseline"] = _paired_injury_delta(pair["baseline"], pair["injury"])

    fold_weight_summary: dict[str, dict] = {}
    for decay_name in DECAYS:
        f = eval_preds[(eval_preds["decay_scheme"] == decay_name) & (eval_preds["model"] == "baseline")].copy()
        fold_weight_summary[decay_name] = {
            "median_training_games": round(float(f["training_games"].median()), 3),
            "median_effective_training_games": round(float(f["effective_training_games"].median()), 3),
            "median_oldest_game_weight": round(float(f["oldest_game_weight"].median()), 6),
            "median_newest_game_weight": round(float(f["newest_game_weight"].median()), 6),
        }

    report = {
        "status": "RESEARCH_ONLY_RECENCY_WEIGHTING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "question": "Can recency weighting retain older information while improving chronological ATS performance for Baseline and/or Injury?",
        "method": {
            "models": ["baseline", "injury"],
            "ridge_alpha": ALPHA,
            "minimum_training_games": MIN_TRAIN_GAMES,
            "decay_schemes_frozen_before_results": {
                "equal_weight": "all training games weight 1",
                "half_life_4_seasons": "game weight halves every 4 seasons of age",
                "half_life_2_seasons": "game weight halves every 2 seasons of age",
                "half_life_1_season": "game weight halves every 1 season of age",
            },
            "weight_normalization": "weights normalized to mean 1 in each fold so Ridge alpha remains comparable",
            "market_lines": "nflverse schedule spread_line for historical seasons and 2026 Weeks 1-7; user-verified Bovada board for 2026 Week 8",
            "2026_scope": "Weeks 1-8 only",
            "common_game_policy": "Each season restricted to games predicted by both models under all four decay schemes.",
        },
        "feature_counts": {"baseline": len(baseline_features), "injury": len(injury_features)},
        "common_game_counts": {str(s): len(ids) for s, ids in common_ids_by_season.items()},
        "fold_weight_summary": fold_weight_summary,
        "season_results": season_report,
        "regime_results": regime_report,
        "all_2023_to_2026_scope": all_scope,
        "cautions": [
            "Decay schemes were frozen before results, but this remains retrospective research rather than a pristine untouched holdout.",
            "Multiple decay schemes are compared, so the best observed result should not be treated as a production winner without prospective confirmation.",
            "Recency weighting can capture roster, coaching, rules, and league-environment change; it is not specific to injury-data quality.",
            "Historical nflverse schedule lines are not verified executable sportsbook quotes.",
            "No production model or official prospective record is modified.",
        ],
    }

    (OUT / "baseline_injury_recency_weighting_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(summary_rows).to_csv(OUT / "baseline_injury_recency_weighting_by_season.csv", index=False)
    eval_preds[[
        "game_id", "season", "week", "gameday", "away_team", "home_team", "market_spread_line", "market_source",
        "home_score", "away_score", "model", "decay_scheme", "half_life_seasons", "training_games",
        "effective_training_games", "training_first_season", "training_last_season", "oldest_game_weight", "newest_game_weight",
        "pred_home", "pred_away", "pred_home_margin", "ats_edge", "actual_ats_margin", "ats_direction", "ats_outcome",
    ]].to_csv(OUT / "baseline_injury_recency_weighting_predictions.csv", index=False)

    print(json.dumps({
        "common_game_counts": report["common_game_counts"],
        "fold_weight_summary": report["fold_weight_summary"],
        "regime_results": report["regime_results"],
        "all_scope": report["all_2023_to_2026_scope"],
    }, indent=2))


if __name__ == "__main__":
    main()
