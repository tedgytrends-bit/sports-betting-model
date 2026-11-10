#!/usr/bin/env python3
"""Research only: isolate efficiency-history horizon from margin feature scaling.

Hypothesis: a 10-game efficiency lookback retains stale team information across
seasons. Try exactly two predeclared windows (6 vs 10 prior games) and two
predeclared training variants (original unscaled Ridge vs train-fold StandardScaler
+ Ridge, alpha=10). Compare on EXACTLY matched folds and games.

All 2026 games after Week 8 are removed BEFORE training, and the only market
input is for post-hoc evaluation. This is exploratory (2025 and 2026 seasons were
previously studied), not a fresh holdout nor live code change.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import (load_schedule_data, load_pbp, build_efficiency_table, _feature_frame)

OUTDIR = ROOT / "data" / "week09_review"
STEM = "lookback_margin_shadow_20261110"
LOOKBACKS = (6, 10)
TYPES = ("raw", "standardized")
ALPHA = 10.0
MIN_TRAIN = 500
THRESHOLDS = (0.0, 3.5, 5.0)
IGNORE = {"game_id", "gameday", "season", "week", "home_team", "away_team",
          "home_score", "away_score", "test_block"}


def _build_dataset(schedule, eff, window):
    df = _feature_frame(schedule, eff, lookback_games=window)
    df = df.dropna(subset=["gameday", "home_score", "away_score"]).copy()
    df["gameday"] = pd.to_datetime(df["gameday"])
    df["season"] = pd.to_numeric(df["season"], errors="raise")
    df["week"] = pd.to_numeric(df["week"], errors="raise")
    df = df.loc[df["season"].between(2021, 2026)
                & ~((df["season"] == 2026) & (df["week"] > 8))]
    if df["game_id"].duplicated().any():
        raise AssertionError(f"Duplicate game IDs for lookback={window}")
    return df.sort_values(["gameday", "game_id"]).copy()


def _evaluate(frame, col, threshold):
    actual = frame["actual_margin"].to_numpy(dtype=float)
    predicted = frame[col].to_numpy(dtype=float)
    market = frame["market_margin"].to_numpy(dtype=float)
    gap, actual_gap = predicted-market, actual-market
    select = np.abs(gap) > 1e-9
    if threshold > 0:
        select &= np.abs(gap) >= threshold
    w = int((select & ((gap * actual_gap) > 1e-9)).sum())
    l = int((select & ((gap * actual_gap) < -1e-9)).sum())
    pushes = int((select & (np.abs(actual_gap) < 1e-9)).sum())
    bets = int(select.sum())
    if bets != w + l + pushes:
        raise AssertionError("ATS wager counts do not reconcile")
    return {
        "n": int(len(frame)),
        "margin_mae": round(float(np.mean(np.abs(predicted - actual))), 4),
        "margin_rmse": round(float(np.sqrt(np.mean(np.square(predicted - actual)))), 4),
        "mean_abs_margin": round(float(np.mean(np.abs(predicted))), 4),
        "mean_signed_error": round(float(np.mean(predicted - actual)), 4),
        "underdog_ats_selections": int(((market*gap < 0) & select).sum()),
        "favorite_ats_selections": int(((market*gap > 0) & select).sum()),
        "bets": bets, "wins": w, "losses": l, "pushes": pushes,
        "win_rate_excluding_pushes": round(w/(w+l), 4) if (w+l) else None,
        "roi_flat_minus110": round(((w * 100.0 / 110.0)-l)/bets, 4) if bets else None,
    }


def main():
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    eff = build_efficiency_table(pbp)
    frames = {window: _build_dataset(schedule, eff, window) for window in LOOKBACKS}
    common_ids = set(frames[LOOKBACKS[0]]["game_id"])
    for df in frames.values():
        common_ids.intersection_update(df["game_id"])
    if len(common_ids) < 1400:
        raise AssertionError(f"Insufficient matched historical games: {len(common_ids)}")
    for window in LOOKBACKS:
        frames[window] = frames[window].loc[
            frames[window]["game_id"].isin(common_ids)
        ].copy()
        frames[window]["test_block"] = frames[window]["gameday"].dt.to_period("W").astype(str)

    reference = frames[10]
    pred_rows = []
    names = tuple(f"{kind}_{window}" for kind in TYPES for window in LOOKBACKS)
    blocks = reference["test_block"].drop_duplicates().tolist()
    for block in blocks:
        train_indices = {}
        for window in LOOKBACKS:
            data = frames[window]
            test = data.loc[data["test_block"].eq(block)]
            if test.empty:
                continue
            train = data.loc[data["gameday"] < test["gameday"].min()]
            train_indices[window] = (train, test)
        if len(train_indices) != len(LOOKBACKS):
            raise AssertionError(f"Missing block {block} in one feature set")
        n_train = len(train_indices[10][0])
        if n_train < MIN_TRAIN:
            continue
        test_ids = set(train_indices[10][1]["game_id"])
        train_ids = set(train_indices[10][0]["game_id"])
        if any(set(tr.game_id) != train_ids or set(te.game_id) != test_ids
               for tr, te in train_indices.values()):
            raise AssertionError(f"Training/testing game mismatch: {block}")

        out = train_indices[10][1][
            ["game_id", "gameday", "season", "week", "home_team", "away_team",
             "home_score", "away_score"]
        ].copy().sort_values("game_id")
        for window in LOOKBACKS:
            train, test = train_indices[window]
            feats = [c for c in train.columns
                     if c not in IGNORE and pd.api.types.is_numeric_dtype(train[c])]
            active = [c for c in feats if train[c].notna().any()]
            if not active:
                raise AssertionError(f"No train-available features: {block}, {window}")
            medians = train[active].median(numeric_only=True).fillna(0)
            xtrain = train[active].fillna(medians).fillna(0)
            xtest = test[active].fillna(medians).fillna(0)
            margin = train["home_score"] - train["away_score"]
            for kind in TYPES:
                if kind == "raw":
                    model = Ridge(alpha=ALPHA)
                else:
                    model = make_pipeline(StandardScaler(), Ridge(alpha=ALPHA))
                model.fit(xtrain, margin)
                raw_predictions = pd.DataFrame({
                    "game_id": test["game_id"].values,
                    f"{kind}_{window}": model.predict(xtest),
                })
                out = out.merge(raw_predictions, on="game_id", how="left", validate="one_to_one")
        out["train_games"] = n_train
        pred_rows.append(out)

    if not pred_rows:
        raise AssertionError("No matched walk-forward predictions")
    predictions = pd.concat(pred_rows, ignore_index=True)
    if predictions.game_id.duplicated().any():
        raise AssertionError("Repeated prediction game")
    if ((predictions.season == 2026) & (predictions.week > 8)).any():
        raise AssertionError("2026 Week 9 used as model input")
    spread = schedule[["game_id", "spread_line"]].copy()
    spread["spread_line"] = pd.to_numeric(spread["spread_line"], errors="coerce")
    predictions = predictions.merge(
        spread.rename(columns={"spread_line": "market_margin"}),
        on="game_id", how="left", validate="one_to_one"
    )
    predictions["actual_margin"] = predictions["home_score"]-predictions["away_score"]
    if predictions[list(names) + ["market_margin", "actual_margin"]].isna().any().any():
        raise AssertionError("Null final outcome, market, or prediction")
    if not np.isfinite(predictions[list(names) + ["market_margin", "actual_margin"]].to_numpy()).all():
        raise AssertionError("Nonfinite prediction or score")
    report = {
        "status": "EXPLORATORY_RESEARCH_ONLY_NOT_OFFICIAL",
        "hypothesis": "Six prior games better capture roster and team regime change than ten prior games.",
        "method": "Point-in-time prior-game efficiency table, common train/test game IDs, weekly refit; predeclared 6 vs 10 lookback and unscaled vs standardized Ridge(alpha=10). Recorded market spread is evaluation-only.",
        "warning": "Historical 2025 and 2026 W1-8 outcomes have already been repeatedly studied; positive results here would NOT be independently confirmed.",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "models": list(names),
        "thresholds": list(THRESHOLDS),
        "training_minimum": MIN_TRAIN,
        "common_games_eligible": len(common_ids),
        "predicted_games": int(len(predictions)),
        "by_season": {str(k): int(v) for k, v in predictions.groupby("season").size().items()},
        "evaluation": {},
        "promotion_rule": "Do not change official Baseline, Injury, totals, or frozen forecasts. A candidate needs a new genuinely prospective record and consistent margin MAE plus ATS value across seasons.",
    }
    splits = {}
    for year in (2023, 2024, 2025, 2026):
        yearframe = predictions.loc[predictions.season.eq(year)]
        if len(yearframe) < 100:
            raise AssertionError(f"Unexpected low {year} sample: {len(yearframe)}")
        splits[str(year)] = yearframe
    current = splits["2026"]
    for label, frame in [
        *[(year, frameset) for year, frameset in splits.items()],
        ("2026_weeks_1_4", current.loc[current.week.le(4)]),
        ("2026_weeks_5_8", current.loc[current.week.ge(5)]),
        ("2026_spread_7_plus", current.loc[current.market_margin.abs().ge(7)]),
        ("2026_spread_under_7", current.loc[current.market_margin.abs().lt(7)]),
    ]:
        if frame.empty:
            continue
        report["evaluation"][label] = {
            name: {str(t): _evaluate(frame, name, t) for t in THRESHOLDS}
            for name in names
        }
        report["evaluation"][label]["market_only"] = {
            "n": len(frame),
            "margin_mae": round(float(np.mean(np.abs(frame["actual_margin"]-frame["market_margin"]))), 4),
        }

    OUTDIR.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(OUTDIR / f"{STEM}.csv", index=False)
    (OUTDIR / f"{STEM}.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({
        "status": report["status"], "games": report["predicted_games"],
        "by_season": report["by_season"],
        "2025_margin_mae": {name: report["evaluation"]["2025"][name]["0.0"]["margin_mae"]
                            for name in names},
        "2026_margin_mae": {name: report["evaluation"]["2026"][name]["0.0"]["margin_mae"]
                            for name in names},
    }, indent=2))


if __name__ == "__main__":
    main()
