"""Point-in-time starting-QB EPA comparison for an experimental injury model.

QB value is compared with the team's recent *actual QB mix*, not with a fixed
'starter out' penalty. One starter is evaluated per team-game: a second injured
backup never creates an additional point penalty.

The selection of a current starter is a separate data-quality problem. A
verified pregame override takes priority; otherwise the previous game's primary
passer is only a provisional *inference*, never a confirmed starter.

EPA-to-points conversion is a research approximation, not calibrated/validated.
Official/frozen projections and records must not be overwritten by this module.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PRIOR_DROPBACKS = 120.0
RECENT_QB_GAMES = 24
RECENT_TEAM_GAMES = 10
QB_HALF_LIFE_GAMES = 12.0


def qb_game_stats(pbp: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """QB dropback EPA from completed games, with official game date for cutoffs."""
    required = {"game_id", "posteam", "passer_player_id", "epa", "play_type"}
    missing = required - set(pbp.columns)
    if missing:
        raise ValueError(f"Missing PBP columns: {sorted(missing)}")
    dates = schedule[["game_id", "gameday", "home_score", "away_score"]].drop_duplicates("game_id").copy()
    dates["gameday"] = pd.to_datetime(dates["gameday"], errors="coerce")
    # Never use any game without an actual completed score in the EPA history.
    dates = dates.dropna(subset=["gameday", "home_score", "away_score"])
    rows = pbp[
        pbp["passer_player_id"].notna()
        & pbp["posteam"].notna()
        & pbp["play_type"].isin(["run", "pass"])
    ].copy()
    rows["epa"] = pd.to_numeric(rows["epa"], errors="coerce")
    rows = rows.dropna(subset=["epa"])
    for col in ("qb_kneel", "qb_spike"):
        if col in rows:
            rows = rows[pd.to_numeric(rows[col], errors="coerce").fillna(0).ne(1)]
    rows["qb_id"] = rows["passer_player_id"].astype(str).str.strip()
    rows["team"] = rows["posteam"].astype(str).str.upper().str.strip()
    if "passer_player_name" in rows:
        rows["qb_name"] = rows["passer_player_name"].fillna("").astype(str)
    else:
        rows["qb_name"] = ""
    rows = rows.merge(dates, on="game_id", how="inner", validate="many_to_one")
    stats = (
        rows.groupby(["game_id", "gameday", "team", "qb_id"], as_index=False)
        .agg(dropbacks=("epa", "size"), total_epa=("epa", "sum"),
             qb_name=("qb_name", "last"))
    )
    return stats.sort_values(["gameday", "game_id", "qb_id"]).reset_index(drop=True)


def _starter_for(team: str, game_id: str, history: pd.DataFrame,
                 overrides: pd.DataFrame | None) -> tuple[str | None, str, str, str]:
    """Select a verified starter or provisionally infer last game's primary QB."""
    if overrides is not None and not overrides.empty:
        match = overrides[
            overrides["game_id"].astype(str).eq(str(game_id))
            & overrides["team"].astype(str).str.upper().eq(str(team).upper())
        ]
        if len(match) > 1:
            raise ValueError(f"Multiple QB starter overrides: {game_id} {team}")
        if not match.empty:
            r = match.iloc[0]
            if not str(r.get("source_url", "")).startswith("https://"):
                raise ValueError(f"QB starter override lacks source: {game_id} {team}")
            qb_id = str(r["qb_id"]).strip()
            if not qb_id:
                raise ValueError(f"Blank QB ID: {game_id} {team}")
            return qb_id, str(r.get("qb_name", qb_id)), "verified_pregame", str(r["source_url"])
    prior = history[history["team"].eq(team)]
    if prior.empty:
        return None, "", "unknown_no_pregame_evidence", ""
    last_date = prior["gameday"].max()
    last = prior[prior["gameday"].eq(last_date)].sort_values("dropbacks", ascending=False)
    starter = last.iloc[0]
    name = starter["qb_name"] if str(starter["qb_name"]).strip() else str(starter["qb_id"])
    return str(starter["qb_id"]), str(name), "inferred_previous_primary_passer", ""


