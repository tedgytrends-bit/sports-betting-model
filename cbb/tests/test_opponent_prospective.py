"""Ensure v3 is genuinely prospective and absent from earlier frozen records."""
from datetime import datetime, timezone, timedelta

import pytest

from cbb.prospective import build_capture
from cbb.prospective_grade import grade_frozen, summarize


NOW = datetime(2026, 11, 5, 21, 0, tzinfo=timezone.utc)
TIP = "2026-11-05T23:00:00Z"


def forecast(margin=6.0, label=None):
    return {
        "id": "700", "season": 2027, "start_date": TIP,
        "status": "scheduled", "home": "Home", "away": "Away",
        "home_games": 0, "away_games": 0, "neutral": 0,
        "provider": "Bovada", "home_spread": -5.0, "market_total": 150.0,
        "projected_margin_home": margin, "projected_total": 155.0,
        "projected_home_points": (155 + margin) / 2,
        "projected_away_points": (155 - margin) / 2,
        "ats_edge": margin - 5, "total_edge": 5,
        "ats_lean": "home" if margin > 5 else "away",
        "total_lean": "over", "training_games": 13000,
    }


def fixture_game():
    return {
        "id": 700, "season": 2027, "startDate": TIP,
        "status": "scheduled", "homeTeamId": 1, "awayTeamId": 2,
    }


def final():
    return {
        **fixture_game(), "status": "final",
        "homePoints": 82, "awayPoints": 73,
    }


def test_v3_goes_into_new_capture_only():
    older = build_capture([forecast()], [forecast()], [fixture_game()], {}, NOW)
    assert "player_opp_v3" not in older["games"][0]

    future = build_capture(
        [forecast()], [forecast()], [fixture_game()], {}, NOW,
        opponent_player=[forecast(margin=-1.0)],
    )
    assert future["games"][0]["player_opp_v3"]["projected_margin_home"] == -1.0
    assert future["games"][0]["baseline"]["projected_margin_home"] == 6.0
    assert future["games"][0]["player_v2"]["projected_margin_home"] == 6.0
    assert future["games"][0]["freeze_candidate"] is True
    assert future["capture_type"] == "research_shadow"


def test_old_frozen_grades_only_original_models_and_v3_coverage_reported():
    earlier = build_capture([forecast()], [forecast()], [fixture_game()], {}, NOW)
    grade_old = grade_frozen({"capture_utc": earlier["capture_utc"],
                              "game": earlier["games"][0]}, final())
    assert "player_opp_v3" not in grade_old["models"]

    future = build_capture(
        [forecast()], [forecast()], [fixture_game()], {}, NOW,
        opponent_player=[forecast(margin=-1.0)],
    )
    grade_new = grade_frozen({"capture_utc": future["capture_utc"],
                              "game": future["games"][0]}, final())
    assert grade_new["models"]["player_opp_v3"]["ats"] == "L"
    old_and_new = summarize([grade_old, grade_new], untracked=0)
    v3 = [
        r for r in old_and_new["grades"]
        if r["model"] == "player_opp_v3" and r["market"] == "ats"
        and r["threshold"] == 0
    ][0]
    baseline = [
        r for r in old_and_new["grades"]
        if r["model"] == "baseline" and r["market"] == "ats"
        and r["threshold"] == 0
    ][0]
    assert v3["graded_games_with_model"] == 1
    assert v3["tracked_leans"] == 1
    assert baseline["graded_games_with_model"] == 2
    assert baseline["tracked_leans"] == 2


def test_v3_game_ids_must_match_to_prevent_false_joins():
    with pytest.raises(ValueError, match="same game IDs"):
        build_capture([forecast()], [forecast()], [fixture_game()], {}, NOW,
                      opponent_player=[{**forecast(), "id": "999"}])
    with pytest.raises(ValueError, match="same game IDs"):
        build_capture([forecast()], [forecast()], [fixture_game()], {}, NOW,
                      opponent_player=[forecast(), forecast()])
