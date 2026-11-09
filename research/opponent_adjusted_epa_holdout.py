#!/usr/bin/env python3
"""Research-only opponent-adjusted EPA team-strength feature evaluation.

Each team's offense/defense game EPA is adjusted using its opponent's RAW
efficiency in games strictly BEFORE that historical game, relative to the
PRE-game league mean. Rolling last-10 adjusted EPA is only used in LATER games.
Same-day games are snapshotted before ANY updates.

This is causal-style schedule normalization (not a player WAR estimate and
not an opponent-adjusted nflverse-native EPA field). The adjustment uses only
scrimmage play EPA from an already-completed prior game.

Historical window: 2021–2026 week 8; no results from Week 9 or MNF.
Six variants compared over the exact 1021 frozen walk-forward historical games.
Research only; production public projections and totals stay untouched.
"""
from __future__ import annotations

from collections import defaultdict,deque
from datetime import datetime,timezone
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_schedule_data,load_pbp,build_efficiency_model_dataset,build_efficiency_table
from research.standardized_player_injury_holdout import fit_weekly,metrics,feature_names
from research.opponent_adjusted_team_strength_holdout import pregame_elo_and_form

OUT=ROOT/"data"/"week09_review"
SOURCE=ROOT/"data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv"
JSON_OUT=OUT/"opponent_adjusted_epa_holdout_20261109.json"
CSV_OUT=OUT/"opponent_adjusted_epa_holdout_20261109.csv"
MD_OUT=OUT/"opponent_adjusted_epa_holdout_20261109.md"
WINDOW=10
SEASONS=(2021,2022,2023,2024,2025,2026)
EXPECTED={2022:45,2023:285,2024:285,2025:285,2026:121}
ELO_FEATURES=["home_elo_strength","away_elo_strength","elo_strength_diff","elo_home_win_probability"]
EPA_FEATURES=[
    "home_adj_off_epa_last10","away_adj_off_epa_last10",
    "home_adj_def_epa_last10","away_adj_def_epa_last10",
    "home_adj_epa_matchup","away_adj_epa_matchup",
    "adj_epa_matchup_diff","home_adj_epa_form_games","away_adj_epa_form_games",
]
CANDIDATES={
    "baseline_original":("base",False,10.),
    "baseline_std_alpha10":("base",True,10.),
    "opponent_epa_raw":("epa",False,10.),
    "opponent_epa_standardized":("epa",True,10.),
    "opponent_epa_std_alpha100":("epa",True,100.),
    "opponent_epa_plus_elo_standardized":("epa_elo",True,10.),
}

def norm(name):
    name=str(name).upper()
    return "LA" if name=="LAR" else name


