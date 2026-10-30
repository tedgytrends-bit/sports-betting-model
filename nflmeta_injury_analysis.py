"""Leakage-aware research features from NFLMeta 2026 injury exports.

This module is intentionally separate from the live projection model. Practice-day
history can be retrospectively backfilled; features are therefore labeled with
availability/provenance and must not be treated as pregame predictors unless their
observation timestamps establish that they were available before kickoff.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

POSITION_GROUPS = {
    "qb": {"QB"},
    "ol": {"C", "G", "OG", "OT", "T", "OL", "LT", "LG", "RG", "RT"},
    "skill": {"RB", "FB", "WR", "TE"},
    "defense": {"DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "DB", "S", "FS", "SS"},
}


def load_nflmeta_exports(injuries_path: str | Path, practice_path: str | Path):
    injuries = pd.read_csv(injuries_path, low_memory=False)
    practice = pd.read_csv(practice_path, low_memory=False)
    return injuries, practice


def _normalize_team(value) -> str:
    team = str(value).strip().upper()
    return {"LAR": "LA", "JAC": "JAX"}.get(team, team)


def _prepare(injuries: pd.DataFrame, practice: pd.DataFrame):
    required_i = {"season_year", "week", "team_abbr", "player_id", "position",
                  "report_status", "game_status", "source_observed_at"}
    required_p = {"season_year", "week", "team_abbr", "player_id", "practice_date",
                  "practice_status_code", "first_observed_at", "historical_backfill"}
    missing_i = required_i - set(injuries.columns)
    missing_p = required_p - set(practice.columns)
    if missing_i or missing_p:
        raise ValueError(f"Missing injury columns={sorted(missing_i)}; practice columns={sorted(missing_p)}")
    i = injuries.copy()
    p = practice.copy()
    for frame in (i, p):
        frame["season_year"] = pd.to_numeric(frame["season_year"], errors="coerce")
        frame["week"] = pd.to_numeric(frame["week"], errors="coerce")
        frame["team_abbr"] = frame["team_abbr"].map(_normalize_team)
        frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce")
    for col in ("source_observed_at",):
        i[col] = pd.to_datetime(i[col], errors="coerce", utc=True)
    for col in ("practice_date",):
        p[col] = pd.to_datetime(p[col], errors="coerce", utc=True)
    p["first_observed_at"] = pd.to_datetime(p["first_observed_at"], errors="coerce", utc=True)
    p["practice_status_code"] = p["practice_status_code"].fillna("").astype(str).str.upper().str.strip()
    i["position"] = i["position"].fillna("").astype(str).str.upper().str.strip()
    for col in ("report_status", "game_status"):
        i[col] = i[col].fillna("").astype(str).str.upper().str.strip()
    return i, p


def build_team_week_features(injuries: pd.DataFrame, practice: pd.DataFrame) -> pd.DataFrame:
    """Create one row per team/week with descriptive and timing-qualified features.

    Game-status fields are retained as postgame labels only, never as pregame inputs.
    Practice counts count unique players for status incidence and total player-days
    separately, avoiding the common error of treating three practice days as three
    independent injured players.
    """
    i, p = _prepare(injuries, practice)
    key = ["season_year", "week", "team_abbr"]
    rows = []
    for values, players in i.groupby(key, dropna=False):
        season, week, team = values
        pp = p[(p["season_year"] == season) & (p["week"] == week) & (p["team_abbr"] == team)]
        player_ids = set(players["player_id"].dropna())
        pp = pp[pp["player_id"].isin(player_ids)].copy()
        row = {"season_year": int(season), "week": int(week), "team": team,
               "injury_list_players": len(player_ids)}
        # Weekly designation counts are descriptive of the API's current record.
        for label, token in (("out", "OUT"), ("doubtful", "DOUBTFUL"),
                             ("questionable", "QUESTIONABLE")):
            row[f"report_{label}_players"] = int(players["report_status"].str.contains(token, regex=False).sum())
        # These fields can be final/postgame outcomes; explicitly label them as such.
        row["game_inactive_players_postgame"] = int(players["game_status"].eq("INACTIVE").sum())
        row["game_out_players_postgame"] = int(players["game_status"].eq("OUT").sum())

        for code, name in (("DNP", "dnp"), ("LP", "limited"), ("FP", "full")):
            player_set = set(pp.loc[pp["practice_status_code"].eq(code), "player_id"].dropna())
            row[f"practice_{name}_players_any_day"] = len(player_set)
            row[f"practice_{name}_player_days"] = int(pp["practice_status_code"].eq(code).sum())

        # Latest recorded practice day per player. Does not imply the record was
        # observable on that date; first_observed_at is checked independently.
        latest = pp.sort_values("practice_date").dropna(subset=["practice_date"]).drop_duplicates(
            ["player_id"], keep="last"
        )
        for code, name in (("DNP", "dnp"), ("LP", "limited"), ("FP", "full")):
            row[f"latest_practice_{name}_players"] = int(latest["practice_status_code"].eq(code).sum())

        for group, positions in POSITION_GROUPS.items():
            ids = set(players.loc[players["position"].isin(positions), "player_id"].dropna())
            group_pp = pp[pp["player_id"].isin(ids)]
            row[f"{group}_listed_players"] = len(ids)
            row[f"{group}_dnp_players_any_day"] = int(group_pp.loc[
                group_pp["practice_status_code"].eq("DNP"), "player_id"
            ].nunique())
            row[f"{group}_limited_players_any_day"] = int(group_pp.loc[
                group_pp["practice_status_code"].eq("LP"), "player_id"
            ].nunique())
            row[f"{group}_out_designations"] = int(players[
                players["position"].isin(positions) & players["report_status"].str.contains("OUT", regex=False)
            ].shape[0])

        observed = pp["first_observed_at"].dropna()
        row["practice_records"] = int(len(pp))
        row["practice_records_historical_backfill"] = int(
            pp["historical_backfill"].astype(str).str.lower().isin(["true", "1"]).sum()
        )
        row["practice_records_observed_timestamped"] = int(pp["first_observed_at"].notna().sum())
        row["latest_practice_observed_at_utc"] = observed.max().isoformat() if not observed.empty else None
        row["earliest_practice_observed_at_utc"] = observed.min().isoformat() if not observed.empty else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values(key).reset_index(drop=True)


def build_game_injury_features(schedule: pd.DataFrame, team_week: pd.DataFrame) -> pd.DataFrame:
    """Join team-week research features to schedule games and add home-away deltas.

    A feature row is marked point_in_time_verified only when the latest underlying
    practice observation timestamp for both teams precedes kickoff. Missing timing
    is not treated as proof of pregame availability.
    """
    required = {"game_id", "season", "week", "gameday", "home_team", "away_team"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"Schedule missing columns: {sorted(missing)}")
    games = schedule.copy()
    games["season"] = pd.to_numeric(games["season"], errors="coerce")
    games["week"] = pd.to_numeric(games["week"], errors="coerce")
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce", utc=True)
    tw = team_week.copy()
    lookup = {(int(r.season_year), int(r.week), r.team): r._asdict()
              for r in tw.itertuples(index=False)}
    numeric = [c for c in tw.select_dtypes(include=[np.number]).columns
               if c not in ("season_year", "week")]
    output = []
    for game in games.itertuples(index=False):
        season, week = int(game.season), int(game.week)
        home = lookup.get((season, week, _normalize_team(game.home_team)))
        away = lookup.get((season, week, _normalize_team(game.away_team)))
        row = {"game_id": game.game_id, "season": season, "week": week,
               "home_team": _normalize_team(game.home_team), "away_team": _normalize_team(game.away_team)}
        for side, record in (("home", home), ("away", away)):
            row[f"{side}_injury_data_available"] = int(record is not None)
            for col in numeric:
                row[f"{side}_{col}"] = record.get(col, np.nan) if record else np.nan
            row[f"{side}_latest_practice_observed_at_utc"] = (
                record.get("latest_practice_observed_at_utc") if record else None
            )
        for col in numeric:
            row[f"home_minus_away_{col}"] = (
                row.get(f"home_{col}", np.nan) - row.get(f"away_{col}", np.nan)
            )
        latest_times = [
            pd.to_datetime(row.get(f"{side}_latest_practice_observed_at_utc"), errors="coerce", utc=True)
            for side in ("home", "away")
        ]
        kickoff = getattr(game, "gameday")
        row["injury_features_point_in_time_verified"] = bool(
            pd.notna(kickoff) and all(pd.notna(t) and t < kickoff for t in latest_times)
        )
        row["injury_feature_timing_status"] = (
            "Both teams observed before kickoff" if row["injury_features_point_in_time_verified"]
            else "Unverified or observed after kickoff"
        )
        output.append(row)
    return pd.DataFrame(output)


def export_injury_research(injuries_path, practice_path, schedule, output_dir):
    """Write auditable team-week and game-level research tables."""
    injuries, practice = load_nflmeta_exports(injuries_path, practice_path)
    team_week = build_team_week_features(injuries, practice)
    games = build_game_injury_features(schedule, team_week)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    team_week.to_csv(out / "nflmeta_team_week_features.csv", index=False)
    games.to_csv(out / "nflmeta_game_injury_features.csv", index=False)
    return team_week, games
