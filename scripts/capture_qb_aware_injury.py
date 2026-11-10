#!/usr/bin/env python3
"""Generate ONE current-week Injury candidate using prior-QB EPA.

This is the reusable weekly Injury pipeline, replacing the older QB-count
score methodology for *future publications*. The committed, frozen model
archives are never silently rewritten. Output is for inspection and deliberate
publication before kickoff; the public website reads immutable releases.

Usage: python scripts/capture_qb_aware_injury.py --season 2026 --week 9
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp
from injury_model import load_injury_reports,project_qb_aware_injury
from research.validate_qb_starter_confirmations import validate_starter_confirmations

OUT=ROOT/"data"/"qb_epa_shadow"
SEASONS=(2021,2022,2023,2024,2025,2026)


def run(season:int,week:int)->None:
    now=datetime.now(timezone.utc).replace(microsecond=0)
    schedule=load_schedule_data()
    path=ROOT/"data"/"qb_starters"/f"{season}_week{week:02d}_confirmed.csv"
    verified=None
    source_audit=pd.DataFrame()
    rejected_count=0
    if path.exists():
        candidate=pd.read_csv(path,dtype=str,keep_default_na=False)
        verified,source_audit=validate_starter_confirmations(
            schedule,candidate,checked_as_of_utc=now
        )
        rejected_count=int((~source_audit["override_eligible"]).sum())
        print(
            f"QB manually reviewed game-specific overrides: {len(verified)} of {len(candidate)}; "
            f"excluded: {rejected_count}. Review the source audit artifact."
        )
        if verified.empty:
            verified=None
    pbp=load_pbp(SEASONS)
    injuries=load_injury_reports(SEASONS)
    result,board=project_qb_aware_injury(
        schedule,pbp,injuries,season=season,week=week,verified_starters=verified
    )
    if result.game_id.duplicated().any() or len(board)!=2*len(result):
        raise ValueError("QB research output has duplicate/missing team games")
    result["captured_at_utc"]=now.isoformat()
    result["source_type"]="PREGAME_RESEARCH_PENDING_RELEASE"
    qb_counts=board.starter_source.value_counts().to_dict()
    by_game=board.assign(
        verified=board.starter_source.eq("verified_pregame")
    ).groupby("game_id")["verified"].agg(["sum","count"])
    both=(by_game["sum"].eq(2) & by_game["count"].eq(2))
    result["both_qbs_source_verified"]=result.game_id.map(both).fillna(False).astype(bool)
    # Research-only sensitivity: suppress provisional QB shifts here, never
    # overwrite the original current Injury candidate projection.
    for side in ("home","away"):
        result[f"verified_only_projected_{side}"]=result[
            f"projected_{side}_qb_injury"
        ].where(result["both_qbs_source_verified"],result[f"projected_{side}"])
    result["verified_only_projected_total"]=(
        result["verified_only_projected_home"]+result["verified_only_projected_away"]
    )
    OUT.mkdir(parents=True,exist_ok=True)
    stamp=now.strftime("%Y%m%dT%H%M%SZ")
    stem=f"injury_qb_epa_{season}_week{week:02d}_{stamp}"
    preds=OUT/f"{stem}.csv"
    qb=OUT/f"{stem}_qb_detail.csv"
    result.to_csv(preds,index=False)
    source_audit_file=None
    if not source_audit.empty:
        audit_path=OUT/f"{stem}_starter_source_audit.csv"
        source_audit.to_csv(audit_path,index=False)
        source_audit_file=str(audit_path.relative_to(ROOT))
    board.to_csv(qb,index=False)
    metadata={
        "status":"RESEARCH_CAPTURE_ONLY_NO_RETROACTIVE_REWRITE",
        "captured_at_utc":now.isoformat(),
        "season":season,"week":week,
        "model":"injury","model_version":"qb_epa_margin_cap5_v1",
        "non_qb_model":"Ridge score projections with QB rows excluded from injury/practice counts",
        "qb_component":"Prior-to-game regularized QB EPA vs team recent QB mix; capped at +/-5 pts per team; margin-only so base total unchanged",
        "starter_source_counts":qb_counts,
        "verified_starter_count":int(board.starter_source.eq("verified_pregame").sum()),
        "both_starters_verified_games":int(result["both_qbs_source_verified"].sum()),
        "rejected_override_count":rejected_count,
        "starter_source_audit":source_audit_file,
        "verification_policy":"Only manually content-reviewed game-specific source statements with traceable timestamps are eligible. Provisional QB shifts remain research-only.",
        "week_games":int(len(result)),
        "records":str(preds.relative_to(ROOT)),
        "qb_details":str(qb.relative_to(ROOT)),
        "warnings":[
            "NFLverse upcoming starter listings are provisional unless a recent game-specific source is explicitly reviewed.",
            "A source URL and timestamp alone do not establish QB starter confirmation.",
            "The verified-only sensitivity remains research-only and does not rewrite the original candidate.",
            "Selected after analyzing 2026 Weeks 1-8; not independently validated.",
            "This capture does not overwrite the public website or official history; publish a dated immutable snapshot before kickoff."
        ]
    }
    manifest=OUT/f"{stem}_manifest.json"
    manifest.write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(metadata,indent=2))
    print(result[["game_id","projected_away","projected_home",
                  "projected_total","qb_margin_adjustment",
                  "away_qb_name","home_qb_name"]].to_string(index=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season",type=int,default=2026)
    parser.add_argument("--week",type=int,required=True)
    args=parser.parse_args()
    if args.week<1 or args.week>22:parser.error("Week must be between 1 and 22")
    run(args.season,args.week)
