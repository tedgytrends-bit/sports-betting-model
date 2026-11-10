#!/usr/bin/env python3
"""Research-only test: can feature standardization correct margin compression?

Pre-registered comparison:
  A. Existing separate-score Ridge(alpha=10), unscaled.
  B. Direct-margin Ridge(alpha=10), unscaled: MUST equal A by linearity.
  C. Direct-margin StandardScaler + Ridge(alpha=10), train-fold only.
  D. Archived schedule spread as a diagnostic benchmark, never an input feature.

Train strictly on earlier dates (weekly folds, min 500 games); report held-out
chronological 2025 and 2026 Weeks 1-8 separately. No Week 9 outcomes, no
injury/provider API credits, no live-model modification. Fixed coefficients and
edge thresholds; the 2025/2026 folds have already been studied elsewhere and
are NOT fresh untouched validation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
OUT = ROOT / "data" / "week09_review"
PREFIX = "standardized_margin_shadow_20261110"
MIN_TRAIN = 500
ALPHA = 10.0
EDGE_THRESHOLDS = (0.0, 3.5, 5.0)
PREDICTIONS = ("raw_margin", "direct_unscaled_margin", "direct_scaled_margin", "market_margin")


def score(frame: pd.DataFrame, column: str, threshold: float) -> dict:
    p = frame[column].to_numpy(dtype=float)
    y = frame["actual_margin"].to_numpy(dtype=float)
    market = frame["market_margin"].to_numpy(dtype=float)
    edge, cover = p - market, y - market
    selection = np.abs(edge) > 1e-9
    if threshold:
        selection &= np.abs(edge) >= threshold
    win = selection & ((edge * cover) > 1e-9)
    loss = selection & ((edge * cover) < -1e-9)
    push = selection & (np.abs(cover) < 1e-9)
    if int((win | loss | push).sum()) != int(selection.sum()):
        raise AssertionError("ATS grading did not reconcile")
    w, l, pushes = int(win.sum()), int(loss.sum()), int(push.sum())
    bets = int(selection.sum())
    net_units = w * 100.0 / 110.0 - l  # Hypothetical -110; not quoted Bovada.
    return {
        "games": len(frame),
        "margin_mae": round(float(np.abs(p - y).mean()), 4),
        "margin_rmse": round(float(np.sqrt(np.square(p - y).mean())), 4),
        "mean_signed_margin_error": round(float(np.mean(p - y)), 4),
        "mean_abs_predicted_margin": round(float(np.abs(p).mean()), 4),
        "bets": bets,
        "wins": w, "losses": l, "pushes": pushes,
        "win_rate_ex_push": round(w / (w + l), 4) if w + l else None,
        "hypothetical_roi_at_flat_minus110": round(net_units / bets, 4) if bets else None,
    }


def experiment() -> tuple[pd.DataFrame, dict]:
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    dataset = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    data = dataset.dropna(subset=["gameday", "home_score", "away_score"]).copy()
    data["gameday"] = pd.to_datetime(data["gameday"])
    data["season"] = pd.to_numeric(data["season"], errors="raise")
    data["week"] = pd.to_numeric(data["week"], errors="raise")
    data = data[
        data["season"].between(2021, 2026)
        & ~((data["season"] == 2026) & (data["week"] > 8))
    ].sort_values("gameday").copy()
    if data["game_id"].duplicated().any():
        raise AssertionError("Duplicate feature game_id")

    exclude = {
        "game_id", "gameday", "season", "week", "home_team",
        "away_team", "home_score", "away_score",
    }
    features = [
        c for c in data.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(data[c])
    ]
    if not features:
        raise AssertionError("No numeric pregame model features")
    data["test_block"] = data["gameday"].dt.to_period("W").astype(str)

    preds = []
    maximum_identity_error = 0.0
    for block in data["test_block"].drop_duplicates():
        test = data.loc[data["test_block"].eq(block)].copy()
        train = data.loc[data["gameday"] < test["gameday"].min()]
        if len(train) < MIN_TRAIN:
            continue
        active = [c for c in features if train[c].notna().any()]
        medians = train[active].median(numeric_only=True).fillna(0)
        x_train = train[active].fillna(medians).fillna(0)
        x_test = test[active].fillna(medians).fillna(0)
        home = Ridge(alpha=ALPHA).fit(x_train, train["home_score"]).predict(x_test)
        away = Ridge(alpha=ALPHA).fit(x_train, train["away_score"]).predict(x_test)
        margin_y = train["home_score"] - train["away_score"]
        direct = Ridge(alpha=ALPHA).fit(x_train, margin_y).predict(x_test)
        scaled = make_pipeline(
            StandardScaler(), Ridge(alpha=ALPHA)
        ).fit(x_train, margin_y).predict(x_test)
        delta = float(np.max(np.abs((home - away) - direct)))
        maximum_identity_error = max(maximum_identity_error, delta)
        if delta > 1e-6:
            raise AssertionError(f"Direct Ridge != two-score Ridge in {block}: {delta}")
        out = test[["game_id", "season", "week", "gameday", "home_score", "away_score"]].copy()
        out["raw_margin"] = home - away
        out["direct_unscaled_margin"] = direct
        out["direct_scaled_margin"] = scaled
        out["train_games"] = len(train)
        out["active_features"] = len(active)
        preds.append(out)

    if not preds:
        raise AssertionError("No chronological predictions")
    result = pd.concat(preds, ignore_index=True)
    if result["game_id"].duplicated().any():
        raise AssertionError("Repeated game prediction")
    market = schedule[["game_id", "spread_line"]].copy()
    market["spread_line"] = pd.to_numeric(market["spread_line"], errors="coerce")
    result = result.merge(market, on="game_id", how="left", validate="one_to_one")
    result = result.rename(columns={"spread_line": "market_margin"})
    result["actual_margin"] = result["home_score"] - result["away_score"]
    if result[["market_margin", "raw_margin", "direct_unscaled_margin",
               "direct_scaled_margin", "actual_margin"]].isna().any().any():
        raise AssertionError("A prediction, outcome, or archived spread is missing")
    if not np.isfinite(result[list(PREDICTIONS) + ["actual_margin"]].to_numpy()).all():
        raise AssertionError("Non-finite input or prediction")
    if ((result["season"] == 2026) & (result["week"] > 8)).any():
        raise AssertionError("2026 Week 9 data entered historical experiment")

    report = {
        "status": "RESEARCH_ONLY_NO_LIVE_CHANGES",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "The existing unscaled Ridge penalizes small-scale EPA/success features unevenly, compressing margins.",
        "null": "StandardScaler does not improve margin MAE consistently over raw-score Ridge on chronological holdouts.",
        "design": "Identical historical pregame feature frame and date-only weekly walk-forward folds; train-only median imputation and scaling; alpha=10 fixed. Archived nflverse spread used only for evaluation.",
        "holdout_warning": "2025 and 2026 Weeks 1-8 have been examined in prior research. This is exploratory reproducibility, NOT newly sealed validation.",
        "dataset": {"games": int(len(result)), "by_season": {str(k): int(v) for k, v in result.groupby("season").size().items()}},
        "direct_margin_identity_max_error": maximum_identity_error,
        "thresholds": list(EDGE_THRESHOLDS),
        "evaluation": {},
        "decision_rule": "Never promote solely from this experiment. Require positive margin MAE delta against raw baseline in 2025 AND 2026, no deterioration versus market, stable directional ATS evidence, then separate fresh prospective Week 10+ validation.",
        "publication_impact": "None: no site, frozen prediction, official grade, or total model changed.",
    }
    for season in (2023, 2024, 2025, 2026):
        test = result.loc[result["season"] == season]
        if test.empty:
            raise AssertionError(f"No test predictions for season {season}")
        report["evaluation"][str(season)] = {
            model: {str(th): score(test, model, th) for th in EDGE_THRESHOLDS}
            for model in PREDICTIONS
        }
        spread_splits = {
            "spread_0_to_2_5": test.loc[test["market_margin"].abs() < 3],
            "spread_3_to_6_5": test.loc[test["market_margin"].abs().between(3, 6.5)],
            "spread_7_plus": test.loc[test["market_margin"].abs() >= 7],
        }
        report["evaluation"][str(season)]["market_spread_strata"] = {
            key: {model: score(part, model, 0) for model in PREDICTIONS}
            for key, part in spread_splits.items() if len(part)
        }
    report["total_2026_games"] = int((result["season"] == 2026).sum())
    return result, report


def main():
    preds, report = experiment()
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f"{PREFIX}.csv"
    json_path = OUT / f"{PREFIX}.json"
    preds.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "games": report["dataset"]["games"],
        "identity_max_error": report["direct_margin_identity_max_error"],
        "2025": {k: round(v["0.0"]["margin_mae"], 3)
                 for k, v in report["evaluation"]["2025"].items()
                 if isinstance(v, dict) and "0.0" in v},
        "2026": {k: round(v["0.0"]["margin_mae"], 3)
                 for k, v in report["evaluation"]["2026"].items()
                 if isinstance(v, dict) and "0.0" in v},
    }, indent=2))


if __name__ == "__main__":
    main()
