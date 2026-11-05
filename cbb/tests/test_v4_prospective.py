"""Future-only v4 capture tests; older frozen records must remain model-limited."""
from datetime import datetime, timezone
import pytest
from cbb.prospective import build_capture
from cbb.prospective_grade import grade_frozen, summarize

NOW=datetime(2026,11,5,22,0,tzinfo=timezone.utc)
TIP="2026-11-06T00:00:00Z"


def forecast(i="900",margin=6):
    return dict(id=i,season=2027,status="scheduled",start_date=TIP,
                home="Home",away="Away",home_games=1,away_games=1,neutral=0,
                home_spread=-3.5,market_total=140,provider="Bovada",
                projected_margin_home=margin,projected_total=144,
                projected_home_points=(144+margin)/2,
                projected_away_points=(144-margin)/2,
                ats_edge=margin-3.5,total_edge=4,
                ats_lean="home" if margin>3.5 else "away",
                total_lean="over",training_games=30000,
                home_rotation_source_games=1,away_rotation_source_games=1,
                home_rotation_box_coverage=1,away_rotation_box_coverage=1,
                home_rotation_last_box_present=1,
                away_rotation_last_box_present=1,
                home_rotation_key_minutes_missing=.18,
                away_rotation_key_minutes_missing=0)


def game():
    return dict(id=900,season=2027,status="scheduled",startDate=TIP,
                homeTeamId=1,awayTeamId=2)


def captured(with_v4):
    kw=dict(baseline=[forecast()],player=[forecast()],
            opponent_player=[forecast(margin=4)],games=[game()],
            priors={},captured_utc=NOW)
    if with_v4:
        kw["rotation_player"]=[forecast(margin=8)]
        kw["combined_player"]=[forecast(margin=9)]
    return build_capture(**kw)


def final():
    return {**game(),"status":"final","homePoints":80,"awayPoints":70}


def test_v4_only_new_capture():
    old=captured(False)["games"][0]
    new=captured(True)["games"][0]
    assert "player_rot_v4" not in old and "player_all_v4" not in old
    assert new["player_rot_v4"]["projected_margin_home"]==8
    assert new["player_all_v4"]["projected_margin_home"]==9
    assert new["rotation_coverage"]["home"]["prior_key_minutes_missing"]==.18


def test_v4_grading_skips_legacy_immutable_snapshots():
    old=captured(False)
    new=captured(True)
    legacy=grade_frozen({"capture_utc":old["capture_utc"],
                         "game":old["games"][0]},final())
    future=grade_frozen({"capture_utc":new["capture_utc"],
                         "game":new["games"][0]},final())
    assert "player_rot_v4" not in legacy["models"]
    assert "player_all_v4" not in legacy["models"]
    assert future["models"]["player_rot_v4"]["ats"]=="W"
    assert future["models"]["player_all_v4"]["ats"]=="W"
    report=summarize([legacy,future],0)
    for name in ("player_rot_v4","player_all_v4"):
        row=[r for r in report["grades"] if r["model"]==name
             and r["market"]=="ats" and r["threshold"]==0][0]
        assert row["graded_games_with_model"]==1
        assert row["tracked_leans"]==1
    baseline=[r for r in report["grades"] if r["model"]=="baseline"
              and r["market"]=="ats" and r["threshold"]==0][0]
    assert baseline["graded_games_with_model"]==2


def test_v4_game_id_join_rejects_wrong_and_duplicate():
    with pytest.raises(ValueError,match="same unique game IDs"):
        build_capture([forecast()],[forecast()],[game()],{},NOW,
                      rotation_player=[forecast(i="999")])
    with pytest.raises(ValueError,match="same unique game IDs"):
        build_capture([forecast()],[forecast()],[game()],{},NOW,
                      combined_player=[forecast(),forecast()])
