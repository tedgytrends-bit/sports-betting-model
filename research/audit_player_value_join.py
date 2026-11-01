#!/usr/bin/env python3
"""Audit whether historical player stats can be joined to injury reports.

Research-only validation. Does not create model features or change projections.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = (2021,  2022, 2023, 2024, 2025, 2026)
HEADERS = {"User-Agent": "sports-betting-model-player-value-join-audit/1.0"}


def load_stats(season: int) -> pd.DataFrame:
    url = (
        "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
        f"stats_player_week_{season}.parquet"
    )
    response = requests.get(url, headers=HEADERS, timeout=(15, 120))
    response.raise_for_status()
    frame = pd.read_parquet(BytesIO(response.content), engine="pyarrow")
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce")
    frame["week"] = pd.to_numeric(frame["week"], errors="coerce")
    frame["player_id"] = frame["player_id"].astype("string").str.strip()
    frame["team"] = frame["team"].astype("string").str.upper().str.strip()
    return frame


def main() -> None:
    from injury_model import load_injury_reports, _normalize_reports

    stats_frames = [load_stats(season) for season in SEASONS]
    stats = pd.concat(stats_frames, ignore_index=True, sort=False)
    reports = _normalize_reports(load_injury_reports(SEASONS))
    reports["season"] = pd.to_numeric(reports["season"], errors="coerce")
    reports["week"] = pd.to_numeric(reports["week"], errors="coerce")
    reports["gsis_id"] = reports["gsis_id"].astype("string").str.strip()
    reports["team"] = reports["team"].astype("string").str.upper().str.strip()
    reports["position"] = reports["position"].astype("string").str.upper().str.strip()

    keys = ["season", "week", "team", "player_id"]
    stats_keys = stats[keys + ["position", "player_name"]].drop_duplicates(keys)
    injury = reports.rename(columns={"gsis_id": "player_id"}).copy()
    joined = injury.merge(
        stats_keys, on=keys, how="left", suffixes=("_injury", "_stats"),
        indicator=True,
    )
    joined["position_match"] = (
        joined["position_injury"].astype("string").str.upper()
        == joined["position_stats"].astype("string").str.upper()
    )
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "JOIN_AUDIT_ONLY_NO_MODEL_CHANGES",
        "injury_rows": int(len(injury)),
        "injury_rows_with_player_id": int(injury["player_id"].notna().sum()),
        "rows_matching_stats_by_player_season_week_team": int(joined["_merge"].eq("both").sum()),
        "match_rate_pct": float(100 * joined["_merge"].eq("both").mean()) if len(joined) else None,
        "matched_rows_with_position_agreement": int((joined["_merge"].eq("both") & joined["position_match"]).sum()),
        "matched_rows_with_position_disagreement": int((joined["_merge"].eq("both") & ~joined["position_match"]).sum()),
        "unmatched_rows": int(joined["_merge"].eq("left_only").sum()),
        "unique_injury_players": int(injury["player_id"].nunique()),
        "unique_stats_players": int(stats["player_id"].nunique()),
        "season_coverage": [],
        "interpretation": [
            "A match requires the same player ID, season, week, and team.",
            "A successful join establishes identity and weekly-stat availability, not player value or causal injury impact.",
            "Unmatched rows must not be assigned a zero-value player; they remain unvalued.",
        ],
    }
    for season in SEASONS:
        part = joined[joined["season"] == season]
        summary["season_coverage"].append({
            "season": season,
            "injury_rows": int(len(part)),
            "matched_rows": int(part["_merge"].eq("both").sum()),
            "match_rate_pct": float(100 * part["_merge"].eq("both").mean()) if len(part) else None,
            "position_disagreements": int((part["_merge"].eq("both") & ~part["position_match"]).sum()),
        })

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = OUT / f"player_value_join_audit_{stamp}.json"
    detail_path = OUT / f"player_value_join_detail_{stamp}.csv"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    joined.to_csv(detail_path, index=False)
    print(json.dumps(summary, indent=2))
    print(f"Saved: {report_path}")
    print(f"Saved: {detail_path}")


if __name__ == "__main__":
    main()
