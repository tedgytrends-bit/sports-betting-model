"""Research-only recent-regime/training-window analysis for Baseline vs Injury ATS.

Tests whether newer training data improves out-of-sample ATS performance and whether
Injury's incremental value changes in the 2025-2026 higher-coverage regime.

Primary windows preserve the existing 500-game minimum training history:
- expanding_full_history
- rolling_4_seasons (test season plus prior 3 seasons)
- rolling_3_seasons (test season plus prior 2 seasons)

A 2-season window is intentionally excluded because it cannot provide 500 prior
training games for early/midseason folds such as 2026 Week 8.

No production files or official prospective records are modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from injury_model import add_injury_features, load_injury_reports

OUT = ROOT / "data" / "four_model_2026_weeks01_08" / "recent_regime_training_window"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
EVAL_SEASONS = (2023, 2024, 2025, 2026)
ALPHA = 10.0
MIN_TRAIN_GAMES = 500
WINDOWS = {
    "expanding_full_history": None,
    "rolling_4_seasons": 4,
    "rolling_3_seasons": 3,
}
EXCLUDED = {
    "game_id", "gameday", "season", "week", "home_team", "away_team",
    "home_score", "away_score", "spread_line", "total_line",
}


def _numeric_feature_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [
        c for c in columns
        if c in frame.columns and c not in EXCLUDED and pd.api.types.is_numeric_dtype(frame[c])
    ]


def _fit_weekly_window(
    data: pd.DataFrame,
    features: list[str],
    window_seasons: int | None,
    model_name: str,
    window_name: str,
) -> pd.DataFrame:
    work = data.dropna(subset=["gameday", "home_score", "away_score"]).copy()
    work["gameday"] = pd.to_datetime(work["gameday"], errors="coerce")
    work = work.dropna(subset=["gameday"]).sort_values("gameday")
    work["calendar_test_week"] = work["gameday"].dt.to_period("W").astype(str)
    predictions = []

    for fold in work["calendar_test_week"].drop_duplicates():
        test = work[work["calendar_test_week"].eq(fold)].copy()
        if test.empty:
            continue
        train = work[work["gameday"] < test["gameday"].min()].copy()
        if window_seasons is not None:
            test_season = int(pd.to_numeric(test["season"], errors="coerce").dropna().max())
            minimum_season = test_season - window_seasons + 1
            train = train[pd.to_numeric(train["season"], errors="coerce") >= minimum_season].copy()
        if len(train) < MIN_TRAIN_GAMES:
            continue

        active = [c for c in features if c in train.columns and train[c].notna().any()]
        if not active:
            continue
        medians = train[active].median(numeric_only=True).fillna(0)
        x_train = train[active].fillna(medians).fillna(0)
        x_test = test[active].fillna(medians).fillna(0)

        for target, output in (("home_score", "pred_home"), ("away_score", "pred_away")):
            reg = Ridge(alpha=ALPHA)
            reg.fit(x_train, train[target])
            test[output] = reg.predict(x_test)

        test["training_games"] = int(len(train))
        test["training_first_season"] = int(pd.to_numeric(train["season"], errors="coerce").min())
        test["training_last_season"] = int(pd.to_numeric(train["season"], errors="coerce").max())
        test["model"] = model_name
        test["training_window"] = window_name
        predictions.append(test)

    if not predictions:
        return pd.DataFrame()
    return pd.concat(predictions, ignore_index=True).drop_duplicates("game_id")


def _grade(pred: pd.DataFrame) -> pd.DataFrame:
    out = pred.copy()
    out["actual_home_margin"] = out["home_score"] - out["away_score"]
    out["pred_home_margin"] = out["pred_home"] - out["pred_away"]
    out["ats_edge"] = out["pred_home_margin"] - out["spread_line"]
    out["actual_ats_margin"] = out["actual_home_margin"] - out["spread_line"]
    out["ats_direction"] = np.sign(out["ats_edge"])
    out["ats_outcome"] = np.where(
        out["actual_ats_margin"].eq(0), "Push",
        np.where(out["ats_edge"] * out["actual_ats_margin"] > 0, "Win", "Loss"),
    )
    return out


def _record(frame: pd.DataFrame) -> dict:
    f = frame.dropna(subset=["ats_edge", "actual_ats_margin"]).copy()
    wins = int(f["ats_outcome"].eq("Win").sum())
    losses = int(f["ats_outcome"].eq("Loss").sum())
    pushes = int(f["ats_outcome"].eq("Push").sum())
    graded = wins + losses
    profit = wins * (100.0 / 110.0) - losses
    return {
        "games": int(len(f)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "graded_ex_pushes": graded,
        "accuracy_pct_ex_pushes": round(100.0 * wins / graded, 3) if graded else None,
        "profit_units_at_minus110": round(profit, 4),
        "roi_pct_at_minus110": round(100.0 * profit / len(f), 3) if len(f) else None,
        "ats_margin_mae": round(float((f["pred_home_margin"] - f["actual_home_margin"]).abs().mean()), 4) if len(f) else None,
    }


def _paired_injury_delta(base: pd.DataFrame, injury: pd.DataFrame) -> dict:
    cols = ["game_id", "ats_outcome", "ats_direction", "ats_edge"]
    a = base[cols].rename(columns={c: f"baseline_{c}" for c in cols if c != "game_id"})
    b = injury[cols].rename(columns={c: f"injury_{c}" for c in cols if c != "game_id"})
    m = a.merge(b, on="game_id", how="inner")
    flips = m[m["baseline_ats_direction"] != m["injury_ats_direction"]].copy()
    helped = int(((flips["baseline_ats_outcome"] == "Loss") & (flips["injury_ats_outcome"] == "Win")).sum())
    hurt = int(((flips["baseline_ats_outcome"] == "Win") & (flips["injury_ats_outcome"] == "Loss")).sum())
    decisive = helped + hurt
    p = float(binomtest(min(helped, hurt), decisive, 0.5, alternative="two-sided").pvalue) if decisive else None
    return {
        "common_games": int(len(m)),
        "flip_games": int(len(flips)),
        "flip_rate_pct": round(100.0 * len(flips) / len(m), 3) if len(m) else None,
        "injury_helped": helped,
        "injury_hurt": hurt,
        "net_help_minus_hurt": helped - hurt,
        "decisive_flips": decisive,
        "exact_binomial_two_sided_p": round(p, 6) if p is not None else None,
    }


def _coverage_by_season(data: pd.DataFrame) -> dict:
    result = {}
    home = "home_injury_report_available"
    away = "away_injury_report_available"
    if home not in data.columns or away not in data.columns:
        return result
    for season in EVAL_SEASONS:
        s = data[pd.to_numeric(data["season"], errors="coerce").eq(season)].copy()
        if season == 2026:
            s = s[pd.to_numeric(s["week"], errors="coerce").between(1, 8)]
        h = pd.to_numeric(s[home], errors="coerce")
        a = pd.to_numeric(s[away], errors="coerce")
        both = h.eq(1) & a.eq(1)
        result[str(season)] = {
            "games": int(len(s)),
            "both_teams_report_available": int(both.sum()),
            "both_team_coverage_pct": round(100.0 * both.sum() / len(s), 3) if len(s) else None,
            "games_missing_at_least_one_team": int((~both).sum()),
        }
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

    baseline_features = _numeric_feature_columns(data, list(baseline.columns))
    injury_features = list(dict.fromkeys(baseline_features + _numeric_feature_columns(data, injury_cols)))
    if not baseline_features or len(injury_features) <= len(baseline_features):
        raise RuntimeError("Could not build distinct baseline and injury feature sets.")

    all_preds = []
    for window_name, window_seasons in WINDOWS.items():
        for model_name, features in (("baseline", baseline_features), ("injury", injury_features)):
            print(f"Fitting {model_name} with {window_name} ({len(features)} features)...")
            pred = _fit_weekly_window(data, features, window_seasons, model_name, window_name)
            if pred.empty:
                raise RuntimeError(f"No predictions for {model_name}/{window_name}")
            pred = _grade(pred)
            all_preds.append(pred)

    preds = pd.concat(all_preds, ignore_index=True)
    preds = preds[pd.to_numeric(preds["season"], errors="coerce").isin(EVAL_SEASONS)].copy()
    preds = preds[(preds["season"] != 2026) | pd.to_numeric(preds["week"], errors="coerce").between(1, 8)].copy()

    # Exact common-game set by season across all six model/window combinations.
    common_ids_by_season = {}
    for season in EVAL_SEASONS:
        s = preds[pd.to_numeric(preds["season"], errors="coerce").eq(season)]
        sets = []
        for window_name in WINDOWS:
            for model_name in ("baseline", "injury"):
                sets.append(set(s[(s["training_window"] == window_name) & (s["model"] == model_name)]["game_id"]))
        common = set.intersection(*sets) if sets else set()
        common_ids_by_season[season] = common

    common_all = set().union(*common_ids_by_season.values())
    eval_preds = preds[preds["game_id"].isin(common_all)].copy()

    # Long-form summary table.
    summary_rows = []
    season_report = {}
    for season in EVAL_SEASONS:
        season_report[str(season)] = {}
        ids = common_ids_by_season[season]
        season_slice = eval_preds[eval_preds["game_id"].isin(ids)].copy()
        for window_name in WINDOWS:
            season_report[str(season)][window_name] = {}
            pair = {}
            for model_name in ("baseline", "injury"):
                f = season_slice[(season_slice["training_window"] == window_name) & (season_slice["model"] == model_name)].copy()
                rec = _record(f)
                pair[model_name] = f
                season_report[str(season)][window_name][model_name] = rec
                summary_rows.append({"season": season, "training_window": window_name, "model": model_name, **rec})
            delta = _paired_injury_delta(pair["baseline"], pair["injury"])
            season_report[str(season)][window_name]["injury_incremental_vs_baseline"] = delta

    # Aggregate regimes: older full seasons vs recent higher-coverage regime and 2026 separately.
    regime_defs = {
        "2023_2024": (2023, 2024),
        "2025_only": (2025,),
        "2026_weeks_1_8": (2026,),
        "2025_2026_combined": (2025, 2026),
    }
    regime_report = {}
    for regime_name, seasons in regime_defs.items():
        ids = set().union(*[common_ids_by_season[s] for s in seasons])
        regime_report[regime_name] = {}
        for window_name in WINDOWS:
            regime_report[regime_name][window_name] = {}
            pair = {}
            for model_name in ("baseline", "injury"):
                f = eval_preds[
                    eval_preds["game_id"].isin(ids)
                    & eval_preds["training_window"].eq(window_name)
                    & eval_preds["model"].eq(model_name)
                ].copy()
                rec = _record(f)
                pair[model_name] = f
                regime_report[regime_name][window_name][model_name] = rec
            regime_report[regime_name][window_name]["injury_incremental_vs_baseline"] = _paired_injury_delta(pair["baseline"], pair["injury"])

    # Window comparison on exact common games for each model, full evaluated period.
    window_comparison = {}
    for model_name in ("baseline", "injury"):
        window_comparison[model_name] = {}
        for window_name in WINDOWS:
            f = eval_preds[(eval_preds["model"] == model_name) & (eval_preds["training_window"] == window_name)]
            window_comparison[model_name][window_name] = _record(f)

    report = {
        "status": "RESEARCH_ONLY_RECENT_REGIME_TRAINING_WINDOW",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "question": "Does recent-history training improve ATS performance, and has Injury's incremental value improved in the newer injury-data regime?",
        "method": {
            "models": ["baseline", "injury"],
            "ridge_alpha": ALPHA,
            "minimum_training_games": MIN_TRAIN_GAMES,
            "windows": {
                "expanding_full_history": "all completed games before the test fold",
                "rolling_4_seasons": "test season plus prior 3 seasons, still strictly before the fold",
                "rolling_3_seasons": "test season plus prior 2 seasons, still strictly before the fold",
            },
            "two_season_exclusion": "Not tested in the primary comparison because it cannot satisfy the established 500-game minimum by early/midseason; lowering the minimum would confound recency with sample-size methodology.",
            "market_lines": "nflverse schedule spread_line; sportsbook execution not verified",
            "2026_scope": "Weeks 1-8 only",
            "common_game_policy": "Each season is restricted to games predicted by both models under all three primary windows.",
        },
        "feature_counts": {"baseline": len(baseline_features), "injury": len(injury_features)},
        "injury_report_coverage": _coverage_by_season(data),
        "common_game_counts": {str(s): len(ids) for s, ids in common_ids_by_season.items()},
        "season_results": season_report,
        "regime_results": regime_report,
        "window_comparison_all_2023_to_2026_scope": window_comparison,
        "cautions": [
            "This remains retrospective research and not a pristine untouched holdout.",
            "Training-window changes can capture roster/coaching/rule recency effects, not only injury-data quality.",
            "Injury coverage/publishing conventions differ across historical seasons, so regime attribution is suggestive rather than causal.",
            "nflverse schedule lines are not verified executable sportsbook quotes.",
            "No production model or official prospective record is modified.",
        ],
    }

    (OUT / "injury_recent_regime_training_window_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(summary_rows).to_csv(OUT / "injury_recent_regime_training_window_by_season.csv", index=False)
    eval_preds[[
        "game_id", "season", "week", "gameday", "away_team", "home_team", "spread_line",
        "home_score", "away_score", "model", "training_window", "training_games",
        "training_first_season", "training_last_season", "pred_home", "pred_away",
        "pred_home_margin", "ats_edge", "actual_ats_margin", "ats_direction", "ats_outcome",
    ]].to_csv(OUT / "injury_recent_regime_training_window_predictions.csv", index=False)

    print(json.dumps({
        "common_game_counts": report["common_game_counts"],
        "injury_report_coverage": report["injury_report_coverage"],
        "regime_results": report["regime_results"],
        "window_comparison": report["window_comparison_all_2023_to_2026_scope"],
    }, indent=2))


if __name__ == "__main__":
    main()
