"""Research-only historical stability test for fixed Injury-model ATS thresholds.

The thresholds (>=2, >=3, >=4 absolute ATS edge) are frozen from the 2026
Weeks 1-8 exploratory calibration and are evaluated without re-tuning across
all available chronological historical predictions. Production files and
official prospective records are untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from injury_model import add_injury_features, load_injury_reports
from research.efficiency_feature_experiments import _fit_weekly
from research.four_model_comparison import _feature_columns

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
THRESHOLDS = (2.0, 3.0, 4.0)
ALPHA = 10.0
BREAK_EVEN = 110.0 / 210.0
OUT = ROOT / "data" / "four_model_2026_weeks01_08" / "threshold_stability"


def summarize(frame: pd.DataFrame) -> dict:
    graded = frame[frame["actual_ats_margin"] != 0].copy()
    wins = int(((graded["ats_edge"] * graded["actual_ats_margin"]) > 0).sum())
    losses = int(len(graded) - wins)
    pushes = int((frame["actual_ats_margin"] == 0).sum())
    risked = wins + losses + pushes
    profit = wins * (100.0 / 110.0) - losses
    p = float(binomtest(wins, wins + losses, BREAK_EVEN, alternative="greater").pvalue) if wins + losses else None
    return {
        "games": int(len(frame)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "graded_ex_pushes": int(wins + losses),
        "accuracy_pct_ex_pushes": round(100.0 * wins / (wins + losses), 3) if wins + losses else None,
        "profit_units_at_minus110": round(profit, 4),
        "roi_pct_at_minus110": round(100.0 * profit / risked, 3) if risked else None,
        "one_sided_p_vs_minus110_break_even": round(p, 6) if p is not None else None,
        "mean_abs_edge": round(float(frame["ats_edge"].abs().mean()), 3) if len(frame) else None,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
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
    # _feature_columns requires a nonempty passing block, but we only need its injury variant.
    # Supply one harmless baseline numeric column as a placeholder passing list.
    placeholder = [c for c in baseline.columns if c not in {"game_id", "gameday", "season", "week", "home_team", "away_team", "home_score", "away_score", "spread_line", "total_line"}
                   and pd.api.types.is_numeric_dtype(baseline[c])]
    variants = _feature_columns(injury_frame, list(baseline.columns), placeholder[:1], injury_cols)
    features = variants["injury_only_added"]

    data = injury_frame.merge(
        schedule[["game_id", "spread_line", "total_line"]],
        on="game_id", how="left", validate="one_to_one"
    )
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")

    pred = _fit_weekly(data, features, alpha=ALPHA)
    if pred.empty:
        raise RuntimeError("No chronological Injury predictions generated.")
    pred = pred.copy()
    pred["season"] = pd.to_numeric(pred["season"], errors="coerce")
    pred["week"] = pd.to_numeric(pred["week"], errors="coerce")
    pred["actual_home_margin"] = pred["home_score"] - pred["away_score"]
    pred["ats_edge"] = (pred["pred_home"] - pred["pred_away"]) - pred["spread_line"]
    pred["actual_ats_margin"] = pred["actual_home_margin"] - pred["spread_line"]
    pred = pred.dropna(subset=["season", "ats_edge", "actual_ats_margin"]).copy()

    rows = []
    season_results = {}
    for season in sorted(int(x) for x in pred["season"].dropna().unique()):
        sf = pred[pred["season"].eq(season)].copy()
        season_results[str(season)] = {
            "prediction_games": int(len(sf)),
            "week_min": int(sf["week"].min()) if len(sf) else None,
            "week_max": int(sf["week"].max()) if len(sf) else None,
            "thresholds": {},
        }
        for threshold in THRESHOLDS:
            subset = sf[sf["ats_edge"].abs() >= threshold].copy()
            summary = summarize(subset)
            season_results[str(season)]["thresholds"][f">={int(threshold)}"] = summary
            rows.append({"season": season, "threshold": threshold, **summary})

    historical = pred[pred["season"] <= 2025].copy()
    historical_results = {}
    for threshold in THRESHOLDS:
        subset = historical[historical["ats_edge"].abs() >= threshold].copy()
        historical_results[f">={int(threshold)}"] = summarize(subset)

    # Stability diagnostics: number of pre-2026 seasons above break-even and profitable.
    stability = {}
    for threshold in THRESHOLDS:
        key = f">={int(threshold)}"
        eligible = []
        for season, payload in season_results.items():
            if int(season) > 2025:
                continue
            s = payload["thresholds"][key]
            if s["graded_ex_pushes"]:
                eligible.append((season, s))
        stability[key] = {
            "seasons_with_games": len(eligible),
            "seasons_above_minus110_break_even": sum((s["accuracy_pct_ex_pushes"] or 0) > 100 * BREAK_EVEN for _, s in eligible),
            "profitable_seasons": sum((s["profit_units_at_minus110"] or 0) > 0 for _, s in eligible),
            "season_details": [
                {
                    "season": int(season),
                    "graded_games": s["graded_ex_pushes"],
                    "accuracy_pct_ex_pushes": s["accuracy_pct_ex_pushes"],
                    "roi_pct_at_minus110": s["roi_pct_at_minus110"],
                }
                for season, s in eligible
            ],
        }

    report = {
        "status": "RESEARCH_ONLY_FIXED_THRESHOLD_STABILITY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "question": "Do the exact Injury ATS thresholds identified in 2026 Weeks 1-8 remain useful across prior chronological seasons?",
        "fixed_thresholds_points": list(THRESHOLDS),
        "method": {
            "model": "injury_only_added",
            "ridge_alpha": ALPHA,
            "chronology": "Same weekly chronological fitting procedure; training games strictly precede each test fold.",
            "market_lines": "nflverse schedule spread_line for historical seasons; sportsbook execution not verified.",
            "threshold_selection": "Thresholds >=2, >=3, >=4 were frozen before this historical stability evaluation; no threshold re-tuning was performed.",
            "roi": "Flat 1-unit risk at -110; pushes return stake.",
        },
        "available_prediction_coverage": {
            "first_season": int(pred["season"].min()),
            "last_season": int(pred["season"].max()),
            "games": int(len(pred)),
        },
        "season_results": season_results,
        "historical_2025_and_earlier_combined": historical_results,
        "stability": stability,
        "cautions": [
            "The earliest season can be partial because the chronological model requires a minimum training history before predictions begin.",
            "Historical seasons have informed prior research and are not a pristine untouched holdout.",
            "nflverse schedule lines are not verified executable Bovada prices.",
            "The 2026 Weeks 1-8 threshold results remain the prospective-ish comparison sample and are not overwritten by this test.",
            "No production model or official prospective record is changed.",
        ],
    }

    pd.DataFrame(rows).to_csv(OUT / "injury_ats_threshold_stability_by_season.csv", index=False)
    (OUT / "injury_ats_threshold_stability_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
