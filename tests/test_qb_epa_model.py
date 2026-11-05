"""Guard against QB double penalties, future-data leakage and missing starter labels."""
import numpy as np
import pandas as pd
import pytest

from injury_model import _counts_for_team
from qb_epa_model import qb_game_stats, build_qb_epa_board, attach_qb_shifts, attach_qb_margin_adjustment, starters_from_game_schedule


def sample():
    schedule = pd.DataFrame([
        dict(game_id="g1", gameday="2026-09-01", home_team="BAL", away_team="JAX", home_score=21, away_score=17),
        dict(game_id="g2", gameday="2026-09-08", home_team="BAL", away_team="JAX", home_score=24, away_score=10),
        dict(game_id="target", gameday="2026-11-05", home_team="BAL", away_team="JAX", home_score=np.nan, away_score=np.nan),
        dict(game_id="future", gameday="2026-11-10", home_team="BAL", away_team="JAX", home_score=30, away_score=0),
    ])
    plays = []
    for game_id, team, qb_id, epa, n in [
        ("g1", "BAL", "lamar", .25, 12),
        ("g2", "BAL", "lamar", .20, 12),
        ("g1", "JAX", "trevor", .10, 12),
        ("g2", "JAX", "trevor", .10, 12),
        ("g2", "BAL", "fagnano", -.70, 3),
        ("future", "BAL", "fagnano", 99.0, 15),
    ]:
        for _ in range(n):
            plays.append(dict(game_id=game_id, posteam=team,
                              passer_player_id=qb_id, passer_player_name=qb_id,
                              epa=epa, play_type="pass"))
    return schedule, pd.DataFrame(plays)


def override(qb="fagnano"):
    return pd.DataFrame([{
        "game_id": "target", "team": "BAL", "qb_id": qb,
        "qb_name": qb, "source_url": "https://www.baltimoreravens.com/news/qb"
    }])


def test_verified_starter_and_prior_data_only():
    schedule, plays = sample()
    stats = qb_game_stats(plays, schedule)
    board = build_qb_epa_board(stats, schedule, schedule.iloc[[2]], override())
    assert len(board) == 2
    bal = board[board.team.eq("BAL")].iloc[0]
    assert bal.qb_id == "fagnano"
    assert bal.starter_source == "verified_pregame"
    assert bal.qb_prior_dropbacks == 3
    assert bal.qb_delta_epa_per_dropback < 0
    assert 0 < bal.starter_recent_team_dropback_share < 1
    assert bal.qb_point_shift_experimental < 0
    assert bal.qb_prior_dropbacks != 18  # excludes future-game plays


def test_no_qb_absence_double_count():
    rows = pd.DataFrame([
        {"position": "QB", "report_status": "OUT", "practice_status": "Did Not Participate"},
        {"position": "QB", "report_status": "OUT", "practice_status": "Did Not Participate"},
        {"position": "WR", "report_status": "OUT", "practice_status": "Did Not Participate"},
    ])
    original = _counts_for_team(rows)
    neutral = _counts_for_team(rows, exclude_qb=True)
    assert original["qb_out"] == 2
    assert original["inj_out"] == 3
    assert neutral["qb_out"] == 0
    assert neutral["inj_out"] == 1
    assert neutral["practice_dnp"] == 1
    assert neutral["injury_report_available"] == 1


def test_unverified_starter_explicitly_labeled():
    schedule, plays = sample()
    stats = qb_game_stats(plays, schedule)
    board = build_qb_epa_board(stats, schedule, schedule.iloc[[2]])
    bal = board[board.team.eq("BAL")].iloc[0]
    assert bal.starter_source == "inferred_previous_primary_passer"
    assert bal.qb_id == "lamar"


def test_invalid_override_fails_closed():
    schedule, plays = sample()
    stats = qb_game_stats(plays, schedule)
    bad = override()
    bad.loc[0, "source_url"] = ""
    with pytest.raises(ValueError, match="lacks source"):
        build_qb_epa_board(stats, schedule, schedule.iloc[[2]], bad)


