"""Pregame injury features for the experimental NFL efficiency projections.

Historical reports are filtered to updates available before kickoff. For the current
upcoming slate, a saved repository snapshot takes precedence over the live source.
No hand-authored point penalties are applied: the projection estimator learns the
relationship between pregame injury features and scores from historical games.
"""
from __future__ import annotations

from pathlib import Path
from io import BytesIO
import re
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


def _snapshot_capture_time(path: Path) -> pd.Timestamp | pd.NaT:
    """Read the UTC capture timestamp embedded in a snapshot filename."""
    match = re.search(r"_(\d{8}T\d{6}Z)$", path.stem)
    if not match:
        return pd.NaT
    return pd.to_datetime(match.group(1), format="%Y%m%dT%H%M%SZ", errors="coerce", utc=True)


def _snapshot_is_structurally_valid(snapshot: pd.DataFrame) -> bool:
    """Reject snapshots with missing/duplicate player IDs or missing team values.

    This intentionally validates structure only; it does not certify feed
    completeness or original injury-report publication timing.
    """
    required = {"gsis_id", "team"}
    if snapshot.empty or not required.issubset(snapshot.columns):
        return False
    ids = snapshot["gsis_id"].astype("string").str.strip()
    if ids.isna().any() or ids.eq("").fillna(False).any():
        return False
    if ids.duplicated(keep=False).any():
        return False
    teams = snapshot["team"].astype("string").str.strip()
    if teams.isna().any() or teams.eq("").fillna(False).any():
        return False
    return True


def _latest_snapshot_for(season: int, week: int) -> pd.DataFrame | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob(f"injuries_{season}_week_{week:02d}_*.csv"))
    if not files:
        return None
    # Filename timestamp is capture time, so lexicographic ordering is chronological.
    snapshot = pd.read_csv(files[-1], low_memory=False)
    if not _snapshot_is_structurally_valid(snapshot):
        return None
    snapshot["_snapshot_captured_at_utc"] = _snapshot_capture_time(files[-1])
    snapshot["_snapshot_filename"] = files[-1].name
    return snapshot


