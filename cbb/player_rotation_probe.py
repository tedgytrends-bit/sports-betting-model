"""Authenticated, low-quota probe for past-game individual participation schema.

Logs limited response examples and aggregate coverage only. Never print key.
"""
from __future__ import annotations
from collections import Counter
from statistics import median
import json
import os
import requests

HEADERS = {"Authorization": "Bearer " + os.environ["CBBD_API_KEY"]}
API = "https://api.collegebasketballdata.com/games/players"
SAMPLES = [
    ("2024", "2023-11-01T00:00:00Z", "2023-11-08T00:00:00Z"),
    ("2025", "2024-11-01T00:00:00Z", "2024-11-08T00:00:00Z"),
    ("2026", "2025-11-01T00:00:00Z", "2025-11-08T00:00:00Z"),
    ("2027", "2026-11-01T00:00:00Z", "2026-11-06T00:00:00Z"),
]
for season, start, end in SAMPLES:
    resp=requests.get(API, params={"season":season,"startDateRange":start,"endDateRange":end},
                      headers=HEADERS, timeout=90)
    print("SEASON",season,"STATUS",resp.status_code)
    resp.raise_for_status()
    data=resp.json()
    if not isinstance(data,list):
        raise RuntimeError("Expected list from CBBD")
    game_ids={str(g.get("gameId")) for g in data}
    players=[p for team in data for p in (team.get("players") or [])]
    minutes=[p.get("minutes") for p in players]
    starts=Counter(str(p.get("starter")) for p in players)
    print("SHAPE",json.dumps({
        "season":season,"team_rows":len(data),"unique_game_ids":len(game_ids),
        "teams":len(set(str(g.get("teamId")) for g in data)),
        "total_player_rows":len(players),
        "non_null_minutes":sum(m is not None for m in minutes),
        "starter_flag_counts":dict(starts),
        "team_keys":list(data[0]) if data else [],
        "first_team":{k: v for k,v in (data[0] if data else {}).items()
                      if k in ("gameId","teamId","startDate","isHome","gameMinutes","gamePace")},
        "player_keys":list(players[0]) if players else [],
        "first_player":{k:v for k,v in (players[0] if players else {}).items()
                        if k in ("athleteId","athleteSourceId","name","minutes","starter",
                                  "points","usage","position")},
    },default=str))
