"""Upcoming CBB projection report: market sign, leans, and past-tip safety."""
import pytest
from cbb.readable_projections import render_projections, ats_lean, total_lean


def game(i=1, tip="2026-11-07T20:00:00Z", spread=-3.5, total=151.5):
    forecast = dict(
        projected_away_points=71.2,
        projected_home_points=78.3,
        projected_total=149.5,
        projected_margin_home=7.1,
        ats_lean="home", ats_edge=3.6,
        total_lean="under", total_edge=-2.0,
    )
    away = dict(forecast, ats_lean="away", ats_edge=-1.3,
                total_lean="over", total_edge=1.6)
    return dict(
        id=str(i), tip_utc=tip,
        away="VCU", home="Memphis",
        market=dict(provider="Draft Kings", home_spread=spread, total=total),
        baseline=forecast, player_v2=forecast,
        player_opp_v3=away, player_rot_v4=forecast,
        player_all_v4=away,
    )


def captured(games):
    return dict(
        capture_type="research_shadow",
        capture_utc="2026-11-06T20:00:00Z",
        season=2027, games=games,
    )


def test_all_models_market_and_score_shown_without_retrospective_claims():
    text = render_projections(captured([game()]))
    assert "Upcoming Projections" in text
    assert "Next eight days:** 1" in text
    assert "With market lines:** 1" in text
    assert "VCU @ Memphis" in text
    assert "Memphis -3.5" in text
    assert "VCU +3.5" in text
    assert "Under 151.5" in text
    assert "Over 151.5" in text
    assert "71.2" in text and "78.3" in text and "149.5" in text
    assert "Player + opponent + rotation v4" in text
    assert "Team baseline" in text and "Player v2" in text
    assert "[Results and ROI](README.md)" in text
    assert "originally frozen" in text


def test_missing_market_is_not_a_fake_betting_lean():
    empty = game(spread=None, total=None)
    result = render_projections(captured([empty]))
    assert "Without market lines:** 1" in result
    assert "No games had a usable spread or total" in result
    assert "Under 151.5" not in result
    assert ats_lean(empty, empty["baseline"]) == "—"
    assert total_lean(empty, empty["baseline"]) == "—"


def test_one_market_type_does_not_infer_missing_other_type():
    missing_total = game(total=None)
    text = render_projections(captured([missing_total]))
    assert "Memphis -3.5" in text
    assert "Total —" in text
    assert total_lean(missing_total, missing_total["baseline"]) == "—"
    assert ats_lean(missing_total, missing_total["baseline"]) != "—"


def test_refuses_past_tipped_and_duplicate_games():
    with pytest.raises(ValueError, match="past game"):
        render_projections(captured([game(tip="2026-11-06T19:00:00Z")]))
    with pytest.raises(ValueError, match="Duplicate"):
        render_projections(captured([game(), game()]))


def test_rejects_bad_capture_and_naive_timestamp():
    with pytest.raises(ValueError, match="not a CBB"):
        render_projections(dict(captured([game()]), capture_type="past"))
    with pytest.raises(ValueError, match="timezone"):
        render_projections(dict(captured([game()]), capture_utc="2026-11-06T20:00:00"))


def test_only_present_models_printed():
    incomplete = game()
    incomplete.pop("player_all_v4")
    text = render_projections(captured([incomplete]))
    assert "Player + opponent + rotation v4" not in text
    assert "Player + opponent v3" in text
