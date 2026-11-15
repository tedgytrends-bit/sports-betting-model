#!/usr/bin/env python3
"""Publish immutable Sunday morning NFL Week 10 research/public pre-inactives refresh.

Use the preserved user's Nov 15 screenshot market and NFL.com Nov 14 final
*game designations*. Patch the public NFLverse snapshot only for explicitly
listed players with exact team/name matches; never infer OUT for questionable
players, nor silently fabricate IDs for unmatched names. The official model
continues to score by its established team count pipeline; no new coefficients.

Run before the first Sunday 2026 Week 10 kickoff. Do not edit or overwrite
Nov12 original 28-row score snapshot, Bovada initial prices or Thursday result.
"""
from __future__ import annotations
import json,re,sys,unicodedata
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp,build_efficiency_model_dataset,project_upcoming_efficiency
from injury_model import load_injury_reports,project_qb_aware_injury,_kickoff_utc
from scripts.capture_qb_aware_injury import SEASONS,load_coach_expected_starters,reject_known_inactive_qb
from research.validate_qb_starter_confirmations import validate_starter_confirmations

PUB=ROOT/"data"/"public_snapshots"
SUNDAY=PUB/"nfl_week10_bovada_sunday_2026-11-15T1256Z.csv"
REPORT=PUB/"nfl_week10_sunday_official_injury_designations_2026-11-15.csv"
INIT=PUB/"nfl_week10_initial_projections_2026-11-12.csv"
OUT=PUB/"nfl_week10_sunday_pregame_2026-11-15.csv"
META=PUB/"nfl_week10_sunday_pregame_2026-11-15_manifest.json"
DETAIL=PUB/"nfl_week10_sunday_injury_overlay_audit_2026-11-15.csv"
WATCH=ROOT/"data"/"qb_starters"/"2026_week10_watchlist.csv"
CONFIRMED=ROOT/"data"/"qb_starters"/"2026_week10_confirmed.csv"
SEASON,WEEK=2026,10
SIDES={"OUT","QUESTIONABLE","DOUBTFUL"}

def canonical(s):
    s=str(s).upper().strip()
    return "LA" if s=="LAR" else s

def normalize_name(x):
    s=unicodedata.normalize("NFKD",str(x)).encode("ascii","ignore").decode()
    s=re.sub(r"[^a-zA-Z0-9 ]","",s).strip().lower()
    s=re.sub(r"\b(jr|ii|iii|iv|sr)\b","",s)
    return " ".join(s.split())

def latest_saved_snapshot():
    paths=sorted((ROOT/"data"/"injury_snapshots").glob("injuries_2026_week_10_*.csv"))
    if not paths:
        raise FileNotFoundError("Latest saved nflverse Week10 injury source unavailable")
    return paths[-1],pd.read_csv(paths[-1],low_memory=False)

