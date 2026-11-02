"""Research-only audit of historical injury report availability by game.

This diagnoses feed coverage and point-in-time filtering. It does not change
model features, projections, production behavior, or official prospective data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import load_schedule_data
from injury_model import load_injury_reports, injury_coverage_diagnostics

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)  # Match the four-model experiment window.
OUT = ROOT / "data" / "injury_coverage_audit"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    schedule = load_schedule_data()
    reports = load_injury_reports(SEASONS)
    detail = injury_coverage_diagnostics(schedule, reports)

    if detail.empty:
        raise RuntimeError("Injury coverage diagnostics returned no scheduled games.")

    detail["season"] = detail["Season/week/type"].str.split("/").str[0].astype(int)
    detail["week"] = detail["Season/week/type"].str.split("/").str[1].astype(int)
    detail["both_teams_covered"] = (
        detail["Home report rows"].gt(0) & detail["Away report rows"].gt(0)
    )
    detail["either_team_covered"] = (
        detail["Home report rows"].gt(0) | detail["Away report rows"].gt(0)
    )

    seasonal = (
        detail.groupby("season", as_index=False)
        .agg(
            scheduled_games=("Matchup", "size"),
            both_teams_covered=("both_teams_covered", "sum"),
            at_least_one_team_covered=("either_team_covered", "sum"),
            no_team_covered=("either_team_covered", lambda s: int((~s).sum())),
            games_with_pregame_feed_rows=("Rows available pre-kickoff", lambda s: int(s.gt(0).sum())),
            games_with_snapshot=("Snapshot file found", "sum"),
        )
    )
    seasonal["both_team_coverage_pct"] = (
        100 * seasonal["both_teams_covered"] / seasonal["scheduled_games"]
    ).round(2)

    # Explain coverage failures by season using feed and timing diagnostics.
    cause = (
        detail.groupby("season", as_index=False)
        .agg(
            total_raw_feed_rows=("Feed rows season/week", "sum"),
            rows_after_game_type_match=("Rows after game-type match", "sum"),
            rows_with_valid_timestamps=("Rows with valid timestamps", "sum"),
            rows_available_pregame=("Rows available pre-kickoff", "sum"),
            games_snapshot_after_kickoff=("Snapshot timing", lambda s: int(s.eq("After kickoff").sum())),
            games_snapshot_timestamp_unavailable=("Snapshot timing", lambda s: int(s.eq("Timestamp unavailable").sum())),
        )
    )
    seasonal = seasonal.merge(cause, on="season", how="left")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    detail_path = OUT / f"injury_coverage_game_detail_{stamp}.csv"
    seasonal_path = OUT / f"injury_coverage_by_season_{stamp}.csv"
    report_path = OUT / f"injury_coverage_report_{stamp}.json"
    detail.to_csv(detail_path, index=False)
    seasonal.to_csv(seasonal_path, index=False)

    report = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS),
        "scheduled_games_diagnosed": int(len(detail)),
        "season_summary": seasonal.to_dict(orient="records"),
        "diagnostic_definitions": {
            "both_teams_covered": "At least one eligible pregame report row for both teams.",
            "games_with_pregame_feed_rows": "At least one timestamped live-feed row remained after kickoff and game-type filtering.",
            "snapshot": "Saved snapshot metadata is evaluated separately from the live feed.",
        },
        "cautions": [
            "A report row does not establish that every player or injury was reported.",
            "No report is missing information, not evidence of a healthy roster.",
            "Coverage diagnostics do not alter model predictions or official prospective results.",
        ],
        "files": {
            "game_detail": str(detail_path),
            "season_summary": str(seasonal_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
