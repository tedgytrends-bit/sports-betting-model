"""Audit CBBD roster year mapping; aggregate only, never print credentials."""
from collections import Counter, defaultdict
import json
import os
import requests

session=requests.Session()
headers={"Authorization":"Bearer "+os.environ["CBBD_API_KEY"]}

def read(path,params):
    r=session.get("https://api.collegebasketballdata.com"+path,
                  params=params,headers=headers,timeout=100)
    r.raise_for_status()
    result=r.json()
    if not isinstance(result,list):
        raise RuntimeError(f"{path}: expected list")
    return result

def norm(s):
    return "".join(c for c in str(s or "").casefold() if c.isalnum())

for season in (2025,2026):
    rosters=read("/teams/roster",{"season":season})
    current=read("/stats/player/season",{"season":season})
    previous=read("/stats/player/season",{"season":season-1})
    portal=read("/recruiting/portal",{"year":season-1})
    recruits=read("/recruiting/players",{"year":season-1})
    current_ids={str(p.get("athleteId")) for p in current if p.get("athleteId") is not None}
    previous_ids={str(p.get("athleteId")) for p in previous if p.get("athleteId") is not None}
    current_source={str(p.get("athleteSourceId")) for p in current if p.get("athleteSourceId") is not None}
    recruit_ids={(str(p["athleteId"]),str((p.get("committedTo") or {}).get("id")))
                   for p in recruits if p.get("athleteId") is not None}
    portal_names={(norm((p.get("firstName") or "")+" "+(p.get("lastName") or "")),
                   str((p.get("destination") or {}).get("id")))
                  for p in portal if (p.get("destination") or {}).get("id") is not None}
    groups=defaultdict(Counter)
    teams=Counter()
    sample=[]
    total=0
    for roster in rosters:
        if roster.get("season")!=season:continue
        team_id=str(roster["teamId"])
        teams[team_id]+=1
        for p in roster.get("players") or []:
            total+=1
            co=f'{p.get("startSeason")}:{p.get("endSeason")}'
            a=str(p.get("id"))
            so=str(p.get("sourceId"))
            g=groups[co]
            g["n"]+=1
            g["stats_now"]+=a in current_ids or so in current_source
            g["stats_before"]+=a in previous_ids
            g["recruit"]+=(a,team_id) in recruit_ids
            g["transfer"]+=(norm(p.get("name")),team_id) in portal_names
            if len(sample)<12 and (a,team_id) in recruit_ids:
                sample.append({"name":p.get("name"),"team":roster.get("team"),
                    "season":season,"cohort":co,"now":a in current_ids,"prior":a in previous_ids})
    print(json.dumps({"season":season,"roster_records":len(rosters),
      "unique_team_ids":len(teams),"duplicate_team_ids":sum(n>1 for n in teams.values()),
      "rostered_players":total,"season_player_rows":len(current),
      "prior_player_rows":len(previous),"portal_records":len(portal),
      "recruit_records":len(recruits),"groups":
      {k:dict(v) for k,v in sorted(groups.items(),key=lambda x:(-x[1]["n"],x[0]))[:22]},
      "matched_recruit_samples":sample},separators=(",",":")))
