#!/usr/bin/env python3
"""Audit whether historical player stats can be joined to injury reports.

Research-only validation. Does not create model features or change projections.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
# GitHub Actions executes this file with research/ as sys.path[0]. Add the
# repository root so top-level project modules (for example injury_model.py)
# can be imported reliably both in CI and when run locally.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    frame["season_type"] = frame["season_type"].fillna("REG").astype("string").str.upper().str.strip()
    frame["season_type"] = frame["season_type"].replace({
        "REGULAR": "REG", "POSTSEASON": "POST", "PRESEASON": "PRE",
        "WC": "POST", "DIV": "POST", "CON": "POST", "SB": "POST",
    })
    return frame


def normalize_position(value: object) -> str:
    """Map source-specific position labels into comparable broad NFL groups."""
    raw = str(value or "").strip().upper()
    aliases = {
        "SAF": "S", "FS": "S", "SS": "S",
        "OT": "T", "OLB": "LB", "ILB": "LB", "MLB": "LB",
        "NT": "DT", "DL": "DT",
        "DB": "DB",
    }
    return aliases.get(raw, raw)


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
    reports["season_type"] = reports["season_type"].fillna("REG").astype("string").str.upper().str.strip()
    reports["season_type"] = reports["season_type"].replace({
        "REGULAR": "REG", "POSTSEASON": "POST", "PRESEASON": "PRE",
        "WC": "POST", "DIV": "POST", "CON": "POST", "SB": "POST",
    })

    keys = ["season", "week", "season_type", "team", "player_id"]
    stats_keys = stats[keys + ["position", "player_name"]].drop_duplicates(keys)
    player_week_keys = stats[["season", "week", "season_type", "player_id"]].drop_duplicates()
    team_keys = stats[["season", "week", "season_type", "player_id", "team"]].drop_duplicates()
    injury = reports.rename(columns={"gsis_id": "player_id"}).copy()
    joined = injury.merge(
        stats_keys, on=keys, how="left", suffixes=("_injury", "_stats"),
        indicator=True,
    )
    joined["position_match"] = (
        joined["position_injury"].map(normalize_position)
        == joined["position_stats"].map(normalize_position)
    )
    joined = joined.merge(player_week_keys.assign(player_week_seen=True), on=["season", "week", "season_type", "player_id"], how="left")
    joined = joined.merge(team_keys.assign(player_week_team_seen=True), on=["season", "week", "season_type", "player_id", "team"], how="left")
    joined["player_week_seen"] = joined["player_week_seen"].fillna(False).astype(bool)
    joined["player_week_team_seen"] = joined["player_week_team_seen"].fillna(False).astype(bool)
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "JOIN_AUDIT_ONLY_NO_MODEL_CHANGES",
        "injury_rows": int(len(injury)),
        "injury_rows_with_player_id": int(injury["player_id"].notna().sum()),
        "rows_matching_stats_by_player_season_week_type_team": int(joined["_merge"].eq("both").sum()),
        "rows_with_player_stats_same_season_week_type_any_team": int(joined["player_week_seen"].sum()),
        "rows_with_player_stats_same_season_week_type_and_team": int(joined["player_week_team_seen"].sum()),
        "match_rate_pct": float(100 * joined["_merge"].eq("both").mean()) if len(joined) else None,
        "matched_rows_with_position_agreement": int((joined["_merge"].eq("both") & joined["position_match"]).sum()),
        "matched_rows_with_position_disagreement": int((joined["_merge"].eq("both") & ~joined["position_match"]).sum()),
        "unmatched_rows": int(joined["_merge"].eq("left_only").sum()),
        "unique_injury_players": int(injury["player_id"].nunique()),
        "unique_stats_players": int(stats["player_id"].nunique()),
        "season_coverage": [],
        "team_mismatch_rows": int((joined["player_week_seen"] & ~joined["player_week_team_seen"]).sum()),
        "no_weekly_stats_rows": int((~joined["player_week_seen"]).sum()),
        "position_coverage": [],
        "status_coverage": [],
        "position_disagreement_pairs": [],
        "position_normalization_note": "Common aliases SAF/FS/SS->S, OT->T, OLB/ILB/MLB->LB, NT/DL->DT are normalized for comparison.",
        "season_type_coverage": [],
        "interpretation": [
            "A strict match requires player ID, season, week, season type, and team.",
            "A successful join establishes identity and weekly-stat availability, not player value or causal injury impact.",
            "Players absent from weekly statistical output are not assumed to have zero value; they remain unvalued.",
            "Same-player-week records with a different team are flagged separately.",
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
            "same_player_week_any_team": int(part["player_week_seen"].sum()),
            "team_mismatch_rows": int((part["player_week_seen"] & ~part["player_week_team_seen"]).sum()),
            "no_weekly_stats_rows": int((~part["player_week_seen"]).sum()),
        })

    for col, target in (("position_injury", "position_coverage"), ("report_status", "status_coverage")):
        if col in joined.columns:
            grouped = joined.groupby(col, dropna=False).agg(
                injury_rows=("player_id", "size"),
                strict_matches=("_merge", lambda x: int(x.eq("both").sum())),
                same_player_week=("player_week_seen", "sum"),
                team_mismatches=("player_week_team_seen", lambda x: int((joined.loc[x.index, "player_week_seen"] & ~x).sum())),
            ).reset_index()
            summary[target] = grouped.rename(columns={col: "category"}).to_dict(orient="records")

    disagreements = joined[joined["_merge"].eq("both") & ~joined["position_match"]]
    if len(disagreements):
        pairs = disagreements.groupby(["position_injury", "position_stats"], dropna=False).size().reset_index(name="rows")
        summary["position_disagreement_pairs"] = pairs.sort_values("rows", ascending=False).head(40).to_dict(orient="records")

    season_types = joined.groupby(["season_type"], dropna=False).agg(
        injury_rows=("player_id", "size"),
        strict_matches=("_merge", lambda x: int(x.eq("both").sum())),
    ).reset_index()
    summary["season_type_coverage"] = season_types.to_dict(orient="records")

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
