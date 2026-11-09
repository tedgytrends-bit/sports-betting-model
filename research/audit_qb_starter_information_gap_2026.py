#!/usr/bin/env python3
"""QB starting-identity information-gap audit, 2026 Weeks 1–8 (research only).

Unlike the previously reported 63–52–6 retrospective QB overlay, this script
computes TWO separate QB candidates using the SAME frozen non-QB predictions:
  - pregame_provisional: identity inferred strictly from last game's primary
    passer, using preceding completed games only.
  - retrospective_actual: uses target game's recorded starter ID, available
    after the game. This is an UNAVAILABLE perfect-information comparator.

Production qb_epa_model.py provides the adjustment and caps both sides +/-5
preserving projected total. No Week 9 scores, odds, or public records used.
Historical line is nflverse schedule spread_line (NOT Bovada execution).
No selection of hyperparameters from these outcomes.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import sys,json
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp
from qb_epa_model import (qb_game_stats,build_qb_epa_board,
                          attach_qb_margin_adjustment,starters_from_game_schedule)

INPUT=ROOT/"data/qb_epa_shadow/qb_epa_2026_week01_08_paired_20261105T161043Z.csv"
OUT=ROOT/"data/week09_review"
RESULT=OUT/"qb_starter_information_gap_20261109.json"
ROWS=OUT/"qb_starter_information_gap_20261109.csv"
MARKDOWN=OUT/"qb_starter_information_gap_20261109.md"
SEASONS=(2021,2022,2023,2024,2025,2026)

def evaluate(frame,col):
    d=frame.dropna(subset=[col,"home_score","away_score","spread_line","total_line"]).copy()
    # all candidates graded on a common set of known-starting-QB games
    margin=d[col].to_numpy(dtype=float)
    actual=(d.home_score-d.away_score).to_numpy(dtype=float)
    line=d.spread_line.to_numpy(dtype=float)
    pred_edge=margin-line
    actual_edge=actual-line
    wins=int((pred_edge*actual_edge>0).sum())
    losses=int((pred_edge*actual_edge<0).sum())
    push=int(((actual_edge==0)&(pred_edge!=0)).sum())
    no_lean=int((pred_edge==0).sum())
    return {
        "games":len(d),"wins":wins,"losses":losses,"pushes":push,
        "no_lean":no_lean,
        "margin_mae":round(float(np.abs(margin-actual).mean()),4),
        "win_rate_ex_push":round(wins/(wins+losses),4) if wins+losses else None,
        "roi_assumed_minus110":round((wins*100/110-losses)/(wins+losses+push),4)
        if wins+losses+push else None,
        "min_3_5_edge":{
            "bets":int((np.abs(pred_edge)>=3.5).sum()),
            "wins":int(((np.abs(pred_edge)>=3.5)&(pred_edge*actual_edge>0)).sum()),
            "losses":int(((np.abs(pred_edge)>=3.5)&(pred_edge*actual_edge<0)).sum()),
            "pushes":int(((np.abs(pred_edge)>=3.5)&(actual_edge==0)).sum()),
        },
    }

def main():
    archive=pd.read_csv(INPUT)
    if len(archive)!=121 or archive.game_id.duplicated().any():
        raise ValueError("2026 paired frozen backtest expected 121 unique games")
    if not archive.season.eq(2026).all() or archive.week.max()>8:
        raise ValueError("Week 9 data leaked into historic QB cohort")
    schedule=load_schedule_data()
    pbp=load_pbp(SEASONS)
    stats=qb_game_stats(pbp,schedule)
    targets=schedule.loc[schedule.game_id.isin(archive.game_id)].copy()
    if len(targets)!=121 or targets.home_score.isna().any() or targets.away_score.isna().any():
        raise ValueError("Incomplete historical schedule targets")
    recorded=starters_from_game_schedule(schedule,completed_only=True)
    recorded=recorded[recorded.game_id.isin(targets.game_id)].copy()
    if len(recorded)!=242:raise ValueError(f"Missing recorded actual QB starters: {len(recorded)}")

    print("Create strictly last-game primary passer inference, NO target starters",flush=True)
    inferred=build_qb_epa_board(stats,schedule,targets,overrides=None,observed=None)
    print("Create ORACLE comparator using postgame starter metadata (cannot be used pregame)",flush=True)
    hindsight=build_qb_epa_board(stats,schedule,targets,observed=recorded)
    if inferred.starter_source.isin(["schedule_recorded_starter_postgame","verified_pregame"]).any():
        raise ValueError("Hindsight identity leaked into pregame board")
    if not hindsight.starter_source.eq("schedule_recorded_starter_postgame").all():
        raise ValueError("Retrospective starter identity source incomplete")

    def qb_wide(board,tag):
        a=board[board.side.eq("away")][["game_id","qb_id","qb_name","starter_source","qb_prior_dropbacks","qb_point_shift_experimental","confidence"]].copy()
        h=board[board.side.eq("home")][["game_id","qb_id","qb_name","starter_source","qb_prior_dropbacks","qb_point_shift_experimental","confidence"]].copy()
        a=a.rename(columns={c:"away_"+tag+"_"+c for c in a.columns if c!="game_id"})
        h=h.rename(columns={c:"home_"+tag+"_"+c for c in h.columns if c!="game_id"})
        return a.merge(h,on="game_id",validate="one_to_one")

    base=archive[["game_id","season","week","gameday","home_team","away_team",
                  "home_score","away_score","spread_line","total_line",
                  "injury_nonqb_home","injury_nonqb_away"]].copy()
    base["projected_home"]=base.injury_nonqb_home
    base["projected_away"]=base.injury_nonqb_away
    for tag,board in [("inferred",inferred),("hindsight",hindsight)]:
        pred=attach_qb_margin_adjustment(base[["game_id","projected_home","projected_away"]],board)
        base=base.merge(pred[["game_id","qb_margin_adjustment"]].rename(columns={
            "qb_margin_adjustment":tag+"_qb_margin_shift"
        }),on="game_id",validate="one_to_one")
        base=base.merge(qb_wide(board,tag),on="game_id",validate="one_to_one")

    base["baseline_margin"]=base.injury_nonqb_home-base.injury_nonqb_away
    base["inferred_margin"]=base.baseline_margin+base.inferred_qb_margin_shift
    base["hindsight_margin"]=base.baseline_margin+base.hindsight_qb_margin_shift
    base["both_qbs_matched_actual"]=(
        base.away_inferred_qb_id.eq(base.away_hindsight_qb_id)&
        base.home_inferred_qb_id.eq(base.home_hindsight_qb_id)
    )
    base["home_qb_changed"]=~base.home_inferred_qb_id.eq(base.home_hindsight_qb_id)
    base["away_qb_changed"]=~base.away_inferred_qb_id.eq(base.away_hindsight_qb_id)
    base["total_qb_identity_mismatches"]=base.home_qb_changed.astype(int)+base.away_qb_changed.astype(int)
    base["qb_margin_knowledge_gap"]=base.hindsight_margin-base.inferred_margin
    base["actual_home_margin"]=base.home_score-base.away_score
    base["has_all_three"]=base[["baseline_margin","inferred_margin","hindsight_margin"]].notna().all(axis=1)
    common=base[base.has_all_three].copy()
    if len(common)<110:
        raise ValueError(f"Insufficient common sample to compare QB forecasts fairly: {len(common)}")

    # Independently compare postgame starter ids with the archival retrospective rows.
    known=archive.set_index("game_id")
    for side in ("home","away"):
        old=base.set_index("game_id")[f"{side}_hindsight_qb_id"]
        if not (old==known[f"{side}_qb_id"]).all():
            raise ValueError("Retrospective QB identity differs from saved research")

    slices={
        "all_common":common,
        "both_qbs_same_as_last_primary":common[common.both_qbs_matched_actual],
        "at_least_one_qb_differs_from_last_primary":common[~common.both_qbs_matched_actual],
    }
    report_groups={name:{
        "games":len(g),
        "nonqb":evaluate(g,"baseline_margin"),
        "pregame_inferred_qb":evaluate(g,"inferred_margin"),
        "retrospective_actual_qb":evaluate(g,"hindsight_margin"),
    } for name,g in slices.items()}
    full={
        "status":"RESEARCH_ONLY_STARTER_INFORMATION_GAP",
        "date_utc":datetime.now(timezone.utc).isoformat(),
        "source_archived_paired_nonqb":str(INPUT.relative_to(ROOT)),
        "season":2026,"weeks":"1–8","games_archived":len(base),
        "games_common":len(common),
        "qb_team_games":len(base)*2,
        "inferred_correct_teams":int(
            base.home_inferred_qb_id.eq(base.home_hindsight_qb_id).sum()+
            base.away_inferred_qb_id.eq(base.away_hindsight_qb_id).sum()),
        "inferred_wrong_teams":int(base.total_qb_identity_mismatches.sum()),
        "games_with_any_incorrect_inferred_starter":int((~base.both_qbs_matched_actual).sum()),
        "missing_inferred_qb_margin":int(base.inferred_qb_margin_shift.isna().sum()),
        "missing_hindsight_qb_margin":int(base.hindsight_qb_margin_shift.isna().sum()),
        "median_abs_qb_margin_information_gap":round(float(common.qb_margin_knowledge_gap.abs().median()),4),
        "p90_abs_qb_margin_information_gap":round(float(common.qb_margin_knowledge_gap.abs().quantile(.90)),4),
        "comparison":report_groups,
        "descriptive_unseen_qb_changes":base[~base.both_qbs_matched_actual][[
            "game_id","home_inferred_qb_name","home_hindsight_qb_name",
            "away_inferred_qb_name","away_hindsight_qb_name","qb_margin_knowledge_gap"
        ]].sort_values("qb_margin_knowledge_gap",key=lambda x:x.abs(),ascending=False).head(20).to_dict("records"),
        "limits":[
            "Only 121 historical 2026 W1–8 games; no Week 9 outcomes in this research",
            "The postgame-starter model is a retrospective oracle, NOT a true pregame model",
            "Prior-game inferred QB misses late injuries, suspensions, rookie starters and trades",
            "Market price from nflverse schedule, not verified executable Bovada quotes",
            "Same +/-5 cap and margin-only overlay; other hyperparameters are unmodified",
            "Do not tune or promote based on this analysis. Official published forecasts unchanged",
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    base.to_csv(ROWS,index=False)
    RESULT.write_text(json.dumps(full,indent=2,default=str)+"\n")
    lines=["# QB starter hindsight-bias audit: 2026 Weeks 1–8",
        "",
        "Research only. This report separates **pregame inferable QB identity** from **actual QB known after kickoff**.",
        "All model comparisons use the same 2026 pregame non-QB Injury forecast and the same nflverse lines.",
        "",
        f"- Correct previous-game QB inference: **{full['inferred_correct_teams']} of {full['qb_team_games']}** team-games.",
        f"- Incorrect inference: **{full['inferred_wrong_teams']}** team-games; {full['games_with_any_incorrect_inferred_starter']} games affected.",
        f"- QBs with missing inference: {full['missing_inferred_qb_margin']} game margins.",
        "",
        "| Group | N | Non-QB Injury ATS | Prior-only QB ATS | Postgame QB oracle ATS | Non-QB margin MAE | Prior-only MAE | Postgame-oracle MAE |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    def record(x):
        return f"{x['wins']}–{x['losses']}–{x['pushes']}"
    for name,g in report_groups.items():
        lines.append(
            f"| {name} | {g['games']} | {record(g['nonqb'])} | "
            f"{record(g['pregame_inferred_qb'])} | {record(g['retrospective_actual_qb'])} | "
            f"{g['nonqb']['margin_mae']:.2f} | {g['pregame_inferred_qb']['margin_mae']:.2f} | "
            f"{g['retrospective_actual_qb']['margin_mae']:.2f} |")
    lines+=["","## What this establishes","",
        "- Retroactive QB knowledge must not be claimed as a prospective betting result.",
        "- Identify verified starting QBs and their replacement options before freezing the live board.",
        "- For teams without verified starters, label *inferred*, and don't invent an OUT penalty.",
        "- Evaluate model effects on QB-change weeks separately from all stable-starter weeks.",
        "- A postgame oracle is useful only to estimate a potential upper bound on identity quality.",
        ""]
    MARKDOWN.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"summary":{k:full[k] for k in [
        "games_common","inferred_correct_teams","inferred_wrong_teams",
        "games_with_any_incorrect_inferred_starter","missing_inferred_qb_margin"
    ]},"results":report_groups},indent=2),flush=True)

if __name__=="__main__":
    main()
