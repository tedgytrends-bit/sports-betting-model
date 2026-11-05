"""Fetch and cache CBBD data in bounded calendar-month windows.

Never commit the CBBD_API_KEY. Monthly chunks avoid the documented 3,000
game-per-request cap, which an entire CBB season would exceed.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

API="https://api.collegebasketballdata.com"


def windows(season):
    for year, months in ((season-1,range(10,13)),(season,range(1,6))):
        for m in months:
            start=datetime(year,m,1,tzinfo=timezone.utc)
            end=datetime(year+(m==12),m%12+1,1,tzinfo=timezone.utc)
            yield start.isoformat().replace("+00:00","Z"),end.isoformat().replace("+00:00","Z")


def request(session, endpoint, params, key):
    for attempt in range(4):
        try:
            r=session.get(API+endpoint,params=params,timeout=50,
                headers={"Authorization":"Bearer "+key,"Accept":"application/json"})
            if r.status_code in (429,500,502,503,504) and attempt<3:
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            data=r.json()
            if not isinstance(data,list):
                raise ValueError("Expected list from "+endpoint)
            # CBBD caps at 3,000 *games*, not 3,000 rows.
            # /games/teams has two records per game and may legitimately
            # return 3,000+ records for a single monthly time window.
            games_in_response=(len({str(x.get("gameId")) for x in data})
                               if endpoint=="/games/teams" else len(data))
            if games_in_response>=3000:
                raise ValueError("Potential 3,000-game response truncation; shorten request window")
            return data
        except requests.RequestException:
            if attempt==3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Unreachable")


def fetch_season(season,root="cbb/data/raw",refresh=False):
    folder=Path(root)/str(season)
    folder.mkdir(parents=True,exist_ok=True)
    key=os.environ.get("CBBD_API_KEY")
    session=requests.Session()
    output={}
    for name,path in (("games","/games"),("boxes","/games/teams"),("lines","/lines")):
        dest=folder/(name+".json")
        if dest.exists() and not refresh:
            output[name]=json.loads(dest.read_text(encoding="utf-8"))
            continue
        if not key:
            raise RuntimeError("Missing CBBD_API_KEY. Request at https://collegebasketballdata.com/key")
        indexed={}
        for start,end in windows(season):
            for record in request(session,path,dict(season=season,startDateRange=start,endDateRange=end),key):
                rid=str(record.get("id") or record.get("gameId"))
                identity=(rid,str(record.get("teamId") or "")) if name=="boxes" else (rid,)
                indexed[identity]=record
        output[name]=list(indexed.values())
        dest.write_text(json.dumps(output[name],separators=(",",":")),encoding="utf-8")
        print(f"{season} {name}: cached {len(output[name])} records")
    return output


def load_seasons(seasons,root="cbb/data/raw"):
    output=dict(games=[],boxes=[],lines=[])
    for season in seasons:
        data=fetch_season(season,root=root)
        for k in output:
            output[k].extend(data[k])
    return output
