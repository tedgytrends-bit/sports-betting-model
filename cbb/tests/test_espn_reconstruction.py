from cbb.reconstruction_markets import closing_quote, summarize


def test_neutral_floor_and_research_roi():
    event = {"id": "9", "competitions": [{"competitors": [
        {"homeAway":"away","team":{"location":"Alpha"}},
        {"homeAway":"home","team":{"location":"Beta"}}],
        "odds":[{"provider":{"name":"Test book"},"pointSpread":{"away":{"close":{"line":"-2"}}},
                 "total":{"over":{"close":{"line":"o150"}}}}]}]}
    row = {"home":"Alpha","date":"2026-11-24","market":{},
           "final":{"espnId":"9","homePoints":76,"awayPoints":74},
           "player_rot_v4":{"projected_margin_home":6,"projected_total":145}}
    assert closing_quote(row,event)["home_spread"] == -2
    results = summarize([row], [event])
    for market in ("ats","total"):
        for threshold in (0,3.5):
            assert results[f"combined|player_rot_v4|{market}|{threshold}"] == {
                "W":0,"L":0,"P":1,"roi_pct_flat_minus110":0}


def test_missing_quote_is_ungraded():
    event = {"id":"1","competitions":[{"competitors":[
        {"homeAway":"home","team":{"location":"Alpha"}},
        {"homeAway":"away","team":{"location":"Beta"}}],"odds":[{"provider":{"name":"Test book"}}]}]}
    assert closing_quote({"home":"Alpha"},event) == {}
