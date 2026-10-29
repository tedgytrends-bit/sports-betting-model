"""Pregame injury features for the experimental NFL efficiency projections.

Historical reports are filtered to updates available before kickoff. For the current
upcoming slate, a saved repository snapshot takes precedence over the live source.
No hand-authored point penalties are applied: the projection estimator learns the
relationship between pregame injury features and scores from historical games.
"""
from __future__ import annotations

from pathlib import Path
from io import BytesIO
import requests
import numpy as np
import pandas as pd

INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
SNAPSHOT_DIR = Path(__file__).resolve().parent / "data" / "injury_snapshots"
USER_AGENT = {"User-Agent": "sports-betting-model-injury-features/1.0"}
POSITION_GROUPS = {
    "qb": {"QB"},
    "ol": {"C", "G", "OG", "OT", "T", "OL", "LT", "LG", "RG", "RT"},
    "skill": {"RB", "FB", "WR", "TE"},
    "defense": {"DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "DB", "S", "FS", "SS"},
}


def load_injury_reports(seasons=(2021, 2022, 2023, 2024, 2025, 2026)) -> pd.DataFrame:
    """Load the public historical injury report feeds; fail if any requested year fails."""
    frames, errors = [], []
    for season in seasons:
        url = INJURY_URL.format(season=int(season))
        try:
            response = requests.get(url, timeout=(10, 45), headers=USER_AGENT)
            response.raise_for_status()
            frame = pd.read_csv(BytesIO(response.content), low_memory=False)
            frame["source_season"] = int(season)
            frames.append(frame)
        except Exception as exc:
            errors.append(f"{season}: {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError("Could not load complete injury history: " + " | ".join(errors))
    if not frames:
        raise RuntimeError("No injury report seasons were loaded.")
    reports = pd.concat(frames, ignore_index=True, sort=False)
    required = {"season", "week", "team", "position", "report_status", "practice_status", "date_modified"}
    missing = required - set(reports.columns)
    if missing:
        raise ValueError(f"Injury feed missing required columns: {sorted(missing)}")
    return reports


def _latest_snapshot_for(season: int, week: int) -> pd.DataFrame | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob(f"injuries_{season}_week_{week:02d}_*.csv"))
    if not files:
        return None
    # Filename timestamp is capture time, so lexicographic ordering is chronological.
    return pd.read_csv(files[-1], low_memory=False)


def _normalize_reports(reports: pd.DataFrame) -> pd.DataFrame:
    data = reports.copy()
    for col in ("season", "week"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    for col in ("team", "position", "report_status", "practice_status"):
        data[col] = data[col].fillna("").astype(str).str.upper().str.strip()
    data["date_modified"] = pd.to_datetime(data["date_modified"], errors="coerce", utc=True)
    if "season_type" not in data:
        data["season_type"] = "REG"
    data["season_type"] = data["season_type"].fillna("REG").astype(str).str.upper().str.strip()
    data["season_type"] = data["season_type"].replace({"REGULAR": "REG", "POSTSEASON": "POST"})
    player_col = next((c for c in ("player_name", "full_name", "player", "gsis_id") if c in data.columns), None)
    if player_col is None:
        data["_player_key"] = data.index.astype(str)
    else:
        data["_player_key"] = data[player_col].fillna("").astype(str).str.upper().str.strip()
        blank = data["_player_key"].eq("")
        data.loc[blank, "_player_key"] = data.index[blank].astype(str)
    return data


def _kickoff_utc(game: pd.Series) -> pd.Timestamp | pd.NaT:
    day = pd.to_datetime(game.get("gameday"), errors="coerce")
    if pd.isna(day):
        return pd.NaT
    gametime = game.get("gametime")
    if pd.isna(gametime) or str(gametime).strip() in ("", "nan", "NaT"):
        # Without kickoff time, only reports from a prior calendar date are safe.
        return pd.Timestamp(day).tz_localize("UTC")
    local = pd.to_datetime(f"{pd.Timestamp(day).date()} {gametime}", errors="coerce")
    if pd.isna(local):
        return pd.Timestamp(day).tz_localize("UTC")
    return local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def _counts_for_team(rows: pd.DataFrame) -> dict:
    features = {}
    if rows.empty:
        return {"injury_report_available": 0.0, **{k: np.nan for k in _feature_names()}}
    status = rows["report_status"]
    practice = rows["practice_status"]
    pos = rows["position"]
    out = status.eq("OUT")
    doubtful = status.str.contains("DOUBTFUL", regex=False)
    questionable = status.str.contains("QUESTIONABLE", regex=False)
    dnp = practice.str.contains("DID NOT PARTICIPATE", regex=False)
    limited = practice.str.contains("LIMITED", regex=False)
    features["injury_report_available"] = 1.0
    features["inj_out"] = float(out.sum())
    features["inj_doubtful"] = float(doubtful.sum())
    features["inj_questionable"] = float(questionable.sum())
    features["practice_dnp"] = float(dnp.sum())
    features["practice_limited"] = float(limited.sum())
    for group, positions in POSITION_GROUPS.items():
        in_group = pos.isin(positions)
        features[f"{group}_out"] = float((out & in_group).sum())
        features[f"{group}_doubtful"] = float((doubtful & in_group).sum())
        features[f"{group}_questionable"] = float((questionable & in_group).sum())
    return features


def _feature_names() -> list[str]:
    names = ["inj_out", "inj_doubtful", "inj_questionable", "practice_dnp", "practice_limited"]
    for group in POSITION_GROUPS:
        names.extend([f"{group}_out", f"{group}_doubtful", f"{group}_questionable"])
    return names


def add_injury_features(dataset: pd.DataFrame, schedule: pd.DataFrame, reports: pd.DataFrame) -> pd.DataFrame:
    """Attach report features to each game using only data available before kickoff.

    For future games, the latest committed snapshot for that exact season/week is
    preferred. Historical games use the timestamped source feed, deduplicated to
    the latest pre-kickoff report per player/team/game week.
    """
    normalized = _normalize_reports(reports)
    games = schedule.copy()
    games["season"] = pd.to_numeric(games["season"], errors="coerce")
    games["week"] = pd.to_numeric(games["week"], errors="coerce")
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce")
    type_col = "game_type" if "game_type" in games.columns else "season_type"
    if type_col in games.columns:
        games["season_type"] = games[type_col].fillna("REG").astype(str).str.upper().str.strip()
    else:
        games["season_type"] = "REG"
    games["season_type"] = games["season_type"].replace({"REGULAR": "REG", "POSTSEASON": "POST"})
    results = []
    for _, game in games.iterrows():
        if pd.isna(game["season"]) or pd.isna(game["week"]) or pd.isna(game["gameday"]):
            continue
        kickoff = _kickoff_utc(game)
        base = normalized[
            (normalized["season"] == game["season"])
            & (normalized["week"] == game["week"])
            & (normalized["season_type"] == game["season_type"])
        ]
        # If a saved snapshot exists for this future week, use it as the current source.
        snapshot = None
        if pd.isna(game.get("home_score")) or pd.isna(game.get("away_score")):
            snapshot = _latest_snapshot_for(int(game["season"]), int(game["week"]))
        if snapshot is not None and not snapshot.empty:
            try:
                snap = _normalize_reports(snapshot)
                snap = snap[
                    (snap["season"] == game["season"])
                    & (snap["week"] == game["week"])
                    & (snap["season_type"] == game["season_type"])
                ]
                if not snap.empty:
                    base = snap
            except Exception:
                # Fall back to the timestamped feed; the UI surfaces missing coverage.
                pass
        if pd.notna(kickoff):
            base = base[base["date_modified"].notna() & (base["date_modified"] < kickoff)]
        else:
            base = base[base["date_modified"].dt.date < pd.Timestamp(game["gameday"]).date()]
        if not base.empty:
            base = base.sort_values("date_modified").drop_duplicates(["team", "_player_key"], keep="last")
        row = {"game_id": game["game_id"]}
        for side, team_col in (("home", "home_team"), ("away", "away_team")):
            team_rows = base[base["team"] == str(game[team_col]).upper().strip()]
            values = _counts_for_team(team_rows)
            for key, value in values.items():
                row[f"{side}_{key}"] = value
        results.append(row)
    if not results:
        raise ValueError("No injury features could be generated for scheduled games.")
    feature_frame = pd.DataFrame(results).drop_duplicates("game_id")
    out = dataset.drop(columns=[c for c in dataset.columns if c.startswith(("home_injury_", "away_injury_", "home_inj_", "away_inj_", "home_qb_", "away_qb_", "home_ol_", "away_ol_", "home_skill_", "away_skill_", "home_defense_", "away_defense_"))], errors="ignore")
    return out.merge(feature_frame, on="game_id", how="left", validate="one_to_one")
