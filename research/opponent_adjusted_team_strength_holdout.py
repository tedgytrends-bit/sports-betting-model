#!/usr/bin/env python3
"""Research-only NFL opponent-strength and schedule-adjusted team-form audit.

Test pregame Elo opponent strength and opponent-adjusted net scoring, separately
and together, as supplements to the unchanged 24-feature Baseline. Evaluate
chronologically on 2022W16-2026W8 using the exact 1,021 games in the archived
four-model research report. No 2026 Week 9 results, odds or injury data enter
the test. The publicly frozen Week 8/9 record and totals model are untouched.

Features are computed with STRICT point-in-time ordering:
- On each date, take all pregame Elo snapshots BEFORE updating ANY same-date
  final scores.
- For games in later dates, update Elo from completed prior games only.
- Regress ratings 25% to 1500 at each new season, with no future year leakage.
- Adjust each past team's net points by that opponent's PRE-game Elo strength
  and site; then average the last eight games strictly before the target date.
This is an exploratory score-margin model, not calibrated win probability.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
from research.standardized_player_injury_holdout import fit_weekly, metrics, feature_names

OUT=ROOT/"data"/"week09_review"
REF=ROOT/"data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv"
REPORT=OUT/"opponent_adjusted_team_strength_holdout_20261109.json"
PRED=OUT/"opponent_adjusted_team_strength_holdout_20261109.csv"
MD=OUT/"opponent_adjusted_team_strength_holdout_20261109.md"
SEASONS=(2021,2022,2023,2024,2025,2026)
EXPECTED={2022:45,2023:285,2024:285,2025:285,2026:121}
ELO_K=20.0
ELO_HFA=55.0
ELO_PER_POINT=25.0
SITE_ADVANTAGE_POINTS=2.2
ELO_REGRESSION=0.25
FORM_WINDOW=8
TESTS={
    "baseline_original":("base",False,10.0),
    "baseline_standardized":("base",True,10.0),
    "baseline_plus_elo":("elo",False,10.0),
    "baseline_plus_elo_standardized":("elo",True,10.0),
    "baseline_plus_elo_sos_form":("elo_sos",False,10.0),
    "baseline_plus_elo_sos_form_standardized":("elo_sos",True,10.0),
}

def team_alias(t):
    return "LA" if str(t).upper()=="LAR" else str(t).upper()


def pregame_elo_and_form(schedule:pd.DataFrame)->pd.DataFrame:
    """Apply strictly pregame Elo/SOS features, batched by date."""
    required={"game_id","season","week","gameday","home_team","away_team","home_score","away_score"}
    if not required.issubset(schedule.columns):
        raise ValueError("Schedule columns unavailable: "+str(required-set(schedule.columns)))
    raw=schedule.copy()
    raw["gameday"]=pd.to_datetime(raw.gameday,errors="coerce")
    raw=raw.dropna(subset=["gameday"]).sort_values(["gameday","game_id"])
    if raw.game_id.duplicated().any():raise ValueError("Duplicate schedule games")
    if not ((raw.season>=2021)&((raw.season<=2025)|((raw.season==2026)&(raw.week<=8)))).all():
        raise ValueError("Unexpected 2026 Week 9 or historical year in opponent ratings")

    ratings=defaultdict(lambda:1500.0)
    history=defaultdict(lambda:deque(maxlen=FORM_WINDOW))
    year=None
    output=[]
    for date, group in raw.groupby("gameday",sort=True):
        new_seasons=group.season.dropna().astype(int).unique().tolist()
        if len(new_seasons)!=1:raise ValueError(f"Multiple seasons share a date: {date}")
        season=int(new_seasons[0])
        if year is None:year=season
        elif year!=season:
            if season!=year+1:raise ValueError(f"Nonconsecutive season order {year}->{season}")
            for t in list(ratings):
                ratings[t]=1500.+(ratings[t]-1500.)*(1.-ELO_REGRESSION)
            year=season

        pending_updates=[]
        for g in group.itertuples(index=False):
            home,away=team_alias(g.home_team),team_alias(g.away_team)
            if home==away:raise ValueError("A team is playing itself")
            h,a=ratings[home],ratings[away]
            # True before-date Elo snapshots, not a team's eventual season rating.
            hp=1./(1.+10.**(-((h+ELO_HFA-a)/400.)))
            hf=list(history[home])
            af=list(history[away])
            strength_home=(h-1500.)/ELO_PER_POINT
            strength_away=(a-1500.)/ELO_PER_POINT
            home_rolling=float(np.mean(hf)) if hf else np.nan
            away_rolling=float(np.mean(af)) if af else np.nan
            output.append({
                "game_id":g.game_id,
                "home_elo_strength":strength_home,
                "away_elo_strength":strength_away,
                "elo_strength_diff":strength_home-strength_away,
                "elo_home_win_probability":hp,
                "home_opp_adj_margin_last8":home_rolling,
                "away_opp_adj_margin_last8":away_rolling,
                "opp_adj_margin_diff_last8":home_rolling-away_rolling,
                "home_opp_adj_games_last8":len(hf),
                "away_opp_adj_games_last8":len(af),
                "opponent_strength_asof":pd.Timestamp(date).isoformat(),
            })
            if pd.notna(g.home_score) and pd.notna(g.away_score):
                margin=float(g.home_score)-float(g.away_score)
                if not np.isfinite(margin):raise ValueError("Bad historical score")
                # Opponent-adjusted previous-game performance: playing a strong
                # opponent should make the same final margin look *better*.
                h_relative=margin+strength_away-SITE_ADVANTAGE_POINTS
                a_relative=-margin+strength_home+SITE_ADVANTAGE_POINTS
                pending_updates.append((home,away,hp,margin,h_relative,a_relative))
        # No current-day final score informs ANY earlier game on that day.
        for home,away,p,margin,home_relative,away_relative in pending_updates:
            if home==away:raise ValueError("Duplicate teams")
            observed=1. if margin>0 else 0. if margin<0 else .5
            # Fixed, prespecified log-margin dampening; prevents blowouts from
            # producing unbounded rating changes.
            multiplier=min(2.4,max(.6,np.log1p(abs(margin))/np.log(8.)))
            change=ELO_K*(observed-p)*multiplier
            ratings[home]+=change
            ratings[away]-=change
            history[home].append(home_relative)
            history[away].append(away_relative)
    result=pd.DataFrame(output)
    if result.game_id.duplicated().any() or len(result)!=len(raw):
        raise ValueError("Elo feature coverage is not one-to-one")
    return result


def synthetic_point_in_time_test():
    # Both games on Jan 1 see *exactly* neutral ratings; Jan 8 sees updated
    # values and strength from Jan 1. This protects against same-day leakage.
    demo=pd.DataFrame([
        {"game_id":"t1","season":2021,"week":1,"gameday":"2021-01-01","home_team":"A","away_team":"B","home_score":31,"away_score":7},
        {"game_id":"t2","season":2021,"week":1,"gameday":"2021-01-01","home_team":"C","away_team":"D","home_score":10,"away_score":20},
        {"game_id":"t3","season":2021,"week":2,"gameday":"2021-01-08","home_team":"A","away_team":"C","home_score":np.nan,"away_score":np.nan},
    ])
    obs=pregame_elo_and_form(demo).set_index("game_id")
    for t in ["t1","t2"]:
        if abs(float(obs.loc[t,"elo_strength_diff"]))>1e-9:raise ValueError("Same-date Elo leakage")
        if not np.isnan(obs.loc[t,"home_opp_adj_margin_last8"]):raise ValueError("Same-date form leakage")
    if obs.loc["t3","home_elo_strength"]<=0 or obs.loc["t3","away_elo_strength"]>=0:
        raise ValueError("Historical result not reflected in later Elo")
    if not np.isfinite(obs.loc["t3","opp_adj_margin_diff_last8"]):
        raise ValueError("Prior opponent adjusted form missing")


def main():
    synthetic_point_in_time_test()
    schedule=load_schedule_data()
    schedule=schedule[
        schedule.season.between(2021,2025)|
        ((schedule.season==2026)&(schedule.week<=8))
    ].copy()
    if schedule.empty:raise ValueError("Missing historical schedule")
    print("Create pregame-only Elo and schedule-adjusted form",flush=True)
    strength=pregame_elo_and_form(schedule)
    print("Load PBP and original efficiency feature builder",flush=True)
    pbp=load_pbp(SEASONS)
    base=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    originals=feature_names(base)
    if len(originals)!=24:raise ValueError(f"Unexpected baseline features {len(originals)}")
    enriched=base.merge(strength.drop(columns="opponent_strength_asof"),on="game_id",validate="one_to_one")
    elo_cols=["home_elo_strength","away_elo_strength","elo_strength_diff","elo_home_win_probability"]
    form_cols=["home_opp_adj_margin_last8","away_opp_adj_margin_last8",
               "opp_adj_margin_diff_last8","home_opp_adj_games_last8","away_opp_adj_games_last8"]
    available={
        "base":(base,originals),
        "elo":(enriched,originals+elo_cols),
        "elo_sos":(enriched,originals+elo_cols+form_cols),
    }
    candidates=[]
    for label,(group,scaled,alpha) in TESTS.items():
        data,features=available[group]
        print(f"Chronological fit: {label} ({len(features)} features)",flush=True)
        candidates.append(fit_weekly(data,features,scaled,alpha,label))
    joined=pd.concat(candidates,ignore_index=True)
    reference=pd.read_csv(REF,low_memory=False)
    ref=reference.loc[reference.model.eq("baseline")]
    if len(ref)!=1021 or ref.game_id.duplicated().any():
        raise ValueError("Historical baseline cohort changed")
    ids=set(ref.game_id)
    for label in TESTS:
        sample=joined[joined.research_variant.eq(label)]
        if set(sample.game_id)!=ids:
            raise ValueError(f"{label}: mismatching game IDs ({len(sample)} vs {len(ids)})")
    if joined.duplicated(["game_id","research_variant"]).any():raise ValueError("Duplicate predictions")
    baseline=joined.loc[joined.research_variant.eq("baseline_original")].set_index("game_id")
    older=ref.set_index("game_id")
    err=max(float(np.abs(baseline.pred_home-older.pred_home).max()),
            float(np.abs(baseline.pred_away-older.pred_away).max()))
    if err>1e-4:raise ValueError(f"Failed to reproduce saved baseline, score diff={err}")
    joined=joined.merge(
        ref[["game_id","spread_line","total_line"]],
        on="game_id",how="left",validate="many_to_one")
    if joined[["spread_line","home_score","away_score"]].isna().any().any():
        raise ValueError("Historical games or lines missing")
    summary={}
    for label in TESTS:
        x=joined[joined.research_variant.eq(label)]
        years={str(int(y)):metrics(g) for y,g in x.groupby("season")}
        if {int(k) for k in years}!=set(EXPECTED):raise ValueError(f"Incomplete years: {label}")
        if any(v["games"]!=EXPECTED[int(y)] for y,v in years.items()):
            raise ValueError(f"Unexpected seasonal count: {label}")
        years["2025_and_2026_1_8"]=metrics(x[x.season>=2025])
        summary[label]=years
    report={
        "status":"RESEARCH_ONLY_OPPONENT_ADJUSTED_TEAM_STRENGTH",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "model_family":"Ridge(alpha=10) Baseline vs opponent-adjusted Elo and past-margin form; no market odds as feature",
        "data_window":"2021 training; 2022 Week 16–2026 Week 8 chronological test; Week 9 fully excluded",
        "elo_parameters":{
            "neutral_initial_rating":1500,"home_advantage_rating":ELO_HFA,
            "k":ELO_K,"rating_points_per_game_point":ELO_PER_POINT,
            "prior_season_regression_frac":ELO_REGRESSION,
            "form_window_games":FORM_WINDOW,"site_adjustment_points":SITE_ADVANTAGE_POINTS,
        },
        "leakage_guards":"Compute same-date features before any scores update Elo; train-only medians/scalers and past games only",
        "synthetic_time_guard":"PASSED",
        "baseline_saved_score_max_difference":err,
        "historical_reference":str(REF.relative_to(ROOT)),
        "historical_spread_reference":"nflverse archived schedule, not executable Bovada pregame lines",
        "variants":{k:{"features":len(available[v[0]][1]),"standardized_on_prior_train_only":v[1]} for k,v in TESTS.items()},
        "by_year":summary,
        "limitations":[
            "Post-hoc exploratory hypotheses motivated by 2026 Week 9 errors; 2025 and 2026 are not pristine unseen data.",
            "Elo parameters are fixed heuristics and require future independent validation.",
            "Elo adjusted last-eight scoring form uses previous opponent pregame Elo and actual past score, not true opponent-adjusted EPA.",
            "QB injuries and player-role values are not included in this experiment.",
            "No Week 9 or MNF outcomes and no future scores used for historical predictions.",
            "History from 2021 only; preseason priors begin at neutral rather than rosters/rating sources.",
            "No code for published baseline/injury/totals or official results has been modified.",
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    joined.sort_values(["season","week","game_id","research_variant"]).to_csv(PRED,index=False)
    REPORT.write_text(json.dumps(report,indent=2)+"\n")
    lines=["# Opponent-adjusted NFL team strength: walk-forward experiment",
           "",
           "**Research only.** This test does not change Tedgy Trends' public projections, totals, or official records.",
           "Game-by-game opponent Elo and strength-of-schedule-adjusted recent form are computed before kickoff.",
           "Identical 1,021 games; 2025 and 2026 Weeks 1–8 reported separately.",
           "",
           "| Variant | 2025 ATS | 2025 ≥3.5 pts | 2025 margin MAE | 2026 W1–8 ATS | 2026 ≥3.5 pts | 2026 margin MAE |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    def rec(x):
        y=x["ATS_all_games"]
        return f"{y['wins']}–{y['losses']}–{y['pushes']}"
    def e35(x):
        y=x["ATS_min_edge_3_5"]
        return f"{y['wins']}–{y['losses']}–{y['pushes']}"
    for label,yrs in summary.items():
        a=yrs["2025"];b=yrs["2026"]
        lines.append(f"| {label} | {rec(a)} | {e35(a)} | {a['margin_mae']:.2f} | {rec(b)} | {e35(b)} | {b['margin_mae']:.2f} |")
    lines.extend(["",
                  "## Validation and decision",
                  "",
                  f"- Historical Baseline replication max absolute score difference: {err:.8f}.",
                  "- 2021 is training only; 2022 is a partial evaluation; 2023–2025 complete evaluated seasons.",
                  "- Evaluate MAE, ATS directional win rate and conditional edge results together, not merely favorites.",
                  "- No optimizer chose Elo features based on Week 9 or MNF; this is a **shadow** research comparison.",
                  "- Require stable year-over-year improvement and new prospective weeks before considering a public replacement.",
                  ""])
    MD.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":report["status"],
                      "baseline_reproduction_diff":err,
                      "2025":{k:v["2025"] for k,v in summary.items()},
                      "2026_weeks1_8":{k:v["2026"] for k,v in summary.items()},
                      "files":[str(x.relative_to(ROOT)) for x in [REPORT,MD,PRED]]},indent=2),flush=True)


if __name__=="__main__":
    main()
