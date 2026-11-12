#!/usr/bin/env python3
"""Research-only Week 10 QB identity correction, preserving the initial public board.

Two exact, source-backed player changes:
  Arizona: Minshew (IR) -> Carson Beck (rookie; zero prior NFL dropbacks).
  Seattle: Darnold (OUT) -> Drew Lock (coach expected).
Both team-source attestations have real reviewed UTC timestamps. All other 12
Sunday/Thursday/Monday games retain the original version. Market lines are
not reissued, and 2026 Week 8/9 history never changes.
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
from scripts.capture_qb_aware_injury import SEASONS,load_coach_expected_starters,reject_known_inactive_qb
from research.validate_qb_starter_confirmations import validate_starter_confirmations

PUB=ROOT/"data"/"public_snapshots"
BASE=PUB/"nfl_week10_initial_projections_2026-11-12.csv"
OUT=PUB/"nfl_week10_qb_corrected_2026-11-12.csv"
META=PUB/"nfl_week10_qb_corrected_2026-11-12_manifest.json"
VERIFIED=ROOT/"data"/"qb_starters"/"2026_week10_confirmed.csv"
WATCH=ROOT/"data"/"qb_starters"/"2026_week10_watchlist.csv"
TARGETS={
    "2026_10_LA_ARI":("ARI","Carson Beck","00-0041561"),
    "2026_10_SEA_LV":("SEA","Drew Lock","00-0035704"),
}

def main():
    if OUT.exists() or META.exists():
        raise FileExistsError("Already recorded; never rewrite a pregame correction")
    now=datetime.now(timezone.utc).replace(microsecond=0)
    if not BASE.exists() or not VERIFIED.exists() or not WATCH.exists():
        raise FileNotFoundError("Missing immutable base or QB provenance")
    original=pd.read_csv(BASE)
    if len(original)!=28 or original.game_id.nunique()!=14:
        raise ValueError("Initial published board does not include all 14 games")
    initial=original.loc[original.model.eq("injury")].set_index("game_id")
    schedule=load_schedule_data()
    sources=pd.read_csv(VERIFIED,dtype=str,keep_default_na=False)
    if len(sources)!=2 or set(sources.game_id)!=set(TARGETS):
        raise ValueError("Confirmed QB file must contain ONLY two reviewed corrections")
    overrides,audit=validate_starter_confirmations(
        schedule,sources,checked_as_of_utc=now
    )
    if len(overrides)!=2 or not audit.override_eligible.all():
        raise ValueError("Refuse to promote source-unsafe QB correction: "+audit.to_json(orient="records"))
    pbp=load_pbp(SEASONS)
    injuries=load_injury_reports(SEASONS)
    expected=load_coach_expected_starters(schedule,2026,10)
    new,board=project_qb_aware_injury(
        schedule,pbp,injuries,season=2026,week=10,
        verified_starters=overrides,expected_starters=expected
    )
    reject_known_inactive_qb(board,pd.read_csv(WATCH,dtype=str,keep_default_na=False))
    assert len(new)==14 and len(board)==28
    selected=new.loc[new.game_id.isin(TARGETS)].copy()
    if len(selected)!=2:
        raise ValueError("Missing required revised matchups")
    rows=[]
    for row in selected.to_dict("records"):
        gid=row["game_id"]
        team,name,gsis=TARGETS[gid]
        home,away=str(row["home_team"]),str(row["away_team"])
        side="home" if home==team else "away" if away==team else ""
        if not side:
            raise ValueError("Unexpected side for corrected QB "+gid)
        selected_qb=board.loc[board.game_id.eq(gid)&board.team.eq(team)]
        if len(selected_qb)!=1 or selected_qb.iloc[0].qb_name!=name or selected_qb.iloc[0].qb_id!=gsis or selected_qb.iloc[0].starter_source!="verified_pregame":
            raise ValueError("Corrected QB starter identity not exactly source-verified: "+gid)
        old=initial.loc[gid]
        if gid=="2026_10_LA_ARI" and str(old.home_qb_name).strip()!="Gardner Minshew":
            raise ValueError("Initial Cardinals QB identity changed retroactively")
        if gid=="2026_10_SEA_LV" and str(old.away_qb_name).strip()!="Sam Darnold":
            raise ValueError("Initial Seahawks QB identity changed retroactively")
        cutoff=_kickoff_utc(schedule.loc[schedule.game_id.eq(gid)].iloc[0])
        if pd.isna(cutoff) or cutoff<=pd.Timestamp(now):
            raise ValueError("Cannot issue correction after target game kickoff")
        new_home=float(row["projected_home"]);new_away=float(row["projected_away"])
        total=float(row["projected_total"])
        if not all(np.isfinite(v) for v in (new_home,new_away,total)) or abs(new_home+new_away-total)>.02:
            raise ValueError("Invalid revised scores "+gid)
        rows.append({
            "game_id":gid,"season":2026,"week":10,"away_team":away,"home_team":home,
            "published_at_utc":now.isoformat().replace("+00:00","Z"),
            "publication_status":"QB_CORRECTED_PREGAME_RESEARCH_UPDATE_NOT_FINAL",
            "kickoff_utc":cutoff.isoformat().replace("+00:00","Z"),
            "model":"injury","model_version":"qb_epa_margin_cap5_v1_source_corrected",
            "projected_away":round(new_away,6),
            "projected_home":round(new_home,6),
            "projected_total":round(total,6),
            "model_home_margin":round(new_home-new_away,6),
            "home_injury_report_available":row.get("home_injury_report_available",""),
            "away_injury_report_available":row.get("away_injury_report_available",""),
            "home_qb_name":row.get("home_qb_name",""),
            "away_qb_name":row.get("away_qb_name",""),
            "home_qb_starter_source":row.get("home_starter_source",""),
            "away_qb_starter_source":row.get("away_starter_source",""),
            "qb_margin_adjustment":row.get("qb_margin_adjustment",""),
            "qb_change_team":team,"qb_change_name":name,
            "qb_confidence":str(selected_qb.iloc[0].confidence),
            "qb_prior_dropbacks":float(selected_qb.iloc[0].qb_prior_dropbacks),
            "initial_published_at_utc":str(old.published_at_utc),
            "initial_projected_away":float(old.projected_away),
            "initial_projected_home":float(old.projected_home),
            "initial_projected_total":float(old.projected_total),
            "source_url":str(selected_qb.iloc[0].source_url),
        })
    out=pd.DataFrame(rows)
    meta={
        "status":"QB_CORRECTED_PREGAME_RESEARCH_UPDATE_NOT_FINAL",
        "captured_at_utc":now.isoformat().replace("+00:00","Z"),
        "games_updated":len(out),
        "initial_frozen_file":str(BASE.relative_to(ROOT)),
        "correction_file":str(OUT.relative_to(ROOT)),
        "corrected_QBs":out[["game_id","qb_change_team","qb_change_name","qb_prior_dropbacks","qb_confidence"]].to_dict("records"),
        "market_snapshot_unchanged":"data/public_snapshots/nfl_week10_bovada_initial_2026-11-12.csv",
        "starter_source_gate":"Reviewed primary team reports for named Week 10 matchup, publication and review prior to kickoff. Updated game can still change by gameday.",
        "invariant":"The initial 28-row published first pregame model record is immutable. These two Sunday candidate updates cannot rewrite it.",
        "rookie_note":"Carson Beck has no prior NFL regular-season dropbacks. The 2026 historical EPA QB magnitude has NOT been validated for a rookie; treat model margin as a research sensitivity, not a calibrated value.",
    }
    PUB.mkdir(parents=True,exist_ok=True)
    out.to_csv(OUT,index=False)
    META.write_text(json.dumps(meta,indent=2,allow_nan=False)+"\n")
    print(json.dumps(meta,indent=2))
    print(out[["game_id","projected_away","projected_home","projected_total","home_qb_name","away_qb_name"]].to_string(index=False))

if __name__=="__main__":
    main()
