#!/usr/bin/env python3
"""Publish immutable *initial* 2026 Week 10 Baseline and QB-aware Injury forecasts.

Run ONLY before Thursday kickoff. This first public version is intentionally
marked provisional as not all starting QBs have been independently confirmed.
Saturday/Sunday refreshed forecasts must have a new filename, never overwrite
this captured, prospective version or the initial user-supplied Bovada prices.

Research/prospectively published numbers do not imply profitable betting advice.
Uses nflverse and the already committed injury snapshot; consumes no paid APIs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from model import (load_schedule_data, load_pbp, build_efficiency_model_dataset,
                   project_upcoming_efficiency)
from injury_model import load_injury_reports, project_qb_aware_injury, _kickoff_utc
from scripts.capture_qb_aware_injury import (
    SEASONS,load_coach_expected_starters,add_verified_only_sensitivity,
    reject_known_inactive_qb,
)
from research.validate_qb_starter_confirmations import validate_starter_confirmations

PUB=ROOT/"data"/"public_snapshots"
OUT=PUB/"nfl_week10_initial_projections_2026-11-12.csv"
META=PUB/"nfl_week10_initial_projections_2026-11-12_manifest.json"
MARKET=PUB/"nfl_week10_bovada_initial_2026-11-12.csv"
WATCH=ROOT/"data"/"qb_starters"/"2026_week10_watchlist.csv"
CONFIRMED=ROOT/"data"/"qb_starters"/"2026_week10_confirmed.csv"
SEASON,WEEK,EXPECTED=2026,10,14


def subset(df, label):
    target=df.loc[
        pd.to_numeric(df["season"],errors="coerce").eq(SEASON)
        & pd.to_numeric(df["week"],errors="coerce").eq(WEEK)
    ].copy()
    if len(target)!=EXPECTED or target.game_id.nunique()!=EXPECTED:
        raise ValueError(f"{label}: expected {EXPECTED} unique Week 10 games, got {len(target)}")
    return target


def main():
    if OUT.exists() or META.exists():
        raise FileExistsError("Immutable Week 10 initial public release already exists; do not rewrite")
    now=datetime.now(timezone.utc).replace(microsecond=0)
    captured=pd.Timestamp(now)
    schedule=load_schedule_data()
    target=subset(schedule,"NFL schedule")
    kickoffs={}
    for g in target.to_dict("records"):
        time=_kickoff_utc(pd.Series(g))
        if pd.isna(time):
            raise ValueError(f"Unknown kickoff time: {g['game_id']}")
        if time<=captured:
            raise ValueError(f"Cannot publish initial Week 10 board after kickoff: {g['game_id']}")
        kickoffs[g["game_id"]]=time.isoformat().replace("+00:00","Z")

    if not MARKET.exists():
        raise FileNotFoundError("User Bovada Thursday screenshot snapshot missing")
    quotes=pd.read_csv(MARKET)
    if len(quotes)!=EXPECTED or quotes.duplicated(["away_team","home_team"]).any():
        raise ValueError("Expected exactly 14 unique Thursday Bovada quotes")
    def canonical(code):
        return "LA" if str(code).upper()=="LAR" else str(code).upper()
    book={(canonical(q.away_team),canonical(q.home_team)):q for q in quotes.itertuples()}
    for g in target.itertuples():
        if (canonical(g.away_team),canonical(g.home_team)) not in book:
            raise ValueError(f"Missing Bovada screenshot quote for {g.game_id}")

    pbp=load_pbp(SEASONS)
    features=build_efficiency_model_dataset(schedule,pbp,lookback_games=10)
    baseline=subset(project_upcoming_efficiency(features,min_train_games=500),"Baseline")
    reports=load_injury_reports(SEASONS)

    overrides=None
    rejected=[]
    if CONFIRMED.exists():
        raw=pd.read_csv(CONFIRMED,dtype=str,keep_default_na=False)
        verified,metadata=validate_starter_confirmations(
            schedule,raw,checked_as_of_utc=now
        )
        rejected=metadata.loc[~metadata.override_eligible,
            ["game_id","team","eligibility_reason"]].to_dict("records")
        overrides=verified if not verified.empty else None
    expected=load_coach_expected_starters(schedule,SEASON,WEEK)
    injury,board=project_qb_aware_injury(
        schedule,pbp,reports,season=SEASON,week=WEEK,
        verified_starters=overrides,expected_starters=expected
    )
    injury=subset(injury,"Injury")
    if WATCH.exists():
        reject_known_inactive_qb(board,pd.read_csv(WATCH,dtype=str,keep_default_na=False))
    injury=add_verified_only_sensitivity(injury,board)
    if len(board)!=2*EXPECTED or board.duplicated(["game_id","team"]).any():
        raise AssertionError("Incomplete Week 10 QB detail")
    if (injury.projected_home+injury.projected_away-injury.projected_total).abs().max()>1e-6:
        raise AssertionError("Injury score sum is not the model total")
    if (baseline.projected_home+baseline.projected_away-baseline.projected_total).abs().max()>1e-6:
        raise AssertionError("Baseline score sum is not the model total")

    rows=[]
    for model,frame in (("baseline",baseline),("injury",injury)):
        for row in frame.to_dict("records"):
            gameid=row["game_id"]
            home,away=canonical(row["home_team"]),canonical(row["away_team"])
            quote=book[(away,home)]
            a,h,t=[float(row[k]) for k in ("projected_away","projected_home","projected_total")]
            if not all(np.isfinite(v) and 0<=v<=75 for v in (a,h,t)):
                raise ValueError(f"Nonfinite/outlying model score {gameid} {model}")
            if abs(a+h-t)>0.02:
                raise ValueError(f"Projected total mismatch {gameid} {model}")
            rows.append({
                "published_at_utc":now.isoformat().replace("+00:00","Z"),
                "publication_status":"INITIAL_PUBLIC_PREGAME_2026_WEEK10_PROVISIONAL_QB",
                "game_id":gameid,
                "season":SEASON,"week":WEEK,
                "gameday":pd.to_datetime(row["gameday"]).strftime("%Y-%m-%d"),
                "kickoff_utc":kickoffs[gameid],
                "away_team":away,"home_team":home,
                "model":model,
                "model_version":"baseline_ridge_alpha10_lookback10" if model=="baseline"
                    else "qb_epa_margin_cap5_v1_provisional",
                "projected_away":round(a,6),
                "projected_home":round(h,6),
                "projected_total":round(t,6),
                "model_home_margin":round(h-a,6),
                "training_games":int(row["training_games"]),
                "home_injury_report_available":row.get("home_injury_report_available",""),
                "away_injury_report_available":row.get("away_injury_report_available",""),
                "home_qb_name":row.get("home_qb_name",""),
                "away_qb_name":row.get("away_qb_name",""),
                "home_qb_starter_source":row.get("home_starter_source",""),
                "away_qb_starter_source":row.get("away_starter_source",""),
                "qb_margin_adjustment":row.get("qb_margin_adjustment",""),
                "original_non_qb_home":row.get("original_non_qb_home",""),
                "original_non_qb_away":row.get("original_non_qb_away",""),
                "verified_only_projected_home":row.get("verified_only_projected_home",""),
                "verified_only_projected_away":row.get("verified_only_projected_away",""),
                "both_qbs_source_verified":row.get("both_qbs_source_verified",""),
                "bovada_home_favored_spread_initial":float(quote.home_favorite_spread),
                "bovada_total_initial":float(quote.total_line),
                "bovada_snapshot_at_utc":str(quote.captured_at_utc),
                "source_note":"Initial published BEFORE Thursday kickoff. QB identities may be provisional; Sunday final pending.",
            })
    result=pd.DataFrame(rows).sort_values(["kickoff_utc","game_id","model"]).reset_index(drop=True)
    if len(result)!=2*EXPECTED or result.duplicated(["game_id","model"]).any():
        raise AssertionError("Initial release missing or duplicating model per game")
    if not result.groupby("game_id")["kickoff_utc"].nunique().eq(1).all():
        raise AssertionError("Kickoff disagreement across models")
    if not result.groupby("game_id")["bovada_home_favored_spread_initial"].nunique().eq(1).all():
        raise AssertionError("Market sign disagreement across models")

    sources=board.starter_source.value_counts().to_dict()
    summary={
        "status":"INITIAL_PUBLIC_PREGAME_2026_WEEK10_PROVISIONAL_QB",
        "published_at_utc":now.isoformat().replace("+00:00","Z"),
        "games":EXPECTED,"rows":len(result),
        "models":["baseline","injury"],
        "report_path":str(OUT.relative_to(ROOT)),
        "market_initial_path":str(MARKET.relative_to(ROOT)),
        "market_source":"Bovada screenshots user sent Thursday Nov 12 ~07:20-07:21 CT, not an authenticated sportsbook quote timestamp",
        "model_training":"Completed nflverse games through prior week; unscaled Ridge(alpha=10), ten-game team lookback, existing production model coefficients unmodified",
        "injury_data":"Public nflverse injury feed; latest saved Week 10 injury snapshot preferred when point-in-time eligible",
        "starter_source_counts":sources,
        "verified_starters":int(board.starter_source.eq("verified_pregame").sum()),
        "two_verified_teams_games":int(injury.both_qbs_source_verified.sum()),
        "source_rejected_rows":rejected,
        "known_out_or_ir_watchlist_checked":WATCH.exists(),
        "release_ready_final_injury":bool(board.starter_source.eq("verified_pregame").all()),
        "results_record_policy":"Initial publication is preserved and may be graded as its own forward public snapshot. A later Week 10 final model and market snapshot must be saved separately and selected for prospective grade BEFORE each kickoff, not retroactively.",
        "warning":"Model starter names and injury inputs may remain provisional; these are INITIAL public estimates, NOT confirmed final pregames. No retroactive Week 8/9 changes and no claims of betting profitability.",
    }
    PUB.mkdir(parents=True,exist_ok=True)
    result.to_csv(OUT,index=False)
    META.write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("warning","model_training","results_record_policy")},indent=2))
    print(result.loc[result.model=="injury",[
        "game_id","projected_away","projected_home","projected_total",
        "away_qb_name","home_qb_name","home_qb_starter_source"
    ]].to_string(index=False))


if __name__=="__main__":
    main()
