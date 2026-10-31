"""Player-level pregame injury features for experimental NFL shadow projections.

Uses individual GSIS IDs and player production from prior play-by-play. These
features are deliberately separate from the official production model until
chronological validation demonstrates incremental value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STATUS_WEIGHT = {"OUT": 1.0, "DOUBTFUL": 0.8, "QUESTIONABLE": 0.4}
POSITION_GROUPS = {
    "qb": {"QB"},
    "skill": {"RB", "FB", "WR", "TE"},
    "ol": {"C", "G", "OG", "OT", "T", "OL", "LT", "LG", "RG", "RT"},
    "defense": {"DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "DB", "S", "FS", "SS"},
}


def _build_usage_index(pbp: pd.DataFrame) -> dict[tuple[int, str], pd.DataFrame]:
    """Aggregate PBP player involvement once, rather than rescanning all plays per game."""
    base_cols = ["season", "week"]
    frames = []
    for col, weight, team_col, prefix in (
        ("passer_player_id", 3.0, "posteam", "OFF|"),
        ("rusher_player_id", 1.0, "posteam", "OFF|"),
        ("receiver_player_id", 1.25, "posteam", "OFF|"),
        ("solo_tackle_1_player_id", 0.35, "defteam", "DEF|"),
        ("solo_tackle_2_player_id", 0.2, "defteam", "DEF|"),
        ("sack_player_id", 1.5, "defteam", "DEF|"),
        ("interception_player_id", 2.0, "defteam", "DEF|"),
    ):
        if col not in pbp.columns or team_col not in pbp.columns:
            continue
        part = pbp[base_cols + [team_col, col]].dropna(subset=[team_col, col]).copy()
        part["season"] = pd.to_numeric(part["season"], errors="coerce")
        part["week"] = pd.to_numeric(part["week"], errors="coerce")
        part = part.dropna(subset=["season", "week"])
        part["player_key"] = prefix + part[col].astype(str)
        part = part.rename(columns={team_col: "team"})
        grouped = part.groupby(["season", "week", "team", "player_key"]).size().rename("events").reset_index()
        grouped["value"] = grouped["events"].astype(float) * weight
        frames.append(grouped[["season", "week", "team", "player_key", "value"]])
    if not frames:
        return {}
    all_usage = pd.concat(frames, ignore_index=True).groupby(
        ["season", "week", "team", "player_key"], as_index=False
    )["value"].sum()
    return {
        (int(season), str(team)): group[["week", "player_key", "value"]].copy()
        for (season, team), group in all_usage.groupby(["season", "team"])
    }


def _player_usage(usage_index: dict, season: int, week: int, team: str) -> dict[str, float]:
    """Sum player involvement strictly before the target week."""
    history = usage_index.get((int(season), str(team)))
    if history is None:
        return {}
    prior = history[history["week"] < week]
    if prior.empty:
        return {}
    totals = prior.groupby("player_key")["value"].sum()
    return totals.to_dict()


def build_player_injury_features(
    schedule: pd.DataFrame,
    pbp: pd.DataFrame,
    reports: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return game-level weighted player absences and a player-by-player audit table.

    Availability weights are transparent status weights, not point penalties.
    Player value is based on prior-season-to-date PBP involvement; OL players remain
    explicitly unvalued where individual PBP attribution is unavailable.
    """
    from injury_model import _normalize_reports, _latest_snapshot_for, _snapshot_is_structurally_valid

    rep = _normalize_reports(reports)
    games = schedule.copy()
    games["season"] = pd.to_numeric(games["season"], errors="coerce")
    games["week"] = pd.to_numeric(games["week"], errors="coerce")
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce")
    rep["gsis_id"] = rep.get("gsis_id", pd.Series("", index=rep.index)).astype("string").str.strip()
    rep["team"] = rep["team"].astype(str).str.upper().str.strip()
    rep["position"] = rep["position"].astype(str).str.upper().str.strip()
    rep["report_status"] = rep["report_status"].astype(str).str.upper().str.strip()
    rep["practice_status"] = rep["practice_status"].astype(str).str.upper().str.strip()
    details, feature_rows = [], []
    usage_index = _build_usage_index(pbp)

    for _, game in games.iterrows():
        if pd.isna(game["season"]) or pd.isna(game["week"]) or pd.isna(game["gameday"]):
            continue
        season, week = int(game["season"]), int(game["week"])
        game_rows = rep[(rep["season"] == season) & (rep["week"] == week)].copy()
        game_type = str(game.get("game_type", game.get("season_type", "REG"))).upper().strip()
        if "season_type" in rep.columns:
            normalized_type = rep["season_type"].astype(str).str.upper().replace({"REGULAR": "REG", "POSTSEASON": "POST"})
            game_rows = game_rows[normalized_type.eq(game_type.replace("REGULAR", "REG").replace("POSTSEASON", "POST"))]
        # A valid committed snapshot is the point-in-time source for the upcoming slate.
        snapshot = _latest_snapshot_for(season, week) if pd.isna(game.get("home_score")) or pd.isna(game.get("away_score")) else None
        if snapshot is not None and _snapshot_is_structurally_valid(snapshot):
            game_rows = _normalize_reports(snapshot)
        elif "date_modified" in game_rows:
            # Historical reports: latest update per player strictly before kickoff.
            kickoff = pd.Timestamp(game["gameday"])
            if "gametime" in game and pd.notna(game.get("gametime")):
                local = pd.to_datetime(f"{kickoff.date()} {game['gametime']}", errors="coerce")
                if pd.notna(local):
                    kickoff = local.tz_localize("America/New_York").tz_convert("UTC").tz_localize(None)
            game_rows["date_modified"] = pd.to_datetime(game_rows["date_modified"], errors="coerce", utc=True).dt.tz_localize(None)
            game_rows = game_rows[game_rows["date_modified"] < kickoff]
            game_rows = game_rows.sort_values("date_modified").drop_duplicates(["team", "gsis_id"], keep="last")

        row = {"game_id": game["game_id"]}
        for side, team_col in (("home", "home_team"), ("away", "away_team")):
            team = str(game[team_col]).upper()
            team_rows = game_rows[game_rows["team"].eq(team)]
            usage = _player_usage(usage_index, season, week, team)
            # Normalize each player's involvement against the team's total so the
            # index is interpretable and not dominated by raw snap volume.
            off_total = sum(v for k, v in usage.items() if k.startswith("OFF|")) or 1.0
            def_total = sum(v for k, v in usage.items() if k.startswith("DEF|")) or 1.0
            missing_off = missing_def = missing_qb = 0.0
            missing_ol = 0
            for _, player in team_rows.iterrows():
                status = str(player.get("report_status", "")).upper().strip()
                practice = str(player.get("practice_status", "")).upper()
                weight = STATUS_WEIGHT.get(status, 0.0)
                if not weight and "DID NOT PARTICIPATE" in practice:
                    weight = 0.2
                elif not weight and "LIMITED" in practice:
                    weight = 0.1
                if weight <= 0:
                    continue
                pid = str(player.get("gsis_id", "")).strip()
                pos = str(player.get("position", "")).upper().strip()
                is_defense = pos in POSITION_GROUPS["defense"]
                usage_value = usage.get(("DEF|" if is_defense else "OFF|") + pid, 0.0)
                role_value = usage_value / (def_total if is_defense else off_total)
                valued = pos not in POSITION_GROUPS["ol"] and usage_value > 0
                impact_index = role_value * weight if valued else np.nan
                if pos == "QB":
                    missing_qb += role_value * weight
                elif pos in POSITION_GROUPS["skill"]:
                    missing_off += role_value * weight
                elif pos in POSITION_GROUPS["defense"]:
                    missing_def += role_value * weight
                elif pos in POSITION_GROUPS["ol"]:
                    missing_ol += 1
                details.append({
                    "game_id": game["game_id"], "team": team, "side": side,
                    "player_id": pid, "player_name": str(player.get("player_name", player.get("full_name", ""))),
                    "position": pos, "report_status": status, "practice_status": practice,
                    "availability_weight": weight, "prior_pbp_involvement": usage_value,
                    "team_usage_share": role_value, "player_impact_index": impact_index,
                    "valuation_status": "valued_from_prior_pbp_usage" if valued else
                        ("OL_player_identity_retained_but_not_individually_valued" if pos in POSITION_GROUPS["ol"] else "no_prior_pbp_usage"),
                })
            row[f"{side}_player_off_absence_index"] = missing_off
            row[f"{side}_player_def_absence_index"] = missing_def
            row[f"{side}_player_qb_absence_index"] = missing_qb
            row[f"{side}_unvalued_ol_absences"] = missing_ol
            row[f"{side}_player_injury_report_available"] = int(not team_rows.empty)
        feature_rows.append(row)

    if not feature_rows:
        raise ValueError("No player-level injury features could be generated.")
    features = pd.DataFrame(feature_rows).drop_duplicates("game_id")
    detail_frame = pd.DataFrame(details)
    return features, detail_frame