def build_reconciled_snapshot(now,official):
    previous,base=latest_saved_snapshot()
    if not {"team","full_name","gsis_id","report_status","snapshot_captured_at_utc"}.issubset(base.columns):
        raise ValueError("Unexpected saved NFLverse snapshot schema")
    if base.gsis_id.isna().any() or base.gsis_id.duplicated().any():
        raise ValueError("NFLverse snapshot has incomplete/duplicate GSIS")
    expected={(str(row.team),normalize_name(row.player_name)):str(row.final_game_status).upper()
              for row in official.itertuples(index=False)}
    if len(expected)!=len(official):
        raise ValueError("Duplicate official team+player names")
    base["_teamkey"]=base.team.map(canonical)
    base["_namekey"]=base.full_name.map(normalize_name)
    if base.duplicated(["_teamkey","_namekey"]).any():
        raise ValueError("Duplicate NFLverse snapshot team/name matching keys")
    original=base.report_status.fillna("").astype(str).str.upper().str.strip()
    updated=[]
    missed=[]
    contradictions=[]
    for i,row in base.iterrows():
        key=(row["_teamkey"],row["_namekey"])
        old=original.loc[i]
        if key in expected:
            new=expected.pop(key)
            if new not in SIDES:
                raise ValueError(f"Invalid authoritative status for {key}: {new}")
            if new!=old:
                contradictions.append({"team":key[0],"player":row.full_name,
                    "old_snapshot":old,"official_new":new})
            base.loc[i,"report_status"]=new
            base.loc[i,"status_authority"]="NFL_WEEK10_NOV14_FINAL"
            updated.append({"team":key[0],"player":row.full_name,
                "old_snapshot":old,"official_new":new,
                "matched_to_nflverse_gsis":str(row.gsis_id)})
        else:
            # Preserve existing unlabeled statuses; the linked official report
            # has no direct matching row, so absence is not used as negative proof.
            base.loc[i,"status_authority"]="NFLVERSE_LATEST_UNCHANGED"
    for (team,name),status in expected.items():
        missed.append({"team":team,"player_name_normalized":name,"official_status":status})
    match_rate=len(updated)/len(official)
    if match_rate < 0.78:
        raise ValueError(f"Unsafe low status identity match rate {match_rate:.1%}: {missed[:15]}")
    # Clearly flag unmatched explicit statuses, rather than manufacture GSIS.
    extra=pd.DataFrame(
        [{"team":x["team"],"player":x["player_name_normalized"],
          "old_snapshot":"NO_MATCH","official_new":x["official_status"],
          "matched_to_nflverse_gsis":""} for x in missed]
    )
    audit=pd.concat([pd.DataFrame(updated),extra],ignore_index=True)
    base.drop(columns=["_teamkey","_namekey"],inplace=True)
    ts=now.strftime("%Y-%m-%dT%H:%M:%SZ")
    base["snapshot_captured_at_utc"]=ts
    # Preserve the real original source URL; source overrides are traced separately.
    base["official_status_report_url"]="https://amp.nfl.com/news/nfl-week-10-injury-report-2026-season"
    base["official_status_report_updated_at_utc"]="2026-11-14T21:48:00Z"
    filename=f"injuries_2026_week_10_{now.strftime('%Y%m%dT%H%M%SZ')}.csv"
    path=ROOT/"data"/"injury_snapshots"/filename
    if path.exists():
        raise FileExistsError("A newer pregame snapshot already saved at same UTC second")
    path.parent.mkdir(parents=True,exist_ok=True)
    base.to_csv(path,index=False)
    return path,audit,{"latest_original_source":str(previous.relative_to(ROOT)),
        "new_snapshot":str(path.relative_to(ROOT)),
        "official_players":int(len(official)),
        "official_matched":len(updated),"unmatched_official":missed,
        "matched_fraction":round(match_rate,4),
        "explicit_status_changes":contradictions}

