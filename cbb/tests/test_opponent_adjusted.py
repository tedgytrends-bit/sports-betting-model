"""Chronology and opponent rating regression tests (no API requests)."""
import pytest

from cbb.opponent_adjusted import (
    ADJ_FEATURES, attach_adjustments, fit_ratings, pregame_opponent_adjustments,
)


def game(i, day, home=1, away=2, hp=85, ap=65, season=2025, status="final"):
    return dict(
        id=i, season=season, startDate=day + "T20:00:00Z",
        homeTeamId=home, awayTeamId=away, homeTeam="Home", awayTeam="Away",
        homePoints=hp, awayPoints=ap, status=status, neutralSite=False,
    )


def test_same_day_games_freeze_before_all_outcomes():
    games = [
        game(1, "2024-11-10", home=1, away=2, hp=155, ap=50),
        game(2, "2024-11-10", home=1, away=3, hp=50, ap=155),
        game(3, "2024-11-11", home=1, away=2, hp=90, ap=80),
    ]
    feat = pregame_opponent_adjustments(games)
    for field in ADJ_FEATURES:
        assert feat["1"][field] == feat["2"][field]
    assert feat["1"]["home_adj_off"] == 100.0
    assert feat["1"]["home_adj_pace"] == 69.0
    assert feat["3"]["home_adj_off"] != 100.0


def test_previous_opponent_quality_affects_adj_offense():
    samples = [
        game(1, "2024-11-09", home=2, away=3, hp=50, ap=55),
        game(2, "2024-11-10", home=1, away=2, hp=90, ap=60),
        game(3, "2024-11-11", home=1, away=4, status="scheduled", hp=None, ap=None),
        game(4, "2024-11-12", home=1, away=3, hp=70, ap=60),
    ]
    feats = pregame_opponent_adjustments(samples)
    assert feats["3"]["home_adj_off"] > 100
    assert feats["3"]["away_adj_off"] == 100
    assert feats["3"]["home_opponent_net"] != 0


def test_no_future_game_or_same_day_score_leakage():
    samples = [
        game(1, "2024-11-09", home=1, away=2, hp=95, ap=40),
        game(2, "2024-11-11", home=1, away=3, hp=90, ap=65),
        game(3, "2024-11-11", home=2, away=3, hp=45, ap=125),
        game(4, "2024-11-13", home=1, away=2, hp=110, ap=80),
    ]
    a = pregame_opponent_adjustments(samples)
    revised = [dict(g) for g in samples]
    revised[1]["homePoints"] = 25
    revised[2]["awayPoints"] = 35
    revised[3]["homePoints"] = 30
    b = pregame_opponent_adjustments(revised)
    assert a["2"] == b["2"]
    assert a["3"] == b["3"]
    assert a["4"] != b["4"]


def test_seasons_reset_and_unknown_games_are_neutral():
    samples = [
        game(1, "2024-11-10", home=1, away=2, hp=145, ap=45),
        game(2, "2025-11-10", home=1, away=2, season=2026, status="scheduled", hp=None, ap=None),
    ]
    p = pregame_opponent_adjustments(samples)
    assert p["2"]["home_adj_off"] == 100.0
    assert p["2"]["home_adj_net"] == 0


def test_join_requires_all_features():
    x = pregame_opponent_adjustments([game(1, "2024-11-10")])
    result = attach_adjustments([{"id": "1", "season": 2025}], x)
    assert result[0]["away_adj_def"] == 100
    with pytest.raises(ValueError, match="Missing opponent"):
        attach_adjustments([{"id": "99"}], x)


def test_extreme_observations_are_finite_and_bounded():
    x = fit_ratings({"1": [("2", 170, 45, 100)] * 20,
                     "2": [("1", 45, 170, 48)] * 20})
    for values in x.values():
        assert 55 <= values[0] <= 160
        assert 55 <= values[1] <= 160
        assert 48 <= values[2] <= 100
