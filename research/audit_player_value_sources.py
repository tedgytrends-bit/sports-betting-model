#!/usr/bin/env python3
"""Audit nflverse weekly player stats and participation coverage (research only).

Downloads the official per-season releases and reports schema, game/player coverage,
and whether participation data can identify players on the field. No model features
or production projections are changed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
PARTICIPATION_SEASONS = (2021, 2022, 2023, 2024, 2025)
HEADERS = {"User-Agent": "sports-betting-model-player-value-audit/1.0"}
TIMEOUT = (15, 120)


def read_release(url: str) -> pd.DataFrame:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    from io import BytesIO
    return pd.read_parquet(BytesIO(response.content), engine="pyarrow")


def load_player_stats(season: int) -> pd.DataFrame:
    url = (
        "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
        f"stats_player_week_{season}.parquet"
    )
    frame = read_release(url)
    frame["__source_url"] = url
    return frame


def load_participation(season: int) -> pd.DataFrame:
    url = (
        "https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/"
        f"pbp_participation_{season}.parquet"
    )
    frame = read_release(url)
    frame["__source_url"] = url
    return frame


def first_present(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in frame.columns), None)


def main() -> None:
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    season_rows, errors, schemas = [], [], {}
    stats_frames = []
    participation_frames = []

    for season in SEASONS:
        try:
            frame = load_player_stats(season)
            stats_frames.append(frame)
            pid = first_present(frame, ("player_id", "gsis_id"))
            team = first_present(frame, ("recent_team", "team"))
            season_col = first_present(frame, ("season",))
            week = first_present(frame, ("week",))
            schemas[f"player_stats_{season}"] = list(frame.columns)
            season_rows.append({
                "season": season, "source": "weekly_player_stats",
                "rows": int(len(frame)),
                "unique_player_ids": int(frame[pid].nunique()) if pid else None,
                "player_id_column": pid, "team_column": team,
                "game_or_week_keys_present": bool(season_col and week),
                "has_position": "position" in frame.columns,
                "has_offensive_production": any(c in frame.columns for c in
                    ("passing_yards", "rushing_yards", "receiving_yards", "targets")),
                "status": "loaded",
            })
        except Exception as exc:
            errors.append({"season": season, "source": "weekly_player_stats",
                           "error": f"{type(exc).__name__}: {exc}"})
            season_rows.append({"season": season, "source": "weekly_player_stats",
                                "status": "failed", "error": str(exc)})

    for season in PARTICIPATION_SEASONS:
        try:
            frame = load_participation(season)
            participation_frames.append(frame)
            schemas[f"participation_{season}"] = list(frame.columns)
            game_col = first_present(frame, ("nflverse_game_id", "game_id"))
            play_col = first_present(frame, ("play_id",))
            players_col = first_present(frame, ("players_on_play",))
            off_col = first_present(frame, ("offense_players",))
            def_col = first_present(frame, ("defense_players",))
            season_rows.append({
                "season": season, "source": "play_participation",
                "rows": int(len(frame)),
                "unique_games": int(frame[game_col].nunique()) if game_col else None,
                "has_play_key": bool(play_col),
                "players_on_play_column": players_col,
                "offense_players_column": off_col,
                "defense_players_column": def_col,
                "status": "loaded",
            })
        except Exception as exc:
            errors.append({"season": season, "source": "play_participation",
                           "error": f"{type(exc).__name__}: {exc}"})
            season_rows.append({"season": season, "source": "play_participation",
                                "status": "failed", "error": str(exc)})

    stats = pd.concat(stats_frames, ignore_index=True, sort=False) if stats_frames else pd.DataFrame()
    participation = (
        pd.concat(participation_frames, ignore_index=True, sort=False)
        if participation_frames else pd.DataFrame()
    )
    summary = {
        "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
        "status": "SOURCE_COVERAGE_AUDIT_ONLY_NO_MODEL_CHANGES",
        "player_stats_seasons_requested": list(SEASONS),
        "participation_seasons_requested": list(PARTICIPATION_SEASONS),
        "player_stats_rows_loaded": int(len(stats)),
        "participation_play_rows_loaded": int(len(participation)),
        "player_stats_columns": list(stats.columns) if not stats.empty else [],
        "participation_columns": list(participation.columns) if not participation.empty else [],
        "errors": errors,
        "interpretation": [
            "Weekly player statistics provide historical player-level production; use only weeks strictly before the target kickoff.",
            "Participation identifies players on the field and may support position/role and offensive-line opportunity coverage.",
            "Participation releases are audited through 2025; 2026 participation is not assumed available.",
            "This audit measures source coverage only and does not infer player quality, replacement value, or causal injury impact."
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    (OUT / f"player_value_source_audit_{stamp}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    pd.DataFrame(season_rows).to_csv(
        OUT / f"player_value_source_coverage_{stamp}.csv", index=False
    )
    (OUT / f"player_value_source_schemas_{stamp}.json").write_text(
        json.dumps(schemas, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(pd.DataFrame(season_rows).to_string(index=False))
    if errors:
        raise RuntimeError(f"{len(errors)} source download(s) failed; see audit output.")
    print("Player-value source audit completed. No model or production projections changed.")


if __name__ == "__main__":
    main()
