
#!/usr/bin/env python3
"""Chronological, point-in-time comparison of baseline and player-injury models.

Research only. Does not alter official projections or prospective grading.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import (
    load_schedule_data,
    load_pbp,
    build_efficiency_model_dataset,
    chronological_backtest,
)
from injury_model import load_injury_reports
from player_injury_model import build_player_injury_features

OUTPUT_DIR = ROOT / "data" / "player_injury_backtests"


def _rmse(actual, predicted):
    return float(np.sqrt(mean_squared_error(actual, predicted)))


def _prediction_frame(result):
    frame = result["predictions"].copy()
    required = {
        "game_id", "gameday", "home_score", "away_score",
        "pred_home_score", "pred_away_score",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"Chronological backtest output missing columns: {sorted(missing)}"
        )
    if frame["game_id"].duplicated().any():
        raise ValueError("Duplicate game IDs found in predictions.")
    return frame


def _evaluate(predictions, schedule):
    scored = predictions.copy()
    scored["pred_total"] = scored["pred_home_score"] + scored["pred_away_score"]
    scored["actual_total"] = scored["home_score"] + scored["away_score"]
    scored["pred_home_margin"] = (
        scored["pred_home_score"] - scored["pred_away_score"]
    )
    scored["actual_home_margin"] = (
        scored["home_score"] - scored["away_score"]
    )

    metrics = {
        "games": int(len(scored)),
        "home_score_mae": float(
            mean_absolute_error(scored["home_score"], scored["pred_home_score"])
        ),
        "away_score_mae": float(
            mean_absolute_error(scored["away_score"], scored["pred_away_score"])
        ),
        "total_mae": float(
            mean_absolute_error(scored["actual_total"], scored["pred_total"])
        ),
        "total_rmse": _rmse(scored["actual_total"], scored["pred_total"]),
        "home_margin_mae": float(
            mean_absolute_error(
                scored["actual_home_margin"], scored["pred_home_margin"]
            )
        ),
        "home_margin_rmse": _rmse(
            scored["actual_home_margin"], scored["pred_home_margin"]
        ),
    }

    market_cols = [
        c for c in ("game_id", "spread_line", "total_line")
        if c in schedule.columns
    ]
    if len(market_cols) > 1:
        lines = schedule[market_cols].drop_duplicates("game_id")
        scored = scored.merge(
            lines, on="game_id", how="left", validate="one_to_one"
        )

        if scored["total_line"].notna().any():
            valid = scored.dropna(subset=["total_line"])
            metrics["games_with_total_line"] = int(len(valid))
            metrics["total_market_mae"] = float(
                mean_absolute_error(valid["actual_total"], valid["total_line"])
            )
            metrics["total_model_vs_market_mae_delta"] = (
                metrics["total_mae"] - metrics["total_market_mae"]
            )

        if scored["spread_line"].notna().any():
            valid = scored.dropna(subset=["spread_line"])
            metrics["games_with_spread_line"] = int(len(valid))
            market_margin = -valid["spread_line"]

            metrics["market_home_margin_mae"] = float(
                mean_absolute_error(
                    valid["actual_home_margin"], market_margin
                )
            )
            metrics["model_home_margin_mae_on_market_games"] = float(
                mean_absolute_error(
                    valid["actual_home_margin"], valid["pred_home_margin"]
                )
            )
            metrics["home_margin_mae_vs_market_delta"] = (
                metrics["model_home_margin_mae_on_market_games"]
                - metrics["market_home_margin_mae"]
            )

            model_edge = valid["pred_home_margin"] + valid["spread_line"]
            actual_ats_margin = (
                valid["actual_home_margin"] + valid["spread_line"]
            )
            non_push = actual_ats_margin.ne(0)

            metrics["ats_directional_accuracy"] = (
                float(
                    (
                        np.sign(model_edge[non_push])
                        == np.sign(actual_ats_margin[non_push])
                    ).mean()
                )
                if non_push.any()
                else None
            )

    return metrics


def main():
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    seasons = (2021, 2022, 2023, 2024, 2025, 2026)

    print("Loading schedule, play-by-play, and historical injury data...")
    schedule = load_schedule_data()
    pbp = load_pbp(seasons)
    reports = load_injury_reports(seasons)

    print("Building baseline and player-injury datasets...")
    base = build_efficiency_model_dataset(
        schedule, pbp, lookback_games=10
    )
    injury_features, player_audit = build_player_injury_features(
        schedule, pbp, reports
    )
    shadow_data = base.merge(
        injury_features,
        on="game_id",
        how="left",
        validate="one_to_one",
    )

    print("Running chronological baseline backtest...")
    baseline_result = chronological_backtest(
        base, min_train_games=500
    )

    print("Running chronological injury-model backtest...")
    injury_result = chronological_backtest(
        shadow_data, min_train_games=500
    )

    baseline = _prediction_frame(baseline_result)
    injury = _prediction_frame(injury_result)

    baseline_ids = set(baseline["game_id"])
    injury_ids = set(injury["game_id"])

    if baseline_ids != injury_ids:
        raise RuntimeError(
            "Baseline and injury test sets differ: "
            f"baseline={len(baseline_ids)}, injury={len(injury_ids)}"
        )

    paired = baseline.merge(
        injury[["game_id", "pred_home_score", "pred_away_score"]],
        on="game_id",
        how="inner",
        suffixes=("_baseline", "_injury"),
        validate="one_to_one",
    )

    if paired.empty:
        raise RuntimeError(
            "Baseline and injury backtests produced no common test games."
        )

    # The baseline prediction frame already contains season.
    # Merge it from the schedule only if it is genuinely missing.
    if "season" not in paired.columns:
        season_data = schedule[["game_id", "season"]].drop_duplicates("game_id")
        paired = paired.merge(
            season_data,
            on="game_id",
            how="left",
            validate="one_to_one",
        )

    paired["season"] = pd.to_numeric(paired["season"], errors="coerce")

    if paired["season"].isna().any():
        raise RuntimeError(
            "Some paired predictions could not be matched to a season."
        )

    # Keep the actual scores already present in baseline.
    # Do NOT merge the actual scores a second time.
    paired["baseline_total"] = (
        paired["pred_home_score_baseline"]
        + paired["pred_away_score_baseline"]
    )
    paired["injury_total"] = (
        paired["pred_home_score_injury"]
        + paired["pred_away_score_injury"]
    )
    paired["baseline_home_margin"] = (
        paired["pred_home_score_baseline"]
        - paired["pred_away_score_baseline"]
    )
    paired["injury_home_margin"] = (
        paired["pred_home_score_injury"]
        - paired["pred_away_score_injury"]
    )

    paired["actual_total"] = paired["home_score"] + paired["away_score"]
    paired["actual_home_margin"] = (
        paired["home_score"] - paired["away_score"]
    )

    paired["baseline_total_abs_error"] = (
        paired["baseline_total"] - paired["actual_total"]
    ).abs()
    paired["injury_total_abs_error"] = (
        paired["injury_total"] - paired["actual_total"]
    ).abs()
    paired["baseline_margin_abs_error"] = (
        paired["baseline_home_margin"] - paired["actual_home_margin"]
    ).abs()
    paired["injury_margin_abs_error"] = (
        paired["injury_home_margin"] - paired["actual_home_margin"]
    ).abs()

    baseline_metrics = _evaluate(baseline, schedule)
    injury_metrics = _evaluate(injury, schedule)

    coverage = {}
    for side in ("home", "away"):
        col = f"{side}_player_injury_report_available"
        if col in injury_features.columns:
            coverage[f"{side}_team_game_report_rows"] = int(
                pd.to_numeric(
                    injury_features[col], errors="coerce"
                ).fillna(0).sum()
            )

    coverage["games_with_any_player_detail"] = (
        int(player_audit["game_id"].nunique())
        if not player_audit.empty else 0
    )
    coverage["player_detail_rows"] = int(len(player_audit))
    coverage["player_rows_with_prior_usage_value"] = (
        int(
            player_audit["valuation_status"]
            .eq("valued_from_prior_pbp_usage").sum()
        )
        if not player_audit.empty else 0
    )
    coverage["player_rows_without_prior_usage"] = (
        int(
            player_audit["valuation_status"]
            .eq("no_prior_pbp_usage").sum()
        )
        if not player_audit.empty else 0
    )
    coverage["offensive_line_rows_not_individually_valued"] = (
        int(
            player_audit["valuation_status"]
            .eq(
                "OL_player_identity_retained_but_not_individually_valued"
            ).sum()
        )
        if not player_audit.empty else 0
    )

    report = {
        "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
        "model_version": "player-injury-shadow-0.1",
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "historical_seasons": list(seasons),
        "training_minimum_games": 500,
        "baseline": baseline_metrics,
        "player_injury": injury_metrics,
        "paired_comparison": {
            "common_test_games": int(len(paired)),
            "same_test_game_sets": True,
            "total_mae_delta_injury_minus_baseline": float(
                paired["injury_total_abs_error"].mean()
                - paired["baseline_total_abs_error"].mean()
            ),
            "home_margin_mae_delta_injury_minus_baseline": float(
                paired["injury_margin_abs_error"].mean()
                - paired["baseline_margin_abs_error"].mean()
            ),
        },
        "injury_coverage": coverage,
        "timing_caveat": (
            "Historical features use feed date_modified strictly before "
            "kickoff. This is a source-timestamp backtest, not proof that "
            "the information was publicly available at that exact time."
        ),
        "methodology": (
            "Same weekly chronological folds, same Ridge estimator and "
            "minimum training size. No random split. Injury features use "
            "prior-week player PBP usage and historical injury updates "
            "filtered before each game's kickoff."
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")

    paired_path = (
        OUTPUT_DIR / f"player_injury_paired_predictions_{stamp}.csv"
    )
    report_path = (
        OUTPUT_DIR / f"player_injury_backtest_report_{stamp}.json"
    )

    paired.to_csv(paired_path, index=False)
    report_path.write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print(json.dumps(report, indent=2))
    print(f"Saved paired predictions: {paired_path}")
    print(f"Saved backtest report: {report_path}")
    print("No official model, projection, or prospective record was changed.")


if __name__ == "__main__":
    main()
