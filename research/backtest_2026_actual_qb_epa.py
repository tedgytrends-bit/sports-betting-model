#!/usr/bin/env python3
"""Paired 2026 Weeks 1-8 Injury vs QB EPA research evaluation.

Use *historically observed first passer* to identify the person who played.
This is retrospective identity (hindsight), not proof of point-in-time starter
availability. Player EPA inputs come only from games strictly BEFORE target.
The prospective model must use independently verified pregame starters.
Original public snapshots and model grades are NEVER rewritten.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from model import (load_schedule_data,load_pbp,
                   build_efficiency_model_dataset,chronological_backtest)
from injury_model import load_injury_reports,add_injury_features
from qb_epa_model import (qb_game_stats,build_qb_epa_board,
                          attach_qb_shifts,observed_first_passer,starters_from_game_schedule)

OUT=ROOT/"data"/"qb_epa_shadow"
SEASONS=(2021,2022,2023,2024,2025,2026)
COMPARE_WEEKS=range(1,9)


def simple_frame(backtest:dict, prefix:str)->pd.DataFrame:
    x=backtest["predictions"].copy()
    return x[["game_id","season","week","gameday",
              "home_team","away_team","home_score","away_score",
              "pred_home_score","pred_away_score"]].rename(columns={
                 "pred_home_score":f"{prefix}_home",
                 "pred_away_score":f"{prefix}_away"})


def grades(rows:pd.DataFrame,prefix:str)->dict:
    df=rows.dropna(subset=[
        f"{prefix}_home",f"{prefix}_away","home_score","away_score"
    ]).copy()
    df["model_margin"]=df[f"{prefix}_home"]-df[f"{prefix}_away"]
    df["model_total"]=df[f"{prefix}_home"]+df[f"{prefix}_away"]
    actual_margin=df["home_score"]-df["away_score"]
    actual_total=df["home_score"]+df["away_score"]
    result={
        "n":int(len(df)),
        "margin_mae":round(float(np.abs(actual_margin-df["model_margin"]).mean()),4),
        "total_mae":round(float(np.abs(actual_total-df["model_total"]).mean()),4),
        "score_mae":round(float(
            (np.abs(df["home_score"]-df[f"{prefix}_home"])
            +np.abs(df["away_score"]-df[f"{prefix}_away"])).mean()/2
        ),4),
    }
    # The same market line is used across every model, from a single
    # schedule row, so ATS/totals records cannot differ due to line choice.
    for market,actual,pred,key in (
        ("spread_line",actual_margin,df["model_margin"],"ats"),
        ("total_line",actual_total,df["model_total"],"totals"),
    ):
        ok=pd.to_numeric(df[market],errors="coerce").notna()
        sub=df[ok]
        m=pd.to_numeric(sub[market])
        act=(actual.loc[sub.index]-m).to_numpy(dtype=float)
        lean=(pred.loc[sub.index]-m).to_numpy(dtype=float)
        wins=int(((lean*act)>0).sum())
        losses=int(((lean*act)<0).sum())
        pushes=int(((act==0)&(lean!=0)).sum())
        no_lean=int((lean==0).sum())
        graded=wins+losses
        result[key]={"wins":wins,"losses":losses,"pushes":pushes,
                     "no_lean":no_lean,"graded":graded,
                     "win_pct":round(wins/graded,4) if graded else None,
                     "roi_-110":round((wins*100/110-losses)/graded,4) if graded else None}
    return result


def main()->None:
    now=datetime.now(timezone.utc).replace(microsecond=0)
    print("Load schedule, player PBP and injury history",flush=True)
    schedule=load_schedule_data()
    pbp=load_pbp(SEASONS)
    reports=load_injury_reports(SEASONS)
    game_base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    schedule=schedule.copy()
    schedule["season"]=pd.to_numeric(schedule["season"],errors="coerce")
    schedule["week"]=pd.to_numeric(schedule["week"],errors="coerce")

    print("Identify historical passers from completed-game participation",flush=True)
    observations=observed_first_passer(pbp,schedule)
    obs=starters_from_game_schedule(schedule,completed_only=True)
    required_complete=game_base[
        game_base["home_score"].notna()&game_base["away_score"].notna()
    ].copy()
    target_26=required_complete[
        required_complete["season"].eq(2026)
        &required_complete["week"].isin(COMPARE_WEEKS)
    ].copy()
    target_teams=pd.concat([
        target_26[["game_id","home_team"]].rename(columns={"home_team":"team"}),
        target_26[["game_id","away_team"]].rename(columns={"away_team":"team"})
    ],ignore_index=True)
    matched=target_teams.merge(obs,on=["game_id","team"],how="left",validate="one_to_one")
    missing=matched[matched["qb_id"].isna()]
    print(f"2026 test games {len(target_26)}; team QB observations: {len(matched)-len(missing)} of {len(matched)}",flush=True)
    if not missing.empty: print("Unknown actual QB first passer:\n"+missing.to_string(index=False),flush=True)

    print("Build point-in-time QB EPA for all completed historical games",flush=True)
    stats=qb_game_stats(pbp,schedule)
    board=build_qb_epa_board(stats,schedule,required_complete,observed=obs)
    if not board["starter_source"].isin(
        ["schedule_recorded_starter_postgame","inferred_previous_primary_passer",
         "unknown_no_pregame_evidence"]
    ).all(): raise AssertionError("Illegal pregame source label")

    print("Fit weekly chronological original Injury model",flush=True)
    old=add_injury_features(game_base,schedule,reports)
    old_pred=simple_frame(chronological_backtest(old,min_train_games=500),"injury_old")

    print("Fit weekly QB-neutral Injury model",flush=True)
    neutral=add_injury_features(game_base,schedule,reports,exclude_qb=True)
    neutral_pred=simple_frame(
        chronological_backtest(neutral,min_train_games=500),"injury_nonqb")

    # This is a fully refitted Injury regression. QB absence isn't counted
    # twice: all QB rows are excluded from the general injury counts.
    # The model learns the QB-specific signal from prior historic outcomes.
    # 'Observed' QB identity comes from the target game (retrospective test);
    # the EPA value itself never includes that game's play results.
    qb_feats=board.pivot(index="game_id",columns="side",values="qb_point_shift_experimental")
    qb_feats=qb_feats.rename(columns={
        "home":"home_qb_epa_point_shift_input",
        "away":"away_qb_epa_point_shift_input"}).reset_index()
    assert qb_feats.game_id.is_unique
    fitted=neutral.merge(qb_feats,on="game_id",how="left",validate="one_to_one")
    print("Fit chronological Injury model WITH QB EPA features",flush=True)
    fitted_pred=simple_frame(
        chronological_backtest(fitted,min_train_games=500),"injury_qb_fitted")

    paired=old_pred.merge(
        neutral_pred[["game_id","injury_nonqb_home","injury_nonqb_away"]],
        on="game_id",how="inner",validate="one_to_one"
    ).merge(
        fitted_pred[["game_id","injury_qb_fitted_home","injury_qb_fitted_away"]],
        on="game_id",how="inner",validate="one_to_one"
    )
    paired=paired[
        paired["season"].eq(2026)&paired["week"].isin(COMPARE_WEEKS)
    ].copy()
    overlay_input=paired[["game_id","injury_nonqb_home","injury_nonqb_away"]].rename(
        columns={"injury_nonqb_home":"projected_home",
                 "injury_nonqb_away":"projected_away"})
    overlay=attach_qb_shifts(overlay_input,board).rename(columns={
        "home_qb_adjusted":"injury_qb_overlay_home",
        "away_qb_adjusted":"injury_qb_overlay_away"})
    paired=paired.merge(
        overlay[["game_id","injury_qb_overlay_home","injury_qb_overlay_away"]],
        on="game_id",how="left",validate="one_to_one"
    )
    paired=paired.merge(
        schedule[["game_id","spread_line","total_line"]].drop_duplicates("game_id"),
        on="game_id",how="left",validate="one_to_one"
    )
    qb_2026=board[board["game_id"].isin(paired["game_id"])].copy()
    for side in ("home","away"):
        one=qb_2026[qb_2026.side.eq(side)][[
            "game_id","qb_id","qb_name","starter_source","confidence",
            "qb_prior_dropbacks","qb_shrunk_epa_per_dropback",
            "qb_delta_epa_per_dropback","qb_point_shift_experimental",
            "starter_recent_team_dropback_share"
        ]].rename(columns={x:f"{side}_{x}" for x in (
            "qb_id","qb_name","starter_source","confidence",
            "qb_prior_dropbacks","qb_shrunk_epa_per_dropback",
            "qb_delta_epa_per_dropback","qb_point_shift_experimental",
            "starter_recent_team_dropback_share"
        )})
        paired=paired.merge(one,on="game_id",how="left",validate="one_to_one")

    model_keys=("injury_old","injury_nonqb","injury_qb_fitted","injury_qb_overlay")
    all_scores={name:grades(paired,name) for name in model_keys}
    weekly=[]
    for week in COMPARE_WEEKS:
        wk=paired[paired.week.eq(week)]
        for name in model_keys:
            weekly.append({"week":week,"model":name,**grades(wk,name)})
    score_table=pd.DataFrame([
        {"model":name,**{k:v for k,v in sc.items() if k not in ("ats","totals")},
         "ats_w":sc["ats"]["wins"],"ats_l":sc["ats"]["losses"],
         "ats_p":sc["ats"]["pushes"],"ats_roi":sc["ats"]["roi_-110"],
         "totals_w":sc["totals"]["wins"],"totals_l":sc["totals"]["losses"],
         "totals_p":sc["totals"]["pushes"],"totals_roi":sc["totals"]["roi_-110"]}
        for name,sc in all_scores.items()
    ])
    # Unknown/changed starter audits, do not treat opening-day starter as
    # the starter every later week.
    starters=obs[
        obs["season"].eq(2026)&obs["week"].isin(COMPARE_WEEKS)
    ].copy()
    week1=ROOT/"data"/"qb_starters"/"2026_week01_user_reference.csv"
    if week1.exists():
        seed=pd.read_csv(week1)[["team","opening_day_qb_name"]]
        starters=starters.merge(seed,on="team",how="left",validate="many_to_one")
    # Select replacements/change events by the *actual observed passer ID*
    # at each consecutive team appearance (not roster transactions guessed).
    starters=starters.sort_values(["team","week","game_id"])
    starters["prev_qb_id"]=starters.groupby("team")["qb_id"].shift()
    starters["changed_since_previous_game"]=(
        starters["prev_qb_id"].notna()&
        starters["prev_qb_id"].ne(starters["qb_id"])
    )
    inferred_only=board[
        board.game_id.isin(paired.game_id)&
        board.starter_source.ne("schedule_recorded_starter_postgame")
    ][["game_id","team","starter_source","qb_name"]]
    report={
        "created_at_utc":now.isoformat(),
        "status":"RESEARCH_ONLY_2026_WEEK01_TO_08",
        "test_games":int(len(paired)),
        "models":all_scores,
        "starter_audit":{
            "complete_qb_team_games":int(len(target_teams)),
            "schedule_recorded_starters":int(len(matched)-len(missing)),
            "first_vs_primary_disagreement":int(
                starters["first_matches_primary"].eq(False).sum()
            ),
            "observed_changes_team_weeks":int(
                starters["changed_since_previous_game"].sum()
            ),
            "fallback_to_previous_game_qb":int(len(inferred_only)),
            "warning":"The target game's first passer is known RETROSPECTIVELY; it is not a verified pregame starter. EPA features are strictly from preceding games.",
        },
        "training":"Every test-week regression fits only on games before that week; same folds, schedule market, and league history for old/new.",
        "non_qb_rule":"All QB rows removed from QB count AND general injury/practice counts before QB EPA feature is added.",
        "clinical_limitations":[
            "2026 holdout comparison uses postgame starter identity and cannot establish prospective performance.",
            "PBP first passer is a proxy for the opening QB and may be wrong where first pass was after early substitution or trick play.",
            "QB EPA prior shrinkage and conversion were selected before evaluation but have not undergone extensive external validation.",
            "Injury report source does not guarantee complete point-in-time unavailable-player coverage.",
            "Do not overwrite published 2026 Week 8-9 official frozen projections."
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    stamp=now.strftime("%Y%m%dT%H%M%SZ")
    paths={
        "predictions":OUT/f"qb_epa_2026_week01_08_paired_{stamp}.csv",
        "summary":OUT/f"qb_epa_2026_week01_08_summary_{stamp}.csv",
        "weekly":OUT/f"qb_epa_2026_week01_08_weekly_{stamp}.csv",
        "starters":OUT/f"qb_epa_2026_week01_08_starters_{stamp}.csv",
        "qb_detail":OUT/f"qb_epa_2026_week01_08_qb_detail_{stamp}.csv",
        "report":OUT/f"qb_epa_2026_week01_08_report_{stamp}.json"
    }
    paired.sort_values(["week","gameday","game_id"]).to_csv(paths["predictions"],index=False)
    score_table.to_csv(paths["summary"],index=False)
    pd.DataFrame(weekly).to_csv(paths["weekly"],index=False)
    starters.to_csv(paths["starters"],index=False)
    qb_2026.to_csv(paths["qb_detail"],index=False)
    report["outputs"]={k:str(v.relative_to(ROOT)) for k,v in paths.items()}
    paths["report"].write_text(json.dumps(report,indent=2,default=str)+"\n")
    print("ALL WEEK 1-8 RESULTS\n"+score_table.to_string(index=False),flush=True)
    print("QB starter changes "+str(report["starter_audit"]),flush=True)
    print("Report "+str(paths["report"]),flush=True)


if __name__=="__main__":
    main()
