#!/usr/bin/env python3
"""True pregame-information QB replacement shadow backtest, 2025 + 2026 W1–8.

Historical team score model trained chronologically, excluding ALL QB injury
counts. QB identities inferred ONLY from prior completed games, never target
game starter metadata, final stats or postgame first pass. Compare no-QB delta
vs production margin-only QB adjustment capped +/-5 points per offense.

An ACTUAL target-game starter ID is joined *only after forecasting* for a
retrospective error audit and never fed to the pregame projection.

Freeze 2026 data at Week 8, before Week 9; 2021 training only. Use identical
games and nflverse historical spread / total lines across candidates. Same
QB math as published Week 9 cap5 but no source-verified pregame overrides.
Research only, not a valid record of bets or an executable Bovada line.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import sys,json
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp,build_efficiency_model_dataset,chronological_backtest
from injury_model import load_injury_reports,add_injury_features
from qb_epa_model import qb_game_stats,build_qb_epa_board,attach_qb_margin_adjustment,starters_from_game_schedule

OUT=ROOT/"data/week09_review"
REF=ROOT/"data/qb_epa_shadow/qb_epa_2026_week01_08_paired_20261105T161043Z.csv"
MANIFEST=OUT/"realistic_qb_replacement_holdout_20261109.json"
PRED=OUT/"realistic_qb_replacement_holdout_20261109.csv"
MD=OUT/"realistic_qb_replacement_holdout_20261109.md"
YEARS=(2021,2022,2023,2024,2025,2026)
LIMITS={2025:285,2026:121}

def metrics(data,pred):
    x=data.dropna(subset=[pred,"home_score","away_score","spread_line"]).copy()
    actual=x.home_score-x.away_score
    predicted=x[pred]
    edge=predicted-x.spread_line
    actual_ats=actual-x.spread_line
    wins=int((edge*actual_ats>0).sum())
    losses=int((edge*actual_ats<0).sum())
    pushes=int(((actual_ats==0)&(edge!=0)).sum())
    no_lean=int((edge==0).sum())
    sel=x[edge.abs()>=3.5]
    eg=sel[pred]-sel.spread_line;ag=sel.home_score-sel.away_score-sel.spread_line
    w35=int((eg*ag>0).sum());l35=int((eg*ag<0).sum());p35=int((ag==0).sum())
    return {
        "games":len(x),"wins":wins,"losses":losses,"pushes":pushes,
        "no_lean":no_lean,
        "margin_mae":round(float((predicted-actual).abs().mean()),4),
        "avg_absolute_projected_margin":round(float(predicted.abs().mean()),4),
        "ats_min3_5":{"bets":len(sel),"wins":w35,"losses":l35,"pushes":p35},
        "roi_assumed_flat_minus110":round(float((wins*100/110-losses)/(wins+losses+pushes)),4),
    }

def main():
    schedule=load_schedule_data()
    schedule=schedule[
        schedule.season.between(2021,2025)|
        (schedule.season.eq(2026)&schedule.week.le(8))
    ].copy()
    if (schedule.season.eq(2026)&schedule.week.gt(8)).any():
        raise ValueError("2026 Week 9 leakage")
    print("Load historical pre-Week9 play-by-play and injury reports",flush=True)
    pbp=load_pbp(YEARS)
    pbp=pbp[pbp.game_id.isin(set(schedule.game_id))].copy()
    reports=load_injury_reports(YEARS)
    base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    nonqb=add_injury_features(base,schedule,reports,exclude_qb=True)
    print("Chronological Ridge non-QB injury scoring, 500 minimum training games",flush=True)
    result=chronological_backtest(nonqb,min_train_games=500)["predictions"]
    result=result.loc[
        (result.season.eq(2025))|
        (result.season.eq(2026)&result.week.le(8))
    ].copy()
    if result.game_id.duplicated().any() or result.groupby("season").size().to_dict()!=LIMITS:
        raise ValueError("Expected 285 games in 2025 and 121 in 2026 W1–8")
    ref=pd.read_csv(REF,low_memory=False).set_index("game_id")
    test=result[result.season.eq(2026)].set_index("game_id")
    if set(test.index)!=set(ref.index):raise ValueError("2026 target game IDs differ from saved archive")
    recheck=max(float((test.pred_home_score-ref.injury_nonqb_home).abs().max()),
                float((test.pred_away_score-ref.injury_nonqb_away).abs().max()))
    if recheck>0.0001:raise ValueError(f"NonQB score model fails to reproduce archival predictions: {recheck}")

    targets=schedule[schedule.game_id.isin(result.game_id)].copy()
    stats=qb_game_stats(pbp,schedule)
    print("Infer QB from prior game's passer only (no target-game identity)",flush=True)
    inferred=build_qb_epa_board(stats,schedule,targets,overrides=None,observed=None)
    if inferred.starter_source.isin(["verified_pregame","schedule_recorded_starter_postgame","retrospective_first_pass_attempt"]).any():
        raise ValueError("Target-game QB starter identity leaked into pregame research")
    true_starters=starters_from_game_schedule(schedule,completed_only=True)
    true_starters=true_starters[true_starters.game_id.isin(targets.game_id)].copy()
    if len(true_starters)!=2*len(targets):raise ValueError("Missing postgame actual starter IDs (audit only)")
    identities=true_starters[["game_id","team","qb_id"]].rename(columns={"qb_id":"actual_qb_id"})
    checked=inferred.merge(identities,on=["game_id","team"],validate="one_to_one")
    checked["inferred_matches_later_actual"]=checked.qb_id.eq(checked.actual_qb_id)

    qbin=result[["game_id","pred_home_score","pred_away_score"]].rename(columns={
        "pred_home_score":"projected_home","pred_away_score":"projected_away"
    })
    overlay=attach_qb_margin_adjustment(qbin,inferred,max_abs_team_qb_impact=5.0)
    keep=["game_id","qb_margin_adjustment","projected_home_qb_injury","projected_away_qb_injury","projected_total_qb_injury"]
    scored=result.merge(overlay[keep],on="game_id",validate="one_to_one")
    scored["nonqb_margin"]=scored.pred_home_score-scored.pred_away_score
    scored["qb_pregame_margin"]=scored.projected_home_qb_injury-scored.projected_away_qb_injury
    scored["nonqb_total"]=scored.pred_home_score+scored.pred_away_score
    if not np.allclose(scored.nonqb_total,scored.projected_total_qb_injury,equal_nan=True,atol=1e-7):
        raise ValueError("QB margin-only overlay changed projected totals")
    scored=scored.merge(
        schedule[["game_id","spread_line","total_line"]].drop_duplicates("game_id"),
        on="game_id",validate="one_to_one")
    per_game_qbs=checked.pivot(index="game_id",columns="side",values="inferred_matches_later_actual")
    per_game_qbs.columns=[f"{side}_inferred_matches_actual" for side in per_game_qbs.columns]
    scored=scored.merge(per_game_qbs.reset_index(),on="game_id",validate="one_to_one")
    scored["any_qb_identity_changed"]=~(scored["home_inferred_matches_actual"]&scored["away_inferred_matches_actual"])
    common=scored.dropna(subset=["qb_pregame_margin","nonqb_margin","spread_line"])
    if len(common)<390:raise ValueError("Insufficient comparable pregame QB matches")
    summary={}
    for season in (2025,2026):
        d=common[common.season.eq(season)]
        groups={
            "all":d,
            "no_qb_change":d[~d.any_qb_identity_changed],
            "one_or_more_qb_changes":d[d.any_qb_identity_changed],
        }
        summary[str(season)]={key:{
            "n":len(sub),
            "no_qb_overlay":metrics(sub,"nonqb_margin") if len(sub) else None,
            "pregame_qb_overlay":metrics(sub,"qb_pregame_margin") if len(sub) else None,
        } for key,sub in groups.items()}
    qbcorrect=checked.groupby(checked.game_id.map(
        targets.set_index("game_id").season))["inferred_matches_later_actual"].agg(["sum","count"])
    quality={str(int(y)):{
        "correct_inferred_qb_team_games":int(a["sum"]),
        "total_qb_team_games":int(a["count"]),
        "pct_correct":round(100*a["sum"]/a["count"],2)
    } for y,a in qbcorrect.iterrows()}
    report={
        "status":"RESEARCH_ONLY_REALISTIC_QB_2025_2026",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "season_cutoff":"2026 Week 8; absolutely no 2026 Week9 PBP/outcomes",
        "2026_saved_nonqb_score_max_diff":recheck,
        "starter_method":"Prior primary passer from preceding completed game ONLY, no known target starter",
        "historical_QB_id_accuracy":quality,
        "model":"Legacy non-QB Injury Ridge + production margin-only QB EPA shift, capped 5 per team",
        "comparison":summary,
        "common_games":len(common),
        "missing_pregame_qb_forecasts":len(scored)-len(common),
        "limits":[
            "Actual QB identities are used only to audit inferred starter correctness after prediction",
            "Not a source-verified, prospective team-sheet QB starter archive; cannot claim verified actual 2025 starters pregame",
            "QB value parameters developed and assessed using 2026 retrospective analysis; this historical study is NOT independent prospective proof",
            "2026 W9 and MNF outcomes are completely excluded",
            "Schedule market spread is an nflverse archived number, not executable Bovada pricing",
            "Public predictions, Week8–9 grading, and totals model remain unchanged",
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    cols=["game_id","season","week","gameday","home_team","away_team",
          "home_score","away_score","spread_line","total_line",
          "pred_home_score","pred_away_score","nonqb_margin",
          "qb_margin_adjustment","qb_pregame_margin","nonqb_total",
          "any_qb_identity_changed","home_inferred_matches_actual","away_inferred_matches_actual"]
    scored[cols].sort_values(["season","week","game_id"]).to_csv(PRED,index=False)
    MANIFEST.write_text(json.dumps(report,indent=2)+"\n")
    lines=["# Pregame-inferable QB EPA replacement adjustment: 2025 and 2026 W1–8",
           "",
           "Unlike the earlier retrospective QB test, this version **does not use actual target-game QB identity in the prediction**.",
           "Player EPA and team efficiency are taken only from earlier completed games.",
           "",
           "| Season | N | Non-QB Injury ATS | QB-adjusted ATS | Non-QB margin MAE | QB-adjusted margin MAE |",
           "|---|---:|---:|---:|---:|---:|"]
    def record(v):
        return f"{v['wins']}–{v['losses']}–{v['pushes']}"
    for y in ("2025","2026"):
        g=summary[y]["all"]
        a=g["no_qb_overlay"];b=g["pregame_qb_overlay"]
        lines.append(f"| {y} | {g['n']} | {record(a)} | {record(b)} | {a['margin_mae']:.2f} | {b['margin_mae']:.2f} |")
    lines.extend(["",
       "## Starting-QB inference coverage",
       "",
       *[f"- {y}: {v['correct_inferred_qb_team_games']}/{v['total_qb_team_games']} inferred correct ({v['pct_correct']}%)." for y,v in quality.items()],
       "",
       "This tests realism of the identity feed, **not a calibrated value in points above a replacement**.",
       "For public releases, verified starter overrides must be sourced and frozen before kickoff.",
       "Original official scores and Week 9 ledger are unchanged.",
       ""])
    MD.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"quality":quality,"by_season":summary,"saved_nonqb_score_diff":recheck},indent=2),flush=True)

if __name__=="__main__":
    main()
