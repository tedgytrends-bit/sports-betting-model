#!/usr/bin/env python3
"""Chronological holdout audit of the QB-EPA injury candidate.

All estimates use prior games only. Historical starters are *inferred from the
previous game's primary passer*, not looked up from future same-game PBP.
Therefore this audit measures an automated starter inference workflow, NOT a
counterfactual where the actual injured replacement was known ahead of time.
The result must not replace official/prospective tracked records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset, chronological_backtest
from injury_model import load_injury_reports, add_injury_features
from qb_epa_model import qb_game_stats, build_qb_epa_board, attach_qb_shifts

OUT = ROOT / "data" / "qb_epa_shadow"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)


def _frame(result, name):
    frame = result["predictions"].copy()
    return frame[[
        "game_id", "season", "week", "gameday", "home_team", "away_team",
        "home_score", "away_score", "pred_home_score", "pred_away_score",
    ]].rename(columns={
        "pred_home_score": f"{name}_home", "pred_away_score": f"{name}_away"
    })


def _metrics(df, label):
    if df.empty:
        return dict(model=label, n=0)
    margin_actual = df["home_score"] - df["away_score"]
    total_actual = df["home_score"] + df["away_score"]
    margin_pred = df[f"{label}_home"] - df[f"{label}_away"]
    total_pred = df[f"{label}_home"] + df[f"{label}_away"]
    return {
        "model": label, "n": len(df),
        "margin_mae": round(float(np.abs(margin_pred - margin_actual).mean()), 4),
        "total_mae": round(float(np.abs(total_pred - total_actual).mean()), 4),
        "home_score_mae": round(float(np.abs(df[f"{label}_home"] - df["home_score"]).mean()), 4),
        "away_score_mae": round(float(np.abs(df[f"{label}_away"] - df["away_score"]).mean()), 4),
    }


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)
    base = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)

    original = add_injury_features(base, schedule, reports)
    original_preds = _frame(chronological_backtest(original, min_train_games=500), "original_injury")
    nonqb = add_injury_features(base, schedule, reports, exclude_qb=True)
    nonqb_preds = _frame(chronological_backtest(nonqb, min_train_games=500), "nonqb_injury")
    paired = nonqb_preds.merge(
        original_preds[["game_id", "original_injury_home", "original_injury_away"]],
        on="game_id", how="inner", validate="one_to_one"
    )
    paired = paired[pd.to_numeric(paired["season"], errors="coerce").isin((2025, 2026))].copy()
    if paired.empty:
        raise RuntimeError("No 2025/2026 chronological test cases found")
    stats = qb_game_stats(pbp, schedule)
    board = build_qb_epa_board(stats, schedule, paired)
    if board.starter_source.eq("verified_pregame").any():
        raise AssertionError("No retrospectively verified overrides should be used")
    v2_input = paired[["game_id", "nonqb_injury_home", "nonqb_injury_away"]].rename(
        columns={"nonqb_injury_home": "projected_home", "nonqb_injury_away": "projected_away"}
    )
    v2 = attach_qb_shifts(v2_input, board).rename(columns={
        "home_qb_adjusted": "qb_epa_v2_home", "away_qb_adjusted": "qb_epa_v2_away"
    })
    paired = paired.merge(
        v2[["game_id", "qb_epa_v2_home", "qb_epa_v2_away"]],
        on="game_id", how="left", validate="one_to_one"
    )
    reports_rows = []
    for season in (2025, 2026):
        sub = paired[paired["season"].eq(season)].copy()
        common = sub.dropna(subset=["qb_epa_v2_home", "qb_epa_v2_away"])
        for label in ("original_injury", "nonqb_injury", "qb_epa_v2"):
            reports_rows.append({"season": season, **_metrics(common, label)})
    metrics = pd.DataFrame(reports_rows)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    pairfile = OUT / f"qb_epa_chronological_2025_2026_{stamp}.csv"
    metricfile = OUT / f"qb_epa_metrics_2025_2026_{stamp}.csv"
    paired.to_csv(pairfile, index=False)
    metrics.to_csv(metricfile, index=False)
    manifest = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "time_utc": now.isoformat(),
        "model": "injury_qb_epa_v2_research",
        "heldout_seasons": [2025, 2026],
        "leakage_guard": "Only historical primary QB from LAST game may be inferred, never from target game.",
        "starter_validation_limit": "Actual game-day starters were NOT historically verified; new injured replacements will be missed.",
        "estimator": "Chronological Ridge injury model excluding ALL QB injury rows plus regularized QB EPA delta * recent team dropbacks",
        "warning": "No tuning against these outcomes; not validated for public betting recommendations.",
        "metrics_csv": str(metricfile.relative_to(ROOT)),
        "paired_csv": str(pairfile.relative_to(ROOT)),
        "missing_v2_predictions": int(paired[["qb_epa_v2_home", "qb_epa_v2_away"]].isna().any(axis=1).sum()),
    }
    (OUT / f"qb_epa_backtest_manifest_{stamp}.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(metrics.to_string(index=False))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
