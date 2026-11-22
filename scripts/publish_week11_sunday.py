"""Publish Sunday Week 11 scores from the existing Baseline and Injury models."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import PBP_COLUMNS, normalize_schedule, build_efficiency_model_dataset, project_upcoming_efficiency
from injury_model import project_qb_aware_injury, _kickoff_utc
from research.validate_live_qb_roster import enforce_active_roster_qbs
from scripts.capture_qb_aware_injury import add_verified_only_sensitivity

PUB = ROOT / "data/public_snapshots"


def main():
    inputs = Path(sys.argv[1])
    now = pd.Timestamp.now(tz="UTC").floor("s")
    output = PUB / "nfl_week11_sunday_pregame_2026-11-22.csv"
    if output.exists():
        raise FileExistsError("This release already exists")
    schedule = normalize_schedule(pd.read_csv(inputs / "schedule.csv", low_memory=False))
    schedule = schedule.loc[schedule.season.between(2021, 2026)].copy()
    # Official November 9 flex announcement supersedes the stale schedule feed.
    schedule.loc[schedule.game_id.eq("2026_11_PIT_PHI"), "gametime"] = "13:00"
    schedule.loc[schedule.game_id.eq("2026_11_JAX_NYG"), "gametime"] = "16:25"
    target = schedule.loc[schedule.season.eq(2026) & schedule.week.eq(11) & schedule.home_score.isna() & schedule.away_score.isna()]
    kicks = {g.game_id: _kickoff_utc(pd.Series(g._asdict())) for g in target.itertuples()}
    if len(kicks) != 12 or any(pd.isna(t) or t <= now for t in kicks.values()):
        raise ValueError("Expected 12 upcoming Sunday/Monday games")
    years = range(2021, 2027)
    pbp = pd.concat([pd.read_csv(inputs / f"pbp_{year}.csv.gz",
        usecols=lambda c: c in PBP_COLUMNS, low_memory=False) for year in years], ignore_index=True)
    reports = pd.concat([pd.read_csv(inputs / f"injury_{year}.csv", low_memory=False)
                         for year in years], ignore_index=True)
    roster = pd.read_csv(inputs / "roster.csv", low_memory=False)
    # The schedule is provisional. Apply current team-supported expectations.
    expectations = []
    references = {

        "BAL": ("Jacoby Brissett", "https://www.baltimoreravens.com/news/transcript-press-conferences-11-18-26"),
    }
    for team, (name, url) in references.items():
        game = target.loc[target.away_team.eq(team)].iloc[0]
        identity = roster.loc[roster.team.eq(team) & roster.full_name.eq(name) & roster.week.eq(11)]
        if len(identity) != 1 or identity.iloc[0].status != "ACT":
            raise ValueError("Expected QB is absent from the current active roster")
        expectations.append(dict(game_id=game.game_id, team=team, qb_id=identity.iloc[0].gsis_id,
            qb_name=name, source_url=url, source_report_date="2026-11-18",
            expectation_status="COACH_EXPECTED_NOT_FINAL",
            review_note="Team Week 11 report documents this quarterback preparing for the matchup. Game-day starter remains provisional."))
    expected = pd.DataFrame(expectations)
    baseline = project_upcoming_efficiency(build_efficiency_model_dataset(schedule, pbp))
    baseline = baseline.loc[baseline.game_id.isin(kicks)].copy()
    from research.validate_qb_starter_confirmations import validate_starter_confirmations
    raw_confirmations = pd.read_csv(ROOT / "data/qb_starters/2026_week11_confirmed.csv")
    verified, source_audit = validate_starter_confirmations(schedule, raw_confirmations, checked_as_of_utc=now)
    if len(verified) != 1:
        raise ValueError("Johnson starter confirmation failed")
    injury, board = project_qb_aware_injury(schedule, pbp, reports, season=2026, week=11,
                                           expected_starters=expected, verified_starters=verified)
    injury = injury.loc[injury.game_id.isin(kicks)].copy()
    board = board.loc[board.game_id.isin(kicks)].copy()
    if board.loc[board.team.eq("ARI"), "qb_name"].tolist() != ["Josh Johnson"]:
        raise ValueError("Arizona starter must be Johnson")
    roster_audit = enforce_active_roster_qbs(board, roster, season=2026, week=11)
    injury = add_verified_only_sensitivity(injury, board)
    quotes = pd.read_csv(PUB / "nfl_week11_bovada_sunday_2026-11-22T1424Z.csv")
    quotes["game_id"] = "2026_11_" + quotes.away_team + "_" + quotes.home_team
    if set(quotes.game_id) != set(kicks) or quotes.game_id.duplicated().any():
        raise ValueError("Bovada coverage differs from the schedule")
    market = quotes.set_index("game_id")
    rows = []
    for model, frame in (("baseline", baseline), ("injury", injury)):
        for raw in frame.to_dict("records"):
            gid = raw["game_id"]
            q = market.loc[gid]
            if pd.Timestamp(q.captured_at_utc) >= kicks[gid]:
                raise ValueError("Quote must precede kickoff")
            record = {k: v for k, v in raw.items() if not isinstance(v, pd.Timestamp)}
            record.update(published_at_utc=now.isoformat(), publication_status="SUNDAY_PUBLIC_PREGAME_2026_WEEK11",
                model=model, model_version="baseline_ridge_alpha10_lookback10" if model == "baseline" else "qb_epa_margin_cap5_v1_provisional",
                gameday=pd.Timestamp(raw["gameday"]).strftime("%Y-%m-%d"),
                kickoff_utc=kicks[gid].isoformat(), model_home_margin=raw["projected_home"] - raw["projected_away"],
                bovada_home_favored_spread=q.home_favorite_spread, bovada_total=q.total_line,
                bovada_snapshot_at_utc=q.captured_at_utc,
                source_note="Sunday morning board with final injury designations. Johnson confirmed for Arizona, Mayfield expected per NFL Network. Game-day inactives pending.")
            if model == "injury":
                for side in ("home", "away"):
                    detail = board.loc[board.game_id.eq(gid) & board.side.eq(side)].iloc[0]
                    for col in ("qb_name", "qb_id", "starter_source", "qb_prior_dropbacks", "confidence"):
                        record[f"{side}_{col if col.startswith('qb_') else 'qb_' + col}"] = detail[col]
            rows.append(record)
    result = pd.DataFrame(rows).sort_values(["kickoff_utc", "game_id", "model"])
    if len(result) != 24 or result.duplicated(["game_id", "model"]).any():
        raise ValueError("Incomplete release")
    assert np.isfinite(result[["projected_home", "projected_away", "projected_total"]]).all().all()
    np.testing.assert_allclose(result.projected_home + result.projected_away, result.projected_total, atol=1e-6)
    pd.testing.assert_series_equal(
        injury.projected_total.reset_index(drop=True),
        (injury.original_non_qb_home + injury.original_non_qb_away).reset_index(drop=True),
        check_names=False,
    )
    result.to_csv(output, index=False, float_format="%.10g")
    board.to_csv(PUB / "nfl_week11_qb_identity_2026-11-22.csv", index=False)
    roster_audit.to_csv(PUB / "nfl_week11_qb_identity_roster_2026-11-22.csv", index=False)
    source_audit.to_csv(PUB / "nfl_week11_qb_identity_source_audit_2026-11-22.csv", index=False)
    hashes = {}
    for name in ["schedule.csv", "roster.csv", *(f"pbp_{y}.csv.gz" for y in years), *(f"injury_{y}.csv" for y in years)]:
        with (inputs / name).open("rb") as handle:
            hashes[name] = hashlib.file_digest(handle, "sha256").hexdigest()
    (output.with_name(output.stem + "_manifest.json")).write_text(json.dumps(dict(
        published_at_utc=now.isoformat(), games=12, models=["baseline", "injury"],
        starter_evidence=board.starter_source.value_counts().to_dict(),
        roster_checked_team_games=len(roster_audit), paid_api_requests=0, input_sha256=hashes,
        injury_snapshot="data/injury_snapshots/injuries_2026_week_11_20261122T065119Z.csv",
        kickoff_source="https://media.nfl.com/news-and-releases/week-11-schedule-change--jaguars-giants-to-4-25-p-m--et--steeler",
        sunday_refresh="New snapshot after updated user Bovada quotes and final injury reports",
    ), indent=2) + "\n")
    print(result[["game_id", "model", "projected_away", "projected_home", "projected_total"]].to_string(index=False))


if __name__ == "__main__":
    main()