def _one_team(game_id: str, side: str, team: str, cutoff: pd.Timestamp,
              stats: pd.DataFrame, overrides: pd.DataFrame | None) -> dict:
    history = stats[stats["gameday"].lt(cutoff)].copy()
    qb_id, qb_name, starter_source, source_url = _starter_for(team, game_id, history, overrides)
    team_hist = history[history["team"].eq(team)]
    recent_game_ids = (
        team_hist[["game_id", "gameday"]].drop_duplicates()
        .sort_values(["gameday", "game_id"], ascending=False)
        .head(RECENT_TEAM_GAMES)["game_id"]
    )
    recent = team_hist[team_hist["game_id"].isin(recent_game_ids)]
    reference_dropbacks = float(recent["dropbacks"].sum())
    reference_epa = (
        float(recent["total_epa"].sum() / reference_dropbacks)
        if reference_dropbacks else np.nan
    )
    expected_dropbacks = (
        reference_dropbacks / len(recent_game_ids) if len(recent_game_ids) else np.nan
    )
    lg_count = float(history["dropbacks"].sum())
    league_rate = float(history["total_epa"].sum() / lg_count) if lg_count else np.nan
    player_history = history[history["qb_id"].eq(qb_id)] if qb_id is not None else history.iloc[0:0]
    last_games = (
        player_history.sort_values(["gameday", "game_id"], ascending=False)
        .head(RECENT_QB_GAMES).copy()
    )
    n = len(last_games)
    if n:
        decay = 0.5 ** (np.arange(n) / QB_HALF_LIFE_GAMES)
        weighted_dropbacks = float((last_games["dropbacks"].to_numpy() * decay).sum())
        weighted_epa = float((last_games["total_epa"].to_numpy() * decay).sum())
    else:
        weighted_dropbacks = weighted_epa = 0.0
    player_raw = weighted_epa / weighted_dropbacks if weighted_dropbacks else np.nan
    # Regularize low-sample players toward the historically observed league QB
    # rate. Do not invent a 0- or 5-point rookie deduction.
    player_shrunk = (
        (weighted_epa + PRIOR_DROPBACKS * league_rate) /
        (weighted_dropbacks + PRIOR_DROPBACKS)
        if pd.notna(league_rate) and qb_id is not None else np.nan
    )
    delta_epa = (
        player_shrunk - reference_epa
        if pd.notna(player_shrunk) and pd.notna(reference_epa) else np.nan
    )
    point_shift = (
        delta_epa * expected_dropbacks
        if pd.notna(delta_epa) and pd.notna(expected_dropbacks) else np.nan
    )
    return {
        "game_id": game_id, "side": side, "team": team,
        "qb_id": qb_id or "", "qb_name": qb_name,
        "starter_source": starter_source, "source_url": source_url,
        "qb_prior_dropbacks": float(player_history["dropbacks"].sum()),
        "qb_weighted_dropbacks": weighted_dropbacks,
        "qb_raw_epa_per_dropback": player_raw,
        "qb_shrunk_epa_per_dropback": player_shrunk,
        "team_recent_qb_epa_per_dropback": reference_epa,
        "team_recent_dropbacks_per_game": expected_dropbacks,
        "qb_delta_epa_per_dropback": delta_epa,
        "qb_point_shift_experimental": point_shift,
        "confidence": (
            "insufficient_data" if qb_id is None or weighted_dropbacks < 40
            else "limited_sample" if weighted_dropbacks < 160
            else "sample_available"
        ),
    }


def build_qb_epa_board(
    stats: pd.DataFrame,
    schedule: pd.DataFrame,
    targets: pd.DataFrame,
    overrides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute two QB comparisons per game using only completed prior games.

    The historical table must come from qb_game_stats(), which rejects games
    without completed scores. Each game's history is strictly earlier than
    its gameday. This makes the same function safe for chronological backtests.
    """
    required = {"game_id", "gameday", "home_team", "away_team"}
    if not required.issubset(targets.columns):
        raise ValueError(f"Targets missing {sorted(required - set(targets.columns))}")
    out = []
    games = targets.copy()
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce")
    if games["gameday"].isna().any():
        raise ValueError("Target game dates are missing")
    if games["game_id"].duplicated().any():
        raise ValueError("Duplicate target game IDs")
    for game in games.itertuples(index=False):
        for side in ("home", "away"):
            team = str(getattr(game, f"{side}_team")).upper().strip()
            out.append(_one_team(
                str(game.game_id), side, team, game.gameday, stats, overrides
            ))
    result = pd.DataFrame(out)
    if len(result) != 2 * len(games):
        raise ValueError("Incomplete QB comparison")
    return result


def attach_qb_shifts(projections: pd.DataFrame, qb_board: pd.DataFrame) -> pd.DataFrame:
    """Research-only score adjustments after retraining without QB-count injuries."""
    out = projections.copy()
    for side in ("home", "away"):
        frame = qb_board[qb_board["side"].eq(side)][["game_id", "qb_point_shift_experimental"]]
        if frame["game_id"].duplicated().any():
            raise ValueError(f"Duplicate {side} QB adjustments")
        shift_col = f"{side}_qb_shift"
        out = out.merge(
            frame.rename(columns={"qb_point_shift_experimental": shift_col}),
            on="game_id", how="left", validate="one_to_one",
        )
        # Unknown starter/history does NOT silently assume a zero adjustment.
        out[f"{side}_qb_adjusted"] = out[f"projected_{side}"] + out[shift_col]
    out["projected_total_qb_adjusted"] = (
        out["home_qb_adjusted"] + out["away_qb_adjusted"]
    )
    return out