def build_opponent_adjusted_epa(schedule,pbp_eff):
    required={"game_id","season","week","gameday","home_team","away_team","home_score","away_score"}
    if not required.issubset(schedule.columns):
        raise ValueError(f"Schedule missing {required-set(schedule.columns)}")
    s=schedule.copy()
    s["gameday"]=pd.to_datetime(s.gameday,errors="coerce")
    s=s.dropna(subset=["gameday"]).sort_values(["gameday","game_id"])
    if s.game_id.duplicated().any():raise ValueError("Repeated schedule game ids")

    eff=pbp_eff[["game_id","team","off_epa","def_epa_allowed"]].copy()
    eff=eff[eff.game_id.isin(set(s.game_id))].copy() # NO 2026 W9 PBP
    eff["team"]=eff.team.map(norm)
    if eff.duplicated(["game_id","team"]).any():
        raise ValueError("Duplicate team PBP efficiency")
    lookup={(r.game_id,r.team):(float(r.off_epa),float(r.def_epa_allowed))
            for r in eff.itertuples(index=False) if pd.notna(r.off_epa) and pd.notna(r.def_epa_allowed)}
    raw_history=defaultdict(lambda:deque(maxlen=WINDOW))
    adjusted_history=defaultdict(lambda:deque(maxlen=WINDOW))
    league_off=deque(maxlen=500)
    league_def=deque(maxlen=500)
    result=[]
    for date,group in s.groupby("gameday",sort=True):
        # Take a PRE-date snapshot of league norms and all team strengths.
        league_mean_off=float(np.mean(league_off)) if league_off else 0.
        league_mean_def=float(np.mean(league_def)) if league_def else 0.
        pending=[]
        for g in group.itertuples(index=False):
            home,away=norm(g.home_team),norm(g.away_team)
            h=list(adjusted_history[home])
            a=list(adjusted_history[away])
            h_off=float(np.mean([r[0] for r in h])) if h else np.nan
            a_off=float(np.mean([r[0] for r in a])) if a else np.nan
            h_def=float(np.mean([r[1] for r in h])) if h else np.nan
            a_def=float(np.mean([r[1] for r in a])) if a else np.nan
            match_home=h_off-a_def
            match_away=a_off-h_def
            result.append({
                "game_id":g.game_id,
                "home_adj_off_epa_last10":h_off,
                "away_adj_off_epa_last10":a_off,
                "home_adj_def_epa_last10":h_def,
                "away_adj_def_epa_last10":a_def,
                "home_adj_epa_matchup":match_home,
                "away_adj_epa_matchup":match_away,
                "adj_epa_matchup_diff":match_home-match_away,
                "home_adj_epa_form_games":len(h),
                "away_adj_epa_form_games":len(a),
            })
            if pd.isna(g.home_score) or pd.isna(g.away_score):
                continue
            h_data=lookup.get((g.game_id,home))
            a_data=lookup.get((g.game_id,away))
            if h_data is None or a_data is None:continue
            ho,hd=h_data
            ao,ad=a_data
            if not np.isfinite([ho,hd,ao,ad]).all():continue
            h_prior=list(raw_history[home])
            a_prior=list(raw_history[away])
            a_prior_def=float(np.mean([x[1] for x in a_prior])) if a_prior else league_mean_def
            h_prior_def=float(np.mean([x[1] for x in h_prior])) if h_prior else league_mean_def
            h_prior_off=float(np.mean([x[0] for x in h_prior])) if h_prior else league_mean_off
            a_prior_off=float(np.mean([x[0] for x in a_prior])) if a_prior else league_mean_off
            # Example: score high EPA against a strong opposing defense (low
            # prior allowed EPA) -> adjust offensive rating UP.
            h_adj_off=ho-(a_prior_def-league_mean_def)
            a_adj_off=ao-(h_prior_def-league_mean_def)
            # Defense performs worse facing elite offenses; remove the prior
            # strength of that offense from today's allowed EPA.
            h_adj_def=hd-(a_prior_off-league_mean_off)
            a_adj_def=ad-(h_prior_off-league_mean_off)
            pending.append((home,away,ho,hd,ao,ad,h_adj_off,h_adj_def,a_adj_off,a_adj_def))
        # Every same-date game uses only pre-date raw offense/defense ratings.
        for home,away,ho,hd,ao,ad,hao,had,aao,aad in pending:
            raw_history[home].append((ho,hd))
            raw_history[away].append((ao,ad))
            adjusted_history[home].append((hao,had))
            adjusted_history[away].append((aao,aad))
            league_off.extend((ho,ao))
            league_def.extend((hd,ad))
    frame=pd.DataFrame(result)
    if len(frame)!=len(s) or frame.game_id.duplicated().any():
        raise ValueError("EPA adjusted feature matrix incomplete")
    return frame


