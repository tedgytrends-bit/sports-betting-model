"""Offline deterministic validation of season roster guards and roster priors."""
from cbb.player_adjusted import eligible, roster_priors, extend_rows, PLAYER_FEATURES
from cbb.player_ingest import ENDPOINTS


def athlete(i, start, end, name):
    return dict(id=i,sourceId=str(i),name=name,startSeason=start,endSeason=end)


def fixtures():
    return {2026: {
        "rosters": [dict(teamId=1,season=2026,team="Alpha",players=[
            athlete(10,2024,2026,"Veteran A"),
            athlete(11,2026,2026,"Transfer B"),
            athlete(12,2026,2026,"Freshman C"),
            athlete(13,2027,2027,"FUTURE PLAYER"),  # must never leak
        ])],
        "prior_players": [
            dict(athleteId=10,athleteSourceId="10",teamId=1,games=30,minutes=800,
                 points=300,offensiveRating=112,defensiveRating=98,PORPAG=2,usage=24),
            dict(athleteId=11,athleteSourceId="11",teamId=2,games=28,minutes=900,
                 points=400,offensiveRating=108,defensiveRating=100,PORPAG=1,usage=28),
            dict(athleteId=13,athleteSourceId="13",teamId=2,games=30,minutes=1100,
                 points=900,offensiveRating=150,defensiveRating=60,PORPAG=9,usage=35),
        ],
        "portal": [dict(year=2025,firstName="Transfer",lastName="B",
                        origin=dict(id=2),destination=dict(id=1))],
        "recruits": [dict(year=2025,athleteId=12,stars=5,committedTo=dict(id=1))],
    }}


def test_future_membership_rejected():
    assert eligible(athlete(10,2025,2026,"Active"),2026)
    assert eligible(athlete(12,2026,2026,"Current freshman"),2026)
    assert eligible(athlete(13,2026,2027,"Current entrant"),2026)
    assert not eligible(athlete(14,2027,2027,"Future"),2026)
    assert not eligible(athlete(9,2023,2025,"Departed"),2026)
    assert not eligible(dict(id=15),2026)  # unknown dates are not assumed


def test_player_prior_verified_transfer_and_freshman():
    priors,coverage=roster_priors(fixtures())
    p=priors[(2026,"1")]
    assert p["matched_players"]==2
    assert p["eligible_players"]==3
    assert p["transfer_count"]==1
    assert p["portal_verified"]==1
    assert p["elite_freshmen"]==1
    assert p["recruit_stars"]==3
    assert round(p["return_minutes_share"],2)==1
    assert p["prior_offense"]>0


def test_priors_only_prior_season_and_fade_with_games():
    priors,_=roster_priors(fixtures())
    games=[{"id":1,"homeTeamId":1,"awayTeamId":2},
           {"id":2,"homeTeamId":1,"awayTeamId":2}]
    rows=[{"id":"1","season":2026,"home_games":0,"away_games":0},
          {"id":"2","season":2026,"home_games":24,"away_games":24}]
    output=extend_rows(rows,games,priors)
    assert output[0]["home_matched_players"]==2
    assert output[1]["home_matched_players"]<0.4
    assert output[0]["away_matched_players"]==0
    assert output[0]["home_prior_offense"]>output[1]["home_prior_offense"]
    assert "home_recruit_stars" in PLAYER_FEATURES


def test_player_input_endpoints_use_past_season():
    data={name: selector(2026) for name,_,selector in ENDPOINTS}
    assert data["prior_players"]=={"season":2025}
    assert data["rosters"]=={"season":2026}
    assert data["portal"]=={"year":2025}
    assert data["recruits"]=={"year":2025}