def test_missing_history_not_turned_into_zero():
    schedule, plays = sample()
    stats = qb_game_stats(plays, schedule)
    new_team = pd.DataFrame([dict(game_id="new", gameday="2026-09-01",
                                   home_team="NEW", away_team="JAX")])
    board = build_qb_epa_board(stats, schedule, new_team)
    one = board[board.team.eq("NEW")].iloc[0]
    assert one.starter_source == "unknown_no_pregame_evidence"
    assert pd.isna(one.qb_point_shift_experimental)


def test_attachment_preserves_unknowns():
    projection = pd.DataFrame([
        dict(game_id="a", projected_home=20., projected_away=15.),
        dict(game_id="b", projected_home=21., projected_away=17.),
    ])
    board = pd.DataFrame([
        dict(game_id="a", side="home", qb_point_shift_experimental=-3.),
        dict(game_id="a", side="away", qb_point_shift_experimental=1.),
    ])
    result = attach_qb_shifts(projection, board)
    assert result.loc[0, "home_qb_adjusted"] == 17.
    assert result.loc[0, "away_qb_adjusted"] == 16.
    assert pd.isna(result.loc[1, "projected_total_qb_adjusted"])


def test_established_qb_is_already_in_team_baseline():
    schedule, plays = sample()
    stats = qb_game_stats(plays, schedule)
    board = build_qb_epa_board(stats, schedule, schedule.iloc[[2]])
    bal = board[board.team.eq("BAL")].iloc[0]
    # 24 of 27 previous BAL QB dropbacks belong to the same quarterback;
    # direct long-term vs recent EPA comparison would penalize the incumbent.
    assert bal.starter_recent_team_dropback_share == pytest.approx(24 / 27)
    raw_gap = bal.qb_shrunk_epa_per_dropback - bal.team_recent_qb_epa_per_dropback
    assert bal.qb_delta_epa_per_dropback == pytest.approx(raw_gap * 3 / 27)


def test_nflverse_schedule_recognizes_completed_game_starters():
    schedule, plays = sample()
    schedule["home_qb_id"] = ["lamar", "lamar", "fagnano", "fagnano"]
    schedule["home_qb_name"] = ["Lamar Jackson", "Lamar Jackson", "Joe Fagnano", "Joe Fagnano"]
    schedule["away_qb_id"] = ["trevor"]*4
    schedule["away_qb_name"] = ["Trevor Lawrence"]*4
    observed = starters_from_game_schedule(schedule, completed_only=True)
    assert set(observed.game_id) == {"g1","g2","future"}
    # Future has scores in this synthetic set; "target" must stay excluded.
    assert "target" not in set(observed.game_id)
    current = starters_from_game_schedule(schedule, completed_only=False)
    assert current[current.game_id.eq("target")].iloc[0].starter_evidence == "schedule_provisional_qb_unverified"
    assert set(observed.starter_evidence) == {"schedule_recorded_starter_postgame"}
    stats = qb_game_stats(plays, schedule)
    board = build_qb_epa_board(stats, schedule, schedule.iloc[[2]], observed=current)
    bal = board[board.team.eq("BAL")].iloc[0]
    assert bal.qb_id == "fagnano"
    assert bal.starter_source == "schedule_provisional_qb_unverified"


def test_qb_margin_only_preserves_total_and_moves_spread():
    base = pd.DataFrame([{"game_id":"g1","projected_home":24., "projected_away":23.}])
    board = pd.DataFrame([
        {"game_id":"g1","side":"home","qb_point_shift_experimental":-5.0},
        {"game_id":"g1","side":"away","qb_point_shift_experimental":-0.2},
    ])
    projected=attach_qb_margin_adjustment(base,board).iloc[0]
    assert projected.qb_margin_adjustment == pytest.approx(-4.8)
    assert projected.projected_home_qb_injury == pytest.approx(21.6)
    assert projected.projected_away_qb_injury == pytest.approx(25.4)
    assert projected.projected_total_qb_injury == pytest.approx(47.0)


def test_qb_margin_only_requires_both_qb_shifts():
    base = pd.DataFrame([{"game_id":"g1","projected_home":24., "projected_away":23.}])
    board = pd.DataFrame([{"game_id":"g1","side":"away","qb_point_shift_experimental":0.0}])
    result=attach_qb_margin_adjustment(base,board)
    assert pd.isna(result.loc[0,"projected_total_qb_injury"])