def synthetic_leakage_test():
    # Day 1 scores/PBP must not appear as pregame features until day 2.
    s=pd.DataFrame([
        dict(game_id="d1",season=2021,week=1,gameday="2021-01-01",home_team="A",away_team="B",home_score=31,away_score=13),
        dict(game_id="d2",season=2021,week=1,gameday="2021-01-01",home_team="C",away_team="D",home_score=30,away_score=12),
        dict(game_id="d3",season=2021,week=2,gameday="2021-01-08",home_team="A",away_team="C",home_score=np.nan,away_score=np.nan),
    ])
    e=pd.DataFrame([
        dict(game_id=g,team=t,off_epa=x,def_epa_allowed=y) for g,t,x,y in [
            ("d1","A",.22,-.12),("d1","B",-.12,.22),
            ("d2","C",.17,-.06),("d2","D",-.06,.17)]])
    f=build_opponent_adjusted_epa(s,e).set_index("game_id")
    for key in ("d1","d2"):
        if f.loc[key,"home_adj_epa_form_games"]!=0 or not pd.isna(f.loc[key,"home_adj_off_epa_last10"]):
            raise ValueError("Same-day EPA leakage")
    if f.loc["d3","home_adj_epa_form_games"]!=1 or not np.isfinite(f.loc["d3","home_adj_epa_matchup"]):
        raise ValueError("Subsequent EPA features unavailable")
    # A cancelled/future game's PBP must not enter prior history.
    e=pd.concat([e,pd.DataFrame([dict(game_id="d3",team="A",off_epa=999.,def_epa_allowed=999.)])])
    again=build_opponent_adjusted_epa(s,e).set_index("game_id")
    if f.loc["d3","home_adj_off_epa_last10"] != again.loc["d3","home_adj_off_epa_last10"]:
        raise ValueError("Pregame game PBP leakage")


