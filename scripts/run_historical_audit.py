#!/usr/bin/env python3
"""Automated chronological NFL ATS/totals audit. Research only; not a betting recommendation."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

from model import (
    MODEL_VERSION,
    load_schedule_data,
    load_pbp,
    build_efficiency_model_dataset,
    chronological_backtest,
    chronological_direct_total_backtest,
    chronological_market_residual_backtest,
    chronological_ats_residual_backtest,
    chronological_market_anchored_ats_backtest,
)

OUT = Path("research/reports")
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
MIN_TRAIN_GAMES = 500
EDGE_THRESHOLD = 3.5


def mae(actual, predicted):
    a = pd.to_numeric(actual, errors="coerce")
    p = pd.to_numeric(predicted, errors="coerce")
    valid = a.notna() & p.notna()
    return float((a[valid] - p[valid]).abs().mean()) if valid.any() else np.nan


def roi_at_minus_110(edges, actual_margins, threshold=EDGE_THRESHOLD):
    edges = pd.to_numeric(edges, errors="coerce")
    actual = pd.to_numeric(actual_margins, errors="coerce")
    valid = edges.notna() & actual.notna()
    edges, actual = edges[valid], actual[valid]
    bets = edges.abs() >= threshold
    edges, actual = edges[bets], actual[bets]
    # Positive edge means home side; negative edge means away side.
    outcomes = np.where(edges > 0, np.sign(actual), -np.sign(actual))
    wins = int((outcomes > 0).sum())
    losses = int((outcomes < 0).sum())
    pushes = int((outcomes == 0).sum())
    n = len(outcomes)
    net_units = wins * (100 / 110) - losses
    return {
        "bets": n,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_pct_ex_push": 100 * wins / (wins + losses) if wins + losses else np.nan,
        "net_units_at_minus_110": net_units,
        "roi_pct_per_unit_risked": 100 * net_units / n if n else np.nan,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Starting automated historical audit for model v{MODEL_VERSION}")
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    dataset = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    score_backtest = chronological_backtest(dataset, min_train_games=MIN_TRAIN_GAMES)
    pred = score_backtest["predictions"].copy()
    pred = pred.merge(
        schedule[["game_id", "spread_line", "total_line"]].drop_duplicates("game_id"),
        on="game_id", how="left", validate="one_to_one"
    )
    for col in ["home_score", "away_score", "spread_line", "total_line", "pred_home_score", "pred_away_score"]:
        pred[col] = pd.to_numeric(pred[col], errors="coerce")
    pred["actual_home_margin"] = pred["home_score"] - pred["away_score"]
    pred["predicted_home_margin"] = pred["pred_home_score"] - pred["pred_away_score"]
    pred["actual_total"] = pred["home_score"] + pred["away_score"]
    pred["predicted_total_from_scores"] = pred["pred_home_score"] + pred["pred_away_score"]
    pred["ats_edge_score_model"] = pred["predicted_home_margin"] - pred["spread_line"]
    pred["total_edge_score_model"] = pred["predicted_total_from_scores"] - pred["total_line"]

    metrics = []
    metrics.append({"market": "ATS", "model": "Efficiency score model", "games": int(pred.dropna(subset=["spread_line", "actual_home_margin", "predicted_home_margin"]).shape[0]),
                    "model_mae": mae(pred["actual_home_margin"], pred["predicted_home_margin"]),
                    "market_benchmark_mae": mae(pred["actual_home_margin"], pred["spread_line"]),
                    **roi_at_minus_110(pred["ats_edge_score_model"], pred["actual_home_margin"] - pred["spread_line"])})
    metrics.append({"market": "Totals", "model": "Efficiency score sum", "games": int(pred.dropna(subset=["total_line", "actual_total", "predicted_total_from_scores"]).shape[0]),
                    "model_mae": mae(pred["actual_total"], pred["predicted_total_from_scores"]),
                    "market_benchmark_mae": mae(pred["actual_total"], pred["total_line"]),
                    **roi_at_minus_110(pred["total_edge_score_model"], pred["actual_total"] - pred["total_line"])})

    try:
        direct_totals = chronological_direct_total_backtest(dataset, min_train_games=MIN_TRAIN_GAMES)
        if "actual_total" not in direct_totals:
            direct_totals["actual_total"] = pd.to_numeric(direct_totals["home_score"], errors="coerce") + pd.to_numeric(direct_totals["away_score"], errors="coerce")
        direct_totals = direct_totals.merge(schedule[["game_id", "total_line"]], on="game_id", how="left", validate="one_to_one")
        pred_col = next((c for c in ["direct_projected_total", "predicted_total", "pred_total", "pred_actual_total"] if c in direct_totals.columns), None)
        if pred_col:
            direct_totals["edge"] = pd.to_numeric(direct_totals[pred_col], errors="coerce") - pd.to_numeric(direct_totals["total_line"], errors="coerce")
            metrics.append({"market": "Totals", "model": "Direct total model", "games": int(direct_totals.dropna(subset=["total_line", "actual_total", pred_col]).shape[0]),
                            "model_mae": mae(direct_totals["actual_total"], direct_totals[pred_col]),
                            "market_benchmark_mae": mae(direct_totals["actual_total"], direct_totals["total_line"]),
                            **roi_at_minus_110(direct_totals["edge"], direct_totals["actual_total"] - direct_totals["total_line"])})
    except Exception as exc:
        print(f"WARNING: direct totals audit failed: {type(exc).__name__}: {exc}")

    try:
        residual = chronological_market_residual_backtest(dataset, schedule, min_train_games=MIN_TRAIN_GAMES)
        print("Market residual totals output columns:", list(residual.columns))
        residual.to_csv(OUT / "automated_totals_market_residual_predictions.csv", index=False)
    except Exception as exc:
        print(f"WARNING: market-residual totals audit failed: {type(exc).__name__}: {exc}")

    try:
        ats_resid = chronological_ats_residual_backtest(dataset, schedule, min_train_games=MIN_TRAIN_GAMES)
        print("ATS residual output columns:", list(ats_resid.columns))
        ats_resid.to_csv(OUT / "automated_ats_residual_predictions.csv", index=False)
    except Exception as exc:
        print(f"WARNING: ATS residual audit failed: {type(exc).__name__}: {exc}")

    try:
        anchored = chronological_market_anchored_ats_backtest(dataset, schedule, min_train_games=MIN_TRAIN_GAMES)
        print("Market-anchored ATS output columns:", list(anchored.columns))
        anchored.to_csv(OUT / "automated_ats_market_anchored_predictions.csv", index=False)
    except Exception as exc:
        print(f"WARNING: market-anchored ATS audit failed: {type(exc).__name__}: {exc}")

    metric_df = pd.DataFrame(metrics)
    metric_df.insert(0, "model_version", MODEL_VERSION)
    metric_df.insert(1, "generated_at_utc", pd.Timestamp.now(tz="UTC").isoformat())
    metric_df.to_csv(OUT / "automated_historical_audit_summary.csv", index=False)
    pred.to_csv(OUT / "automated_score_model_predictions.csv", index=False)
    (OUT / "automated_historical_audit_status.json").write_text(
        json.dumps({
            "model_version": MODEL_VERSION,
            "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "status": "completed",
            "games_in_score_model_backtest": int(len(pred)),
            "summary_rows": int(len(metric_df)),
            "note": "Historical research only. Public schedule lines are not verified sportsbook-timestamp records. ROI assumes a fixed 3.5-point edge threshold and -110 odds, so treat as exploratory."
        }, indent=2),
        encoding="utf-8",
    )
    print(metric_df.to_string(index=False))
    print("Saved automated audit outputs to research/reports/")


if __name__ == "__main__":
    main()
