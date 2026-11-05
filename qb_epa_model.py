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
                 overrides: pd.DataFrame | None,
                 observed: pd.DataFrame | None = None) -> tuple[str | None, str, str, str]:
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
    # Retrospective only: identify who first passed in the target game.
    # Identity from target PBP is postgame evidence, not a legitimate
    # point-in-time starter prediction; target-game EPA is never used.
    if observed is not None and not observed.empty:
        match = observed[
            observed["game_id"].astype(str).eq(str(game_id))
            & observed["team"].astype(str).str.upper().eq(str(team).upper())
        ]
        if len(match) > 1:
            raise ValueError(f"Multiple observed starter rows: {game_id} {team}")
        if not match.empty:
            item = match.iloc[0]
            return str(item["qb_id"]), str(item["qb_name"]), str(item.get("starter_evidence", "observed_first_passer_postgame")), ""
    prior = history[history["team"].eq(team)]
    if prior.empty:
        return None, "", "unknown_no_pregame_evidence", ""
    last_date = prior["gameday"].max()
    last = prior[prior["gameday"].eq(last_date)].sort_values("dropbacks", ascending=False)
    starter = last.iloc[0]
    name = starter["qb_name"] if str(starter["qb_name"]).strip() else str(starter["qb_id"])
    return str(starter["qb_id"]), str(name), "inferred_previous_primary_passer", ""


