"""No-hindsight daily CBB reporting, calendar rollover and paired-sample tests."""
from datetime import date, datetime, timezone

import pytest

from cbb.performance_report import (
    central_date, generate_performance_report, head_to_head, scorecard,
)
from cbb.prospective_grade import iso_weeks_between


def graded(i, tip, ats="W", total="W", player=True, v4=False):
    models = {
        "baseline": {
            "ats": ats, "total": total, "ats_edge": 4.2,
            "total_edge": -4.5, "margin_mae": 13.5,
            "total_mae": 15.0,
        },
    }
    if player:
        models["player_v2"] = {
            "ats": "L" if ats == "W" else "W",
            "total": "W", "ats_edge": -3.6,
            "total_edge": 2.2, "margin_mae": 8.0,
            "total_mae": 14.0,
        }
    if v4:
        models["player_all_v4"] = {
            "ats": "W", "total": "L", "ats_edge": 7.0,
            "total_edge": 4.0, "margin_mae": 9.0,
            "total_mae": 12.0,
        }
    return {
        "id": str(i),
        "tip_utc": tip,
        "captured_utc": "2026-11-05T21:30:00Z",
        "away": "Away", "home": "Home",
        "away_points": 68, "home_points": 73,
        "market_provider": "Bovada", "home_spread": -3.5,
        "market_total": 142.0, "models": models,
    }


def now():
    return datetime(2026, 11, 7, 17, tzinfo=timezone.utc)


def test_iso_week_rollover_from_thursday_to_next_monday():
    assert list(iso_weeks_between(
        date(2026, 11, 5), date(2026, 11, 9)
    )) == ["2026-W45", "2026-W46"]
    assert list(iso_weeks_between(
        date(2026, 12, 31), date(2027, 1, 5)
    )) == ["2026-W53", "2027-W01"]


def test_time_zone_groups_evening_games_under_previous_central_date():
    game = graded(1, "2026-11-06T01:00:00Z")
    assert central_date(game) == "2026-11-05"
    report = generate_performance_report([game], 3, 1, now())
    assert report["daily_by_central_date"][0]["date_central"] == "2026-11-05"
    assert report["tracked_games"] == 1
    assert report["completed_untracked_since_first_capture"] == 3
    assert report["invalid_frozen_records"] == 1
    assert report["first_graded_tip_utc"] == "2026-11-06T01:00:00Z"


def test_all_direction_roi_includes_pushes_and_exact_threshold():
    games = [graded(1, "2026-11-06T01:00:00Z"),
             graded(2, "2026-11-06T23:00:00Z", ats="L"),
             graded(3, "2026-11-07T01:00:00Z", ats="P")]
    score = scorecard(games, "baseline", "ats", 0)
    assert (score["wins"], score["losses"], score["pushes"]) == (1, 1, 1)
    assert score["selections"] == 3
    assert score["roi_minus_110_pct"] == -3.03
    assert scorecard(games, "baseline", "ats", 3.5) == score
    assert scorecard(games, "player_v2", "total", 3.5)["selections"] == 0
    assert scorecard(games, "player_v2", "total", 0)["selections"] == 3


def test_no_backfill_of_v4_and_paired_mae_only_on_matching_snapshots():
    old = graded(1, "2026-11-06T01:00:00Z")
    fresh = graded(2, "2026-11-06T23:00:00Z", v4=True)
    report = generate_performance_report([old, fresh], 0, 0, now())
    v4 = report["all_tracked"]["player_all_v4"]["ats"]["0"]
    assert v4["games_with_model"] == 1 and v4["selections"] == 1
    assert report["all_tracked"]["player_v2"]["ats"]["0"]["selections"] == 2
    comparisons = {d["model"]: d for d in report["paired_model_accuracy_vs_baseline"]}
    assert comparisons["player_all_v4"]["paired_games"] == 1
    assert comparisons["player_all_v4"]["ats_mae_improvement_vs_baseline"] == 4.5
    assert comparisons["player_rot_v4"]["paired_games"] == 0


def test_rolling_48h_excludes_older_results_from_recent_card():
    games = [graded(1, "2026-11-06T01:00:00Z"),
             graded(2, "2026-11-06T23:00:00Z")]
    report = generate_performance_report(games, 0, 0, now())
    assert report["tracked_games"] == 2
    assert report["last_48_hours"]["tracked_games"] == 2
    assert len(report["daily_by_central_date"]) == 2
    later = datetime(2026, 11, 10, 0, tzinfo=timezone.utc)
    expired = generate_performance_report(games, 0, 0, later)
    assert expired["last_48_hours"]["tracked_games"] == 0
    assert expired["last_7_days"]["tracked_games"] == 2


def test_refuse_posttip_or_duplicate_or_future_results():
    a = graded(1, "2026-11-06T01:00:00Z")
    with pytest.raises(ValueError, match="Duplicate"):
        generate_performance_report([a, a], 0, 0, now())
    with pytest.raises(ValueError, match="not frozen pretip"):
        generate_performance_report(
            [{**a, "captured_utc": "2026-11-06T01:00:01Z"}],
            0, 0, now(),
        )
    with pytest.raises(ValueError, match="Future"):
        generate_performance_report(
            [{**a, "tip_utc": "2026-11-08T10:00:00Z"}],
            0, 0, now(),
        )
