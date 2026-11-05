#!/usr/bin/env python3
"""Week 9 QB-aware injury research capture.

Fits the *non-QB* injury model using historical data, then adds one
starter-versus-recent-team-QB EPA adjustment per offense. This prevents counting
QB absence once via position/aggregate injury features and again through EPA.

Research only: NEVER updates published Week 9 frozen projections or records.
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

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset, project_upcoming_efficiency
from injury_model import load_injury_reports, add_injury_features
from qb_epa_model import qb_game_stats, build_qb_epa_board, attach_qb_shifts

OUT = ROOT / "data" / "qb_epa_shadow"
STARTERS = ROOT / "data" / "qb_starters" / "2026_week09_confirmed.csv"
FROZEN = ROOT / "data" / "public_snapshots" / "nfl_week_09_six_model_research_2026-11-04.csv"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)


def main() -> None:
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)

    print("Building QB-neutral (non-QB injury) historical training frame...")
    base = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    no_qb_count = add_injury_features(base, schedule, reports, exclude_qb=True)
    projections = project_upcoming_efficiency(no_qb_count, min_train_games=500)
    selected = projections[
        pd.to_numeric(projections["season"], errors="coerce").eq(2026)
        & pd.to_numeric(projections["week"], errors="coerce").eq(9)
    ].copy()
    if len(selected) != 15 or selected["game_id"].nunique() != 15:
        raise ValueError(f"Expected 15 distinct Week 9 games, got {len(selected)}")
    if not STARTERS.exists():
        raise FileNotFoundError(STARTERS)
    overrides = pd.read_csv(STARTERS, dtype={"qb_id": str}).fillna("")
    required = {"game_id", "team", "qb_id", "qb_name", "source_url", "source_published_at_utc"}
    if not required.issubset(overrides):
        raise ValueError(f"Starter overrides missing: {sorted(required - set(overrides))}")
    # Overrides must predate the game, and must not be quietly replaced by
    # an automatically inferred last-game QB.
    target_dates = selected[["game_id", "gameday"]].copy()
    target_dates["gameday"] = pd.to_datetime(target_dates["gameday"], errors="coerce")
    check = overrides.merge(target_dates, on="game_id", how="left", validate="many_to_one")
    published = pd.to_datetime(check["source_published_at_utc"], utc=True, errors="coerce")
    dates_utc = pd.to_datetime(check["gameday"], utc=True, errors="coerce")
    if published.isna().any() or dates_utc.isna().any() or (published >= dates_utc).any():
        raise ValueError("Starter override must be published strictly before game date")
    active_teams = set()
    for game in selected.itertuples():
        active_teams.update(((game.game_id, game.home_team), (game.game_id, game.away_team)))
    if any((r.game_id, r.team) not in active_teams for r in overrides.itertuples()):
        raise ValueError("Starter override has mismatched game or team")

    print("Building pregame QB EPA rates and team baseline comparisons...")
    summary = qb_game_stats(pbp, schedule)
    board = build_qb_epa_board(summary, schedule, selected, overrides=overrides)
    if len(board) != 30 or board.duplicated(["game_id", "team"]).any():
        raise ValueError("Expected exactly 30 unique team-QB rows in Week 9")
    baltimore = board[
        board["game_id"].eq("2026_09_JAX_BAL") & board["team"].eq("BAL")
    ]
    if len(baltimore) != 1 or baltimore.iloc[0]["qb_name"] != "Joe Fagnano":
        raise ValueError("Confirmed Fagnano starter was not used")

    adjusted = attach_qb_shifts(selected, board)
    if adjusted["game_id"].nunique() != 15:
        raise ValueError("QB adjustment dropped games")
    adjusted["model"] = "injury_qb_epa_v2_research"
    adjusted["model_status"] = "RESEARCH_ONLY_UNCALIBRATED"
    adjusted["captured_at_utc"] = captured.isoformat()
    adjusted["non_qb_injury_baseline_home"] = adjusted["projected_home"]
    adjusted["non_qb_injury_baseline_away"] = adjusted["projected_away"]
    adjusted["projected_home"] = adjusted["home_qb_adjusted"]
    adjusted["projected_away"] = adjusted["away_qb_adjusted"]
    adjusted["projected_total"] = adjusted["projected_total_qb_adjusted"]
    adjusted["projected_home_margin"] = adjusted["projected_home"] - adjusted["projected_away"]

    # Preserve a read-only comparison to the original; NEVER overwrite it.
    if FROZEN.exists():
        frozen = pd.read_csv(FROZEN)
        original = frozen[frozen["model"].eq("injury")][
            ["game_id", "projected_home", "projected_away", "projected_total"]
        ].rename(columns={
            "projected_home": "original_injury_home",
            "projected_away": "original_injury_away",
            "projected_total": "original_injury_total",
        })
        adjusted = adjusted.merge(original, on="game_id", how="left", validate="one_to_one")

    # Attach named QB evidence to the score table for a transparent two-QB view.
    cols = [
        "game_id", "qb_name", "qb_id", "starter_source", "source_url",
        "confidence", "qb_prior_dropbacks", "qb_shrunk_epa_per_dropback",
        "team_recent_qb_epa_per_dropback", "qb_delta_epa_per_dropback",
        "qb_point_shift_experimental", "starter_recent_team_dropback_share",
    ]
    for side in ("home", "away"):
        part = board[board["side"].eq(side)][cols].copy()
        part = part.rename(columns={c: f"{side}_{c}" for c in cols if c != "game_id"})
        adjusted = adjusted.merge(part, on="game_id", how="left", validate="one_to_one")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    qbf = OUT / f"week09_qb_epa_{stamp}.csv"
    projf = OUT / f"week09_injury_qb_epa_shadow_{stamp}.csv"
    board.to_csv(qbf, index=False)
    adjusted.to_csv(projf, index=False)
    manifest = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "timestamp_utc": captured.isoformat(),
        "model": "injury_qb_epa_v2_research",
        "point_shift": "(shrunken starter EPA - recent team QB-mix EPA) times the non-starter share of team dropbacks times expected dropbacks/game",
        "starter_sources": "Manual source-verified override; otherwise automatically inferred last-game primary passer, expressly unverified",
        "non_qb_injury_features": "All QB rows excluded from QB count AND general injury/practice counts before refit",
        "training": "Chronological historical schedule/PBP and injury reports. Today's game EPA excluded.",
        "conservative_prior": "120 equivalent league QB dropbacks; 12-QB-game half-life for up to 24 previous QB appearances",
        "warning": "EPA point conversion is unvalidated. Shadow outputs must not update official Week 9 frozen projections or records.",
        "games": int(len(adjusted)),
        "qb_rows": int(len(board)),
        "confirmed_qb_rows": int(board.starter_source.eq("verified_pregame").sum()),
        "unverified_qb_rows": int(board.starter_source.eq("inferred_previous_primary_passer").sum()),
        "unknown_qb_rows": int(board.starter_source.eq("unknown_no_pregame_evidence").sum()),
        "output_qb": str(qbf.relative_to(ROOT)),
        "output_projections": str(projf.relative_to(ROOT)),
    }
    (OUT / f"week09_qb_epa_manifest_{stamp}.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    print(adjusted.loc[adjusted.game_id.eq("2026_09_JAX_BAL"), [
        "game_id", "away_qb_name", "home_qb_name", "away_qb_delta_epa_per_dropback",
        "home_qb_delta_epa_per_dropback", "projected_away", "projected_home",
        "original_injury_away", "original_injury_home",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