def _one_team(game_id: str, side: str, team: str, cutoff: pd.Timestamp,
              stats: pd.DataFrame, overrides: pd.DataFrame | None,
              observed: pd.DataFrame | None = None) -> dict:
    history = stats[stats["gameday"].lt(cutoff)].copy()
    qb_id, qb_name, starter_source, source_url = _starter_for(team, game_id, history, overrides, observed=observed)
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
    # The team baseline ALREADY includes this QB's recent plays. For an
    # incumbent responsible for nearly all recent dropbacks, a further
    # player-level change double-corrects the offense. Blend the incremental
    # adjustment by the fraction of team QB snaps NOT represented by him.
    current_qb_recent_dropbacks = float(
        recent.loc[recent["qb_id"].eq(qb_id), "dropbacks"].sum()
    ) if qb_id is not None else 0.0
    starter_recent_share = (
        current_qb_recent_dropbacks / reference_dropbacks
        if reference_dropbacks else np.nan
    )
    delta_epa = (
        (player_shrunk - reference_epa) * (1.0 - starter_recent_share)
        if pd.notna(player_shrunk) and pd.notna(reference_epa)
        and pd.notna(starter_recent_share) else np.nan
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
        "starter_recent_team_dropback_share": starter_recent_share,
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
    observed: pd.DataFrame | None = None,
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
                str(game.game_id), side, team, game.gameday, stats, overrides, observed
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


def observed_first_passer(pbp: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Postgame identity audit, not a prospective starter feed.

    The first passer with an observed dropback approximates the real starter.
    Compare with the most active passer to flag early injuries/substitutions.
    All EPA ratings in build_qb_epa_board remain pregame-only.
    """
    required = {"game_id", "posteam", "passer_player_id"}
    missing = required - set(pbp.columns)
    if missing:
        raise ValueError(f"PBP cannot determine passers: {sorted(missing)}")
    complete = schedule.dropna(subset=["home_score", "away_score"])[
        ["game_id", "season", "week", "gameday", "home_team", "away_team"]
    ].drop_duplicates("game_id")
    p = pbp.loc[
        pbp["game_id"].isin(complete["game_id"])
        & pbp["posteam"].notna()
        & pbp["passer_player_id"].notna()
        & pbp["play_type"].eq("pass")
    ].copy()
    p["qb_id"] = p["passer_player_id"].astype(str).str.strip()
    p["team"] = p["posteam"].astype(str).str.upper().str.strip()
    p["qb_name"] = (p["passer_player_name"].fillna("").astype(str)
                    if "passer_player_name" in p else p["qb_id"])
    p["original_row_order"] = np.arange(len(p))
    if "game_seconds_remaining" in p:
        p["game_seconds_remaining"] = pd.to_numeric(
            p["game_seconds_remaining"], errors="coerce"
        )
        p = p.sort_values(
            ["game_id", "team", "game_seconds_remaining", "original_row_order"],
            ascending=[True, True, False, True], kind="stable"
        )
    else:
        p = p.sort_values(["game_id", "team", "original_row_order"], kind="stable")
    first = p.drop_duplicates(["game_id", "team"]).copy()
    appearances = (p.groupby(["game_id", "team", "qb_id"], as_index=False)
                   .size().rename(columns={"size": "passer_plays"}))
    primary = (appearances.sort_values(
        ["game_id", "team", "passer_plays", "qb_id"],
        ascending=[True, True, False, True]
    ).drop_duplicates(["game_id", "team"])
     .rename(columns={"qb_id": "primary_qb_id", "passer_plays": "primary_passer_plays"}))
    first = first[["game_id", "team", "qb_id", "qb_name"]]
    out = first.merge(
        primary[["game_id", "team", "primary_qb_id", "primary_passer_plays"]],
        on=["game_id", "team"], how="left", validate="one_to_one"
    )
    out["first_matches_primary"] = out["qb_id"].eq(out["primary_qb_id"])
    out["starter_evidence"] = "retrospective_first_pass_attempt"
    games = pd.concat([
        complete[["game_id", "season", "week", "home_team"]]
            .rename(columns={"home_team": "team"}),
        complete[["game_id", "season", "week", "away_team"]]
            .rename(columns={"away_team": "team"}),
    ], ignore_index=True)
    out = games.merge(out, on=["game_id", "team"], how="left", validate="one_to_one")
    out["first_matches_primary"] = out["first_matches_primary"].fillna(False)
    return out


def starters_from_game_schedule(schedule: pd.DataFrame, *, completed_only: bool = True) -> pd.DataFrame:
    """Read NFLverse per-game starting QB IDs/names, including in-season changes.

    When completed_only=True use *retrospective* actual starter metadata from
    final-score games. This cannot substitute for archived pregame confirmations.
    """
    need = {"game_id", "season", "week", "gameday",
            "home_team", "away_team", "home_qb_id", "away_qb_id",
            "home_qb_name", "away_qb_name"}
    if not need.issubset(schedule.columns):
        raise ValueError(f"Game schedule lacks starting-QB metadata: {sorted(need-set(schedule.columns))}")
    source = schedule.copy()
    if completed_only:
        source = source.dropna(subset=["home_score", "away_score"])
    rows = []
    for side in ("home", "away"):
        temp = source[["game_id", "season", "week", "gameday",
                       f"{side}_team", f"{side}_qb_id", f"{side}_qb_name"]].rename(columns={
            f"{side}_team": "team", f"{side}_qb_id": "qb_id",
            f"{side}_qb_name": "qb_name"
        })
        rows.append(temp)
    out = pd.concat(rows, ignore_index=True)
    out["qb_id"] = out["qb_id"].astype("string").str.strip()
    out["qb_name"] = out["qb_name"].astype("string").str.strip()
    out = out[out["qb_id"].notna() & out["qb_id"].ne("")
              & out["qb_name"].notna() & out["qb_name"].ne("")]
    out["starter_evidence"] = ("schedule_recorded_starter_postgame" if completed_only
                               else "schedule_provisional_qb_unverified")
    if out.duplicated(["game_id", "team"]).any():
        raise ValueError("Duplicate starting QB metadata in schedule")
    return out.reset_index(drop=True)


def attach_qb_margin_adjustment(
    nonqb_projections: pd.DataFrame,
    qb_board: pd.DataFrame,
    *,
    max_abs_team_qb_impact: float = 5.0,
) -> pd.DataFrame:
    """The single forward Injury candidate: preserve the direct total projection.

    The previous team performance already reflects its recent QB mix. For
    each offense, apply only the *incremental* EPA-based QB replacement value,
    removing all QB rows from the general injury features before training.

    A change in expected team QB value shifts the home winning margin by
    (home_qb_shift - away_qb_shift). Its scoring allocation is symmetric: half
    to home and half away, maintaining the independent total estimate. The
    method was chosen after seeing retrospective 2026 performance and hence
    needs prospectively frozen, unmodified evaluation. Unknown QB status stays
    missing; never silently replace with zero.
    """
    required = {"game_id", "projected_home", "projected_away"}
    if not required.issubset(nonqb_projections.columns):
        raise ValueError(f"Non-QB injury projections lack {sorted(required - set(nonqb_projections.columns))}")
    if nonqb_projections["game_id"].duplicated().any():
        raise ValueError("Duplicate game IDs in Injury score base")
    out = nonqb_projections.copy()
    for side in ("home", "away"):
        frame = qb_board[qb_board["side"].eq(side)][
            ["game_id", "qb_point_shift_experimental"]
        ].rename(columns={"qb_point_shift_experimental": f"{side}_qb_point_shift"})
        if frame["game_id"].duplicated().any():
            raise ValueError(f"Duplicate {side} QB estimate")
        out = out.merge(frame, how="left", on="game_id", validate="one_to_one")
    # Guard against thin-sample QB EPA tails. Five points is near the 95th
    # percentile of the magnitude of single-team shifts in the 2026 review
    # (4.65 points). Chosen after that review; prospective testing is needed.
    if not np.isfinite(max_abs_team_qb_impact) or max_abs_team_qb_impact <= 0:
        raise ValueError("max_abs_team_qb_impact must be finite and positive")
    out["home_qb_point_shift_capped"] = pd.to_numeric(
        out["home_qb_point_shift"], errors="coerce"
    ).clip(-max_abs_team_qb_impact, max_abs_team_qb_impact)
    out["away_qb_point_shift_capped"] = pd.to_numeric(
        out["away_qb_point_shift"], errors="coerce"
    ).clip(-max_abs_team_qb_impact, max_abs_team_qb_impact)
    out["qb_margin_adjustment"] = (
        out["home_qb_point_shift_capped"] - out["away_qb_point_shift_capped"]
    )
    out["projected_home_qb_injury"] = (
        pd.to_numeric(out["projected_home"], errors="coerce")
        + out["qb_margin_adjustment"] / 2
    )
    out["projected_away_qb_injury"] = (
        pd.to_numeric(out["projected_away"], errors="coerce")
        - out["qb_margin_adjustment"] / 2
    )
    out["projected_total_qb_injury"] = (
        out["projected_home_qb_injury"] + out["projected_away_qb_injury"]
    )
    # Strong invariant, including rounding tolerance; critical to keep the
    # original total-model quality rather than changing it accidentally.
    known = out["qb_margin_adjustment"].notna()
    if known.any():
        original_total = out.loc[known, "projected_home"] + out.loc[known, "projected_away"]
        if not np.allclose(out.loc[known, "projected_total_qb_injury"], original_total, atol=1e-8):
            raise AssertionError("QB margin adjustment unexpectedly altered total")
    return out
