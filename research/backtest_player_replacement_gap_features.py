#!/usr/bin/env python3
"""Research only: does player-specific, prior-only performance *relative to peers*
add predictive value to NFL non-QB injury counts?

Longitudinal prior-week player values were already audited and saved by
research/build_longitudinal_player_value_audit.py. Value gap compares injured
player's prior production to a same-team positional historical peer benchmark
(NOT a confirmed active backup). Value units are heterogeneous by position.
Use per-group signals; never sum raw gap units across RB/WR/TE/DEF.
Target-week practice/injury designations are selected strictly before kickoff
from the historical NFL injury feed (not by target-game player statistics).
Quarterbacks are explicitly excluded. Offensive-line value is unavailable.
All preprocessing and Ridge training use only prior games in each weekly fold.

2026 Week 9 is fully excluded from evaluation and training. No live releases,
frozen scores, records, or totals models are altered.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import json,sys
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
from injury_model import load_injury_reports, add_injury_features, _normalize_reports, _kickoff_utc
from research.standardized_player_injury_holdout import fit_weekly,metrics,feature_names

OUT=ROOT/"data/week09_review"
SOURCE=ROOT/"data/player_injury_backtests/longitudinal_player_value_audit_20261109T173724Z.csv"
HISTORY=ROOT/"data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv"
MANIFEST=OUT/"player_replacement_gap_holdout_20261109.json"
PREDICTIONS=OUT/"player_replacement_gap_holdout_20261109.csv"
FINDINGS=OUT/"player_replacement_gap_holdout_20261109.md"
SEASONS=(2021,2022,2023,2024,2025,2026)
GROUPS=("RB","WR","TE","DEF")
STATUS_WEIGHTS={"OUT":1.0,"DOUBTFUL":0.8,"QUESTIONABLE":0.4}
EXPECTED={2022:45,2023:285,2024:285,2025:285,2026:121}
VARIANTS={
    "baseline_unscaled":("base",False,10.0),
    "nonqb_counts_unscaled":("counts",False,10.0),
    "nonqb_counts_std":("counts",True,10.0),
    "player_signed_gap_std":("signed",True,10.0),
    "player_positive_gap_std":("positive",True,10.0),
    "counts_plus_positive_gap_std":("combined",True,10.0),
}

def norm_team(t):
    t=str(t).strip().upper()
    return "LA" if t=="LAR" else t

def game_type(x):
    t=str(x).strip().upper()
    return "POST" if t in {"WC","WILDCARD","DIV","CON","CONF","SB","POSTSEASON"} else "REG" if t in {"REGULAR","REG",""} else t

def prepare_values():
    val=pd.read_csv(SOURCE,dtype={"player_id":"string","team":"string"},low_memory=False)
    required={"season","week","team","player_id","position_group","value_gap",
              "historical_games","valuation_status"}
    if not required.issubset(val.columns):
        raise ValueError(f"Source longitudinal player value audit missing {required-set(val.columns)}")
    val=val.copy()
    val["team"]=val.team.map(norm_team)
    val["player_id"]=val.player_id.astype(str).str.strip()
    val["season"]=pd.to_numeric(val.season,errors="raise").astype(int)
    val["week"]=pd.to_numeric(val.week,errors="raise").astype(int)
    val["position_group"]=val.position_group.fillna("").astype(str).str.upper()
    val=val[val.position_group.isin(GROUPS)].copy()
    if val.duplicated(["season","week","team","player_id"]).any():
        raise ValueError("Ambiguous longitudinal player rows")
    val["value_gap"]=pd.to_numeric(val.value_gap,errors="coerce")
    # Bounded research feature avoids few-play single-week outliers from
    # overwhelming score regression. These are NOT manually assigned points.
    val["signed_replacement_gap"]=val.value_gap.clip(-2.0,2.0)
    val["positive_replacement_gap"]=val.value_gap.clip(lower=0.,upper=2.)
    return val

def build_game_values(schedule,reports,values):
    reps=_normalize_reports(reports)
    reps["team"]=reps.team.map(norm_team)
    reps["gsis_id"]=reps.gsis_id.astype("string").str.strip()
    reps["date_modified"]=pd.to_datetime(reps.date_modified,utc=True,errors="coerce")
    reps["season_type"]=reps.season_type.map(game_type)
    val_lookup=values.set_index(["season","week","team","player_id"])
    all_rows=[]
    matched_total=0; missing_total=0; outs_total=0
    # Minimize duplicated weekly filtering by pre-grouping season/week/type.
    by_week={key:d for key,d in reps.groupby(["season","week","season_type"],dropna=False)}
    for _,g in schedule.sort_values("gameday").iterrows():
        year=int(g.season);week=int(g.week)
        typ=game_type(g.get("game_type",g.get("season_type","REG")))
        subset=by_week.get((year,week,typ))
        if subset is None:subset=reps.iloc[0:0]
        cutoff=_kickoff_utc(g)
        if pd.isna(cutoff):raise ValueError("Missing game kickoff: "+str(g.game_id))
        reports_prior=subset[subset.date_modified.notna()&subset.date_modified.lt(cutoff)]
        if not reports_prior.empty:
            reports_prior=reports_prior.sort_values("date_modified").drop_duplicates(
                ["team","gsis_id"],keep="last")
        record={"game_id":g.game_id}
        for side in ("home","away"):
            team=norm_team(g[f"{side}_team"])
            team_rows=reports_prior[reports_prior.team.eq(team)]
            record[f"{side}_replacement_report_available"]=int(not team_rows.empty)
            for group in GROUPS:
                record[f"{side}_{group.lower()}_signed_replacement_gap"]=0.0
                record[f"{side}_{group.lower()}_positive_replacement_gap"]=0.0
                record[f"{side}_{group.lower()}_unvalued_out_count"]=0.0
            for player in team_rows.itertuples(index=False):
                pos=str(player.position).upper()
                if pos=="QB":continue
                status=str(player.report_status).upper().strip()
                w=STATUS_WEIGHTS.get(status,0)
                if not w:continue
                if status=="OUT":outs_total+=1
                pid=str(player.gsis_id).strip()
                key=(year,week,team,pid)
                if key not in val_lookup.index:
                    missing_total+=1
                    # No missing player's true value is assigned a zero score.
                    # Unknown remains covered by raw injury-count features.
                    continue
                obs=val_lookup.loc[key]
                if isinstance(obs,pd.DataFrame):raise ValueError("Duplicate value lookup row")
                group=str(obs.position_group)
                if group not in GROUPS:continue
                if pd.isna(obs.signed_replacement_gap):
                    missing_total+=1
                    if status=="OUT":
                        record[f"{side}_{group.lower()}_unvalued_out_count"]+=1
                    continue
                matched_total+=1
                record[f"{side}_{group.lower()}_signed_replacement_gap"]+=w*float(obs.signed_replacement_gap)
                record[f"{side}_{group.lower()}_positive_replacement_gap"]+=w*float(obs.positive_replacement_gap)
        all_rows.append(record)
    features=pd.DataFrame(all_rows)
    if features.game_id.duplicated().any():raise ValueError("Repeated game")
    return features,{"valued_absence_rows":matched_total,"unvalued_absence_rows":missing_total,
                     "status_out_rows_nonqb":outs_total,
                     "game_rows":len(features)}

def main():
    print("Load historic schedule, reports, pregame PBP and prior-only player-value audit",flush=True)
    schedule=load_schedule_data()
    schedule=schedule[(schedule.season.between(2021,2025))|
                      ((schedule.season==2026)&(schedule.week<=8))].copy()
    pbp=load_pbp(SEASONS)
    reports=load_injury_reports(SEASONS)
    vals=prepare_values()
    print("Build point-in-time player replacement gap features (non-QB only)",flush=True)
    gap,coverage=build_game_values(schedule,reports,vals)
    base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    basenames=feature_names(base)
    if len(basenames)!=24:raise ValueError("Expected 24 original Baseline features")
    counts=add_injury_features(base,schedule,reports,exclude_qb=True)
    countnames=[c for c in feature_names(counts) if c not in basenames]
    if not countnames:raise ValueError("NonQB injury counts unavailable")
    gapnames={
        "signed":[c for c in gap.columns if c.endswith(("_signed_replacement_gap","_unvalued_out_count","_replacement_report_available"))],
        "positive":[c for c in gap.columns if c.endswith(("_positive_replacement_gap","_unvalued_out_count","_replacement_report_available"))],
    }
    if len(gapnames["signed"])!=18 or len(gapnames["positive"])!=18:
        raise ValueError(f"Expected 18 distinct player-role columns, got {gapnames}")
    g_base=base.merge(gap,on="game_id",validate="one_to_one")
    g_count=counts.merge(gap,on="game_id",validate="one_to_one")
    variants={
        "base":(base,basenames),
        "counts":(counts,basenames+countnames),
        "signed":(g_base,basenames+gapnames["signed"]),
        "positive":(g_base,basenames+gapnames["positive"]),
        "combined":(g_count,basenames+countnames+gapnames["positive"]),
    }
    forecasts=[]
    for label,(group,standardized,alpha) in VARIANTS.items():
        d,cols=variants[group]
        print(f"Fit {label}: {len(cols)} predictors",flush=True)
        forecasts.append(fit_weekly(d,cols,standardized,alpha,label))
    merged=pd.concat(forecasts,ignore_index=True)
    ref=pd.read_csv(HISTORY,low_memory=False)
    ref=ref[ref.model.eq("baseline")]
    ids=set(ref.game_id)
    if len(ids)!=1021:raise ValueError("Historical research cohort changed")
    for label in VARIANTS:
        sub=merged[merged.research_variant.eq(label)]
        if set(sub.game_id)!=ids or sub.game_id.duplicated().any():
            raise ValueError(f"Unequal game cohort {label}")
    original=merged[merged.research_variant.eq("baseline_unscaled")].set_index("game_id")
    prior=ref.set_index("game_id")
    err=max(float(np.abs(original.pred_home-prior.pred_home).max()),
            float(np.abs(original.pred_away-prior.pred_away).max()))
    if err>1e-4:raise ValueError(f"Baseline doesn't reproduce archive: {err}")
    merged=merged.merge(ref[["game_id","spread_line","total_line"]],on="game_id",validate="many_to_one")
    out={}
    for label in VARIANTS:
        d=merged[merged.research_variant.eq(label)]
        summary={str(int(y)):metrics(group) for y,group in d.groupby("season")}
        if {int(y) for y in summary}!=set(EXPECTED):raise ValueError("Missing cohort season")
        for year,c in EXPECTED.items():
            if summary[str(year)]["games"]!=c:raise ValueError("Wrong year count")
        out[label]=summary

    report={
        "status":"RESEARCH_ONLY_NONQB_PLAYER_GAP_HOLDOUT",
        "date_utc":datetime.now(timezone.utc).isoformat(),
        "scope":"2021 train; 2022 late-season through 2026 Week8 walk forward, 1021 common games",
        "public_model_unchanged":True,
        "no_2026_week09_results":True,
        "QB_excluded_from_nonQB_gap_features":True,
        "prior_value_file":str(SOURCE.relative_to(ROOT)),
        "comparison_reference":str(HISTORY.relative_to(ROOT)),
        "baseline_reproduction_diff":err,
        "features":{"baseline":len(basenames),"nonqb_injury_counts":len(countnames),
                    "replacement_gap_signed":len(gapnames["signed"]),
                    "replacement_gap_positive":len(gapnames["positive"])},
        "injury_coverage":coverage,
        "absent_status_weights":STATUS_WEIGHTS,
        "predictors":VARIANTS,
        "season_results":out,
        "known_limitations":[
            "Longitudinal historical player value gap is NOT an independently measured WAR or point value.",
            "Comparison peer is best other previously observed same-team positional player, NOT a verified available backup.",
            "OL and QB value gaps are NOT included; OL counts are in nonQB count comparator, QB must be a separate model.",
            "Injury source is latest known pre-kickoff designation; player value is strictly prior season/week.",
            "Heterogeneous positions are separated and outlier gaps clipped at +/-2 feature units, not points.",
            "League data feed misses long-term injured reserve players omitted from weekly reports.",
            "Historical 2025 and 2026 folds have already been used in model-design discussions; not untouched blind validation.",
            "No market opening/closing movement in model inputs; grades use nflverse archived spreads not Bovada transaction prices.",
            "Only research files were added; public official projections and ledger remain unchanged.",
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    merged.sort_values(["season","week","game_id","research_variant"]).to_csv(PREDICTIONS,index=False)
    MANIFEST.write_text(json.dumps(report,indent=2)+"\n")
    lines=[
        "# Player-specific non-QB injury replacement-gap features: chronological test",
        "",
        "Experimental performance/participation proxies, **not calibrated individual player point values**.",
        "The peer benchmark is not a confirmed active replacement.",
        f"Valued report absences: {coverage['valued_absence_rows']}; unvalued report absences: {coverage['unvalued_absence_rows']}.",
        "",
        "| Candidate | 2025 ATS | 2025 ATS >=3.5 | 2025 margin MAE | 2026 W1–8 ATS | 2026 ATS >=3.5 | 2026 margin MAE |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    def record(d,k):
        t=d[k];return f"{t['wins']}–{t['losses']}–{t['pushes']}"
    for label,yrs in out.items():
        a=yrs["2025"];b=yrs["2026"]
        lines.append(f"| {label} | {record(a,'ATS_all_games')} | {record(a,'ATS_min_edge_3_5')} | {a['margin_mae']:.2f} | {record(b,'ATS_all_games')} | {record(b,'ATS_min_edge_3_5')} | {b['margin_mae']:.2f} |")
    lines.extend(["","## Promotion gate","",
        "No change to the public model unless improvements replicate across years and real future frozen games.",
        "Next requirement: verify active next-man-up depth and estimate performance *above actual replacement*.",
        ""])
    FINDINGS.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":report["status"],"coverage":coverage,
        "2025":{k:v["2025"] for k,v in out.items()},
        "2026":{k:v["2026"] for k,v in out.items()}},indent=2),flush=True)

if __name__=="__main__":
    main()
