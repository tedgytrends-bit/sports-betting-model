#!/usr/bin/env python3
"""Derive a COMPLETE directional view without rewriting the original NFL record.

A retrospectively adopted Nov16 zero-edge policy uses the PRE-EXISTING,
PRE-GAME published Baseline forecast to break an exact Injury-market tie.
If both model totals were equal to market, use UNDER ONLY for games kicking
off after policy adoption, never select a retroactive winner from final score.

This is a derived FULL-DIRECTION record, not the original Injury model's
published picks. The immutable initial grades in nfl_2026_graded_games.csv
must continue to show IND@JAX Week8 "No lean".
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data"/"public_results"/"nfl_2026_graded_games.csv"
DST=ROOT/"data"/"public_results"/"nfl_2026_full_directional_games.csv"
SUMMARY=ROOT/"data"/"public_results"/"nfl_2026_full_directional_summary.csv"
META=ROOT/"data"/"public_results"/"nfl_2026_full_directional_policy.json"
POLICY_AT="2026-11-16T14:55:00Z"
GRADE_FIELDS=["game_id","week","day","away_team","home_team","score_status","actual_away","actual_home",
              "home_favored_spread","bovada_total","ats_pick","ats_result","total_pick","total_result",
              "original_total_pick","original_total_result","projected_total","selection_provenance",
              "fallback_model","fallback_projected_total","policy_adopted_utc","published_at_utc",
              "forecast_file","score_source_url","record_class"]
SUM_FIELDS=["season","week","model","record_class","games_expected","games_final","games_pending",
    "ats_wins","ats_losses","ats_pushes","ats_no_lean",
    "totals_wins","totals_losses","totals_pushes","totals_no_lean","ats_win_pct","totals_win_pct",
    "illustrative_flat_110_ats_roi_pct","illustrative_flat_110_totals_roi_pct","last_grade_run_utc"]

def read(path):
    with path.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))

def save(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def grade(pick,final_total,market):
    if final_total is None:return "Pending"
    if final_total==market:return "Push"
    return "Win" if (final_total>market)==(pick=="Over") else "Loss"

def wins(row,col):
    c=Counter(x[col] for x in row if x["score_status"]=="FINAL")
    return [c.get("Win",0),c.get("Loss",0),c.get("Push",0),c.get("No lean",0)]

def summary(rows,week,now):
    rows=[r for r in rows if week=="ALL" or str(r["week"])==str(week)]
    a=wins(rows,"ats_result")
    t=wins(rows,"total_result")
    result=dict(
        season=2026,week=week,model="injury",record_class="DERIVED_DIRECTIONAL_TIEBREAK",
        games_expected=len(rows),games_final=sum(r["score_status"]=="FINAL" for r in rows),
        games_pending=sum(r["score_status"]=="PENDING" for r in rows),last_grade_run_utc=now
    )
    for name,values in (("ats",a),("totals",t)):
        w,l,p,n=values
        result.update({
            name+"_wins":w,name+"_losses":l,name+"_pushes":p,name+"_no_lean":n,
            name+"_win_pct":round(w/(w+l)*100,2) if w+l else "",
            "illustrative_flat_110_"+name+"_roi_pct":round(100*((w*100/110)-l)/(w+l+p),2) if w+l+p else "",
        })
    return result

def main():
    base=read(SRC)
    if len(base)<86 or len({(r["game_id"],r["model"]) for r in base})!=len(base):
        raise ValueError("Official original results missing or game/model repeated")
    by_game={(r["game_id"],r["model"]):r for r in base}
    rows=[]
    special=[]
    for original in base:
        if original["model"]!="injury" or original["record_class"]!="PUBLIC_PUBLISHED":
            continue
        r=original.copy()
        r["original_total_pick"]=r["total_pick"]
        r["original_total_result"]=r["total_result"]
        r["fallback_model"]=""
        r["fallback_projected_total"]=""
        r["selection_provenance"]="ORIGINAL_PUBLISHED_INJURY_DIRECTION"
        r["policy_adopted_utc"]=POLICY_AT
        r["record_class"]="DERIVED_DIRECTIONAL_TIEBREAK"
        if r["total_pick"]=="No lean" or r["total_result"]=="No lean":
            if r["total_pick"]!="No lean" or r["total_result"]!="No lean" or float(r["projected_total"])!=float(r["bovada_total"]):
                raise ValueError("Original no-edge forecast differs from market "+r["game_id"])
            b=by_game.get((r["game_id"],"baseline"))
            market=float(r["bovada_total"])
            if b and b["record_class"]=="PUBLIC_PUBLISHED" and b["score_status"]==r["score_status"]:
                projected=float(b["projected_total"])
                if not math.isfinite(projected):
                    raise ValueError("Unusable baseline tie-breaker "+r["game_id"])
                pick="Over" if projected>market else "Under" if projected<market else None
                if pick is not None:
                    r["total_pick"]=pick
                    r["selection_provenance"]="POSTHOC_POLICY_USING_PREEXISTING_PREGAME_BASELINE"
                    r["fallback_model"]="baseline"
                    r["fallback_projected_total"]=str(projected)
            if r["total_pick"]=="No lean":
                # The default Unders for exact two-model ties is prospective
                # from the adoption of this policy. Not retroactive.
                if not r["kickoff_utc"]:
                    raise ValueError("Historical exact tie has no documented independent pregame direction "+r["game_id"])
                kickoff=datetime.fromisoformat(r["kickoff_utc"].replace("Z","+00:00"))
                adoption=datetime.fromisoformat(POLICY_AT.replace("Z","+00:00"))
                if kickoff<=adoption:
                    raise ValueError("Cannot create retrospective fallback without a pregame source "+r["game_id"])
                r["total_pick"]="Under"
                r["selection_provenance"]="PROSPECTIVE_POLICY_EXACT_TWO_MODEL_TIE_UNDER"
            final=None
            if r["score_status"]=="FINAL":
                final=int(float(r["actual_away"]))+int(float(r["actual_home"]))
            r["total_result"]=grade(r["total_pick"],final,market)
            special.append({
                "game_id":r["game_id"],"result":r["total_result"],
                "selection":r["total_pick"],"reason":r["selection_provenance"],
                "baseline_projection":r["fallback_projected_total"],
                "original_injury_projection":r["projected_total"],
                "bovada_total":r["bovada_total"],
                "actual_total":final,
            })
        if r["score_status"]=="FINAL" and (r["total_result"] not in ("Win","Loss","Push") or r["ats_result"]=="No lean"):
            raise ValueError("Completed game without directional model grade "+r["game_id"])
        if r["total_pick"] not in ("Over","Under"):
            raise ValueError("Undirected total for "+r["game_id"])
        rows.append(r)
    if len(rows)<43 or len({r["game_id"] for r in rows})!=len(rows):
        raise ValueError("Incomplete injury-only directional record")
    # Provenance lock for the one historical exception: NOT an Injury pick.
    w8=[r for r in rows if r["game_id"]=="2026_08_IND_JAX"]
    if len(w8)!=1:raise ValueError("Missing original zero-edge game")
    g=w8[0]
    if not (g["total_pick"]=="Over" and g["total_result"]=="Win"
            and g["original_total_result"]=="No lean"
            and g["fallback_projected_total"]=="46.9"
            and g["projected_total"]=="46.0" and g["bovada_total"]=="46.0"
            and int(float(g["actual_away"]))+int(float(g["actual_home"]))==49):
        raise ValueError("Week8 fallback does not match pre-existing pregame source and actual final")
    old=read(DST) if DST.exists() else []
    for previous in old:
        if previous["score_status"]!="FINAL":continue
        candidate=next((r for r in rows if r["game_id"]==previous["game_id"]),None)
        if candidate is None:raise ValueError("Retroactive deletion of a final game")
        for k in ("total_pick","total_result","ats_pick","ats_result","actual_home","actual_away",
                  "fallback_projected_total","selection_provenance","forecast_file","home_favored_spread","bovada_total"):
            if str(previous[k])!=str(candidate[k]):
                raise ValueError("Attempted to rewrite derived directional FINAL "+previous["game_id"]+" field "+k)
    new_fields=[{k:str(v.get(k,"")) for k in GRADE_FIELDS} for v in rows]
    old_fields=[{k:str(v.get(k,"")) for k in GRADE_FIELDS} for v in old]
    if old_fields and new_fields==old_fields:
        print(json.dumps({"status":"NO_CHANGE","graded_games":sum(r["score_status"]=="FINAL" for r in rows)}))
        return
    timestamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    weeks=sorted({int(r["week"]) for r in rows})
    summaries=[summary(rows,"ALL",timestamp)]+[summary(rows,w,timestamp) for w in weeks]
    save(DST,rows,GRADE_FIELDS)
    save(SUMMARY,summaries,SUM_FIELDS)
    META.write_text(json.dumps({
        "policy_adopted_utc":POLICY_AT,
        "record_class":"DERIVED_DIRECTIONAL_TIEBREAK",
        "name":"Complete directional record — Injury with pregame Baseline tie-break on zero-edge games",
        "explicit_non_claim":"Original Injury model never published an Over selection for Week8 IND@JAX; original prospective record remains 23-18 plus one no-pick. The derived 24-18 includes an Over assigned after results were known under a retrospective rule using an independently published pregame Baseline projection.",
        "tie_policy":"If Injury projected total equals Bovada, take direction of previously PUBLIC_PUBLISHED Baseline projected total vs pregame Bovada market. If both equal, choose Under only for post-policy kickoffs; do not retroactively infer earlier matches.",
        "historical_fallbacks":special,
        "never_rewrite":str(SRC.relative_to(ROOT)),
        "latest_generated_at_utc":timestamp,
    },indent=2)+"\n")
    print(json.dumps({"status":"UPDATED","games":len(rows),"special":special,"overall":summaries[0]},indent=2))

if __name__=="__main__":
    main()
