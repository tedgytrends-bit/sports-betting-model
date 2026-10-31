#!/usr/bin/env python3
"""Audit historical player-level injury and prior-usage coverage (research only).

This audit does not assign injury point values or modify model projections. It
quantifies whether the 2021-present injury/PBP sources can support player-level,
position-aware calibration and whether prior-season history is available.
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

from model import load_schedule_data, load_pbp
from injury_model import load_injury_reports, _normalize_reports

OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
PLAYER_EVENT_COLUMNS = {
    "passer_player_id": ("posteam", "pass_attempt_or_sack"),
    "rusher_player_id": ("posteam", "rush"),
    "receiver_player_id": ("posteam", "target"),
    "solo_tackle_1_player_id": ("defteam", "solo_tackle_1"),
    "solo_tackle_2_player_id": ("defteam", "solo_tackle_2"),
    "sack_player_id": ("defteam", "sack"),
    "interception_player_id": ("defteam", "interception"),
}
POSITION_GROUPS = {
    "QB": {"QB"},
    "OL": {"C", "G", "OG", "OT", "T", "OL", "LT", "LG", "RG", "RT"},
    "SKILL": {"RB", "FB", "WR", "TE"},
    "DEFENSE": {"DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "DB", "S", "FS", "SS"},
}


def main():
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    print("Loading 2021-present schedule, PBP, and injury reports...")
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = _normalize_reports(load_injury_reports(SEASONS))

    # Build player-event counts with game dates so historical carryover can be audited.
    game_dates = schedule[["game_id", "gameday", "season", "week"]].drop_duplicates("game_id")
    game_dates["gameday"] = pd.to_datetime(game_dates["gameday"], errors="coerce")
    event_frames = []
    for player_col, (team_col, event_name) in PLAYER_EVENT_COLUMNS.items():
        if player_col not in pbp.columns or team_col not in pbp.columns:
            continue
        cols = ["game_id", player_col, team_col]
        part = pbp[cols].dropna(subset=[player_col, team_col]).copy()
        part["player_id"] = part[player_col].astype(str).str.strip()
        part["team"] = part[team_col].astype(str).str.upper().str.strip()
        part["event_type"] = event_name
        event_frames.append(part[["game_id", "player_id", "team", "event_type"]])
    if not event_frames:
        raise RuntimeError("No player-level PBP event columns were available.")
    events = pd.concat(event_frames, ignore_index=True)
    events = events.merge(game_dates, on="game_id", how="left", validate="many_to_one")
    events = events.dropna(subset=["gameday"])
    usage = (events.groupby(["player_id", "team", "game_id", "gameday", "season", "week", "event_type"])
             .size().rename("events").reset_index())

    reports["gsis_id"] = reports.get("gsis_id", pd.Series("", index=reports.index)).astype("string").str.strip()
    reports["position"] = reports["position"].astype(str).str.upper().str.strip()
    reports["team"] = reports["team"].astype(str).str.upper().str.strip()
    reports["report_status"] = reports["report_status"].astype(str).str.upper().str.strip()
    reports["practice_status"] = reports["practice_status"].astype(str).str.upper().str.strip()
    reports["season"] = pd.to_numeric(reports["season"], errors="coerce")
    reports["week"] = pd.to_numeric(reports["week"], errors="coerce")

    # One row per player/team/week/season for coverage counts.
    id_valid = reports["gsis_id"].notna() & reports["gsis_id"].ne("")
    reports["has_player_id"] = id_valid
    reports["position_group"] = reports["position"].map(
        lambda p: next((g for g, ps in POSITION_GROUPS.items() if p in ps), "OTHER")
    )
    player_rows = reports[id_valid].copy()
    player_rows = player_rows.drop_duplicates(["season", "week", "team", "gsis_id"], keep="last")

    # For every injury row, compare usage available by the start of the target week
    # (the current implementation) with all usage strictly before the game date,
    # including prior seasons. This is an availability audit, not a player-value score.
    schedule_key = schedule[["season", "week", "home_team", "away_team", "gameday"]].copy()
    schedule_key["season"] = pd.to_numeric(schedule_key["season"], errors="coerce")
    schedule_key["week"] = pd.to_numeric(schedule_key["week"], errors="coerce")
    schedule_key["gameday"] = pd.to_datetime(schedule_key["gameday"], errors="coerce")
    schedule_key["teams"] = schedule_key.apply(
        lambda r: [str(r["home_team"]).upper(), str(r["away_team"]).upper()], axis=1
    )
    rows = []
    for _, player in player_rows.iterrows():
        season, week = player["season"], player["week"]
        if pd.isna(season) or pd.isna(week):
            continue
        candidates = schedule_key[
            schedule_key["season"].eq(season) & schedule_key["week"].eq(week)
            & schedule_key["teams"].map(lambda t: player["team"] in t)
        ]
        if candidates.empty:
            continue
        target_date = candidates["gameday"].min()
        if pd.isna(target_date):
            continue
        p_usage = usage[(usage["player_id"] == str(player["gsis_id"]))
                        & (usage["team"] == player["team"])]
        prior_same_season = p_usage[
            p_usage["season"].eq(season) & p_usage["week"].lt(week)
        ]
        prior_all = p_usage[p_usage["gameday"] < target_date]
        rows.append({
            "season": int(season), "week": int(week), "team": player["team"],
            "player_id": str(player["gsis_id"]), "player_name": player.get("player_name", player.get("full_name", "")),
            "position": player["position"], "position_group": player["position_group"],
            "report_status": player["report_status"], "practice_status": player["practice_status"],
            "same_season_prior_events": int(prior_same_season["events"].sum()),
            "all_prior_seasons_events": int(prior_all["events"].sum()),
            "has_same_season_prior_usage": bool(not prior_same_season.empty),
            "has_any_prior_usage_including_previous_seasons": bool(not prior_all.empty),
            "prior_season_carryover_adds_history": bool(prior_all["events"].sum() > prior_same_season["events"].sum()),
        })
    detail = pd.DataFrame(rows)

    season_rows = []
    for season in SEASONS:
        raw = reports[reports["season"].eq(season)]
        unique = player_rows[player_rows["season"].eq(season)]
        d = detail[detail["season"].eq(season)] if not detail.empty else pd.DataFrame()
        season_rows.append({
            "season": season,
            "injury_report_rows": int(len(raw)),
            "rows_with_gsis_id_pct": float(100 * raw["has_player_id"].mean()) if len(raw) else None,
            "unique_player_week_rows": int(len(unique)),
            "unique_players": int(unique["gsis_id"].nunique()) if len(unique) else 0,
            "QB_player_week_rows": int(unique["position_group"].eq("QB").sum()),
            "OL_player_week_rows": int(unique["position_group"].eq("OL").sum()),
            "skill_player_week_rows": int(unique["position_group"].eq("SKILL").sum()),
            "defense_player_week_rows": int(unique["position_group"].eq("DEFENSE").sum()),
            "other_position_rows": int(unique["position_group"].eq("OTHER").sum()),
            "rows_with_same_season_prior_pbp_usage_pct": float(100 * d["has_same_season_prior_usage"].mean()) if len(d) else None,
            "rows_with_prior_usage_including_previous_seasons_pct": float(100 * d["has_any_prior_usage_including_previous_seasons"].mean()) if len(d) else None,
            "rows_gaining_history_from_prior_seasons": int(d["prior_season_carryover_adds_history"].sum()) if len(d) else 0,
        })

    summary = {
        "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
        "seasons": list(SEASONS),
        "status": "DATA_AUDIT_ONLY_NO_MODEL_CHANGES",
        "source_rows": {
            "schedule_games": int(len(schedule)),
            "pbp_rows": int(len(pbp)),
            "player_event_rows": int(len(events)),
            "injury_report_rows": int(len(reports)),
            "injury_rows_with_gsis_id": int(reports["has_player_id"].sum()),
            "player_week_detail_rows_audited": int(len(detail)),
        },
        "interpretation": [
            "PBP event counts are participation proxies, not true snap counts or player quality.",
            "Prior-season carryover improves early-season history coverage but does not by itself estimate player value.",
            "OL players are expected to have limited individual attribution in the currently loaded PBP columns.",
            "Official NFL report publication timing and data-provider capture timing are distinct provenance concepts."
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    (OUT / f"player_injury_data_audit_{stamp}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    pd.DataFrame(season_rows).to_csv(OUT / f"player_injury_data_coverage_{stamp}.csv", index=False)
    if not detail.empty:
        detail.to_csv(OUT / f"player_injury_player_usage_audit_{stamp}.csv", index=False)
    print(json.dumps(summary, indent=2))
    print(pd.DataFrame(season_rows).to_string(index=False))
    print("Saved player injury data audit outputs. No model or production projections changed.")


if __name__ == "__main__":
    main()
