#!/usr/bin/env python3
"""Chronological NFL ATS research: scaled efficiency and player-role injury inputs.

No public projections are changed. Every forecast is fitted using games dated
STRICTLY before its weekly evaluation block. Median imputation, active-feature
selection, and StandardScaler are learned from training games ONLY.

Variants:
  1. original unscaled 24-feature Baseline
  2. standardized Baseline (Ridge alpha 10 or 100)
  3. current NON-QB injury counts, unscaled / standardized
  4. standardized player-role injury inputs, with QB player index excluded
  5. standardized counts + player-role injury inputs, QB excluded.

Player-role value is PBP involvement through the prior week, NOT true WAR or
replacement-based point value. OL is tracked with an unvalued count.
Historical nflverse injury coverage is incomplete, and an "OUT" label is not
proof that all long-term IR absences were represented in that weekly report.
Separate QB-EPA adjustments are NOT fitted or evaluated in this experiment.

The historical game archive is fixed through 2026 Week 8; Week 9 and MNF
results are NEVER used to fit or judge these alternatives.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
from injury_model import load_injury_reports, add_injury_features
from player_injury_model import build_player_injury_features

OUT=ROOT/"data"/"week09_review"
REFERENCE=ROOT/"data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv"
PREDICTIONS=OUT/"standardized_player_role_injury_holdout_20261109.csv"
REPORT=OUT/"standardized_player_role_injury_holdout_20261109.json"
SUMMARY=OUT/"standardized_player_role_injury_holdout_20261109.md"
SEASONS=(2021,2022,2023,2024,2025,2026)
MIN_TRAIN=500
EDGE_THRESHOLD=3.5
EXCLUDE={"game_id","gameday","season","week","home_team","away_team","home_score","away_score","spread_line","total_line"}
EXPECTED={2022:45,2023:285,2024:285,2025:285,2026:121}
PROPOSED={
    "baseline_unscaled":("base",False,10.0),
    "baseline_std_alpha10":("base",True,10.0),
    "baseline_std_alpha100":("base",True,100.0),
    "nonqb_counts_unscaled":("counts",False,10.0),
    "nonqb_counts_std_alpha10":("counts",True,10.0),
    "nonqb_counts_std_alpha100":("counts",True,100.0),
    "nonqb_player_role_std_alpha10":("roles",True,10.0),
    "nonqb_counts_plus_roles_std_alpha10":("combined",True,10.0),
}


def feature_names(frame):
    return [c for c in frame.columns
            if c not in EXCLUDE and pd.api.types.is_numeric_dtype(frame[c])]


def load_inputs():
    print("Load validated schedule, PBP and historical injury feed",flush=True)
    schedule=load_schedule_data()
    pbp=load_pbp(SEASONS)
    injuries=load_injury_reports(SEASONS)

    print("Build frozen Baseline efficiency, non-QB injury count, and role usage features",flush=True)
    base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    baseline=feature_names(base)
    if len(baseline)!=24:raise ValueError(f"Expected 24 Baseline predictors, got {len(baseline)}")

    counts=add_injury_features(base,schedule,injuries,exclude_qb=True)
    extra_counts=[c for c in feature_names(counts) if c not in baseline]
    if not extra_counts:raise ValueError("No non-QB injury features were added")

    player_features,player_audit=build_player_injury_features(schedule,pbp,injuries)
    role_cols=[c for c in player_features.columns if c not in ("game_id","home_player_qb_absence_index","away_player_qb_absence_index")]
    if len(role_cols)!=8:raise ValueError(f"Unexpected non-QB role columns: {role_cols}")
    role_frame=base.merge(player_features[["game_id"]+role_cols],on="game_id",how="left",validate="one_to_one")
    combined=counts.merge(player_features[["game_id"]+role_cols],on="game_id",how="left",validate="one_to_one")

    variants={
        "base":(base,baseline),
        "counts":(counts,baseline+extra_counts),
        "roles":(role_frame,baseline+role_cols),
        "combined":(combined,baseline+extra_counts+role_cols),
    }
    if len(set(baseline))!=len(baseline):raise ValueError("Duplicate baseline feature names")
    for name,(frame,cols) in variants.items():
        if len(cols)!=len(set(cols)):raise ValueError(f"Duplicate columns in {name}")
        frame["gameday"]=pd.to_datetime(frame.gameday,errors="coerce")
        frames=frame[
            (frame.season.ge(2021)) & ((frame.season.le(2025)) |
                                      (frame.season.eq(2026)&frame.week.le(8)))
        ].copy()
        variants[name]=(frames,cols)

    if player_audit.empty:raise ValueError("No player role evidence was produced")
    return variants,{"baseline":len(baseline),"nonqb_counts":len(extra_counts),
                     "nonqb_roles":len(role_cols),
                     "role_audit_player_rows":int(len(player_audit))}


def fit_weekly(frame,cols,scaled,alpha,name):
    data=frame.dropna(subset=["gameday","home_score","away_score"]).copy()
    data=data.sort_values("gameday")
    data["fold"]=data.gameday.dt.to_period("W").astype(str)
    result=[]
    for idx,fold in enumerate(data.fold.drop_duplicates()):
        test=data.loc[data.fold.eq(fold)].copy()
        train=data.loc[data.gameday.lt(test.gameday.min())].copy()
        if len(train)<MIN_TRAIN:continue
        active=[c for c in cols if train[c].notna().any()]
        if not active:raise ValueError(f"No active features for {name}, {fold}")
        med=train[active].median(numeric_only=True).fillna(0)
        xtrain=train[active].fillna(med).fillna(0).to_numpy(dtype=float)
        xtest=test[active].fillna(med).fillna(0).to_numpy(dtype=float)
        if not np.isfinite(xtrain).all() or not np.isfinite(xtest).all():
            raise ValueError(f"Nonfinite research features {name}, {fold}")
        if scaled:
            scaler=StandardScaler().fit(xtrain) # TRAIN ONLY
            xtrain=scaler.transform(xtrain)
            xtest=scaler.transform(xtest)
        for target,output in (("home_score","pred_home"),("away_score","pred_away")):
            model=Ridge(alpha=alpha)
            model.fit(xtrain,train[target].to_numpy(dtype=float))
            test[output]=model.predict(xtest)
        if not np.isfinite(test[["pred_home","pred_away"]].to_numpy()).all():
            raise ValueError(f"Nonfinite predictions in {name} fold {fold}")
        test["research_variant"]=name
        test["training_games"]=len(train)
        result.append(test[["game_id","gameday","season","week","home_team","away_team",
                            "home_score","away_score","pred_home","pred_away",
                            "training_games","research_variant"]])
    if not result:raise ValueError(f"No predictions for {name}")
    out=pd.concat(result,ignore_index=True)
    if out.game_id.duplicated().any():raise ValueError(f"Duplicate games for {name}")
    return out


def metrics(rows):
    line=rows.spread_line.to_numpy(dtype=float)
    actual_home=rows.home_score.to_numpy(dtype=float)
    actual_away=rows.away_score.to_numpy(dtype=float)
    home=rows.pred_home.to_numpy(dtype=float)
    away=rows.pred_away.to_numpy(dtype=float)
    margin=home-away
    real_margin=actual_home-actual_away
    totals=home+away
    actual_total=actual_home+actual_away
    edge=margin-line
    actual_ats=real_margin-line
    outcome=np.where(np.isclose(actual_ats,0),"P",
                     np.where(edge*actual_ats>0,"W","L"))
    no_lean=np.isclose(edge,0)
    outcome[no_lean]="N"
    def bet_record(mask):
        o=outcome[mask]
        w=int((o=="W").sum());l=int((o=="L").sum());p=int((o=="P").sum())
        n=int(mask.sum());q=int((o=="N").sum())
        if w+l+p+q!=n:raise ValueError("ATS grades don't reconcile")
        profit=w*(100/110)-l
        return {"bets":w+l+p,"wins":w,"losses":l,"pushes":p,
                "no_lean":q,
                "win_pct":round(100*w/(w+l),2) if w+l else None,
                "net_units_flat_minus110":round(profit,3),
                "roi_pct_flat_minus110":round(100*profit/(w+l+p),3) if w+l+p else None}
    return {
        "games":int(len(rows)),
        "ATS_all_games":bet_record(np.ones(len(rows),dtype=bool)),
        "ATS_min_edge_3_5":bet_record(np.abs(edge)>=EDGE_THRESHOLD),
        "margin_mae":round(float(np.abs(margin-real_margin).mean()),3),
        "total_mae":round(float(np.abs(totals-actual_total).mean()),3),
        "market_margin_mae":round(float(np.abs(line-real_margin).mean()),3),
        "avg_abs_predicted_margin":round(float(np.abs(margin).mean()),3),
        "avg_abs_market_spread":round(float(np.abs(line).mean()),3),
        "count_ats_favorite_leans":int(((line*edge)>0).sum()),
        "count_ats_underdog_leans":int(((line*edge)<0).sum()),
    }


def main():
    variants,feature_counts=load_inputs()
    print("Fit calendar-week chronological candidates (training-only StandardScaler)",flush=True)
    predictions=[]
    for name,(group,scaled,alpha) in PROPOSED.items():
        frame,cols=variants[group]
        print(f"  {name}: {len(cols)} features, alpha={alpha}",flush=True)
        predictions.append(fit_weekly(frame,cols,scaled,alpha,name))
    full=pd.concat(predictions,ignore_index=True)
    # Force IDENTICAL game intersection and nflverse historical closing lines.
    reference=pd.read_csv(REFERENCE,low_memory=False)
    ref=reference[reference.model.eq("baseline")]
    if len(ref)!=1021 or ref.game_id.duplicated().any():
        raise ValueError("Historic reference game set changed")
    refcols=ref[["game_id","spread_line","total_line"]].copy()
    all_ids=set(ref.game_id)
    for name in PROPOSED:
        subset=full[full.research_variant.eq(name)]
        if set(subset.game_id)!=all_ids:
            raise ValueError(f"Comparison games differ for {name}: missing={len(all_ids-set(subset.game_id))}; extra={len(set(subset.game_id)-all_ids)}")
    full=full.merge(refcols,on="game_id",how="left",validate="many_to_one")
    if full[["spread_line","home_score","away_score"]].isna().any().any():
        raise ValueError("Missing archived scores / lines")
    if full.duplicated(["game_id","research_variant"]).any():
        raise ValueError("Duplicate game-variant predictions")

    summary={}
    for name in PROPOSED:
        variant=full[full.research_variant.eq(name)]
        summary[name]={str(year):metrics(subset) for year,subset in variant.groupby("season")}
        summary[name]["2025_and_2026_w1_8_holdouts"]=metrics(variant[variant.season.ge(2025)])
    # Exact baseline reference reproduction: numerically compare frozen predictions.
    old=ref.set_index("game_id")
    test=full[full.research_variant.eq("baseline_unscaled")].set_index("game_id")
    diff=max(float(np.abs(test.pred_home-old.pred_home).max()),
             float(np.abs(test.pred_away-old.pred_away).max()))
    if diff>1e-4:raise ValueError(f"Regression inconsistency: baseline differs from saved research archive by {diff}")
    report={
        "status":"RESEARCH_ONLY_NO_PUBLIC_WEEK_9_OR_WEEK_10_CHANGES",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "source":"Validated nflverse historical schedules/PBP/injuries with original project feature builders",
        "historic_reference":str(REFERENCE.relative_to(ROOT)),
        "strict_walk_forward":"Calendar week; prior games only; medians and scaling from previous games exclusively",
        "research_models":PROPOSED,
        "feature_counts":feature_counts,
        "ridge_alpha_caveat":"Standardizing changes effective regularization; alpha 10 and 100 prespecified exploratory variants, not chosen after heldout results",
        "2021_training_only":True,
        "historical_folds":EXPECTED,
        "baseline_reproduction_max_abs_score_difference":diff,
        "result_summary":summary,
        "data_limitations":[
            "Historical injury player roles are based on prior-week play-by-play involvement, not independent replacement-level WAR.",
            "Individual offensive-line involvement is unavailable; count proxies only.",
            "QB absences are excluded from all new injury features to avoid double counting separately modeled QB EPA.",
            "The production QB-EPA margin adjustment is not reproduced here. These are non-QB feature component comparisons.",
            "Weekly injury feed misses some year-long IR absences; report coverage and prior-season usage vary.",
            "2025 and 2026 were examined by previous experiments. They are chronological historical tests, not pristine blind holdouts.",
            "All prices are nflverse historical closing spreads, not verified Bovada pregame executable quotes.",
            "Multiple experiments after a bad 2026 Week 9 may select noise. Week 10 prospective freeze remains required.",
        ],
        "no_public_change":True,
    }
    OUT.mkdir(parents=True,exist_ok=True)
    full.sort_values(["season","week","game_id","research_variant"]).to_csv(PREDICTIONS,index=False)
    REPORT.write_text(json.dumps(report,indent=2,default=str)+"\n")
    lines=[
        "# Historical standardized efficiency and player-role injury comparison",
        "",
        "**Research only.** The public Week 9 model, totals model, official ledger, and Week 10 projections were not modified.",
        "Identical 1,021 historical games. 2022 W16 start; 2023-2025 full seasons; 2026 weeks 1-8 only.",
        "",
        "## Chronological 2025 evaluation",
        "",
        "| Variant | ATS W-L-P | ATS ≥3.5 pts W-L-P | Margin MAE | Total MAE |",
        "|---|---:|---:|---:|---:|",
    ]
    def wlp(v):
        return f"{v['wins']}–{v['losses']}–{v['pushes']}"
    for name in PROPOSED:
        v=summary[name]["2025"]
        lines.append(f"| {name} | {wlp(v['ATS_all_games'])} | {wlp(v['ATS_min_edge_3_5'])} | {v['margin_mae']:.2f} | {v['total_mae']:.2f} |")
    lines+=["","## 2026 weeks 1-8 evaluation","",
             "| Variant | ATS W-L-P | ATS ≥3.5 pts W-L-P | Margin MAE | Total MAE |",
             "|---|---:|---:|---:|---:|"]
    for name in PROPOSED:
        v=summary[name]["2026"]
        lines.append(f"| {name} | {wlp(v['ATS_all_games'])} | {wlp(v['ATS_min_edge_3_5'])} | {v['margin_mae']:.2f} | {v['total_mae']:.2f} |")
    lines+=["","## How to read this","",
            "- Compare 2025 and 2026 W1–8 separately. Do not choose the largest in-sample ATS count.",
            "- A good model needs lower margin MAE and stable directional accuracy, not just 3-point-edge hits.",
            "- Role input uses prior PBP participation shares and cannot price OL or long-term IR accurately.",
            "- This ablation excludes the production QB-EPA overlay, which needs its own separately audited replacement-based test.",
            "- If improvement is weak or inconsistent, leave the production scores unchanged.",
            ""]
    SUMMARY.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":report["status"],"feature_counts":feature_counts,
                      "baseline_reproduction_diff":diff,
                      "2025":{k:v["2025"] for k,v in summary.items()},
                      "2026":{k:v["2026"] for k,v in summary.items()},
                      "outputs":[str(p.relative_to(ROOT)) for p in [PREDICTIONS,REPORT,SUMMARY]]},indent=2),flush=True)


if __name__=="__main__":
    main()
