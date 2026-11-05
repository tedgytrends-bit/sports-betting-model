"""Read-only source readiness probe for CBB 2026-27."""
from collections import Counter
import json,os,requests

s=requests.Session()
headers={"Authorization":"Bearer "+os.environ["CBBD_API_KEY"]}
def fetch(path,params):
    r=s.get("https://api.collegebasketballdata.com"+path,params=params,headers=headers,timeout=100)
    print("STATUS",path,r.status_code)
    r.raise_for_status()
    return r.json()

nov=dict(season=2027,startDateRange="2026-11-01T00:00:00Z",endDateRange="2026-12-01T00:00:00Z")
games=fetch("/games",nov)
lines=fetch("/lines",nov)
rosters=fetch("/teams/roster",dict(season=2027))
portal=fetch("/recruiting/portal",dict(year=2026))
recruits=fetch("/recruiting/players",dict(year=2026))
previous=fetch("/stats/player/season",dict(season=2026))
statuses=Counter(x.get("status") for x in games)
active=Counter()
for x in rosters:
    if x.get("season")!=2027:continue
    for p in x.get("players") or []:
        start,end=p.get("startSeason"),p.get("endSeason")
        if start is not None and end is not None and start<=2027<=end:
            active[str(x.get("teamId"))]+=1
summary={
 "games_nov":len(games),"game_status_counts":dict(statuses),"lines_nov":len(lines),
 "roster_teams":len(rosters),"teams_with_membership_2027":sum(n>0 for n in active.values()),
 "median_active_roster_count":sorted(active.values())[len(active)//2] if active else 0,
 "portal_2026":len(portal),"recruits_2026":len(recruits),
 "prior_year_players_2026":len(previous),
 "first_future_games":[{"id":g.get("id"),"startDate":g.get("startDate"),
       "away":g.get("awayTeam"),"home":g.get("homeTeam"),"status":g.get("status")}
       for g in games if g.get("status")=="scheduled"][:4],
 "first_market_entry":lines[0] if lines else None
}
print("PROSPECTIVE_READINESS",json.dumps(summary,separators=(",",":"))[:5000])
