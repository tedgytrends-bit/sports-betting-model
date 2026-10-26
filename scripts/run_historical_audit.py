#!/usr/bin/env python3
"""Automated chronological NFL ATS/totals audit. Research only; not a betting recommendation."""
from pathlib import Path
import sys

# Running a script from scripts/ puts that directory first on sys.path; add the repository root
# so the shared model.py module can be imported in GitHub Actions and local CLI runs.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
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


def grouped_diagnostics(frame, season_col, edge_col, actual_margin_col, model_name, market):
    """Report season and edge-band results without tuning thresholds on the same sample."""
    data = frame.copy()
    data[season_col] = pd.to_numeric(data[season_col], errors="coerce")
    data[edge_col] = pd.to_numeric(data[edge_col], errors="coerce")
    data[actual_margin_col] = pd.to_numeric(data[actual_margin_col], errors="coerce")
    data = data.dropna(subset=[season_col, edge_col, actual_margin_col]).copy()
    data["season"] = data[season_col].astype(int)
    data["edge_abs"] = data[edge_col].abs()
    data["edge_band"] = pd.cut(
        data["edge_abs"], bins=[-np.inf, 1.5, 2.5, 3.5, 4.5, 5.5, np.inf],
        labels=["0-1.5", "1.51-2.5", "2.51-3.5", "3.51-4.5", "4.51-5.5", "5.51+"],
        right=True,
    )
    reports = []
    for grouping, key in [("season", "season"), ("edge_band", "edge_band")]:
        for value, group in data.groupby(key, observed=False):
            if group.empty:
                continue
            metrics = roi_at_minus_110(group[edge_col], group[actual_margin_col])
            # All-game prediction diagnostics, independent of betting threshold.
            reports.append({
                "market": market, "model": model_name, "grouping": grouping,
                "group": str(value), "games": int(len(group)),
                "mean_abs_edge": float(group[edge_col].abs().mean()),
                **metrics,
            })
    return reports


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
    diagnostics = []
    audit_warnings = []
    # Evaluate each wager against the market line, not raw score margin/total.
    pred["actual_ats_cover_margin"] = pred["actual_home_margin"] - pred["spread_line"]
    pred["actual_total_over_margin"] = pred["actual_total"] - pred["total_line"]
    diagnostics.extend(grouped_diagnostics(pred, "season", "ats_edge_score_model",
        "actual_ats_cover_margin", "Efficiency score model", "ATS"))
    diagnostics.extend(grouped_diagnostics(pred, "season", "total_edge_score_model",
        "actual_total_over_margin", "Efficiency score sum", "Totals"))
    metrics.append({"market": "ATS", "model": "Efficiency score model", "games": int(pred.dropna(subset=["spread_line", "actual_home_margin", "predicted_home_margin"]).shape[0]),
                    "model_mae": mae(pred["actual_home_margin"], pred["predicted_home_margin"]),
                    "market_benchmark_mae": mae(pred["actual_home_margin"], pred["spread_line"]),
                    **roi_at_minus_110(pred["ats_edge_score_model"], pred["actual_home_margin"] - pred["spread_line"])})
    metrics.append({"market": "Totals", "model": "Efficiency score sum", "games": int(pred.dropna(subset=["total_line", "actual_total", "predicted_total_from_scores"]).shape[0]),
                    "model_mae": mae(pred["actual_total"], pred["predicted_total_from_scores"]),
                    "market_benchmark_mae": mae(pred["actual_total"], pred["total_line"]),
                    **roi_at_minus_110(pred["total_edge_score_model"], pred["actual_total"] - pred["total_line"])})

    try:
        # This backtest returns predictions only, so join actual scores and lines from schedule.
        direct_totals = chronological_direct_total_backtest(dataset, min_train_games=MIN_TRAIN_GAMES)
        direct_totals = direct_totals.merge(
            schedule[["game_id", "season", "home_score", "away_score", "total_line"]].drop_duplicates("game_id"),
            on="game_id", how="left", validate="one_to_one"
        )
        direct_totals["actual_total"] = pd.to_numeric(direct_totals["home_score"], errors="coerce") + pd.to_numeric(direct_totals["away_score"], errors="coerce")
        pred_col = "direct_total_prediction"
        direct_totals["edge"] = pd.to_numeric(direct_totals[pred_col], errors="coerce") - pd.to_numeric(direct_totals["total_line"], errors="coerce")
        direct_totals["actual_total_over_margin"] = direct_totals["actual_total"] - pd.to_numeric(direct_totals["total_line"], errors="coerce")
        diagnostics.extend(grouped_diagnostics(direct_totals, "season", "edge",
            "actual_total_over_margin", "Direct total model", "Totals"))
        direct_totals.to_csv(OUT / "automated_direct_total_predictions.csv", index=False)
        metrics.append({"market": "Totals", "model": "Direct total model", "games": int(direct_totals.dropna(subset=["total_line", "actual_total", pred_col]).shape[0]),
                        "model_mae": mae(direct_totals["actual_total"], direct_totals[pred_col]),
                        "market_benchmark_mae": mae(direct_totals["actual_total"], direct_totals["total_line"]),
                        **roi_at_minus_110(direct_totals["edge"], direct_totals["actual_total"] - direct_totals["total_line"])})
    except Exception as exc:
        message = f"direct totals audit failed: {type(exc).__name__}: {exc}"
        audit_warnings.append(message)
        print(f"WARNING: {message}")

    try:
        residual = chronological_market_residual_backtest(dataset, schedule, min_train_games=MIN_TRAIN_GAMES)
        print("Market residual totals output columns:", list(residual.columns))
        residual_eval = residual.merge(
            schedule[["game_id", "season", "home_score", "away_score", "total_line"]].drop_duplicates("game_id"),
            on="game_id", how="left", validate="one_to_one"
        )
        residual_eval["actual_total"] = pd.to_numeric(residual_eval["home_score"], errors="coerce") + pd.to_numeric(residual_eval["away_score"], errors="coerce")
        residual_eval["edge"] = pd.to_numeric(residual_eval["pred_market_residual"], errors="coerce")
        residual_eval["predicted_total"] = pd.to_numeric(residual_eval["total_line"], errors="coerce") + residual_eval["edge"]
        metrics.append({"market": "Totals", "model": "Market residual model", "games": int(residual_eval.dropna(subset=["total_line", "actual_total", "predicted_total"]).shape[0]),
                        "model_mae": mae(residual_eval["actual_total"], residual_eval["predicted_total"]),
                        "market_benchmark_mae": mae(residual_eval["actual_total"], residual_eval["total_line"]),
                        **roi_at_minus_110(residual_eval["edge"], residual_eval["actual_total"] - residual_eval["total_line"])})
        residual_eval["actual_total_over_margin"] = residual_eval["actual_total"] - pd.to_numeric(residual_eval["total_line"], errors="coerce")
        diagnostics.extend(grouped_diagnostics(residual_eval, "season", "edge",
            "actual_total_over_margin", "Market residual model", "Totals"))
        residual_eval.to_csv(OUT / "automated_totals_market_residual_predictions.csv", index=False)
    except Exception as exc:
        message = f"market-residual totals audit failed: {type(exc).__name__}: {exc}"
        audit_warnings.append(message)
        print(f"WARNING: {message}")

    try:
        ats_resid = chronological_ats_residual_backtest(dataset, schedule, min_train_games=MIN_TRAIN_GAMES)
        print("ATS residual output columns:", list(ats_resid.columns))
        ats_eval = ats_resid.merge(
            schedule[["game_id", "season", "home_score", "away_score", "spread_line"]].drop_duplicates("game_id"),
            on="game_id", how="left", validate="one_to_one"
        )
        ats_eval["actual_home_margin"] = pd.to_numeric(ats_eval["home_score"], errors="coerce") - pd.to_numeric(ats_eval["away_score"], errors="coerce")
        ats_eval["edge"] = pd.to_numeric(ats_eval["predicted_ats_residual"], errors="coerce")
        metrics.append({"market": "ATS", "model": "ATS residual model", "games": int(ats_eval.dropna(subset=["spread_line", "actual_home_margin", "edge"]).shape[0]),
                        "model_mae": mae(ats_eval["actual_home_margin"] - ats_eval["spread_line"], ats_eval["edge"]),
                        "market_benchmark_mae": mae(ats_eval["actual_home_margin"], ats_eval["spread_line"]),
                        **roi_at_minus_110(ats_eval["edge"], ats_eval["actual_home_margin"] - ats_eval["spread_line"])})
        ats_eval["actual_ats_cover_margin"] = ats_eval["actual_home_margin"] - pd.to_numeric(ats_eval["spread_line"], errors="coerce")
        diagnostics.extend(grouped_diagnostics(ats_eval, "season", "edge",
            "actual_ats_cover_margin", "ATS residual model", "ATS"))
        ats_eval.to_csv(OUT / "automated_ats_residual_predictions.csv", index=False)
    except Exception as exc:
        message = f"ATS residual audit failed: {type(exc).__name__}: {exc}"
        audit_warnings.append(message)
        print(f"WARNING: {message}")

    try:
        anchored = chronological_market_anchored_ats_backtest(dataset, schedule, min_train_games=MIN_TRAIN_GAMES)
        print("Market-anchored ATS output columns:", list(anchored.columns))
        anchored_eval = anchored.merge(
            schedule[["game_id", "season", "home_score", "away_score", "spread_line"]].drop_duplicates("game_id"),
            on="game_id", how="left", validate="one_to_one"
        )
        anchored_eval["actual_home_margin"] = pd.to_numeric(anchored_eval["home_score"], errors="coerce") - pd.to_numeric(anchored_eval["away_score"], errors="coerce")
        anchored_eval["edge"] = pd.to_numeric(anchored_eval["market_anchored_home_margin"], errors="coerce") - pd.to_numeric(anchored_eval["spread_line"], errors="coerce")
        metrics.append({"market": "ATS", "model": "Market-anchored ATS model", "games": int(anchored_eval.dropna(subset=["spread_line", "actual_home_margin", "market_anchored_home_margin"]).shape[0]),
                        "model_mae": mae(anchored_eval["actual_home_margin"], anchored_eval["market_anchored_home_margin"]),
                        "market_benchmark_mae": mae(anchored_eval["actual_home_margin"], anchored_eval["spread_line"]),
                        **roi_at_minus_110(anchored_eval["edge"], anchored_eval["actual_home_margin"] - anchored_eval["spread_line"])})
        anchored_eval["actual_ats_cover_margin"] = anchored_eval["actual_home_margin"] - pd.to_numeric(anchored_eval["spread_line"], errors="coerce")
        diagnostics.extend(grouped_diagnostics(anchored_eval, "season", "edge",
            "actual_ats_cover_margin", "Market-anchored ATS model", "ATS"))
        anchored_eval.to_csv(OUT / "automated_ats_market_anchored_predictions.csv", index=False)
    except Exception as exc:
        message = f"market-anchored ATS audit failed: {type(exc).__name__}: {exc}"
        audit_warnings.append(message)
        print(f"WARNING: {message}")

    metric_df = pd.DataFrame(metrics)
    metric_df.insert(0, "model_version", MODEL_VERSION)
    diagnostic_df = pd.DataFrame(diagnostics)
    if not diagnostic_df.empty:
        diagnostic_df.insert(0, "model_version", MODEL_VERSION)
        diagnostic_df.to_csv(OUT / "automated_historical_diagnostics.csv", index=False)
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
            "diagnostic_rows": int(len(diagnostic_df)),
            "warnings": audit_warnings,
            "note": "Historical research only. Public schedule lines are not verified sportsbook-timestamp records. Fixed -110 ROI uses a 3.5-point threshold for point-valued model edges. Residual-model adjustments are much smaller and are not directly comparable to score-model edges."
        }, indent=2),
        encoding="utf-8",
    )
    print(metric_df.to_string(index=False))
    print("Saved automated audit outputs to research/reports/")


if __name__ == "__main__":
    main()
