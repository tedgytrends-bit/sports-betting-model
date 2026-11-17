"""Freeze a research-only QB-off/on pair using local public nflverse inputs."""

from argparse import ArgumentParser
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from injury_model import _kickoff_utc, project_qb_aware_injury
from model import PBP_COLUMNS, normalize_schedule
from research.validate_live_qb_roster import enforce_active_roster_qbs
from research.validate_qb_starter_confirmations import validate_starter_confirmations
from scripts.capture_qb_aware_injury import load_coach_expected_starters


def freeze(inputs, output, season, week):
    started = pd.Timestamp.now(tz="UTC")
    schedule = normalize_schedule(pd.read_csv(inputs / "schedule.csv", low_memory=False))
    start_day = started.tz_convert("America/New_York").tz_localize(None).normalize()
    season_mask = schedule.season.between(2021, season)
    target = schedule.season.eq(season) & schedule.week.eq(week)
    schedule = schedule.loc[season_mask & (schedule.gameday.lt(start_day) | target)].copy()
    slate = schedule.loc[target.reindex(schedule.index)]
    kicks = slate.set_index("game_id").apply(_kickoff_utc, axis=1)
    if (slate.empty or slate[["home_score", "away_score"]].notna().any().any()
            or slate.gametime.isna().any() or not kicks.gt(started).all()):
        raise ValueError("A freeze requires an entirely upcoming slate with known kickoff times")

    years = range(2021, season + 1)
    pbp = pd.concat([
        pd.read_csv(inputs / f"pbp_{year}.csv.gz", usecols=lambda name: name in PBP_COLUMNS, low_memory=False)
        for year in years
    ], ignore_index=True)
    complete = schedule.dropna(subset=["home_score", "away_score"])
    if not set(complete.game_id).issubset(pbp.game_id):
        raise ValueError("Completed games are absent from the supplied play-by-play")
    pbp = pbp.loc[pbp.game_id.isin(complete.game_id)].copy()
    reports = pd.concat([
        pd.read_csv(inputs / f"injury_{year}.csv", low_memory=False) for year in years
    ], ignore_index=True)
    attestations = Path(f"data/qb_starters/{season}_week{week:02d}_confirmed.csv")
    verified = None
    if attestations.exists():
        verified, _ = validate_starter_confirmations(
            schedule, pd.read_csv(attestations), checked_as_of_utc=started
        )
    expected = load_coach_expected_starters(schedule, season, week)
    if expected is not None:
        expected = expected.loc[pd.to_datetime(expected.source_report_date).lt(start_day)]
    scores, board = project_qb_aware_injury(
        schedule, pbp, reports, season=season, week=week, verified_starters=verified,
        expected_starters=expected,
    )
    if set(scores.game_id) != set(kicks.index):
        raise ValueError("The fitted pair did not cover the full upcoming slate")

    roster_path = inputs / f"roster_{season}.csv"
    roster = pd.read_csv(roster_path, low_memory=False)
    # Position/group checks run independently so a blocked game cannot certify a different game.
    roster_status = {}
    for game_id, group in board.groupby("game_id"):
        try:
            enforce_active_roster_qbs(group, roster, season=season, week=week)
            roster_status[game_id] = "both_active_in_current_roster"
        except ValueError as error:
            roster_status[game_id] = str(error)
    frozen = pd.Timestamp.now(tz="UTC").floor("s")
    if not kicks.gt(frozen).all():
        raise ValueError("A game kicked off during forecast generation")
    result = scores[["game_id", "home_team", "away_team", "training_games",
                     "home_injury_report_available", "away_injury_report_available"]].copy()
    result["captured_at_utc"] = frozen
    result["kickoff_utc"] = result.game_id.map(kicks)
    result["qb_off_home_margin"] = scores.original_non_qb_home - scores.original_non_qb_away
    result["qb_on_home_margin"] = scores.projected_home - scores.projected_away
    result["qb_margin_adjustment"] = scores.qb_margin_adjustment
    np.testing.assert_allclose(result.qb_on_home_margin - result.qb_off_home_margin,
                               result.qb_margin_adjustment, equal_nan=True)
    evidence = board[["game_id", "side", "qb_id", "qb_name", "starter_source", "source_url",
                      "qb_prior_dropbacks", "qb_weighted_dropbacks", "confidence"]]
    for side in ("home", "away"):
        detail = evidence.loc[evidence.side.eq(side)].drop(columns="side").set_index("game_id")
        result = result.join(detail.add_prefix(f"{side}_"), on="game_id", validate="one_to_one")
    result["roster_evidence"] = result.game_id.map(roster_status)
    result["research_status"] = "FROZEN_RESEARCH_PAIR_PENDING_PREGAME_BOVADA_QUOTE"
    result = result.sort_values(["kickoff_utc", "game_id"])
    with output.open("x") as handle:
        result.to_csv(handle, index=False, float_format="%.10g")
    with output.with_suffix(".sha256").open("x") as handle:
        names = ["schedule.csv", roster_path.name, *(f"pbp_{year}.csv.gz" for year in years),
                 *(f"injury_{year}.csv" for year in years)]
        for name in names:
            with (inputs / name).open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            handle.write(f"{digest}  {name}\n")
    print(f"Froze {len(result)} research-only pairs at {frozen.isoformat()}")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()
    freeze(args.inputs, args.output, args.season, args.week)