def main():
    if OUT.exists() or META.exists() or DETAIL.exists():
        raise FileExistsError("Already published Sunday snapshot; preserve initial and Sunday files")
    now=datetime.now(timezone.utc).replace(microsecond=0)
    moment=pd.Timestamp(now)
    for item in (SUNDAY,REPORT,INIT,CONFIRMED,WATCH):
        if not item.exists():raise FileNotFoundError(str(item))
    schedule=load_schedule_data()
    selected=schedule.loc[
        pd.to_numeric(schedule.season,errors="coerce").eq(SEASON)
        & pd.to_numeric(schedule.week,errors="coerce").eq(WEEK)
    ].copy()
    if selected.game_id.nunique()!=14:raise ValueError("Missing Week10 full schedule")
    selected=selected.loc[~selected.game_id.eq("2026_10_WAS_NYG")]
    if len(selected)!=13:raise ValueError("Sunday/Monday 13-game slate incomplete")
    before={g.game_id:_kickoff_utc(pd.Series(g._asdict())) for g in selected.itertuples(index=False)}
    if any(pd.isna(x) or x<=moment for x in before.values()):
        raise ValueError("Cannot issue common Sunday pregame snapshot after first kickoff")
    quotes=pd.read_csv(SUNDAY)
    if len(quotes)!=13 or quotes.duplicated(["away_team","home_team"]).any():
        raise ValueError("13 screenshot prices expected")
    book={(canonical(q.away_team),canonical(q.home_team)):q for q in quotes.itertuples(index=False)}
    if len(book)!=13 or any((canonical(g.away_team),canonical(g.home_team)) not in book for g in selected.itertuples()):
        raise ValueError("Mismatch between Sunday games and Bovada screenshot markets")
    if not (pd.to_datetime(quotes.captured_at_utc,utc=True,errors="coerce")<moment).all():
        raise ValueError("Screenshot quote time invalid or in future")
    report=pd.read_csv(REPORT)
    if len(report)<150 or report.game_id.nunique()!=13 or set(report.final_game_status)-SIDES:
        raise ValueError("Official Sunday statuses incomplete")
    if len(set(report.team))!=26:
        raise ValueError("Missing team's game statuses")
    if not (pd.to_datetime(report.report_updated_at_utc,utc=True,errors="coerce")<moment).all():
        raise ValueError("Official NFL report timestamp after evaluation")

    snapshot,audit,source=build_reconciled_snapshot(now,report)
    pbp=load_pbp(SEASONS)
    # The Baseline uses exactly the existing unmodified model structure.
    base=project_upcoming_efficiency(
        build_efficiency_model_dataset(schedule,pbp,lookback_games=10),
        min_train_games=500,
    )
    # The Injury uses updated point-in-time report snapshot plus source-gated QB
    # identity. It does not change cap, weights, regression coefficients.
    historical=load_injury_reports(SEASONS)
    raw_ver=pd.read_csv(CONFIRMED,dtype=str,keep_default_na=False)
    verified,source_audit=validate_starter_confirmations(schedule,raw_ver,checked_as_of_utc=now)
    if not source_audit.override_eligible.all() or len(verified)!=2:
        raise ValueError("Failed Arizona and Seattle QB primary-source verification")
    expected=load_coach_expected_starters(schedule,SEASON,WEEK)
    injury,qb=project_qb_aware_injury(
        schedule,pbp,historical,season=SEASON,week=WEEK,
        verified_starters=verified,expected_starters=expected
    )
    reject_known_inactive_qb(qb,pd.read_csv(WATCH,dtype=str,keep_default_na=False))
    if qb.duplicated(["game_id","team"]).any():raise ValueError("Duplicated QB assignments")
    rows=[]
    official_counts=report.groupby(["game_id","final_game_status"]).size().to_dict()
    for label,frame in (("baseline",base),("injury",injury)):
        frame=frame.loc[frame.game_id.isin(before)]
        if len(frame)!=13 or frame.game_id.nunique()!=13:
            raise ValueError(f"Model {label} missing 13 Sunday future forecasts; schedule may contain premature final scores")
        for row in frame.to_dict("records"):
            gid=row["game_id"]
            a,h,t=[float(row[x]) for x in ("projected_away","projected_home","projected_total")]
            if not all(np.isfinite(x) and 0<=x<=80 for x in (a,h,t)) or abs(a+h-t)>0.02:
                raise ValueError(f"Implausible scores {gid} {label}")
            quote=book[(canonical(row["away_team"]),canonical(row["home_team"]))]
            margin=float(quote.home_favorite_spread)
            total=float(quote.total_line)
            rows.append({
                "published_at_utc":now.isoformat().replace("+00:00","Z"),
                "publication_status":"SUNDAY_NOV15_PREINACTIVES_PREGAME_INJURY_REFRESH",
                "game_id":gid,"season":SEASON,"week":WEEK,
                "gameday":pd.to_datetime(row["gameday"]).strftime("%Y-%m-%d"),
                "kickoff_utc":before[gid].isoformat().replace("+00:00","Z"),
                "away_team":canonical(row["away_team"]),
                "home_team":canonical(row["home_team"]),
                "model":label,
                "model_version":("baseline_ridge10_current_week9_training" if label=="baseline" else "qb_epa_margin_cap5_current_final_status_preinactives"),
                "projected_away":round(a,6),"projected_home":round(h,6),
                "projected_total":round(t,6),
                "model_home_margin":round(h-a,6),
                "training_games":int(row["training_games"]),
                "home_injury_report_available":row.get("home_injury_report_available",""),
                "away_injury_report_available":row.get("away_injury_report_available",""),
                "home_qb_name":row.get("home_qb_name",""),
                "away_qb_name":row.get("away_qb_name",""),
                "home_qb_starter_source":row.get("home_starter_source",""),
                "away_qb_starter_source":row.get("away_starter_source",""),
                "qb_margin_adjustment":row.get("qb_margin_adjustment",""),
                "bovada_home_favored_spread":margin,
                "bovada_total":total,
                "bovada_snapshot_at_utc":str(quote.captured_at_utc),
                "bovada_away_spread_price":int(quote.away_spread_price),
                "bovada_home_spread_price":int(quote.home_spread_price),
                "bovada_over_price":int(quote.over_price),
                "bovada_under_price":int(quote.under_price),
                "injuries_out_count":int(official_counts.get((gid,"OUT"),0)),
                "injuries_doubtful_count":int(official_counts.get((gid,"DOUBTFUL"),0)),
                "injuries_questionable_count":int(official_counts.get((gid,"QUESTIONABLE"),0)),
                "qb_identity_warning":"" if label=="baseline" else "Only Arizona and Seattle starters are primary-source-confirmed; coach-expected Baltimore, others schedule-provisional.",
                "inactives_status":"Final injury designations published; game-day inactives not all released at this snapshot",
            })
    output=pd.DataFrame(rows).sort_values(["kickoff_utc","game_id","model"])
    if len(output)!=26 or output.duplicated(["game_id","model"]).any():
        raise ValueError("Need 26 uniquely paired rows")
    if not (pd.to_datetime(output.published_at_utc,utc=True)<pd.to_datetime(output.kickoff_utc,utc=True)).all():
        raise ValueError("Sunday publication not pregame")
    manifest={
        "status":"SUNDAY_NOV15_PREINACTIVES_PREGAME_INJURY_REFRESH",
        "published_at_utc":now.isoformat().replace("+00:00","Z"),
        "models":["baseline","injury"],"games":13,"rows":len(output),
        "original_immutable":"data/public_snapshots/nfl_week10_initial_projections_2026-11-12.csv",
        "screenshot_prices":str(SUNDAY.relative_to(ROOT)),
        "official_injury_statuses":str(REPORT.relative_to(ROOT)),
        "source_of_week10_injury_snapshot":source,
        "confirmed_2026_week10_qbs":int(qb.starter_source.eq("verified_pregame").sum()),
        "coach_expected_2026_week10_qbs":int(qb.starter_source.eq("coach_expected_pregame_unverified").sum()),
        "qb_source_counts":qb.starter_source.value_counts().to_dict(),
        "policy":"Keep Thursday snapshot immutable. Final NFL injury designations are pre-inactives; do not call them final active lists. Some manually verified QB names and others remain provisional. Sunday 8:30 AM CT earliest kickoff. No paid injury or odds API credits.",
        "note":"Site may display this as separate, timestamped updated pregame projection; original Thursday release remains independently reproducible and gradeable.",
    }
    output.to_csv(OUT,index=False)
    audit.to_csv(DETAIL,index=False)
    META.write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in manifest.items() if k!="source_of_week10_injury_snapshot"},indent=2))
    print(output.loc[output.model.eq("injury"),["game_id","projected_away","projected_home","projected_total","home_qb_name","away_qb_name"]].to_string(index=False))

if __name__=="__main__":
    main()