def _normalize_reports(reports: pd.DataFrame) -> pd.DataFrame:
    data = reports.copy()
    for col in ("season", "week"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    for col in ("team", "position", "report_status", "practice_status"):
        data[col] = data[col].fillna("").astype(str).str.upper().str.strip()
    # Weekly snapshots store capture time in snapshot_captured_at_utc;
    # unlike the live feed, they do not contain date_modified.
    if "date_modified" not in data.columns:
        if "snapshot_captured_at_utc" in data.columns:
            data["date_modified"] = data["snapshot_captured_at_utc"]
        elif "_snapshot_captured_at_utc" in data.columns:
            data["date_modified"] = data["_snapshot_captured_at_utc"]
        else:
            data["date_modified"] = pd.NaT
    data["date_modified"] = pd.to_datetime(data["date_modified"], errors="coerce", utc=True)
    if "_snapshot_captured_at_utc" not in data.columns and "snapshot_captured_at_utc" in data.columns:
        data["_snapshot_captured_at_utc"] = pd.to_datetime(data["snapshot_captured_at_utc"], errors="coerce", utc=True)
    # nflverse injury feeds use game_type; older/local snapshots may use season_type.
    # Preserve the source value instead of silently treating postseason rows as regular season.
    if "season_type" not in data:
        if "game_type" in data:
            data["season_type"] = data["game_type"]
        else:
            data["season_type"] = "REG"
    else:
        missing_type = data["season_type"].isna() | data["season_type"].astype(str).str.strip().eq("")
        if "game_type" in data:
            source_type = data["game_type"].fillna("").astype(str).str.strip()
            has_source_type = missing_type & source_type.ne("")
            data.loc[has_source_type, "season_type"] = data.loc[has_source_type, "game_type"]
            data.loc[missing_type & ~has_source_type, "season_type"] = "REG"
        else:
            data.loc[missing_type, "season_type"] = "REG"
    data["season_type"] = data["season_type"].fillna("REG").astype(str).str.upper().str.strip()
    data["season_type"] = data["season_type"].replace({"REGULAR": "REG", "POSTSEASON": "POST", "PRESEASON": "PRE"})
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


def _counts_for_team(rows: pd.DataFrame, exclude_qb: bool = False) -> dict:
    features = {}
    had_report = not rows.empty
    # In QB-EPA research mode, strip QB rows from ALL aggregate and position
    # counts. Merely dropping qb_out would double-count unavailable QBs via
    # inj_out and practice_dnp. Keep a separate report-availability flag.
    if exclude_qb and had_report:
        rows = rows[rows["position"].astype(str).str.upper().ne("QB")]
    if rows.empty and not had_report:
        return {"injury_report_available": 0.0, **{k: np.nan for k in _feature_names()}}
    status = rows["report_status"].fillna("").astype(str).str.strip().str.upper()
    practice = rows["practice_status"].fillna("").astype(str).str.strip().str.upper()
    pos = rows["position"].fillna("").astype(str).str.strip().str.upper()
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


def add_injury_features(dataset: pd.DataFrame, schedule: pd.DataFrame, reports: pd.DataFrame, *, exclude_qb: bool = False) -> pd.DataFrame:
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
        # For genuinely upcoming games, prefer the latest structurally valid
        # saved snapshot captured before kickoff. Do not infer "upcoming" from
        # score nullability: some schedule feeds populate score placeholders.
        snapshot = None
        now_utc = pd.Timestamp.now(tz="UTC")
        if pd.notna(kickoff):
            candidate_snapshot = _latest_snapshot_for(int(game["season"]), int(game["week"]))
            if candidate_snapshot is not None and not candidate_snapshot.empty:
                candidate_capture = pd.to_datetime(
                    candidate_snapshot["_snapshot_captured_at_utc"].iloc[0],
                    errors="coerce", utc=True
                ) if "_snapshot_captured_at_utc" in candidate_snapshot.columns else pd.NaT
                if pd.notna(candidate_capture) and candidate_capture < kickoff:
                    snapshot = candidate_snapshot
        if snapshot is not None and not snapshot.empty:
            try:
                snap = _normalize_reports(snapshot)
                snap = snap[
                    (snap["season"] == game["season"])
                    & (snap["week"] == game["week"])
                    & (snap["season_type"] == game["season_type"])
                ]
                captured_at = pd.to_datetime(
                    snapshot["_snapshot_captured_at_utc"].iloc[0], errors="coerce", utc=True
                ) if "_snapshot_captured_at_utc" in snapshot.columns else pd.NaT
                # A snapshot is a point-in-time record: its filename timestamp,
                # not each row's source date_modified, establishes when it was available.
                if not snap.empty and pd.notna(captured_at) and pd.notna(kickoff) and captured_at < kickoff:
                    snap["date_modified"] = captured_at
                    base = snap
            except Exception:
                # Fall back to the timestamped feed; never admit an unverified snapshot.
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
            values = _counts_for_team(team_rows, exclude_qb=exclude_qb)
            for key, value in values.items():
                row[f"{side}_{key}"] = value
        results.append(row)
    if not results:
        raise ValueError("No injury features could be generated for scheduled games.")
    feature_frame = pd.DataFrame(results).drop_duplicates("game_id")
    out = dataset.drop(columns=[c for c in dataset.columns if c.startswith(("home_injury_", "away_injury_", "home_inj_", "away_inj_", "home_qb_", "away_qb_", "home_ol_", "away_ol_", "home_skill_", "away_skill_", "home_defense_", "away_defense_"))], errors="ignore")
    return out.merge(feature_frame, on="game_id", how="left", validate="one_to_one")



def injury_coverage_diagnostics(schedule: pd.DataFrame, reports: pd.DataFrame) -> pd.DataFrame:
    """Explain where injury coverage is lost for scheduled games.

    Counts source rows before and after game-type and pre-kickoff filters. This is
    diagnostic only and never changes the feature-generation path.
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
    games["season_type"] = games["season_type"].replace({"REGULAR": "REG", "POSTSEASON": "POST", "PRESEASON": "PRE"})
    rows = []
    for _, game in games.iterrows():
        if pd.isna(game["season"]) or pd.isna(game["week"]) or pd.isna(game["gameday"]):
            continue
        kickoff = _kickoff_utc(game)
        raw = normalized[
            normalized["season"].eq(game["season"])
            & normalized["week"].eq(game["week"])
        ]
        typed = raw[raw["season_type"].eq(game["season_type"])]
        pregame = typed
        if pd.notna(kickoff):
            pregame = typed[typed["date_modified"].notna() & typed["date_modified"].lt(kickoff)]
        else:
            pregame = typed[typed["date_modified"].dt.date < pd.Timestamp(game["gameday"]).date()]
        snapshot = _latest_snapshot_for(int(game["season"]), int(game["week"])) if pd.notna(kickoff) else None
        snapshot_capture = (
            pd.to_datetime(snapshot["_snapshot_captured_at_utc"].iloc[0], errors="coerce", utc=True)
            if snapshot is not None and "_snapshot_captured_at_utc" in snapshot.columns
            else pd.NaT
        )
        snapshot_timing = (
            "Pregame eligible" if pd.notna(snapshot_capture) and pd.notna(kickoff) and snapshot_capture < kickoff
            else "After kickoff" if pd.notna(snapshot_capture) and pd.notna(kickoff)
            else "Timestamp unavailable" if snapshot is not None
            else "No snapshot"
        )
        diagnostic_source = pregame
        source_label = "Live feed"
        if snapshot is not None and snapshot_timing == "Pregame eligible":
            try:
                snapshot_normalized = _normalize_reports(snapshot)
                snapshot_normalized = snapshot_normalized[
                    snapshot_normalized["season"].eq(game["season"])
                    & snapshot_normalized["week"].eq(game["week"])
                    & snapshot_normalized["season_type"].eq(game["season_type"])
                ].copy()
                if not snapshot_normalized.empty:
                    snapshot_normalized["date_modified"] = snapshot_capture
                    diagnostic_source = snapshot_normalized
                    source_label = "Saved snapshot"
            except Exception:
                pass
        home_rows = diagnostic_source[
            diagnostic_source["team"].eq(str(game.get("home_team", "")).upper().strip())
        ]
        away_rows = diagnostic_source[
            diagnostic_source["team"].eq(str(game.get("away_team", "")).upper().strip())
        ]
        home_features = _counts_for_team(home_rows)
        away_features = _counts_for_team(away_rows)
        rows.append({
            "Matchup": f"{game.get('away_team', '?')} @ {game.get('home_team', '?')}",
            "Season/week/type": f"{int(game['season'])}/{int(game['week'])}/{game['season_type']}",
            "Feed rows season/week": len(raw),
            "Rows after game-type match": len(typed),
            "Rows with valid timestamps": int(typed["date_modified"].notna().sum()),
            "Rows available pre-kickoff": len(pregame),
            "Feed teams": ", ".join(sorted(typed["team"].dropna().astype(str).unique())),
            "Snapshot file found": snapshot is not None,
            "Snapshot rows": len(snapshot) if snapshot is not None else 0,
            "Snapshot captured UTC": snapshot_capture.isoformat() if pd.notna(snapshot_capture) else "None",
            "Snapshot timing": snapshot_timing,
            "Diagnostic source used": source_label,
            "Pregame position counts": ", ".join(
                f"{k}={v}" for k, v in diagnostic_source["position"].value_counts().head(8).items()
            ) if not diagnostic_source.empty else "",
            "Home report rows": len(home_rows),
            "Away report rows": len(away_rows),
            "Home QB out": home_features.get("qb_out"),
            "Away QB out": away_features.get("qb_out"),
            "Home OL out": home_features.get("ol_out"),
            "Away OL out": away_features.get("ol_out"),
            "Home players out": home_features.get("inj_out"),
            "Away players out": away_features.get("inj_out"),
            "Home questionable": home_features.get("inj_questionable"),
            "Away questionable": away_features.get("inj_questionable"),
            "Latest report timestamp UTC": (
                typed["date_modified"].max().isoformat() if typed["date_modified"].notna().any() else "None"
            ),
        })
    return pd.DataFrame(rows)


def project_qb_aware_injury(
    schedule: pd.DataFrame,
    pbp: pd.DataFrame,
    reports: pd.DataFrame,
    *,
    season: int,
    week: int,
    verified_starters: pd.DataFrame | None = None,
    expected_starters: pd.DataFrame | None = None,
    lookback_games: int = 10,
    min_train_games: int = 500,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the one forward Injury model with player-specific starting-QB EPA.

    Train the regular Injury Ridge scorer with QB rows removed from *all*
    injury/practice counts. Identify the expected starter using source-verified
    pregame overrides or, with explicit warning labels, NFLverse's current
    per-game QB listing. Add one capped incremental QB EPA margin shift to the
    non-QB score predictions, preserving their original total. Do not silently
    treat an unknown QB or missing history as zero impact.

    Retrospective 2026 selection of the margin-only/cap-five approach is NOT
    untouched evidence of performance; freeze outputs prior to future kickoffs.
    This returns scored research/pregame data; it never rewrites an archive.
    """
    from model import build_efficiency_model_dataset, project_upcoming_efficiency
    from qb_epa_model import (
        qb_game_stats, starters_from_game_schedule, build_qb_epa_board,
        attach_qb_margin_adjustment,
    )
    model_base = build_efficiency_model_dataset(
        schedule, pbp, lookback_games=lookback_games
    )
    non_qb = add_injury_features(model_base, schedule, reports, exclude_qb=True)
    future = project_upcoming_efficiency(non_qb, min_train_games=min_train_games)
    mask = (
        pd.to_numeric(future["season"], errors="coerce").eq(int(season))
        & pd.to_numeric(future["week"], errors="coerce").eq(int(week))
    )
    slate = future.loc[mask].copy()
    if slate.empty or slate["game_id"].duplicated().any():
        raise ValueError(f"No unique upcoming games for season {season} week {week}")
    # NFLverse's upcoming schedule QB fields are provisional; independently
    # source-verified overrides take precedence over those fields.
    scheduled_qbs = starters_from_game_schedule(schedule, completed_only=False)
    scheduled_qbs = scheduled_qbs[
        scheduled_qbs["game_id"].isin(slate["game_id"])
    ].copy()
    qb_board = build_qb_epa_board(
        qb_game_stats(pbp, schedule),
        schedule,
        slate,
        overrides=verified_starters,
        observed=scheduled_qbs,
        expected=expected_starters,
    )
    adjusted = attach_qb_margin_adjustment(slate, qb_board)
    adjusted["original_non_qb_home"] = adjusted["projected_home"]
    adjusted["original_non_qb_away"] = adjusted["projected_away"]
    adjusted["projected_home"] = adjusted["projected_home_qb_injury"]
    adjusted["projected_away"] = adjusted["projected_away_qb_injury"]
    adjusted["projected_total"] = adjusted["projected_total_qb_injury"]
    adjusted["model_home_spread"] = adjusted["projected_away"] - adjusted["projected_home"]
    adjusted["model"] = "injury"
    adjusted["model_version"] = "qb_epa_margin_cap5_v1"
    adjusted["qb_starter_verification"] = "mixed; inspect paired QB evidence"
    # Explicitly keep QB evidence next to corresponding scored game.
    for side in ("home", "away"):
        cols = [
            "game_id", "qb_id", "qb_name", "starter_source", "confidence",
            "qb_prior_dropbacks", "qb_shrunk_epa_per_dropback",
            "qb_delta_epa_per_dropback", "starter_recent_team_dropback_share",
        ]
        subset = qb_board[qb_board["side"].eq(side)][cols].copy()
        subset = subset.rename(columns={
            col: f"{side}_{col}" for col in cols if col != "game_id"
        })
        adjusted = adjusted.merge(
            subset, on="game_id", how="left", validate="one_to_one"
        )
    return adjusted, qb_board
