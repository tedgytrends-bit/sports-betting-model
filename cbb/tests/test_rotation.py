"""Chronological player-game rotation validation."""
import pytest
from cbb.rotation_features import _game_box, pregame_rotation_features, attach_rotations
from cbb.rotation_ingest import rotation_windows


def game(i, day, season=2026, status="final"):
    return dict(id=i, season=season, startDate=day+"T20:00:00Z",
                homeTeamId=1, awayTeamId=2, homeTeam="A", awayTeam="B",
                status=status, homePoints=75, awayPoints=65)


def box(i, team, absent=False):
    p=[]
    for j in range(1,11):
        if absent and j==1:
            continue
        minutes=(30 if j<=5 else 10)
        if absent and j==6:
            minutes=30
        if absent and j>=7:
            minutes=12.5
        p.append(dict(athleteId=team*100+j,minutes=minutes,
                      starter=(j<=5 or (absent and j==6)),
                      points=minutes*.35,usage=(30 if j==1 else 18),
                      offensiveRating=110,defensiveRating=95))
    return dict(gameId=i,teamId=team,season=2026,players=p)


def both(i,absent=False):
    return [box(i,1,absent),box(i,2)]


def test_complete_player_boxes():
    assert _game_box(box(1,1))["minutes_total"]==200
    assert _game_box(box(1,1,True))["minutes_total"]==200
    assert _game_box(dict(gameId=1,teamId=1,players=[])) is None


def test_absence_uses_previous_game_only():
    schedule=[game(i,f"2025-11-{i+2:02d}") for i in range(1,7)]
    schedule[-1]["status"]="scheduled"
    boxes=sum((both(i,i==5) for i in range(1,6)),[])
    output=pregame_rotation_features(schedule,boxes)
    assert output["5"]["home_rotation_key_minutes_missing"]==0
    assert output["6"]["home_rotation_key_minutes_missing"]>0.1
    assert output["6"]["away_rotation_key_minutes_missing"]==0


def test_same_day_is_frozen():
    schedule=[game(1,"2025-11-03"),game(2,"2025-11-04"),
              game(3,"2025-11-04"),game(4,"2025-11-05")]
    a=pregame_rotation_features(schedule,both(1)+both(2)+both(3,True))
    b=pregame_rotation_features(schedule,both(1)+both(2)+both(3))
    assert a["2"]==a["3"]==b["2"]==b["3"]
    assert a["4"]!=b["4"]


def test_missing_box_unknown_not_absence():
    schedule=[game(i,f"2025-11-{i+2:02d}") for i in range(1,6)]
    boxes=sum((both(i) for i in (1,2,3)),[])
    f=pregame_rotation_features(schedule,boxes)["5"]
    assert f["home_rotation_last_box_present"]==0
    assert f["home_rotation_key_minutes_missing"]==0
    assert f["home_rotation_box_coverage"]<1


def test_season_reset():
    rows=[game(1,"2025-11-03"),game(2,"2026-11-03",season=2027,status="scheduled")]
    f=pregame_rotation_features(rows,both(1))
    assert f["2"]["home_rotation_source_games"]==0


def test_weekly_api_windows():
    for s in (2024,2026):
        dates=list(rotation_windows(s))
        assert dates[0][0]==f"{s-1}-10-01T00:00:00Z"
        assert dates[-1][1]==f"{s}-06-01T00:00:00Z"
        assert all(a[1]==b[0] for a,b in zip(dates,dates[1:]))


def test_attach_validation():
    feats=pregame_rotation_features([game(1,"2025-11-03")],both(1))
    assert attach_rotations([dict(id="1")],feats)[0]["home_rotation_source_games"]==0
    with pytest.raises(ValueError,match="Incomplete rotation"):
        attach_rotations([dict(id="99")],feats)