def main():
    synthetic_leakage_test()
    print("Loading schedule and play-by-play before 2026 Week 9",flush=True)
    all_schedule=load_schedule_data()
    schedule=all_schedule[
        all_schedule.season.between(2021,2025)|
        (all_schedule.season.eq(2026)&all_schedule.week.le(8))
    ].copy()
    if len(schedule)<1500:raise ValueError("Insufficient historical schedule")
    pbp=load_pbp(SEASONS)
    print("Building original baseline and historical team-game EPA",flush=True)
    base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    cols=feature_names(base)
    if len(cols)!=24:raise ValueError("Baseline input count changed")
    efficiency=build_efficiency_table(pbp)
    print("Calculating strictly pregame opponent-adjusted EPA",flush=True)
    adjusted=build_opponent_adjusted_epa(schedule,efficiency)
    elo=pregame_elo_and_form(schedule)
    epa=base.merge(adjusted,on="game_id",validate="one_to_one")
    epa_elo=epa.merge(elo[["game_id"]+ELO_FEATURES],on="game_id",validate="one_to_one")
    datasets={
        "base":(base,cols),
        "epa":(epa,cols+EPA_FEATURES),
        "epa_elo":(epa_elo,cols+EPA_FEATURES+ELO_FEATURES),
    }
    forecasts=[]
    for name,(kind,standardized,alpha) in CANDIDATES.items():
        d,features=datasets[kind]
        print(f"Fit {name}: {len(features)} features",flush=True)
        forecasts.append(fit_weekly(d,features,standardized,alpha,name))
    predictions=pd.concat(forecasts,ignore_index=True)
    ref=pd.read_csv(SOURCE,low_memory=False)
    ref=ref[ref.model.eq("baseline")]
    if len(ref)!=1021 or ref.game_id.duplicated().any():
        raise ValueError("Archive reference no longer 1021 games")
    game_ids=set(ref.game_id)
    for name in CANDIDATES:
        subset=predictions[predictions.research_variant.eq(name)]
        if set(subset.game_id)!=game_ids:
            raise ValueError(f"Unequal game samples for {name}, {len(subset)}")
    old=ref.set_index("game_id")
    original=predictions[predictions.research_variant.eq("baseline_original")].set_index("game_id")
    score_err=max(float(np.abs(original.pred_home-old.pred_home).max()),
                  float(np.abs(original.pred_away-old.pred_away).max()))
    if score_err>1e-4:
        raise ValueError(f"Original baseline prediction was not reproduced: {score_err}")
    predictions=predictions.merge(ref[["game_id","spread_line","total_line"]],
                                  on="game_id",how="left",validate="many_to_one")
    if predictions.duplicated(["game_id","research_variant"]).any():
        raise ValueError("Duplicate forecasts")
    summary={}
    for name in CANDIDATES:
        subset=predictions[predictions.research_variant.eq(name)]
        groups={str(int(year)):metrics(group) for year,group in subset.groupby("season")}
        if {int(x) for x in groups}!=set(EXPECTED):raise ValueError("Missing years")
        if any(v["games"]!=EXPECTED[int(k)] for k,v in groups.items()):
            raise ValueError("Incorrect evaluation coverage")
        summary[name]=groups

    result={
        "status":"RESEARCH_ONLY_OPPONENT_ADJUSTED_EPA",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "data_cutoff":"2026 Week 8; no Week 9/MNF results",
        "same_day_leakage_test":"PASSED",
        "baseline_reproduction_max_abs_score_error":score_err,
        "walk_forward":"Prior calendar weeks only, train-only medians and StandardScaler",
        "model_group_counts":{name:len(features) for name,(d,features) in datasets.items()},
        "candidate_variants":CANDIDATES,
        "eval_games_each":1021,
        "outcomes_by_season":summary,
        "definition":"Raw per-game team EPA adjusted by opponent rolling defense/offense EPA estimated strictly before that earlier game; target features average 10 prior adjusted games",
        "limitations":[
            "Research hypothesis conceived after observing 2026 Week 9, so previous historical test periods are not independent confirmation.",
            "Opponents' raw EPA can be noisy and short samples use a historical league fallback.",
            "No adjustment for QB replacement, specific player injury status, or offensive line performance.",
            "Historical market lines are nflverse closing spread, not verified executable Bovada odds.",
            "This compares independently fitted score regressors and does not constitute a validated profitable ATS betting system.",
            "The public frozen official prediction, record and totals model remain untouched.",
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    REPORT=JSON_OUT
    REPORT.write_text(json.dumps(result,indent=2)+"\n")
    predictions.sort_values(["season","week","game_id","research_variant"]).to_csv(CSV_OUT,index=False)
    lines=[
        "# Opponent-adjusted offensive and defensive EPA backtest",
        "",
        "**Research only:** Not a replacement for the live Tedgy Trends public Injury model.",
        "All games in the 2026 Week 9 slate and their outcomes are excluded.",
        "An opponent's strength is calculated *before the earlier game occurred*, not using season-end statistics.",
        "",
        "| Variant | 2025 ATS | 2025 ≥3.5 ATS | 2025 margin MAE | 2026 W1–8 ATS | 2026 ≥3.5 ATS | 2026 margin MAE |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    def rec(x,key):
        z=x[key];return f"{z['wins']}–{z['losses']}–{z['pushes']}"
    for name,g in summary.items():
        a=g["2025"];b=g["2026"]
        lines.append(f"| {name} | {rec(a,'ATS_all_games')} | {rec(a,'ATS_min_edge_3_5')} | {a['margin_mae']:.2f} | {rec(b,'ATS_all_games')} | {rec(b,'ATS_min_edge_3_5')} | {b['margin_mae']:.2f} |")
    lines.extend(["","## Evaluation safeguards","",
                  "- 1,021 identical historical games, with 2021 in training only.",
                  "- Evaluation includes a partial 2022, full 2023–2025 and 2026 Weeks 1–8.",
                  "- No Week 9 data, current inactives, or official results were used.",
                  "- If 2025 and 2026 disagree, do not change published scores.",
                  ""])
    MD_OUT.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"validation":"PASSED",
        "2025":{k:v["2025"] for k,v in summary.items()},
        "2026":{k:v["2026"] for k,v in summary.items()},
        "paths":[str(x.relative_to(ROOT)) for x in (REPORT,CSV_OUT,MD_OUT)]},indent=2),flush=True)


if __name__=="__main__":main()
