#!/usr/bin/env python3
"""Capture daily prospective projections from the play-by-play efficiency model.

This is intentionally separate from the lightweight six-hour market snapshot job.
Predictions are saved as immutable, timestamped rows; they are not overwritten.
"""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset, project_upcoming_efficiency

OUT = Path("data/prospective_ats_tracking")


def main():
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    features = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    projections = project_upcoming_efficiency(features, min_train_games=500)
    if projections.empty:
        print("Efficiency model returned no upcoming projections; no file saved.")
        return

    projections["gameday"] = pd.to_datetime(projections["gameday"], errors="coerce", utc=True)
    now = pd.Timestamp(captured)
    projections = projections[
        projections["gameday"].notna()
        & (projections["gameday"] >= now.normalize())
        & (projections["home_team"].notna())
        & (projections["away_team"].notna())
    ].copy()
    if projections.empty:
        print("No upcoming games in the efficiency projection output; no file saved.")
        return

    market = schedule[["game_id", "spread_line", "total_line", "home_score", "away_score"]].drop_duplicates("game_id")
    market["spread_line"] = pd.to_numeric(market["spread_line"], errors="coerce")
    market["total_line"] = pd.to_numeric(market["total_line"], errors="coerce")
    projections = projections.merge(market, on="game_id", how="left", validate="one_to_one")
    projections = projections[
        projections["home_score"].isna() | projections["away_score"].isna()
    ].copy()
    if projections.empty:
        print("All projected games already have scores; no file saved.")
        return

    # Audit convention: predicted home margin = home points minus away points.
    # The model's model_home_spread uses the opposite sign, so do not copy it.
    projections["model_predicted_home_margin"] = (
        pd.to_numeric(projections["projected_home"], errors="coerce")
        - pd.to_numeric(projections["projected_away"], errors="coerce")
    )
    projections["model_projected_total"] = pd.to_numeric(
        projections["projected_total"], errors="coerce"
    )
    projections["model_ats_edge"] = (
        projections["model_predicted_home_margin"] - projections["spread_line"]
    )
    projections["model_total_edge"] = (
        projections["model_projected_total"] - projections["total_line"]
    )
    projections["captured_at_utc"] = captured.isoformat().replace("+00:00", "Z")
    projections["model_version"] = "0.8.0"
    projections["projection_source"] = "nflverse play-by-play efficiency Ridge model"
    projections["note"] = (
        "Frozen efficiency-model projection generated at capture time using completed-game "
        "play-by-play features. Public schedule-feed lines are not verified executable sportsbook "
        "prices. Capture time alone does not prove prediction preceded kickoff."
    )

    columns = [
        "captured_at_utc", "game_id", "season", "week", "gameday",
        "away_team", "home_team", "spread_line", "total_line",
        "projected_home", "projected_away", "model_predicted_home_margin",
        "model_projected_total", "model_ats_edge", "model_total_edge",
        "training_games", "model_version", "projection_source", "note",
    ]
    result = projections[[c for c in columns if c in projections.columns]].copy()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"efficiency_projection_{captured.strftime('%Y%m%dT%H%M%SZ')}.csv"
    result.to_csv(path, index=False)
    print(f"Saved {len(result)} efficiency-model projection rows: {path}")
    print(f"Capture time UTC: {captured.isoformat()}")
    print(f"Rows with spread lines: {int(result['spread_line'].notna().sum())}")
    print(f"Rows with totals: {int(result['total_line'].notna().sum())}")


if __name__ == "__main__":
    main()
