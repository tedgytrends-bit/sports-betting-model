"""Use the NCAA scoreboard mirror when ESPN's finals feed is unavailable."""
from datetime import datetime, timezone
import requests

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"


def fetch_finals_day(session, day):
    try:
        response = session.get(ESPN,params={"dates":day,"groups":50,"limit":1000},timeout=30)
        response.raise_for_status()
        events = response.json()["events"]
        if not isinstance(events,list) or len(events)>=1000:
            raise ValueError("Invalid ESPN scoreboard")
        return events
    except (requests.RequestException, KeyError, ValueError) as exc:
        print("ESPN scoreboard unavailable",day,type(exc).__name__)
    date = datetime.strptime(day,"%Y%m%d").strftime("%Y/%m/%d")
    url = "https://ncaa-api.henrygd.me/scoreboard/basketball-men/d1/"+date+"/all-conf"
    response = session.get(url,timeout=35)
    response.raise_for_status()
    events = []
    for item in response.json()["games"]:
        g = item["game"]
        if g["gameState"]!="final":
            continue
        tip = datetime.fromtimestamp(int(g["startTimeEpoch"]),timezone.utc).isoformat()
        sides = []
        for k in ("home","away"):
            t = g[k]
            names = t["names"]
            sides.append({"homeAway":k,"score":t["score"],"team":{
                "location":names["short"],"displayName":names.get("full") or names["short"],
                "shortDisplayName":names["short"].replace(" St."," State")}})
        events.append({"id":"ncaa-"+str(g["gameID"]),"source":"NCAA scoreboard mirror",
            "competitions":[{"date":tip,"competitors":sides,
            "status":{"type":{"name":"STATUS_FINAL","completed":True}}}]})
    return events
