#!/usr/bin/env python3
"""Build a player-level injury shadow projection without changing official records."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset, project_upcoming_efficiency
from injury_model import load_injury_reports
from player_injury_model import build_player_injury_features

OUT = ROOT / "data" / "player_injury_shadow"


def main():
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    reports = load_injury_reports((2021, 2022, 2023, 2024, 2025, 2026))

    base = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    baseline = project_upcoming_efficiency(base, min_train_games=500)
    injury_features, player_detail = build_player_injury_features(schedule, pbp, reports)
    shadow_data = base.merge(injury_features, on="game_id", how="left", validate="one_to_one")
    shadow = project_upcoming_efficiency(shadow_data, min_train_games=500)

    baseline = baseline.rename(columns={
        "projected_home": "baseline_projected_home",
        "projected_away": "baseline_projected_away",
        "projected_total": "baseline_projected_total",
    })
    shadow = shadow.rename(columns={
        "projected_home": "player_injury_projected_home",
        "projected_away": "player_injury_projected_away",
        "projected_total": "player_injury_projected_total",
    })
    keep = ["game_id", "gameday", "season", "week", "away_team", "home_team"]
    result = baseline[keep + ["baseline_projected_home", "baseline_projected_away", "baseline_projected_total"]].merge(
        shadow[keep + ["player_injury_projected_home", "player_injury_projected_away", "player_injury_projected_total"]],
        on=keep, how="inner", validate="one_to_one",
    )
    result["home_adjustment_points"] = result["player_injury_projected_home"] - result["baseline_projected_home"]
    result["away_adjustment_points"] = result["player_injury_projected_away"] - result["baseline_projected_away"]
    result["total_adjustment_points"] = result["player_injury_projected_total"] - result["baseline_projected_total"]
    result["captured_at_utc"] = captured.isoformat().replace("+00:00", "Z")
    result["model_version"] = "player-injury-shadow-0.1"
    result["status"] = "EXPERIMENTAL_SHADOW_NOT_OFFICIAL"
    result["training_games"] = shadow.get("training_games", pd.Series(dtype=float)).iloc[0] if not shadow.empty else None

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    projection_path = OUT / f"player_injury_shadow_{stamp}.csv"
    detail_path = OUT / f"player_injury_player_audit_{stamp}.csv"
    result.to_csv(projection_path, index=False)
    player_detail.to_csv(detail_path, index=False)
    print(f"Saved {len(result)} shadow projections: {projection_path}")
    print(f"Saved {len(player_detail)} player-level injury records: {detail_path}")
    print("Official efficiency projections and prospective grading are unchanged.")
    if not player_detail.empty:
        print(player_detail.groupby(["team", "position", "valuation_status"]).size().to_string())


if __name__ == "__main__":
    main()
