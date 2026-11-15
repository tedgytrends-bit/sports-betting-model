#!/usr/bin/env python3
"""Correct only MIA@IND from the saved Sunday Week10 pregame research snapshot.

A published fantasy/depth chart is not a source of authoritative QB availability.
Use the Miami Dolphins' Nov14 game-specific announcement and Nov10 IR release.
The Nov15 07:04 CT 13-game snapshot, Nov15 07:18 NE@DET snapshot, and Bovada
prices remain immutable. Do not promote the new-to-NFL QB EPA estimate as EV.
"""
from __future__ import annotations

import json,sys
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp
from injury_model import load_injury_reports,project_qb_aware_injury,_kickoff_utc
from scripts.capture_qb_aware_injury import (
    SEASONS,load_coach_expected_starters,reject_known_inactive_qb,
)
from research.validate_qb_starter_confirmations import validate_starter_confirmations

GAME="2026_10_MIA_IND"
QB_TEAM="MIA"
QB_NAME="Kyle McCord"
QB_ID="00-0040014"
OLD_QB="Malik Willis"
PUB=ROOT/"data"/"public_snapshots"
ORIGINAL=PUB/"nfl_week10_sunday_pregame_2026-11-15.csv"
NEW=PUB/"nfl_week10_mia_ind_mccord_corrected_2026-11-15.csv"
META=PUB/"nfl_week10_mia_ind_mccord_corrected_2026-11-15_manifest.json"
REVIEW=ROOT/"data"/"qb_starters"/"2026_week10_confirmed.csv"
WATCH=ROOT/"data"/"qb_starters"/"2026_week10_watchlist.csv"
MARKET=PUB/"nfl_week10_bovada_sunday_2026-11-15T1256Z.csv"
STATUS="MIA_IND_KYLE_MCCORD_PREGAME_SOURCE_CORRECTION"

