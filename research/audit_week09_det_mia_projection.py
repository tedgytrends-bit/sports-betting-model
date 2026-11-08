#!/usr/bin/env python3
"""Point-in-time sensitivity audit of Detroit @ Miami Week 9 score.

Research ONLY: never overwrites an official published model snapshot. Rebuild
the identical non-QB injury Ridge estimator and examine what happens when the
five officially OUT Detroit players' *status flags* are hypothetically removed.
Their remaining practice statuses are preserved. The counterfactual is
diagnostic, not a recommendation to ignore their actual injuries.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
from injury_model import load_injury_reports, add_injury_features, _counts_for_team

GAME="2026_09_DET_MIA"
SNAP=ROOT/"data/injury_snapshots/injuries_2026_week_09_20261108T011942Z.csv"
FINAL=ROOT/"data/public_snapshots/nfl_week09_final_injury_2026-11-08.csv"
OUT=ROOT/"data/qb_epa_shadow/det_mia_injury_sensitivity_20261108.json"

def main():
    schedule=load_schedule_data()
    pbp=load_pbp((2021,2022,2023,2024,2025,2026))
    reports=load_injury_reports((2021,2022,2023,2024,2025,2026))
    base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    nonqb=add_injury_features(base,schedule,reports,exclude_qb=True)
    col_drop={"game_id","gameday","season","week","home_team","away_team","home_score","away_score"}
    completed=nonqb.dropna(subset=["home_score","away_score","gameday"]).copy()
    active=[c for c in nonqb.columns if c not in col_drop and pd.api.types.is_numeric_dtype(nonqb[c]) and completed[c].notna().any()]
    med=completed[active].median(numeric_only=True).fillna(0)
    xt=completed[active].fillna(med).fillna(0)
    cur=nonqb.loc[nonqb.game_id.eq(GAME)].copy()
    if len(cur)!=1:raise ValueError(f"Missing unique game {GAME}")
    snap=pd.read_csv(SNAP)
    d=snap[snap.team.eq("DET")].copy()
    if d.empty:raise ValueError("No DET snapshot rows")
    outs=d[d.report_status.fillna("").str.strip().str.upper().eq("OUT")].copy()
    if len(outs)!=5:raise ValueError(f"Expected 5 DET OUT players, got {len(outs)}")
    orig_counts=_counts_for_team(d,exclude_qb=True)
    if any(abs(float(cur.iloc[0]["away_"+k])-v)>1e-8 for k,v in orig_counts.items() if np.isfinite(v)):
        raise ValueError("Saved injury snapshot features differ from latest prediction inputs")
    no_out=d.copy()
    no_out.loc[no_out.report_status.fillna("").str.strip().str.upper().eq("OUT"),"report_status"]=""
    clean_counts=_counts_for_team(no_out,exclude_qb=True)
    hypothetical=cur.copy()
    for k,v in clean_counts.items():hypothetical["away_"+k]=v
    # Independent baseline uses same currently available games/features but NO injury flags.
    base_completed=base.dropna(subset=["home_score","away_score","gameday"]).copy()
    base_cols=[c for c in base.columns if c not in col_drop and pd.api.types.is_numeric_dtype(base[c]) and base_completed[c].notna().any()]
    base_med=base_completed[base_cols].median(numeric_only=True).fillna(0)
    base_game=base.loc[base.game_id.eq(GAME)]
    outputs={}
    def fit_predict(cols,training,medians,real,alt=None):
        x=training[cols].fillna(medians).fillna(0)
        preds={}
        for target in ["home_score","away_score"]:
            model=Ridge(alpha=10.0).fit(x,training[target])
            preds[target]={
                "actual":float(model.predict(real[cols].fillna(medians).fillna(0))[0]),
                "hypothetical":float(model.predict(alt[cols].fillna(medians).fillna(0))[0]) if alt is not None else None,
            }
        return preds
    outputs["injury_nonqb"]=fit_predict(active,completed,med,cur,hypothetical)
    outputs["baseline_current"]=fit_predict(base_cols,base_completed,base_med,base_game)
    final=pd.read_csv(FINAL).loc[lambda x:x.game_id.eq(GAME)]
    expected_margin=float(final.iloc[0].projected_home)-float(final.iloc[0].projected_away)
    predicted=outputs["injury_nonqb"]
    h=predicted["home_score"]["actual"];a=predicted["away_score"]["actual"]
    if abs(h-float(final.iloc[0].original_non_qb_home))>.02 or abs(a-float(final.iloc[0].original_non_qb_away))>.02:
        raise ValueError(f"Could not reproduce official model non-QB component: {h:.4f}, {a:.4f}")
    counter_home=predicted["home_score"]["hypothetical"]
    counter_away=predicted["away_score"]["hypothetical"]
    report={
        "status":"RESEARCH_ONLY_DO_NOT_CHANGE_FROZEN",
        "as_of_utc":datetime.now(timezone.utc).isoformat(),
        "game_id":GAME,
        "published_final_away_det":float(final.iloc[0].projected_away),
        "published_final_home_mia":float(final.iloc[0].projected_home),
        "published_final_margin_mia":expected_margin,
        "published_incremental_qb_shift_mia":float(final.iloc[0].qb_margin_adjustment),
        "reproduced_nonqb_mia":h,
        "reproduced_nonqb_det":a,
        "reproduced_nonqb_margin_mia":h-a,
        "hypothetical_remove_det_out_flags_mia":counter_home,
        "hypothetical_remove_det_out_flags_det":counter_away,
        "hypothetical_remove_det_out_flags_margin_mia":counter_home-counter_away,
        "effect_of_five_det_out_designations_on_mia_margin":(h-a)-(counter_home-counter_away),
        "baseline_no_injury_mia":outputs["baseline_current"]["home_score"]["actual"],
        "baseline_no_injury_det":outputs["baseline_current"]["away_score"]["actual"],
        "baseline_no_injury_margin_mia":outputs["baseline_current"]["home_score"]["actual"]-outputs["baseline_current"]["away_score"]["actual"],
        "det_out_players":[{"name":r.full_name,"position":r.position} for r in outs.itertuples()],
        "latest_det_counts":orig_counts,
        "det_counts_after_hypothetical":clean_counts,
        "warning":"Removing real OUT flags is NOT a realistic game projection; it only isolates feature sensitivity. This is a post-hoc check.",
        "note":"No score/record/file on public website was updated.",
        "model_limit":"Ridge alpha 10 is fitted on unstandardized numeric features, so low-magnitude EPA and higher-magnitude count features are not on equal scales.",
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,default=str)+"\n")
    print(json.dumps(report,indent=2,default=str),flush=True)

if __name__=="__main__":main()
