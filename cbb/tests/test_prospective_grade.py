"""Offline integrity tests for actual frozen pretip CBB grading."""
import pytest
from cbb.prospective_grade import grade_frozen, summarize, iso_week


def frozen(tip="2026-11-06T01:00:00Z", captured="2026-11-05T21:30:00Z"):
    return {
        "capture_utc":captured,
        "game":{
            "id":"700", "tip_utc":tip,"home":"Home","away":"Away",
            "home_team_id":"1","away_team_id":"2",
            "market":{"provider":"Bovada","home_spread":-5.0,"total":155.0},
            "baseline":{"projected_margin_home":11.0,"projected_total":161.0,
                        "ats_edge":6.0,"total_edge":6.0,"ats_lean":"home","total_lean":"over"},
            "player_v2":{"projected_margin_home":0.0,"projected_total":148.0,
                        "ats_edge":-5.0,"total_edge":-7.0,"ats_lean":"away","total_lean":"under"}
        }
    }


def final(hp=84,ap=75,tip="2026-11-06T01:00:00Z"):
    return {"id":700,"season":2027,"status":"final","startDate":tip,
            "homeTeamId":1,"awayTeamId":2,"homePoints":hp,"awayPoints":ap}


def test_grades_both_models_against_original_book_line():
    g=grade_frozen(frozen(),final())
    assert g["models"]["baseline"]["ats"]=="W"
    assert g["models"]["baseline"]["total"]=="W"
    assert g["models"]["player_v2"]["ats"]=="L"
    assert g["models"]["player_v2"]["total"]=="L"
    assert g["home_spread"]==-5.0
    summary=summarize([g],untracked=2)
    ats=[s for s in summary["grades"] if s["model"]=="baseline" and s["market"]=="ats" and s["threshold"]==3.5][0]
    assert (ats["wins"],ats["losses"],ats["pushes"],ats["tracked_leans"])==(1,0,0,1)
    assert ats["roi_if_minus_110_pct"]==90.91
    assert summary["untracked_completed_games_since_first_capture"]==2


def test_pushes_have_zero_profit():
    g=grade_frozen(frozen(),final(hp=80,ap=75))
    assert g["models"]["baseline"]["ats"]=="P"
    assert g["models"]["player_v2"]["ats"]=="P"
    assert g["models"]["baseline"]["total"]=="P"
    summary=summarize([g],0)
    row=[s for s in summary["grades"] if s["model"]=="baseline" and s["market"]=="ats" and s["threshold"]==0][0]
    assert row["roi_if_minus_110_pct"]==0


def test_refuses_after_tip_snapshot():
    with pytest.raises(ValueError,match="not before"):
        grade_frozen(frozen(captured="2026-11-06T01:01:00Z"),final())


def test_refuses_revised_earlier_actual_tip():
    with pytest.raises(ValueError,match="not before"):
        grade_frozen(frozen(captured="2026-11-06T00:50:00Z"),final(tip="2026-11-06T00:45:00Z"))


def test_refuses_team_identity_changes_and_nonfinal():
    with pytest.raises(ValueError,match="Team identities"):
        grade_frozen(frozen(),{**final(),"homeTeamId":99})
    with pytest.raises(ValueError,match="non-final"):
        grade_frozen(frozen(),{**final(),"status":"scheduled"})


def test_iso_week_and_edge_thresholds():
    assert iso_week("2026-11-06T01:00:00Z")=="2026-W45"
    g=grade_frozen(frozen(),final())
    summary=summarize([g],0)
    total=[s for s in summary["grades"] if s["market"]=="total" and s["model"]=="baseline" and s["threshold"]==5.5][0]
    assert total["tracked_leans"]==1
    assert summary["tracked_games"]==1
