#!/usr/bin/env python3
"""Refresh publicly tracked 2026 NFL model results after each completed game day.

Read-only inputs: frozen published forecast versions, user-archived Bovada prices,
Week 8's 14 original graded games, Week 9's independently audited 15 finals,
and a public scoreboard with an EXPLICIT final status. Never train a model,
fetch paid APIs, or grade an uncompleted event.

Latest *published before kickoff* score version wins for each model/game,
without changing the old forecast. Previous finalized game grades are locked:
if a later run would change a score, projection vintage, price or grade, fail
rather than silently rewriting the public record.

Scheduled repeats without newly FINAL games are idempotent and do not commit.

A public model directional-lean record is not an actual bet ledger or
evidence of positive expected value. Baseline Week 9 is labeled research.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT=Path(__file__).resolve().parents[1]
PUB=ROOT/"data"/"public_snapshots"
DEST=ROOT/"data"/"public_results"
WEEK8=ROOT/"data"/"four_model_week08"/"week08_four_model_comparison.csv"
WEEK9=ROOT/"data"/"week09_review"/"week09_full_ats_totals_grade.csv"
MARKETS=ROOT/"data"/"bovada_lines.csv"
OLD=DEST/"nfl_2026_graded_games.csv"
VERIFIED=DEST/"nfl_2026_verified_final_scores.csv"
SUMMARY=DEST/"nfl_2026_results_summary.csv"
META=DEST/"nfl_2026_results_metadata.json"
ESPN="https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates="
CT=ZoneInfo("America/Chicago")
ET=ZoneInfo("America/New_York")
SEASON=2026
ALLOWED_MODEL={"injury","baseline"}
FIELDS=[
    "season","week","game_id","day","kickoff_utc","away_team","home_team",
    "model","record_class","score_status","actual_away","actual_home",
    "projected_away","projected_home","projected_total",
    "home_favored_spread","bovada_total","ats_pick","ats_edge","ats_result",
    "total_pick","total_edge","total_result","published_at_utc",
    "quote_at_utc","forecast_file","score_source_url","score_verified_at_utc",
    "source_warning",
]
FINAL_FIELDS=[
    "season","week","game_id","away_team","home_team","kickoff_utc",
    "actual_away","actual_home","final_status","score_source_url",
    "score_verified_at_utc",
]
SUMMARY_FIELDS=[
    "season","week","model","record_class","games_expected","games_final",
    "games_pending","ats_wins","ats_losses","ats_pushes","ats_no_lean",
    "totals_wins","totals_losses","totals_pushes","totals_no_lean",
    "ats_win_pct","totals_win_pct","illustrative_flat_110_ats_roi_pct",
    "illustrative_flat_110_totals_roi_pct","last_grade_run_utc",
]

def read(path):
    if not path.exists():return []
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        for r in rows:writer.writerow(r)

def canon(value):
    v=str(value).upper().strip()
    return {"LAR":"LA","JAC":"JAX","WSH":"WAS","OAK":"LV","SD":"LAC"}.get(v,v)

def time_value(value):
    if value is None or not str(value).strip():raise ValueError("Missing UTC timestamp")
    t=datetime.fromisoformat(str(value).strip().replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("Timezone-naive timestamp")
    return t.astimezone(timezone.utc)

def number(value):
    x=float(value)
    if not math.isfinite(x):raise ValueError("Non-finite numeric field")
    return x

def as_int(value):
    n=number(value)
    if int(n)!=n or n<0 or n>100:raise ValueError("Invalid NFL final score")
    return int(n)

def grade(edge,real):
    if abs(edge)<1e-8:return "No lean"
    if abs(real)<1e-8:return "Push"
    return "Win" if edge*real>0 else "Loss"

def direction(home,away,edge,market,kind):
    if abs(edge)<1e-8:return "No lean"
    if kind=="total":return "Over" if edge>0 else "Under"
    team=home if edge>0 else away
    side=-market if edge>0 else market
    return f"{team} {side:+g}"

def with_scores(row,away,home,score_source,verified_at):
    r=row.copy()
    r.update({
        "score_status":"FINAL",
        "actual_away":str(as_int(away)),
        "actual_home":str(as_int(home)),
        "score_source_url":score_source,
        "score_verified_at_utc":verified_at,
    })
    model_edge=number(r["projected_home"])-number(r["projected_away"])-number(r["home_favored_spread"])
    total_edge=number(r["projected_total"])-number(r["bovada_total"])
    actual_home_margin=as_int(home)-as_int(away)
    r["ats_result"]=grade(model_edge,actual_home_margin-number(r["home_favored_spread"]))
    r["total_result"]=grade(total_edge,as_int(home)+as_int(away)-number(r["bovada_total"]))
    r["ats_pick"]=direction(r["home_team"],r["away_team"],model_edge,number(r["home_favored_spread"]),"ats")
    r["total_pick"]=direction(r["home_team"],r["away_team"],total_edge,number(r["bovada_total"]),"total")
    r["ats_edge"]=str(round(model_edge,5))
    r["total_edge"]=str(round(total_edge,5))
    return r

def pending_row(row):
    out=row.copy()
    out.update({
        "score_status":"PENDING","actual_away":"","actual_home":"",
        "score_source_url":"","score_verified_at_utc":"",
        "ats_result":"Pending","total_result":"Pending",
    })
    edge=number(out["projected_home"])-number(out["projected_away"])-number(out["home_favored_spread"])
    te=number(out["projected_total"])-number(out["bovada_total"])
    out["ats_pick"]=direction(out["home_team"],out["away_team"],edge,number(out["home_favored_spread"]),"ats")
    out["total_pick"]=direction(out["home_team"],out["away_team"],te,number(out["bovada_total"]),"total")
    out["ats_edge"]=str(round(edge,5));out["total_edge"]=str(round(te,5))
    return out

def week8_rows():
    rows=read(WEEK8)
    if len(rows)!=14 or len({r["game_id"] for r in rows})!=14:
        raise ValueError("Incomplete published Week8 14-game archive")
    out=[]
    for r in rows:
        for model in ("baseline","injury"):
            pred_a=number(r[model+"_away_score"])
            pred_h=number(r[model+"_home_score"])
            total=number(r[model+"_projected_total"])
            if abs(pred_a+pred_h-total)>.110001:raise ValueError("Week8 published rounded score/total mismatch")
            fav=canon(r["market_favorite"])
            spread=number(r["market_spread_points"])
            if fav not in (canon(r["away_team"]),canon(r["home_team"])):
                raise ValueError("Week8 Bovada favorite mismatch "+r["game_id"])
            home_line=spread if fav==canon(r["home_team"]) else -spread
            item={
                "season":"2026","week":"8","game_id":r["game_id"],
                "day":datetime.fromisoformat(r["date"]).strftime("%A"),
                "kickoff_utc":"","away_team":canon(r["away_team"]),
                "home_team":canon(r["home_team"]),"model":model,
                "record_class":"PUBLIC_PUBLISHED",
                "projected_away":str(pred_a),"projected_home":str(pred_h),
                "projected_total":str(total),"home_favored_spread":str(home_line),
                "bovada_total":r["market_total"],"published_at_utc":"",
                "quote_at_utc":"","forecast_file":str(WEEK8.relative_to(ROOT)),
                "source_warning":"Original 14-game Week8 published comparison; no kickoff timestamp in this file.",
            }
            graded=with_scores(item,r["actual_away_score"],r["actual_home_score"],
                               "data/four_model_week08/week08_four_model_comparison.csv",
                               "2026-11-01T23:59:59Z")
            original_ats=r[model+"_ats_result"].lower()
            original_tot=r[model+"_total_result"].lower()
            # The historical published Week8 archive calls a zero-edge
            # directional non-pick "No bet", equivalent to our "No lean".
            if original_tot=="no bet":original_tot="no lean"
            if original_ats=="no bet":original_ats="no lean"
            if graded["ats_result"].lower()!=original_ats or graded["total_result"].lower()!=original_tot:
                raise ValueError("Week8 original audit grade mismatch "+r["game_id"]+" "+model)
            out.append(graded)
    return out

def week9_rows():
    rows=read(WEEK9)
    selected=[r for r in rows if r["model"] in ("official_injury","baseline_research")]
    if len(selected)!=30 or len({r["game_id"] for r in selected})!=15:
        raise ValueError("Week9 audited file missing original 15-game model comparison")
    out=[]
    for r in selected:
        model="injury" if r["model"]=="official_injury" else "baseline"
        t=time_value(r["kickoff_utc"])
        day=t.astimezone(CT).strftime("%A")
        item={
            "season":"2026","week":"9","game_id":r["game_id"],
            "day":day,"kickoff_utc":r["kickoff_utc"],
            "away_team":canon(r["away_team"]),"home_team":canon(r["home_team"]),
            "model":model,
            "record_class":"PUBLIC_PUBLISHED" if model=="injury" else "RESEARCH_COMPARATOR",
            "projected_away":r["model_away"],
            "projected_home":r["model_home"],"projected_total":r["model_total"],
            "home_favored_spread":r["bovada_home_favorite_spread"],
            "bovada_total":r["bovada_total"],
            "quote_at_utc":r["bovada_quote_time_utc"],
            "published_at_utc":r["snapshot_published_at_utc"],
            "forecast_file":"data/week09_review/week09_full_ats_totals_grade.csv",
            "source_warning":"Week9 Baseline is research comparison; not in public Baseline cumulative record" if model=="baseline" else "Week9 official audited frozen Injury",
        }
        if time_value(item["published_at_utc"])>=t or time_value(item["quote_at_utc"])>=t:
            raise ValueError("Week9 retrospective release/quote not pregame")
        graded=with_scores(item,r["actual_away"],r["actual_home"],r["score_source_url"],
                           "2026-11-10T12:00:00Z")
        if graded["ats_result"][0]!=r["ats_result"] or graded["total_result"][0]!=r["total_result"]:
            raise ValueError("Week9 official audit grade mismatch "+r["game_id"]+" "+model)
        out.append(graded)
    return out

def market_quotes():
    candidates=defaultdict(list)
    for r in read(MARKETS):
        if str(r.get("source","")).strip()!="Bovada":continue
        try:
            if int(r["season"])!=SEASON or int(r["week"])<10:continue
            key=(int(r["week"]),canon(r["away_team"]),canon(r["home_team"]))
            when=time_value(r["captured_at_utc"])
            candidates[key].append((when,r))
        except (KeyError,TypeError,ValueError):
            raise ValueError("Invalid archived Bovada quote row")
    return candidates

def future_published_rows():
    """Discover forward model rows from any future published Week10+ file.

    Each new week's model publication needs a source timestamp, game identity,
    projected scores, and original status. Raw research-only and sportsbook
    snapshots without a public publication status are never promoted.
    """
    sources=defaultdict(list)
    kickoff_map={}
    # A future Week11/12 artifact can be named nfl_week11_* with these columns;
    # the grader automatically discovers it, no hand-editing the Results tab.
    for p in sorted(PUB.glob("nfl_week*.csv")):
        if "results" in p.name or "audit" in p.name or "bovada" in p.name or "injury_designations" in p.name or "qb_identity" in p.name:
            continue
        raw=read(p)
        if not raw:continue
        need={"game_id","season","week","away_team","home_team","model",
              "projected_away","projected_home","projected_total","published_at_utc"}
        if not need.issubset(raw[0]):continue
        for row in raw:
            try:week=int(row["week"]);season=int(row["season"])
            except (ValueError,TypeError):raise ValueError("Invalid saved game week in "+p.name)
            if season!=SEASON or week<10:continue
            model=row["model"]
            if model not in ALLOWED_MODEL:continue
            status=str(row.get("publication_status") or "")
            if not status or "RESEARCH_ONLY" in status or "HISTORICAL" in status:
                continue
            game_id=row["game_id"]
            if not game_id.startswith(f"{season}_{week:02d}_"):
                raise ValueError("Malformed game ID "+game_id)
            if canon(row["away_team"])+"_"+canon(row["home_team"])!=game_id.split("_",2)[2]:
                raise ValueError("Published game identity mismatch "+game_id)
            pub=time_value(row["published_at_utc"])
            kick=row.get("kickoff_utc")
            if kick:
                if game_id in kickoff_map and kickoff_map[game_id]!=time_value(kick):
                    raise ValueError("Conflicting kickoffs in public archive "+game_id)
                kickoff_map[game_id]=time_value(kick)
            arr=[number(row[k]) for k in ("projected_away","projected_home","projected_total")]
            if abs(arr[0]+arr[1]-arr[2])>.035 or not all(0<=x<=100 for x in arr):
                raise ValueError("Published model scores invalid "+game_id)
            sources[(game_id,model)].append((pub,p,row))
    return sources,kickoff_map

def score_dates(kickoffs):
    return sorted({x.astimezone(ET).strftime("%Y%m%d") for x in kickoffs})

def load_espn_finals(dates,now,*,fetcher=None):
    if fetcher is None:
        session=requests.Session()
        def fetcher(day):
            resp=session.get(ESPN+day,timeout=(6,22),headers={"User-Agent":"TedgyTrends/1.0 (public prospective NFL grading)"})
            resp.raise_for_status()
            return resp.json()
    found={}
    for day in dates:
        data=fetcher(day)
        if not isinstance(data.get("events"),list):
            raise ValueError("Scoreboard missing event list for "+day)
        for event in data["events"]:
            state=event.get("status",{}).get("type",{})
            if not state.get("completed"):continue
            if "FINAL" not in str(state.get("name","")).upper():
                continue
            competitions=event.get("competitions") or []
            if not competitions:continue
            competition=competitions[0]
            opponents=competition.get("competitors") or []
            if len(opponents)!=2:continue
            sides={r.get("homeAway"):r for r in opponents}
            if set(sides)!={"home","away"}:continue
            away=canon(sides["away"].get("team",{}).get("abbreviation",""))
            home=canon(sides["home"].get("team",{}).get("abbreviation",""))
            if not away or not home or away==home:continue
            kickoff=time_value(event.get("date"))
            if kickoff>now:
                raise ValueError("Scoreboard improperly marks future kickoff complete "+str(event.get("id")))
            a=as_int(sides["away"].get("score"))
            h=as_int(sides["home"].get("score"))
            key=(away,home,kickoff.astimezone(ET).strftime("%Y%m%d"))
            link="https://www.espn.com/nfl/game/_/gameId/"+str(event.get("id"))
            record={
                "away":away,"home":home,"actual_away":a,"actual_home":h,
                "kickoff":kickoff,"link":link,
            }
            if key in found and (found[key]["actual_away"],found[key]["actual_home"])!=(a,h):
                raise ValueError("Inconsistent final score for "+str(key))
            found[key]=record
    return found

def eligible_published(sources,kickoffs,quotes,now):
    base={}
    for (game_id,model),records in sorted(sources.items()):
        if game_id not in kickoffs:
            # An unverified kickoff is not grounds to grade the game.
            continue
        kick=kickoffs[game_id]
        if kick>now:
            # Still show the game as pending; it was published in advance.
            pass
        eligible=[(t,p,r) for t,p,r in records if t<kick]
        if not eligible:raise ValueError("No pregame published forecast "+game_id+" "+model)
        eligible.sort(key=lambda x:(x[0],str(x[1])))
        pub,p,row=eligible[-1]
        week=int(row["week"])
        away,home=canon(row["away_team"]),canon(row["home_team"])
        book=[(t,q) for t,q in quotes.get((week,away,home),[]) if t<kick]
        if not book:
            raise ValueError("Missing archived pregame Bovada line for "+game_id)
        book.sort(key=lambda x:x[0])
        quote_time,q=book[-1]
        entry={
            "season":str(SEASON),"week":str(week),"game_id":game_id,
            "day":kick.astimezone(CT).strftime("%A"),
            "kickoff_utc":kick.isoformat(),
            "away_team":away,"home_team":home,
            "model":model,"record_class":"PUBLIC_PUBLISHED",
            "projected_away":str(number(row["projected_away"])),
            "projected_home":str(number(row["projected_home"])),
            "projected_total":str(number(row["projected_total"])),
            "home_favored_spread":str(number(q["home_favorite_spread"])),
            "bovada_total":str(number(q["total_line"])),
            "published_at_utc":pub.isoformat(),
            "quote_at_utc":quote_time.isoformat(),
            "forecast_file":str(p.relative_to(ROOT)),
            "source_warning":("INJURY QB FIRST-START EPA NOT CALIBRATED — RESEARCH-ONLY BETTING LEAN"
                              if model=="injury" and game_id=="2026_10_MIA_IND"
                              else "Model spread lean is not a verified profitable wager"),
        }
        base[(game_id,model)]=entry
    return base

def immutable_grade(old,new):
    # Do not compare score-source verified timestamp: rechecking an already-final
    # scoreboard is allowed. Actual score, selected pregame quote, prediction
    # vintage, and grades MUST remain fixed after first public final.
    fields=("actual_away","actual_home","projected_away","projected_home",
            "projected_total","home_favored_spread","bovada_total",
            "published_at_utc","quote_at_utc","forecast_file",
            "ats_result","total_result","ats_pick","total_pick")
    if old.get("score_status")!="FINAL" or new.get("score_status")!="FINAL":
        raise ValueError("Cannot rewrite a previously final game as pending")
    changed=[k for k in fields if str(old.get(k,""))!=str(new.get(k,""))]
    if changed:
        raise ValueError(f"Attempted retroactive change to completed {old['game_id']} {old['model']}: {changed}")

def summarize(rows,now):
    by=defaultdict(list)
    for r in rows:
        by[(int(r["week"]),r["model"],r["record_class"])].append(r)
        # Public cumulative excludes Week9 Baseline research entirely
        if r["record_class"]=="PUBLIC_PUBLISHED":
            by[(0,r["model"],"PUBLIC_PUBLISHED")].append(r)
    outputs=[]
    for (week,model,record_class),items in sorted(by.items(),key=lambda x:(x[0][0],x[0][1],x[0][2])):
        finals=[r for r in items if r["score_status"]=="FINAL"]
        scores={}
        for mark,col in (("ats","ats_result"),("totals","total_result")):
            c=Counter(x[col] for x in finals)
            w,l,p,no=(c.get("Win",0),c.get("Loss",0),c.get("Push",0),c.get("No lean",0))
            score=f"{mark}_"
            scores.update({score+"wins":w,score+"losses":l,score+"pushes":p,score+"no_lean":no,
                           score+"win_pct":round(100*w/(w+l),2) if w+l else "",
                           "illustrative_flat_110_"+mark+"_roi_pct":round(100*((w*100/110)-l)/(w+l+p),2) if w+l+p else ""})
        outputs.append({
            "season":SEASON,"week":week if week else "ALL",
            "model":model,"record_class":record_class,
            "games_expected":len(items),"games_final":len(finals),
            "games_pending":len(items)-len(finals),
            **scores,"last_grade_run_utc":now.isoformat(),
        })
    return outputs

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--offline-scores",help="Fixture JSON for regression tests; never set on production schedule")
    args=parser.parse_args()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    existing={ (r["game_id"],r["model"]):r for r in read(OLD) }
    if len(existing)!=len(read(OLD)):
        raise ValueError("Previous public results have duplicate model/game records")
    historical=week8_rows()+week9_rows()
    forecast,kickoffs=future_published_rows()
    quotes=market_quotes()
    pending=eligible_published(forecast,kickoffs,quotes,now)
    # Every published forecast game must have both current forward public models
    games={g for g,m in pending}
    for g in games:
        if {(key[1]) for key in pending if key[0]==g}!={"injury","baseline"}:
            raise ValueError("Public results needs both model vintages per game "+g)
    old_verified=read(VERIFIED)
    if len({r["game_id"] for r in old_verified})!=len(old_verified):
        raise ValueError("Duplicate previously verified final NFL games")
    verified={r["game_id"]:r for r in old_verified}
    if args.offline_scores:
        payload=json.loads(Path(args.offline_scores).read_text())
        score_lookup=load_espn_finals(score_dates(kickoffs.values()),now,fetcher=lambda day:payload[day])
    elif kickoffs:
        # Query only unverified games, never re-download the whole season.
        outstanding=[kickoffs[g] for g in games if g not in verified]
        score_lookup=load_espn_finals(score_dates(outstanding),now) if outstanding else {}
    else:
        score_lookup={}
    for game in sorted(games):
        row=pending[(game,"injury")]
        kickoff=kickoffs[game]
        date=kickoff.astimezone(ET).strftime("%Y%m%d")
        possible=score_lookup.get((row["away_team"],row["home_team"],date))
        if possible:
            if abs((possible["kickoff"]-kickoff).total_seconds())>6*3600:
                raise ValueError("Public score kickoff differs by >6h from frozen game "+game)
            result={
                "season":str(SEASON),"week":row["week"],"game_id":game,
                "away_team":row["away_team"],"home_team":row["home_team"],
                "kickoff_utc":row["kickoff_utc"],
                "actual_away":str(possible["actual_away"]),"actual_home":str(possible["actual_home"]),
                "final_status":"FINAL","score_source_url":possible["link"],
                "score_verified_at_utc":now.isoformat(),
            }
            if game in verified:
                old=verified[game]
                for k in ("actual_home","actual_away","away_team","home_team"):
                    if str(old[k])!=str(result[k]):
                        raise ValueError("A previously verified final score changed unexpectedly "+game)
            else:
                verified[game]=result
    combined=list(historical)
    for key,entry in sorted(pending.items(),key=lambda x:(int(x[1]["week"]),x[1]["kickoff_utc"],x[0][1])):
        score=verified.get(entry["game_id"])
        if score:
            if score["away_team"]!=entry["away_team"] or score["home_team"]!=entry["home_team"]:
                raise ValueError("Scoreboard and forecast team identity mismatch "+entry["game_id"])
            combined.append(with_scores(entry,score["actual_away"],score["actual_home"],
                                        score["score_source_url"],score["score_verified_at_utc"]))
        else:
            combined.append(pending_row(entry))
    if len({(r["game_id"],r["model"]) for r in combined})!=len(combined):
        raise ValueError("Duplicate official model game in graded results")
    for item in combined:
        key=(item["game_id"],item["model"])
        if key in existing and existing[key]["score_status"]=="FINAL":
            immutable_grade(existing[key],item)
    # Keep confirmed score timestamps stable across reruns for deterministic files.
    for game,old in [(r["game_id"],r) for r in old_verified]:
        if game in verified:verified[game]["score_verified_at_utc"]=old["score_verified_at_utc"]
    for item in combined:
        if item["score_status"]=="FINAL" and item["game_id"] in verified:
            item["score_verified_at_utc"]=verified[item["game_id"]]["score_verified_at_utc"]
        if (item["game_id"],item["model"]) in existing and int(item["week"])<=9:
            prev=existing[(item["game_id"],item["model"])]
            item["score_verified_at_utc"]=prev["score_verified_at_utc"]
    combined.sort(key=lambda r:(int(r["week"]),r["kickoff_utc"],r["game_id"],r["model"]))
    # Do not commit on idle scheduled runs; old published records remain stable.
    current_fields=[{k:str(row.get(k,"")) for k in FIELDS} for row in combined]
    old_fields=[{k:str(row.get(k,"")) for k in FIELDS} for row in read(OLD)]
    if old_fields and current_fields==old_fields:
        print(json.dumps({"status":"NO_CHANGE","graded_games":
             len({x["game_id"] for x in combined if x["score_status"]=="FINAL"}),
             "pending_games":len({x["game_id"] for x in combined if x["score_status"]=="PENDING"})}))
        return
    summary=summarize(combined,now)
    DEST.mkdir(parents=True,exist_ok=True)
    write_csv(OLD,combined,FIELDS)
    write_csv(VERIFIED,sorted(verified.values(),key=lambda r:r["game_id"]),FINAL_FIELDS)
    write_csv(SUMMARY,summary,SUMMARY_FIELDS)
    meta={
        "season":SEASON,"graded_at_utc":now.isoformat(),
        "source":"ESPN public scoreboard with explicit completed/final flag for Week10+; verified official Week8/Week9 archived results; user-provided Bovada prices",
        "games_weeks":{str(w):len({r["game_id"] for r in combined if int(r["week"])==w}) for w in sorted({int(r["week"]) for r in combined})},
        "graded_games":len({r["game_id"] for r in combined if r["score_status"]=="FINAL"}),
        "pending_games":len({r["game_id"] for r in combined if r["score_status"]=="PENDING"}),
        "rows":len(combined),"source_file":str(OLD.relative_to(ROOT)),
        "summary_file":str(SUMMARY.relative_to(ROOT)),
        "final_scores_file":str(VERIFIED.relative_to(ROOT)),
        "record_policy":"Week8 both published; Week9 Injury official/Baseline research; Week10+ both pregame published with latest valid before-kickoff version. Rookie/unverified QB labels remain visible; no bet execution implied.",
        "grading":"All-game directional ATS and totals; pushes excluded from win%; illustrative -110 ROI only, never actual bet ROI.",
        "no_retroactive_changes":True,
        "next_release":"GitHub Actions cron Friday, Monday and Tuesday after each NFL game night in America/Chicago (including daylight time).",
    }
    META.write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"verified_new_week10_games":len(verified),
                      "graded_games":meta["graded_games"],
                      "pending_games":meta["pending_games"],
                      "weeks":meta["games_weeks"],
                      "summary":[r for r in summary if str(r["week"]) in ("9","10","ALL")]},indent=2))

if __name__=="__main__":
    main()
