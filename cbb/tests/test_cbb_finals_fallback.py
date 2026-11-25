import requests
from cbb.finals_source import fetch_finals_day
from cbb.espn_grade import match


def test_ncaa_fallback_preserves_identity_and_source():
    class Session:
        def get(self,url,**kwargs):
            if "espn.com" in url:
                raise requests.Timeout("fixture outage")
            class Response:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"games":[{"game":{"gameID":"991","gameState":"final",
                        "startTimeEpoch":"1795564800","home":{"score":"80","names":{"short":"Alpha"}},
                        "away":{"score":"70","names":{"short":"Beta"}}}}]}
            return Response()
    events = fetch_finals_day(Session(),"20261125")
    game = {"id":"old","season":2027,"home":"Alpha","away":"Beta","home_team_id":"a",
            "away_team_id":"b","tip_utc":events[0]["competitions"][0]["date"]}
    final = match(game,events)
    assert final["finalScoreSource"] == "NCAA scoreboard mirror"
    assert final["sourceEventId"] == "ncaa-991"
    assert "espnId" not in final
    assert (final["homePoints"],final["awayPoints"]) == (80,70)
