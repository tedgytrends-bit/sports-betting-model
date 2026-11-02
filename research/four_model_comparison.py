"""Research-only four-way comparison: baseline, injury, efficiency, combined.

All variants use identical chronological weekly folds, Ridge alpha, minimum
training history, game IDs, market lines, and grading. No production files or
official prospective records are written.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from injury_model import add_injury_features, load_injury_reports
from research.efficiency_feature_experiments import (
    _fit_weekly,
    _team_split_history,
    _pregame_split_features,
    _roi_summary,
)

OUT = ROOT / "data" / "four_model_comparison"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
MIN_TRAIN_GAMES = 500
ALPHA = 10.0


def _feature_columns(frame: pd.DataFrame, baseline_columns: list[str],
                     passing_columns: list[str], injury_columns: list[str]) -> dict[str, list[str]]:
    excluded = {
        "game_id", "gameday", "season", "week", "home_team", "away_team",
        "home_score", "away_score", "spread_line", "total_line",
    }
    numeric = lambda cols: [
        c for c in cols if c in frame.columns and c not in excluded
        and pd.api.types.is_numeric_dtype(frame[c])
    ]
    base = numeric(baseline_columns)
    passing = numeric(passing_columns)
    injuries = numeric(injury_columns)
    if not base:
        raise RuntimeError("Baseline feature set is empty.")
    if not passing:
        raise RuntimeError("Passing/rushing feature set is empty.")
    if not injuries:
        raise RuntimeError("Injury feature set is empty.")
    return {
        "baseline_only": list(dict.fromkeys(base)),
        "injury_only_added": list(dict.fromkeys(base + injuries)),
        "efficiency_only_added": list(dict.fromkeys(base + passing)),
        "combined_efficiency_plus_injury": list(dict.fromkeys(base + passing + injuries)),
    }


def _metrics(frame: pd.DataFrame, variant: str) -> dict:
    ats = frame.dropna(subset=["ats_edge", "actual_ats_margin"]).copy()
    totals = frame.dropna(subset=["total_edge", "actual_total_margin"]).copy()

    def accuracy(data: pd.DataFrame, edge: str, actual: str) -> dict:
        graded = data[data[actual] != 0]
        wins = int(((graded[edge] * graded[actual]) > 0).sum())
        losses = int(len(graded) - wins)
        return {
            "graded_games": int(len(graded)),
            "wins": wins,
            "losses": losses,
            "pushes": int((data[actual] == 0).sum()),
            "accuracy_pct": round(100 * wins / len(graded), 3) if len(graded) else None,
        }

    return {
        "variant": variant,
        "games": int(len(frame)),
        "ats_margin_mae": round(float((ats["pred_home_margin"] - ats["actual_home_margin"]).abs().mean()), 4),
        "total_mae": round(float((totals["pred_total"] - totals["actual_total"]).abs().mean()), 4),
        "ats": accuracy(ats, "ats_edge", "actual_ats_margin"),
        "totals": accuracy(totals, "total_edge", "actual_total_margin"),
        "ats_fixed_thresholds": _roi_summary(ats, "ats_edge", "actual_ats_margin", variant),
        "totals_fixed_thresholds": _roi_summary(totals, "total_edge", "actual_total_margin", variant),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading schedule, play-by-play, and historical injury reports...")
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)

    print("Building frozen baseline, strictly pregame efficiency, and as-of injury features...")
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
    data = baseline.merge(
        split_features, on="game_id", how="left", validate="one_to_one"
    ).merge(
        injury_frame[["game_id"] + injury_cols], on="game_id",
        how="left", validate="one_to_one"
    )
    data = data.merge(
        schedule[["game_id", "spread_line", "total_line"]],
        on="game_id", how="left", validate="one_to_one",
    )
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    variants = _feature_columns(data, list(baseline.columns), passing_cols, injury_cols)

    prediction_frames = []
    for name, features in variants.items():
        print(f"Fitting {name}: {len(features)} features...")
        pred = _fit_weekly(data, features, alpha=ALPHA)
        if pred.empty:
            raise RuntimeError(f"No chronological predictions generated for {name}.")
        pred = pred.copy()
        pred["variant"] = name
        pred["actual_total"] = pred["home_score"] + pred["away_score"]
        pred["pred_total"] = pred["pred_home"] + pred["pred_away"]
        pred["actual_home_margin"] = pred["home_score"] - pred["away_score"]
        pred["pred_home_margin"] = pred["pred_home"] - pred["pred_away"]
        pred["ats_edge"] = pred["pred_home_margin"] - pred["spread_line"]
        pred["actual_ats_margin"] = pred["actual_home_margin"] - pred["spread_line"]
        pred["total_edge"] = pred["pred_total"] - pred["total_line"]
        pred["actual_total_margin"] = pred["actual_total"] - pred["total_line"]
        prediction_frames.append(pred)

    all_preds = pd.concat(prediction_frames, ignore_index=True)
    common = set.intersection(*[
        set(group["game_id"]) for _, group in all_preds.groupby("variant")
    ])
    if not common:
        raise RuntimeError("No common games were predicted by all four variants.")
    all_preds = all_preds[all_preds["game_id"].isin(common)].copy()
    summaries = [
        _metrics(group, name)
        for name, group in all_preds.groupby("variant", sort=False)
    ]

    # Coverage is reported separately: missing reports are not interpreted as zero injuries.
    coverage = {}
    for side in ("home", "away"):
        col = f"{side}_injury_report_available"
        if col in data.columns:
            coverage[side] = {
                "games_with_report": int(pd.to_numeric(data[col], errors="coerce").eq(1).sum()),
                "games_without_report": int(pd.to_numeric(data[col], errors="coerce").eq(0).sum()),
                "games_unknown": int(pd.to_numeric(data[col], errors="coerce").isna().sum()),
            }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "variants": list(variants),
            "common_games": int(len(common)),
            "minimum_training_games": MIN_TRAIN_GAMES,
            "ridge_alpha": ALPHA,
            "folds": "chronological weekly; training games strictly before each test week's first game",
            "injury_timing": "injury_model.add_injury_features filters timestamped reports before kickoff; saved snapshots are used only when captured before kickoff",
            "market_lines": "nflverse schedule spread_line and total_line; not verified executable sportsbook quotes",
            "roi_assumption": "flat one-unit stakes at -110; simulation only",
        },
        "feature_counts": {name: len(cols) for name, cols in variants.items()},
        "injury_report_coverage": coverage,
        "results": summaries,
        "cautions": [
            "Historical injury-feed completeness and publication-time coverage are imperfect.",
            "The historical seasons have already informed prior research and are not a pristine holdout.",
            "Directional accuracy and schedule-line ROI do not establish profitability at an executable sportsbook.",
            "This experiment does not alter production projections or official prospective records.",
        ],
    }
    report_path = OUT / f"four_model_report_{stamp}.json"
    predictions_path = OUT / f"four_model_predictions_{stamp}.csv"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    all_preds.to_csv(predictions_path, index=False)
    print(json.dumps({
        "report": str(report_path),
        "predictions": str(predictions_path),
        "common_games": len(common),
        "results": summaries,
    }, indent=2))


if __name__ == "__main__":
    main()
