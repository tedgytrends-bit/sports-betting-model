"""Adapt free ESPN observations to the existing 2027 model input contracts."""
import gzip
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cbb.espn_grade import norm
from cbb.espn_season_cache import ROOT, save
from cbb.prospective import utc_date

RAW = Path("cbb/data/raw/2027")
ARCHIVE = Path("archive/cbb/prospective/2027")


def read(path):
    return json.loads(path.read_text())


def main():
    from cbb.training_checkpoint import INDEX, save_index
    if (RAW / "games.json").exists():
        old = read(RAW / "games.json")
        save_index(old)
    else:
        with gzip.open(INDEX, "rt") as handle:
            old = json.load(handle)
    rosters = read(RAW / "rosters.json") if (RAW / "rosters.json").exists() else []
    names = defaultdict(set)
    historic = defaultdict(dict)
    def index(ident, tip, home, away):
        historic[frozenset((str(home), str(away)))][str(ident)] = utc_date(tip)
    for game in old:
        for side in ("home","away"):
            names[norm(game[side+"Team"])].add(str(game[side+"TeamId"]))
        index(game["id"],game["startDate"],game["homeTeamId"],game["awayTeamId"])
    source_ids = {}
    for f in sorted(ARCHIVE.glob("snapshots/*.json")):
        for g in read(f)["games"]:
            if g.get("espn_id") or str(g["id"]).startswith("espn-"):
                eid = str(g.get("espn_id") or str(g["id"]).removeprefix("espn-"))
                source_ids[eid] = str(g["id"])
            for side in ("home","away"):
                if not str(g[side+"_team_id"]).startswith("espn-"):
                    names[norm(g[side])].add(str(g[side+"_team_id"]))
            index(g["id"],g["tip_utc"],g["home_team_id"],g["away_team_id"])
    for r in rosters:
        if r.get("team"):
            names[norm(r["team"])].add(str(r["teamId"]))
    games, boxes, lines, rotations = {}, [], [], []
    team_ids = {}
    def team(t):
        eid = str(t["id"])
        if eid not in team_ids:
            ids = set().union(*(names[norm(t[k])] for k in ("location","displayName","shortDisplayName") if t.get(k)))
            team_ids[eid] = next(iter(ids)) if len(ids)==1 else "espn-"+eid
        return team_ids[eid]
    used = set()
    for f in sorted((ROOT/"scoreboards").glob("*.json")):
        scoreboard = read(f)
        for e in scoreboard["events"]:
            eid = str(e["id"])
            if eid in used:
                continue
            used.add(eid)
            c, = e["competitions"]
            state = c["status"]["type"]
            if state["name"] not in ("STATUS_FINAL","STATUS_SCHEDULED"):
                continue
            sides = {s["homeAway"]:s for s in c["competitors"]}
            if set(sides)!={"home","away"}:
                raise ValueError(f"Malformed sides {eid}")
            if any(norm(s["team"].get("location")) in ("tbd","tba","tobedetermined","")
                   for s in sides.values()):
                continue
            teams = {k:team(v["team"]) for k,v in sides.items()}
            if teams["home"] == teams["away"]:
                raise ValueError(f"Identical teams for event {eid}")
            tip = utc_date(c["date"])
            matches = [i for i,t in historic[frozenset(teams.values())].items() if abs((t-tip).total_seconds())<=6*3600]
            if eid in source_ids:
                matches = [source_ids[eid]]
            if len(matches)>1:
                raise ValueError(f"Ambiguous archived game {eid}")
            ident = matches[0] if matches else "espn-"+eid
            if ident in games:
                raise ValueError(f"Duplicate mapped game {ident}")
            final = state["name"]=="STATUS_FINAL"
            g = dict(id=ident,espn_id=eid,market_observed_utc=scoreboard.get("scoreboard_observed_utc"),season=2027,startDate=c["date"],neutralSite=c.get("neutralSite",False),
                     status="final" if final else "scheduled")
            for k,v in sides.items():
                g[k+"TeamId"]=teams[k]
                g[k+"Team"]=v["team"]["location"]
                g[k+"Points"]=int(v["score"]) if final else None
            games[ident]=g
            if not final:
                quotes=[]
                for o in c.get("odds") or []:
                    spread=o.get("pointSpread",{}).get("home",{}).get("close",{}).get("line")
                    quotes.append(dict(provider=o["provider"]["name"],spread=spread,overUnder=o.get("overUnder")))
                lines.append(dict(gameId=ident,lines=quotes))
                continue
            path = ROOT/"summaries"/(eid+".json")
            if not path.exists():
                continue
            data=read(path)["boxscore"]
            for b in data["teams"]:
                stats={s["name"]:s["displayValue"] for s in b["statistics"]}
                def attempts(key):
                    return int(stats[key].split("-")[1])
                required=("fieldGoalsMade-fieldGoalsAttempted","freeThrowsMade-freeThrowsAttempted","offensiveRebounds","totalTurnovers")
                if all(k in stats for k in required):
                    boxes.append(dict(gameId=ident,teamId=team(b["team"]),teamStats={
                        "fieldGoals":{"attempted":attempts(required[0])},"freeThrows":{"attempted":attempts(required[1])},
                        "rebounds":{"offensive":int(stats[required[2]])},"turnovers":{"total":int(stats[required[3]])}}))
            for b in data["players"]:
                players=[]
                for table in b["statistics"]:
                    for athlete in table.get("athletes",[]):
                        stats=dict(zip(table.get("keys",[]),athlete.get("stats",[])))
                        if athlete.get("didNotPlay") or not stats:
                            continue
                        players.append(dict(athleteSourceId=athlete["athlete"]["id"],starter=athlete.get("starter"),
                                            minutes=stats.get("minutes"),points=stats.get("points")))
                rotations.append(dict(gameId=ident,teamId=team(b["team"]),season=2027,startDate=c["date"],players=players))
    now=datetime.now(timezone.utc)
    if not boxes or not rotations or not any(g["status"]=="scheduled" and utc_date(g["startDate"])>now for g in games.values()):
        raise ValueError("Incomplete ESPN season inputs")
    # Keep the original prior-season talent, recruiting and transfer observations.
    # Match current ESPN rosters to their original IDs by source ID.
    prior_ids={str(p["sourceId"]):p["id"] for r in rosters for p in r.get("players",[]) if p.get("sourceId") and p.get("id")}
    indexed={str(r["teamId"]):r for r in rosters}
    for path in (ROOT/"rosters").glob("*.json"):
        r=read(path)
        tid=team(r["team"])
        players=[dict(id=prior_ids.get(str(p["id"]),"espn-"+str(p["id"])),sourceId=str(p["id"]),
                      name=p["displayName"],startSeason=2027,endSeason=2027) for p in r["athletes"]]
        if players:
            indexed[tid]=dict(season=2027,teamId=tid,players=players)
    for k,v in dict(games=list(games.values()),boxes=boxes,lines=lines,rosters=list(indexed.values())).items():
        save(RAW/(k+".json"),v)
    path=Path("cbb/data/rotation_live/2027_game_players.json.gz")
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        with gzip.open(path,"rt") as handle:
            prior = {(str(b["gameId"]),str(b["teamId"])):b for b in json.load(handle)}
        # Keep the validated advanced metrics for observations already archived.
        rotations = [prior.get((str(b["gameId"]),str(b["teamId"])), b) for b in rotations]
    with gzip.open(path,"wt") as out:
        json.dump(rotations,out)
    print("Games, team boxes, rotation boxes, market rows:",len(games),len(boxes),len(rotations),len(lines))


if __name__=="__main__":
    main()
