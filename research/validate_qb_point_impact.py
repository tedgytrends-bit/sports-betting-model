#!/usr/bin/env python3
"""Empirical validation of research-only QB absence point-impact estimates.

Tests whether pregame EPA-based QB1 absence estimates relate to actual team
scoring residuals. Uses baseline predictions (not injury-model predictions),
same-team listed replacements with prior history, and strict chronological
holdout summaries. Research only; never changes production projections.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "player_injury_backtests"
MIN_REPLACEMENT_GAMES = 3
MIN_REPLACEMENT_PRIOR_OPPORTUNITIES = 80.0
BOOTSTRAPS = 2000
RNG_SEED = 20261101


def latest(pattern: str) -> Path:
    files = sorted(DATA.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found for {pattern}")
    return files[-1]


def correlation_summary(frame: pd.DataFrame) -> dict:
    clean = frame.dropna(subset=["impact", "score_residual"]).copy()
    if len(clean) < 5:
        return {"n": int(len(clean)), "pearson_r": None, "spearman_r": None,
                "ols_slope_points_per_impact_point": None}
    pearson = float(clean["impact"].corr(clean["score_residual"], method="pearson"))
    spearman = float(clean["impact"].corr(clean["score_residual"], method="spearman"))
    slope = float(np.polyfit(clean["impact"], clean["score_residual"], 1)[0])
    return {"n": int(len(clean)), "pearson_r": pearson,
            "spearman_r": spearman,
            "ols_slope_points_per_impact_point": slope}


def bootstrap_pearson(frame: pd.DataFrame) -> dict:
    clean = frame.dropna(subset=["impact", "score_residual"])
    if len(clean) < 8:
        return {"lower_95": None, "upper_95": None, "valid_draws": 0}
    x = clean["impact"].to_numpy(float)
    y = clean["score_residual"].to_numpy(float)
    rng = np.random.default_rng(RNG_SEED)
    vals = []
    for _ in range(BOOTSTRAPS):
        ix = rng.integers(0, len(x), len(x))
        if np.std(x[ix]) > 1e-12 and np.std(y[ix]) > 1e-12:
            vals.append(float(np.corrcoef(x[ix], y[ix])[0, 1]))
    if not vals:
        return {"lower_95": None, "upper_95": None, "valid_draws": 0}
    return {"lower_95": float(np.quantile(vals, .025)),
            "upper_95": float(np.quantile(vals, .975)),
            "valid_draws": len(vals)}


def main() -> None:
    impact_path = latest("qb_point_impact_audit_*.csv")
    paired_path = latest("player_injury_paired_predictions_*.csv")
    impacts = pd.read_csv(impact_path, dtype={"injured_qb_id": "string",
                                               "replacement_qb_id": "string"})
    paired = pd.read_csv(paired_path)

    required_i = {"game_id", "season", "week", "team", "report_status",
                  "depth_chart_rank", "replacement_qb_id", "replacement_prior_games",
                  "replacement_history_same_team", "conditional_qb_absence_point_impact"}
    required_p = {"game_id", "season", "home_team", "away_team", "home_score",
                  "away_score", "pred_home_score_baseline", "pred_away_score_baseline"}
    if required_i - set(impacts.columns):
        raise ValueError(f"Impact data missing {sorted(required_i - set(impacts.columns))}")
    if required_p - set(paired.columns):
        raise ValueError(f"Paired predictions missing {sorted(required_p - set(paired.columns))}")

    impacts["season"] = pd.to_numeric(impacts["season"], errors="coerce")
    impacts["week"] = pd.to_numeric(impacts["week"], errors="coerce")
    impacts["depth_chart_rank"] = pd.to_numeric(impacts["depth_chart_rank"], errors="coerce")
    impacts["replacement_prior_games"] = pd.to_numeric(impacts["replacement_prior_games"], errors="coerce")
    impacts["impact"] = pd.to_numeric(impacts["conditional_qb_absence_point_impact"], errors="coerce")
    impacts["replacement_prior_opportunities"] = pd.to_numeric(
        impacts.get("replacement_prior_opportunities", pd.Series(np.nan, index=impacts.index)),
        errors="coerce")

    # The point-impact output currently stores prior games and rate reliability,
    # not prior opportunity totals. Use >=3 historical games and same-team flag
    # as the defensible minimum, then expose reliability in the output.
    impacts["same_team"] = impacts["replacement_history_same_team"].astype(str).str.lower().eq("true")
    exposed = impacts[
        impacts["report_status"].astype(str).str.upper().eq("OUT")
        & impacts["depth_chart_rank"].eq(1)
        & impacts["same_team"]
        & impacts["replacement_qb_id"].notna()
        & impacts["replacement_prior_games"].ge(MIN_REPLACEMENT_GAMES)
        & impacts["impact"].notna()
    ].copy()

    home = paired[["game_id", "season", "home_team", "home_score",
                   "pred_home_score_baseline"]].rename(columns={
        "home_team": "team", "home_score": "actual_score",
        "pred_home_score_baseline": "predicted_score"})
    away = paired[["game_id", "season", "away_team", "away_score",
                   "pred_away_score_baseline"]].rename(columns={
        "away_team": "team", "away_score": "actual_score",
        "pred_away_score_baseline": "predicted_score"})
    team_games = pd.concat([home, away], ignore_index=True)
    team_games["score_residual"] = team_games["actual_score"] - team_games["predicted_score"]

    exposed = exposed.merge(team_games, on=["game_id", "season", "team"],
                            how="inner", validate="one_to_one")
    exposed["impact_abs"] = exposed["impact"].abs()

    # Control observations are all other team-games in the paired test set.
    exposed_keys = set(zip(exposed["game_id"], exposed["team"]))
    team_games["is_exposed_qb1_out"] = [
        (g, t) in exposed_keys for g, t in zip(team_games["game_id"], team_games["team"])
    ]
    controls = team_games[~team_games["is_exposed_qb1_out"]].copy()

    # Chronological split: 2021-23 is exploratory; 2024-26 is untouched holdout.
    development = exposed[exposed["season"].le(2023)]
    holdout = exposed[exposed["season"].ge(2024)]

    summaries = {
        "all_eligible_qb1_out_cases": correlation_summary(exposed),
        "development_2021_2023": correlation_summary(development),
        "holdout_2024_2026": correlation_summary(holdout),
    }
    summaries["holdout_2024_2026"]["pearson_bootstrap_95_ci"] = bootstrap_pearson(holdout)

    def residual_stats(frame: pd.DataFrame) -> dict:
        x = frame["score_residual"].dropna()
        return {"n": int(len(x)), "mean_actual_minus_baseline_points": float(x.mean()) if len(x) else None,
                "median_actual_minus_baseline_points": float(x.median()) if len(x) else None,
                "mae_of_baseline_team_score": float(frame.loc[x.index, "score_residual"].abs().mean()) if len(x) else None}

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RESEARCH_ONLY_EMPIRICAL_VALIDATION_NOT_PRODUCTION",
        "impact_source": impact_path.name,
        "paired_prediction_source": paired_path.name,
        "filters": {
            "injury_status": "OUT",
            "injured_qb_depth_rank": 1,
            "replacement_must_have_same_team_prior_history": True,
            "minimum_replacement_prior_games": MIN_REPLACEMENT_GAMES,
            "minimum_prior_opportunities": "Not available in current point-impact output; prior-game threshold used instead."
        },
        "eligible_cases": int(len(exposed)),
        "unique_games": int(exposed["game_id"].nunique()),
        "control_team_games": int(len(controls)),
        "correlation_results": summaries,
        "score_residuals": {
            "eligible_qb1_out": residual_stats(exposed),
            "control_team_games": residual_stats(controls),
        },
        "impact_distribution": {
            "median": float(exposed["impact"].median()) if len(exposed) else None,
            "p25": float(exposed["impact"].quantile(.25)) if len(exposed) else None,
            "p75": float(exposed["impact"].quantile(.75)) if len(exposed) else None,
        },
        "interpretation": {
            "expected_relationship": "If the estimated absence impact is meaningful, larger positive impact should generally associate with more negative actual-minus-baseline team score residuals.",
            "limitations": [
                "The historical baseline prediction is not guaranteed to be fully injury-blind; inspect model feature construction before interpreting causality.",
                "Depth-chart QB2 is not verified as the actual starter or active replacement.",
                "OUT report status and historical depth chart may not prove the player missed the game.",
                "Small eligible samples and nonrandom QB absences limit statistical power.",
                "Controls are descriptive and not matched or randomized.",
                "Correlation is association, not causal calibration; no point adjustment is approved."
            ]
        }
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = DATA / f"qb_point_impact_validation_{stamp}.csv"
    json_path = DATA / f"qb_point_impact_validation_{stamp}.json"
    DATA.mkdir(parents=True, exist_ok=True)
    exposed.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved {csv_path}")
    print(f"Saved {json_path}")


if __name__ == "__main__":
    main()
