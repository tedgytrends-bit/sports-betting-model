#!/usr/bin/env python3
"""One-game pregame QB-aware Injury refinement after official NE-DET inactives.

The 13-game Sunday 07:04 CT prospective file is immutable. This emits a
second, separately dated NE/DET Injury-only forecast after BOTH team's public
game-day lists, before 08:30 CT kickoff. No production parameters change.
"""
from __future__ import annotations
import json,sys,re,unicodedata
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp
from injury_model import load_injury_reports,project_qb_aware_injury,_kickoff_utc
from scripts.capture_qb_aware_injury import SEASONS,load_coach_expected_starters,reject_known_inactive_qb
from research.validate_qb_starter_confirmations import validate_starter_confirmations
PUB=ROOT/"data"/"public_snapshots"
SOURCE=PUB/"nfl_week10_ne_det_official_inactives_2026-11-15.csv"
FROZEN=PUB/"nfl_week10_sunday_pregame_2026-11-15.csv"
MARKET=PUB/"nfl_week10_bovada_sunday_2026-11-15T1256Z.csv"
CORRECTED_SOURCE=ROOT/"data"/"injury_snapshots"/"injuries_2026_week_10_20261115T130438Z.csv"
OUT=PUB/"nfl_week10_ne_det_inactives_adjusted_2026-11-15.csv"
META=PUB/"nfl_week10_ne_det_inactives_adjusted_2026-11-15_manifest.json"
CONFIRMED=ROOT/"data"/"qb_starters"/"2026_week10_confirmed.csv"
WATCH=ROOT/"data"/"qb_starters"/"2026_week10_watchlist.csv"

def normalized(s):
    x=unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower()
    x=re.sub(r"[^a-z0-9 ]","",x)
    x=re.sub(r"\b(jr|ii|iii|iv|sr)\b","",x)
    return " ".join(x.split())