def main():
    if NEW.exists() or META.exists():
        raise FileExistsError("Miami correction previously archived; do not overwrite")
    for f in [ORIGINAL,REVIEW,WATCH,MARKET]:
        if not f.exists():raise FileNotFoundError(str(f))
    now=datetime.now(timezone.utc).replace(microsecond=0)
    current=pd.Timestamp(now)
    schedule=load_schedule_data()
    game=schedule.loc[schedule.game_id.eq(GAME)]
    if len(game)!=1:raise ValueError("MIA@IND missing from saved schedule")
    kickoff=_kickoff_utc(game.iloc[0])
    if pd.isna(kickoff) or current>=kickoff:
        raise ValueError("Cannot publish a QB correction after kickoff")
    original=pd.read_csv(ORIGINAL)
    prior=original.loc[original.game_id.eq(GAME)&original.model.eq("injury")]
    if len(original)!=26 or len(prior)!=1 or prior.iloc[0].away_qb_name!=OLD_QB:
        raise ValueError("Original Sunday model snapshot unexpectedly changed")
    prior=prior.iloc[0]
    raw=pd.read_csv(REVIEW,dtype=str,keep_default_na=False)
    verified,audit=validate_starter_confirmations(
        schedule,raw,checked_as_of_utc=now
    )
    if len(verified)!=3 or not audit.override_eligible.all():
        raise ValueError("At least one current-source QB attestation failed")
    candidate=verified.loc[verified.game_id.eq(GAME)&verified.team.eq(QB_TEAM)]
    if len(candidate)!=1 or candidate.iloc[0].qb_id!=QB_ID or candidate.iloc[0].qb_name!=QB_NAME:
        raise ValueError("Dolphins QB identity is not the source-confirmed McCord GSIS")
    watch=pd.read_csv(WATCH,dtype=str,keep_default_na=False)
    invalid=watch.loc[
        watch.game_id.eq(GAME)
        & watch.team.eq(QB_TEAM)
        & watch.player_name.eq(OLD_QB)
        & watch.starter_confirmation_status.eq("IR_REPORTED")
    ]
    if len(invalid)!=1:
        raise ValueError("Explicit official Nov10 IR block for Malik Willis not recorded")

    pbp=load_pbp(SEASONS)
    injuries=load_injury_reports(SEASONS)
    preds,details=project_qb_aware_injury(
        schedule,pbp,injuries,season=2026,week=10,
        verified_starters=verified,
        expected_starters=load_coach_expected_starters(schedule,2026,10),
    )
    reject_known_inactive_qb(details,watch)
    qb=details.loc[details.game_id.eq(GAME)&details.team.eq(QB_TEAM)]
    if len(qb)!=1:
        raise ValueError("QB detail absent for MIA@IND")
    q=qb.iloc[0]
    if str(q.qb_id)!=QB_ID or str(q.qb_name)!=QB_NAME or q.starter_source!="verified_pregame":
        raise ValueError("Player ID and source of Week10 Miami quarterback not confirmed")
    pred=preds.loc[preds.game_id.eq(GAME)]
    if len(pred)!=1:raise ValueError("Cannot find unique corrected Miami forecast")
    pred=pred.iloc[0]
    scores=[float(pred[k]) for k in ["projected_away","projected_home","projected_total"]]
    if any(not np.isfinite(x) for x in scores) or abs(scores[0]+scores[1]-scores[2])>.02:
        raise ValueError("Invalid prospective model score or total")
    odds=pd.read_csv(MARKET).loc[lambda f:f.away_team.eq("MIA")&f.home_team.eq("IND")]
    if len(odds)!=1:raise ValueError("Bovada screenshot odds don't identify MIA@IND")
    odds=odds.iloc[0]
    result=pd.DataFrame([{
        "game_id":GAME,"away_team":"MIA","home_team":"IND","season":2026,"week":10,
        "published_at_utc":now.isoformat().replace("+00:00","Z"),
        "publication_status":STATUS,"model":"injury",
        "model_version":"qb_epa_margin_cap5_primary_source_mccord_replacement",
        "kickoff_utc":kickoff.isoformat().replace("+00:00","Z"),
        "projected_away":round(scores[0],6),
        "projected_home":round(scores[1],6),
        "projected_total":round(scores[2],6),
        "model_home_margin":round(scores[1]-scores[0],6),
        "away_qb_name":str(pred.away_qb_name),
        "home_qb_name":str(pred.home_qb_name),
        "away_qb_starter_source":str(pred.away_starter_source),
        "home_qb_starter_source":str(pred.home_starter_source),
        "qb_margin_adjustment":float(pred.qb_margin_adjustment),
        "new_qb_id":QB_ID,
        "new_qb_prior_dropbacks":float(q.qb_prior_dropbacks),
        "new_qb_confidence":str(q.confidence),
        "previous_published_at_utc":str(prior.published_at_utc),
        "previous_incorrect_qb":str(prior.away_qb_name),
        "previous_projected_away":float(prior.projected_away),
        "previous_projected_home":float(prior.projected_home),
        "previous_projected_total":float(prior.projected_total),
        "bovada_home_favored_spread":float(odds.home_favorite_spread),
        "bovada_total":float(odds.total_line),
        "bovada_away_spread_price":int(odds.away_spread_price),
        "bovada_home_spread_price":int(odds.home_spread_price),
        "bovada_over_price":int(odds.over_price),
        "bovada_under_price":int(odds.under_price),
        "bovada_snapshot_at_utc":str(odds.captured_at_utc),
        "source_url":"https://www.miamidolphins.com/news/game-preview-miami-dolphins-at-indianapolis-colts",
        "qb_identity_warning":"Confirmed first NFL start, zero prior regular-season NFL dropbacks; EPA-to-points magnitude unvalidated, do not treat ATS edge as calibrated EV.",
    }])
    manifest={
        "status":STATUS,"captured_at_utc":now.isoformat().replace("+00:00","Z"),
        "games":1,"model":"injury",
        "source_verified_for_miami":True,
        "qb_name":QB_NAME,"qb_gsis_id":QB_ID,
        "model_prior_dropbacks":float(q.qb_prior_dropbacks),
        "model_confidence":str(q.confidence),
        "original_26_row_sunday_snapshot":str(ORIGINAL.relative_to(ROOT)),
        "new_file":str(NEW.relative_to(ROOT)),
        "market":str(MARKET.relative_to(ROOT)),
        "all_candidate_QB_source_counts":details.starter_source.value_counts().to_dict(),
        "no_rewrite":"Original Sunday 26 rows, Sunday NE official inactive update, November12 initial board, and previous prospective Week8-9 are untouched.",
        "calibration_caution":"McCord has zero NFL regular-season QB EPA observations. The chosen shrinkage prior might over/understate his real replacement value; no betting recommendation until validated.",
    }
    NEW.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(NEW,index=False)
    META.write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"generated_at":manifest["captured_at_utc"],"model_prior_dropbacks":manifest["model_prior_dropbacks"],
                      "old_away":float(prior.projected_away),"old_home":float(prior.projected_home),
                      "new_away":scores[0],"new_home":scores[1],"new_total":scores[2],
                      "margin_shift":round((scores[1]-scores[0])-(float(prior.projected_home)-float(prior.projected_away)),2)
                     },indent=2))

if __name__=="__main__":
    main()
