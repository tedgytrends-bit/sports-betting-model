import json
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from cbb.training_checkpoint import replay
from cbb.espn_grade import norm
from cbb.prospective import utc_date

root=Path("archive/cbb/prospective/2027")
raw=Path("cbb/data/raw/2027")
zone=ZoneInfo("America/Chicago")
day=datetime(2026,11,25,tzinfo=zone)
cutoff=day.astimezone(timezone.utc)
games=json.loads((raw/"games.json").read_text())
teams={norm(g[s+"Team"]):g[s+"TeamId"] for g in games for s in ("home","away")}
past=[g for g in games if utc_date(g["startDate"])<cutoff]
events={}
for f in Path("cbb/data/espn_season/scoreboards").glob("*.json"):
 for e in json.loads(f.read_text())["events"]:
  c=e["competitions"][0]
  if utc_date(c["date"]).astimezone(zone).date()!=day.date():continue
  sides={s["homeAway"]:s["team"] for s in c["competitors"]}
  if any(t["location"]=="TBD" for t in sides.values()):continue
  events[e["id"]]=(c,sides)
for eid,(c,sides) in events.items():
 g=dict(id="day-"+eid,startDate=c["date"],season=2027,status="scheduled",neutralSite=c.get("neutralSite",False))
 for s,t in sides.items():
  g[s+"Team"]=t["location"]
  g[s+"TeamId"]=teams.get(norm(t["location"]),"espn-"+str(t["id"]))
 past.append(g)
(raw/"games.json").write_text(json.dumps(past))
(raw/"lines.json").write_text("[]")
board=replay(raw,"cbb/data/rotation_live",2027,cutoff)
research={g["id"]:g for g in board["games"]}
archives=[json.loads(f.read_text()) for f in sorted((root/"snapshots").glob("*.json"),reverse=True)]
lines=["# Wednesday, November 25 · Tedgy Trends CBB","","Player + rotation v4. Central time. Scores are away–home. Archived rows use the latest identifiable pretip snapshot. Research rows use current team priors and game history cut off at midnight before the slate. Research rows do not enter the official record.","","| CT | Away at home | Projected score | ATS lean | Total lean | Forecast |","|---|---|---:|---|---|---|"]
for eid,(c,ss) in sorted(events.items(),key=lambda item:item[1][0]["date"]):
 tip=utc_date(c["date"]); g=None
 for b in archives:
  if utc_date(b["capture_utc"])>=tip:continue
  for x in b["games"]:
   if abs((utc_date(x["tip_utc"])-tip).total_seconds())>21600:continue
   for rev in ([False,True] if c.get("neutralSite") and x.get("neutral_site") else [False]):
    side={"away":"home","home":"away"} if rev else {"away":"away","home":"home"}
    if all(norm(x[side[k]]) in {norm(ss[k].get(n,"")) for n in ("location","displayName","shortDisplayName")} for k in ss):
     g=x;break
   if g:break
  if g:break
  else:continue
  break
 source="Archived pretip" if g else "Research replay"
 if not g:g=research["day-"+eid];side={"away":"away","home":"home"}
 m=g["player_rot_v4"]; market=g["market"]; ats=tot="—"
 if m["ats_lean"] in ("away","home"):
  s=m["ats_lean"];spread=market["home_spread"]*(1 if s=="home" else -1);ats=f'{g[s]} {spread:+g}'
 if m["total_lean"] in ("over","under"):tot=f'{m["total_lean"].title()} {market["total"]:g}'
 a=m["projected_"+side["away"]+"_points"];h=m["projected_"+side["home"]+"_points"]
 lines.append(f'| {tip.astimezone(zone):%I:%M %p} | {ss["away"]["location"]} at {ss["home"]["location"]} | {a:.1f}–{h:.1f} | {ats} | {tot} | {source} |')
out=root/"research/2026-11-25-full-slate.md";out.write_text("\n".join(lines)+"\n")
print("FULL SLATE",len(events),sum("Research replay" in line for line in lines))