def main():
    if OUT.exists() or META.exists():
        raise FileExistsError("Official early-game inactive update already stored")
    now=datetime.now(timezone.utc).replace(microsecond=0)
    if any(not p.exists() for p in (SOURCE,FROZEN,MARKET,CORRECTED_SOURCE,CONFIRMED,WATCH)):
        raise FileNotFoundError("Missing original Sunday, official status, or QB source")
    schedule=load_schedule_data()
    g=schedule.loc[schedule.game_id.eq("2026_10_NE_DET")]
    if len(g)!=1:
        raise ValueError("Expected exactly one NE@DET Sunday game")
    cutoff=_kickoff_utc(g.iloc[0])
    if pd.isna(cutoff) or pd.Timestamp(now)>=cutoff:
        raise ValueError("Official inactive-revised score must precede kickoff")
    actual=pd.read_csv(SOURCE)
    if len(actual)!=20 or set(actual.final_active_status)!={"ACTIVE_CONFIRMED","INACTIVE"}:
        raise ValueError("Incomplete team-published NE/DET active/inactive review")
    if not actual.final_active_status.eq("INACTIVE").sum()==12 or not actual.final_active_status.eq("ACTIVE_CONFIRMED").sum()==8:
        raise ValueError("NE/DET expected official 12 inactive 8 explicit active players")
    if any(pd.to_datetime(actual.source_published_at_utc,utc=True)>pd.Timestamp(now)):
        raise ValueError("Inactive source future relative to capture")
    previous=pd.read_csv(CORRECTED_SOURCE)
    if previous.gsis_id.duplicated().any():
        raise ValueError("Prior player IDs duplicated")
    previous["_key"]=previous.team.astype(str).str.upper()+"|"+previous.full_name.map(normalized)
    changes=[]
    missing=[]
    for row in actual.itertuples(index=False):
        key=str(row.team).upper()+"|"+normalized(row.player_name)
        matched=previous.index[previous["_key"].eq(key)]
        if len(matched)>1:
            raise ValueError("Ambiguous day-of-game inactive player "+key)
        if not len(matched):
            missing.append({"player":str(row.player_name),"team":str(row.team),"status":str(row.final_active_status)})
            continue
        idx=matched[0]
        old=str(previous.loc[idx,"report_status"])
        nxt="Out" if row.final_active_status=="INACTIVE" else ""
        previous.loc[idx,"report_status"]=nxt
        previous.loc[idx,"status_authority"]="OFFICIAL_TEAM_INACTIVE_2026-11-15"
        changes.append({"team":str(row.team),"name":str(row.player_name),"status":str(row.final_active_status),"before":old,"after":nxt})
    if len(changes)<11:
        raise ValueError(f"Too few player identities matched for a safe game-day adjustment: {len(changes)}")
    previous=previous.drop(columns=["_key"])
    previous["snapshot_captured_at_utc"]=now.isoformat().replace("+00:00","Z")
    previous["official_inactive_source_url"]=(
        "https://www.patriots.com/news/week-10-inactives-patriots-vs-lions"
    )
    path=ROOT/"data"/"injury_snapshots"/f"injuries_2026_week_10_{now.strftime('%Y%m%dT%H%M%SZ')}.csv"
    if path.exists():
        raise FileExistsError("Snapshot capture timestamp duplicate")
    path.parent.mkdir(parents=True,exist_ok=True)
    previous.to_csv(path,index=False)
    reports=load_injury_reports(SEASONS)
    pbp=load_pbp(SEASONS)
    verified,review=validate_starter_confirmations(schedule,pd.read_csv(CONFIRMED,dtype=str,keep_default_na=False),checked_as_of_utc=now)
    if len(verified)!=2 or not review.override_eligible.all():
        raise ValueError("QB starter verification no longer passed")
    forecast,board=project_qb_aware_injury(
        schedule,pbp,reports,season=2026,week=10,
        verified_starters=verified,
        expected_starters=load_coach_expected_starters(schedule,2026,10),
    )
    reject_known_inactive_qb(board,pd.read_csv(WATCH,dtype=str,keep_default_na=False))
    match=forecast.loc[forecast.game_id.eq("2026_10_NE_DET")]
    if len(match)!=1:
        raise ValueError("Expected one new Sunday NE-DET prediction")
    row=match.iloc[0]
    quote=pd.read_csv(MARKET)
    q=quote.loc[quote.away_team.eq("NE")&quote.home_team.eq("DET")]
    if len(q)!=1:raise ValueError("Missing original user Bovada snapshot")
    q=q.iloc[0]
    original=pd.read_csv(FROZEN)
    old=original.loc[original.game_id.eq("2026_10_NE_DET")&original.model.eq("injury")]
    if len(old)!=1:raise ValueError("Original Sunday NE-DET snapshot missing")
    old=old.iloc[0]
    h,a,t=(float(row[x]) for x in ["projected_home","projected_away","projected_total"])
    if not all(np.isfinite(v) for v in (h,a,t)) or abs(a+h-t)>.02:
        raise ValueError("Invalid after-inactives score")
    result=pd.DataFrame([{
        "published_at_utc":now.isoformat().replace("+00:00","Z"),
        "publication_status":"NE_DET_OFFICIAL_GAMEDAY_INACTIVES_PREGAME_UPDATE",
        "game_id":"2026_10_NE_DET","season":2026,"week":10,
        "away_team":"NE","home_team":"DET",
        "model":"injury","model_version":"qb_epa_margin_cap5_after_official_game_day_inactives",
        "kickoff_utc":cutoff.isoformat().replace("+00:00","Z"),
        "projected_away":round(a,6),"projected_home":round(h,6),
        "projected_total":round(t,6),
        "model_home_margin":round(h-a,6),
        "home_qb_name":str(row["home_qb_name"]), "away_qb_name":str(row["away_qb_name"]),
        "home_qb_starter_source":str(row["home_starter_source"]),
        "away_qb_starter_source":str(row["away_starter_source"]),
        "qb_margin_adjustment":float(row["qb_margin_adjustment"]),
        "prior_sunday_projected_home":float(old.projected_home),
        "prior_sunday_projected_away":float(old.projected_away),
        "prior_sunday_projected_total":float(old.projected_total),
        "bovada_home_favored_spread":float(q.home_favorite_spread),
        "bovada_total":float(q.total_line),
        "bovada_snapshot_at_utc":str(q.captured_at_utc),
        "official_teams_inactive_source":"https://www.patriots.com/news/week-10-inactives-patriots-vs-lions",
    }])
    meta={
        "status":"NE_DET_OFFICIAL_GAMEDAY_INACTIVES_PREGAME_UPDATE",
        "created_utc":now.isoformat().replace("+00:00","Z"),
        "games":1,"model":"injury",
        "initial_immutable":"data/public_snapshots/nfl_week10_initial_projections_2026-11-12.csv",
        "first_sunday_immutable":str(FROZEN.relative_to(ROOT)),
        "matched_gameday_identity_rows":changes,
        "unmatched_gameday_identity_rows":missing,
        "new_source_snapshot":str(path.relative_to(ROOT)),
        "game_inactives_archived":str(SOURCE.relative_to(ROOT)),
        "review_note":"Separate before-kickoff Monday? No: early Sunday international game. Only new NE-DET Injury margin/total in this file. Other 12 Sunday games and Thursday remain original published vintages.",
        "quarterback_source_warning":"NE Drake Maye and DET Jared Goff remain schedule-provisional names; neither official inactive list declares a different starter.",
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(OUT,index=False)
    META.write_text(json.dumps(meta,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":meta["status"],"matched":len(changes),"unmatched":missing,
        "new_ne":round(a,1),"new_det":round(h,1),"new_total":round(t,1),
        "previous_ne":float(old.projected_away),"previous_det":float(old.projected_home)},indent=2))

if __name__=="__main__":
    main()
