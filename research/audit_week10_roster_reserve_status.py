#!/usr/bin/env python3
"""Source-quality diagnostic: injury-report OUT rows vs separate nflverse roster RES.

This is an audit, NOT a new model coefficient or a reconstructed pregame source.
A weekly practice report cannot guarantee that athletes on IR/PUP/reserve were
included. Use the 2026 nflverse public roster release as a second, zero-paid-API
source, and report source freshness and all mismatches explicitly. Never use an
unknown roster status to automatically promote a new starter.
"""
from __future__ import annotations
import io,json
from datetime import datetime,timezone
from pathlib import Path
import sys
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
GAMEWEEK=10
SEASON=2026
ROSTER_URL="https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv"
SUNDAY=ROOT/"data"/"public_snapshots"/"nfl_week10_sunday_pregame_2026-11-15.csv"
CORRECTED=ROOT/"data"/"public_snapshots"/"nfl_week10_mia_ind_mccord_corrected_2026-11-15.csv"
REPORT=ROOT/"data"/"public_snapshots"/"nfl_week10_sunday_official_injury_designations_2026-11-15.csv"
RESULT=ROOT/"data"/"week10_review"/"week10_roster_reserve_secondary_audit_20261115.json"

def main():
    for p in [SUNDAY,CORRECTED,REPORT]:
        if not p.exists():raise FileNotFoundError(str(p))
    url=requests.get(ROSTER_URL,timeout=55)
    url.raise_for_status()
    df=pd.read_csv(io.BytesIO(url.content),low_memory=False)
    cols=set(df.columns)
    mandatory={"team","full_name","gsis_id","position","status","week"}
    if not mandatory.issubset(cols):
        raise ValueError(f"NFLverse roster input schema changed: {sorted(mandatory-cols)}. All available: {list(df.columns)}")
    df["week"]=pd.to_numeric(df.week,errors="coerce")
    if "season" in df.columns:
        df=df.loc[pd.to_numeric(df.season,errors="coerce").eq(SEASON)].copy()
    df=df.loc[df.week.between(1,GAMEWEEK)].copy()
    if df.empty:raise ValueError("Missing 2026 pre-week10 roster source")
    maxweek=int(df.week.max())
    if maxweek < GAMEWEEK-1:
        raise ValueError(f"Public roster too stale (latest week {maxweek}); not safe to infer current inactives")
    df["team"]=df.team.fillna("").astype(str).str.upper().replace({"LAR":"LA"})
    df["full_name"]=df.full_name.fillna("").astype(str)
    df["status"]=df.status.fillna("").astype(str).str.upper()
    df["gsis_id"]=df.gsis_id.fillna("").astype(str)
    df=df.sort_values(["week","team","gsis_id"]).drop_duplicates(["team","gsis_id"],keep="last")
    games=pd.read_csv(SUNDAY)
    injury=games.loc[games.model.eq("injury")]
    teams=set(injury.away_team)|set(injury.home_team)
    df=df.loc[df.team.isin(teams)].copy()
    primary_report=pd.read_csv(REPORT)
    final_out={(r.team,r.player_name.lower().strip()) for r in primary_report.itertuples()
               if r.final_game_status=="OUT"}
    # RES=on a reserve list, not necessarily all specifically injured reserve.
    # The status may have multiple reserve categories; do not call every RES 'IR'.
    reserve=df.loc[df.status.isin({"RES","IR","SUS","EXE"})].copy()
    not_in_final=reserve.loc[
        ~reserve.apply(lambda r:(r.team,r.full_name.lower().strip()) in final_out,axis=1)
    ]
    original_qbs=[]
    for g in injury.itertuples():
        for side in ("away","home"):
            original_qbs.append({
                "game_id":g.game_id,
                "team":getattr(g,side+"_team"),
                "reported":getattr(g,side+"_qb_name")
            })
    corrected=pd.read_csv(CORRECTED).iloc[0]
    for q in original_qbs:
        if q["game_id"]==corrected.game_id and q["team"]=="MIA":
            q["reported"]=corrected.away_qb_name
    qb_check=[]
    for q in original_qbs:
        matched=df.loc[
            df.team.eq(q["team"]) &
            df.full_name.str.lower().eq(str(q["reported"]).lower())
        ]
        if len(matched)!=1:
            qb_check.append({**q,"roster_status":"NOT_EXACTLY_ONE_MATCH","source_latest_week":None})
        else:
            rr=matched.iloc[0]
            qb_check.append({**q,"roster_status":rr.status,
                             "player_id":rr.gsis_id,"source_latest_week":int(rr.week)})
    report={
        "status":"RESEARCH_SECONDARY_ROSTER_RESERVE_AUDIT_NOT_MODEL_INPUT",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "roster_url":ROSTER_URL,
        "roster_total_rows_downloaded":len(pd.read_csv(io.BytesIO(url.content),low_memory=False)),
        "latest_roster_week_in_source":maxweek,
        "game_week":GAMEWEEK,
        "included_teams":len(teams),
        "source_status_counts":df.status.value_counts().to_dict(),
        "reserve_population_count":len(reserve),
        "reserve_not_listed_out_in_final_weekly_report":len(not_in_final),
        "reserve_sample_absent_from_final_report":not_in_final[
            ["team","full_name","position","status","week","gsis_id"]
        ].head(80).to_dict("records"),
        "qb_count":len(qb_check),
        "qb_2026_statuses":qb_check,
        "qb_unavailable_or_missing": [q for q in qb_check
           if q["roster_status"] in {"RES","IR","SUS","EXE","NOT_EXACTLY_ONE_MATCH"}],
        "critical_caveat":"Roster statuses are nflverse public secondary data as-of their latest listed roster week; not proof of live game-day actives. 'RES' is reserve category and may include IR/PUP/suspension. This file is diagnostic only and cannot silently alter live models or historical forecasts.",
    }
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:report[k] for k in ("status","latest_roster_week_in_source","included_teams","reserve_population_count","reserve_not_listed_out_in_final_weekly_report","qb_count","qb_unavailable_or_missing")},indent=2))
if __name__=="__main__":
    main()
