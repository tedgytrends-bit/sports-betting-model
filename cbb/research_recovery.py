"""Research-only grading of archived forecasts; never write official journals."""
import json
from pathlib import Path
from collections import Counter
from zoneinfo import ZoneInfo
import requests
from cbb.espn_grade import match, URL
from cbb.prospective import utc_date
from cbb.reconstruction_markets import summarize

MODELS = ("baseline","player_v2","player_opp_v3","player_rot_v4","player_all_v4")
def main():
    board=json.loads(Path("archive/cbb/prospective/2027/snapshots/20261122T135759379135_45030081991.json").read_text())
    captured=utc_date(board["capture_utc"])
    zone=ZoneInfo("America/Chicago")
    counts=Counter()
    rows=[]
    for g in board["games"]:
        tip=utc_date(g["tip_utc"])
        day=tip.astimezone(zone).date().isoformat()
        if day not in ("2026-11-22","2026-11-23","2026-11-24") or captured>=tip:
            continue
        row={k:g.get(k) for k in ("id","away","home","tip_utc","market",*MODELS)}
        row["date"]=day
        rows.append(row)
    events=[]
    for day in ("20261122","20261123","20261124","20261125"):
        r=requests.get(URL,params={"dates":day,"groups":50,"limit":1000},timeout=45)
        r.raise_for_status()
        events.extend(r.json()["events"])
    for row in rows:
        g=next(g for g in board["games"] if g["id"]==row["id"])
        final=match(g,events)
        row["final"]=final
        if not final: continue
        margin=final["homePoints"]-final["awayPoints"]
        total=final["homePoints"]+final["awayPoints"]
        for model in MODELS:
            m=g.get(model) or {}
            for market,line,actual,lean,edge in (
                ("ats",g["market"].get("home_spread"),margin,m.get("ats_lean"),m.get("ats_edge")),
                ("total",g["market"].get("total"),total,m.get("total_lean"),m.get("total_edge"))):
                if line is None or edge is None or lean not in ("home","away","over","under"): continue
                value=actual+line if market=="ats" else actual-line
                if lean in ("away","under"): value=-value
                outcome="W" if value>0 else "L" if value<0 else "P"
                for threshold in (0,3.5):
                    if abs(edge)>=threshold: counts[(model,market,threshold,outcome)]+=1
    result={"classification":"archived_pretip_research","capture_utc":board["capture_utc"],"rows":rows,"records":{"|".join(map(str,k)):v for k,v in counts.items()}}
    result["research_records_including_retrospective_closes"] = summarize(rows,events)
    Path("research_recovery.json").write_text(json.dumps(result,indent=2))
    report = ["# November 22–24 CBB research results", "",
              "Scores come from the November 22 pretip snapshot. Each grade uses the captured line where available, then an explicitly identified ESPN closing quote retrieved after the final. These rows can overlap official frozen picks.",
              "", "Returns assume a flat stake at -110, including refunded pushes in the amount staked.", ""]
    records = result["research_records_including_retrospective_closes"]
    for period in ("2026-11-22", "2026-11-23", "2026-11-24", "combined"):
        report.extend([f"## {period.title()}","","| Model | Minimum edge | ATS W–L–P | ATS ROI | Totals W–L–P | Totals ROI |",
                       "|---|---:|---:|---:|---:|---:|"])
        for model in MODELS:
            for threshold in (0,3.5):
                cells = [model,str(threshold)]
                for market in ("ats","total"):
                    record=records.get(f"{period}|{model}|{market}|{threshold}")
                    if record:
                        cells.extend([f'{record["W"]}–{record["L"]}–{record["P"]}',f'{record["roi_pct_flat_minus110"]:+.2f}%'])
                    else:
                        cells.extend(["0–0–0","—"])
                report.append("| "+" | ".join(cells)+" |")
        report.append("")
    report.append("[Game records, final scores and market provenance](2026-11-22-to-24.json)")
    Path("research_recovery.md").write_text("\\n".join(report)+"\\n")
    print("RESEARCH_RECORDS",json.dumps(result["records"]))
    for day in ("2026-11-22","2026-11-23","2026-11-24"):
        subset=[r for r in rows if r["date"]==day]
        print("COVERAGE",day,len(subset),sum(r["market"].get("home_spread") is not None for r in subset),sum(r["market"].get("total") is not None for r in subset))
        for row in subset: print("RESEARCH_GAME",json.dumps(row))
if __name__=="__main__": main()
