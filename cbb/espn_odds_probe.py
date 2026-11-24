"""Read-only pretip odds coverage and identity audit."""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from cbb.espn_grade import URL,norm
from cbb.prospective import utc_date

def main():
    now=datetime.now(timezone.utc)
    day=now.astimezone(ZoneInfo("America/Chicago")).date()
    r=requests.get(URL,params={"dates":day.strftime("%Y%m%d"),"groups":50,"limit":1000},timeout=45)
    r.raise_for_status()
    events=r.json()["events"]
    board=json.loads(Path("archive/cbb/prospective/2027/latest.json").read_text())
    rows=[]
    for e in events:
        for c in e.get("competitions",[]):
            tip=utc_date(c["date"])
            if tip<=now or c.get("status",{}).get("type",{}).get("name")!="STATUS_SCHEDULED": continue
            sides={s["homeAway"]:s["team"] for s in c["competitors"]}
            if set(sides)!={"home","away"}: continue
            names={k:{norm(v.get(n,"")) for n in ("location","displayName","shortDisplayName")} for k,v in sides.items()}
            matches=[g for g in board["games"] if abs((utc_date(g["tip_utc"])-tip).total_seconds())<=7200 and all(norm(g[k]) in names[k] for k in sides)]
            row={"event":e["id"],"tip":c["date"],"teams":{k:v["displayName"] for k,v in sides.items()},"odds":c.get("odds",[]),"archive_ids":[g["id"] for g in matches]}
            if len(matches)==1: row["forecast"]=matches[0]
            rows.append(row)
            print("ODDS_AUDIT",json.dumps({k:v for k,v in row.items() if k!="forecast"}))
    Path("espn_odds_audit.json").write_text(json.dumps({"captured":now.isoformat(),"archive_capture":board["capture_utc"],"rows":rows},indent=2))
    print("ODDS_COVERAGE",len(rows),sum(bool(r["odds"]) for r in rows),sum(bool(r["odds"]) and len(r["archive_ids"])==1 for r in rows))
if __name__=="__main__": main()
