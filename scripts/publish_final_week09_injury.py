#!/usr/bin/env python3
"""Publish ONE Week 9 final pregame QB-EPA injury forecast for 14 unplayed games.

Reuses production model/injury_model.py and the recorded source-verified QB
overrides. This release is intentionally immutable once captured and NEVER
rewrites the original 2026 W9 Thu forecasts or historical model records.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import load_schedule_data, load_pbp
from injury_model import load_injury_reports, project_qb_aware_injury, _kickoff_utc
from scripts.capture_qb_aware_injury import SEASONS

PUB = ROOT / "data" / "public_snapshots"
OUT = PUB / "nfl_week09_final_injury_2026-11-08.csv"
META = PUB / "nfl_week09_final_injury_2026-11-08_manifest.json"
STARTERS = ROOT / "data" / "qb_starters" / "2026_week09_confirmed.csv"
FROZEN = PUB / "nfl_week_09_six_model_research_2026-11-04.csv"
MARKET = ROOT / "data" / "bovada_lines.csv"
INJURY_DIR = ROOT / "data" / "injury_snapshots"
WEEK = 9
SEASON = 2026
TNF_ID = "2026_09_JAX_BAL"
EXPECTED_FINAL_GAMES = 14


def load_sources():
    archive = pd.read_csv(FROZEN)
    subset = archive.loc[archive["model"].eq("baseline")]
    if len(subset) != 15 or subset.game_id.duplicated().any():
        raise ValueError("Original immutable Week 9 model archive was modified")
    targets = set(subset.game_id) - {TNF_ID}
    if len(targets) != EXPECTED_FINAL_GAMES:
        raise ValueError("Expected precisely 14 pre-Sunday target games")
    quotes = pd.read_csv(MARKET)
    quotes = quotes.loc[
        pd.to_numeric(quotes.season, errors="coerce").eq(SEASON)
        & pd.to_numeric(quotes.week, errors="coerce").eq(WEEK)
    ]
    quotes = quotes.sort_values("captured_at_utc").drop_duplicates(
        ["away_team", "home_team"], keep="last"
    )
    if len(quotes) != 15:
        raise ValueError("Market archive does not have all 15 Week 9 games")
    latest_snapshots = sorted(INJURY_DIR.glob("injuries_2026_week_09_*.csv"))
    if not latest_snapshots:
        raise ValueError("Missing latest saved official injury report snapshot")
    snapshot = latest_snapshots[-1]
    raw = pd.read_csv(snapshot)
    teams = set(raw.team.dropna().astype(str))
    scheduled_teams = {"LA" if t == "LAR" else t for t in (set(subset.away_team) | set(subset.home_team))}
    if not scheduled_teams.issubset(teams):
        raise ValueError(f"Missing injury report teams: {scheduled_teams - teams}")
    capture = pd.to_datetime(snapshot.stem.rsplit("_", 1)[-1],
                             utc=True, format="%Y%m%dT%H%M%SZ")
    if capture < pd.Timestamp("2026-11-07T18:00:00Z"):
        raise ValueError("Injury report snapshot predates final Friday designations")
    overrides = pd.read_csv(STARTERS, dtype={"qb_id":str}).fillna("")
    if overrides.duplicated(["game_id", "team"]).any():
        raise ValueError("Duplicate verified starter selections")
    return targets,quotes,snapshot,raw,overrides


def main():
    if OUT.exists():
        raise FileExistsError(f"Refusing to rewrite published official Week 9 record: {OUT}")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expected,quotes,snapshot,injury_raw,overrides = load_sources()
    schedule = load_schedule_data()
    sched = schedule[schedule.game_id.isin(expected)].copy()
    if len(sched) != EXPECTED_FINAL_GAMES:
        raise ValueError(f"Schedule match count {len(sched)} isn't 14")
    for _, game in sched.iterrows():
        kickoff = _kickoff_utc(game)
        if pd.isna(kickoff):
            raise ValueError("Kickoff timestamp could not be validated: "+str(game.game_id))
        if kickoff <= pd.Timestamp(now):
            raise ValueError("Refusing to publish model scores after kickoff: "+str(game.game_id))
    pbp=load_pbp(SEASONS)
    reports=load_injury_reports(SEASONS)
    pred,qb=project_qb_aware_injury(
        schedule,pbp,reports,season=SEASON,week=WEEK,verified_starters=overrides
    )
    if len(pred)!=EXPECTED_FINAL_GAMES or set(pred.game_id)!=expected:
        raise ValueError(f"Expected 14 *upcoming* games, got {len(pred)}; "
                         f"missing {expected-set(pred.game_id)}, excess {set(pred.game_id)-expected}")
    if qb.duplicated(["game_id","team"]).any() or len(qb)!=28:
        raise ValueError("Incomplete or duplicate QB identities")
    # The reusable QB engine calls these home_starter_source/away_starter_source.
    # Keep the public Injury archive schema consistent with the existing site.
    pred = pred.rename(columns={
        "home_starter_source": "home_qb_starter_source",
        "away_starter_source": "away_qb_starter_source",
    })
    if pred.game_id.duplicated().any():
        raise ValueError("Duplicate games")
    fields=["projected_home","projected_away","projected_total",
            "home_qb_name","away_qb_name","home_qb_starter_source",
            "away_qb_starter_source","home_injury_report_available",
            "away_injury_report_available"]
    for col in fields:
        if col not in pred.columns or pred[col].isna().any():
            raise ValueError(f"Missing final pregame input: {col}")
    for col in ["home_injury_report_available","away_injury_report_available"]:
        if not pred[col].eq(1).all():
            raise ValueError(f"Not all Week 9 injury reports available: {col}")
    for col in ["projected_home","projected_away","projected_total"]:
        values=pd.to_numeric(pred[col],errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy()).all():
            raise ValueError(f"Non-finite scoring values: {col}")
        if (values<0).any() or (values>75).any():
            raise ValueError(f"Outlier scoring value: {col}")
    if (pred.projected_home+pred.projected_away-pred.projected_total).abs().max() > .02:
        raise ValueError("Invalid final projected total")
    # Respect source-confirmed QB changes and guard against publishing invalid
    # starter IDs where the feed explicitly rules them OUT.
    for r in qb.itertuples(index=False):
        reported=injury_raw.loc[
            injury_raw.team.eq(r.team)&injury_raw.gsis_id.eq(r.qb_id)]
        if reported.report_status.fillna("").str.upper().eq("OUT").any():
            raise ValueError(f"Projected QB explicitly OUT: {r.game_id} {r.qb_name}")
    mandatory={
        ("2026_09_CLE_NO","CLE"):"Shedeur Sanders",
        ("2026_09_ARI_SEA","SEA"):"Drew Lock",
        ("2026_09_ARI_SEA","ARI"):"Gardner Minshew",
        ("2026_09_BUF_MIN","MIN"):"Carson Wentz",
        ("2026_09_NYG_PHI","PHI"):"Joe Milton III",
        ("2026_09_NYG_PHI","NYG"):"J.J. McCarthy",
    }
    for (game_id,team),name in mandatory.items():
        rows=qb.loc[qb.game_id.eq(game_id)&qb.team.eq(team)]
        if len(rows)!=1 or rows.iloc[0].qb_name!=name or rows.iloc[0].starter_source!="verified_pregame":
            raise ValueError(f"Key starter mismatch: {game_id}, {team} expected {name}")
    pred["published_at_utc"]=now.isoformat()
    pred["model"]="injury"
    pred["model_version"]="qb_epa_margin_cap5_v1"
    pred["publication_status"]="FINAL_PREGAME_2026_WEEK09_SUN_MON"
    pred["source_injury_snapshot"]=str(snapshot.relative_to(ROOT))
    # This snapshot captures as-of publication for Sunday/Monday, and doesn't
    # rewrite Thursday TNF or the official Week 8 record.
    pred=pred.sort_values(["gameday","game_id"]).reset_index(drop=True)
    PUB.mkdir(parents=True,exist_ok=True)
    pred.to_csv(OUT,index=False)
    manifest={
        "status":"ONE_FINAL_PREGAME_INJURY_SNAPSHOT_FOR_UNPLAYED_GAMES",
        "published_at_utc":now.isoformat(),
        "model":"injury","model_version":"qb_epa_margin_cap5_v1",
        "week":WEEK,"season":SEASON,"number_of_games":len(pred),
        "game_ids":pred.game_id.tolist(),
        "excluded_completed_tnf":TNF_ID,
        "source_injury_snapshot":str(snapshot.relative_to(ROOT)),
        "injury_source_teams":len(set(injury_raw.team.dropna())),
        "source_bovada_market":str(MARKET.relative_to(ROOT)),
        "verified_starter_count":int(qb.starter_source.eq("verified_pregame").sum()),
        "provisional_starter_count":int(qb.starter_source.eq("schedule_provisional_qb_unverified").sum()),
        "starter_disclaimer":"Pregame starter confirmations and NFLverse provisional listings can change; no guarantee of confirmed game-day inactives",
        "data_warning":"Final is a pregame timestamped model release, not a claim all inactives known; new Saturday/Sunday updates after publication aren't included.",
        "original_archive_unchanged":str(FROZEN.relative_to(ROOT)),
        "record_policy":"This final Sun/Mon release is the one public forward projection for these 14 games. Original Thursday frozen results stay archived, never overwritten.",
        "retrospective_2026_backtest_not_prospective_proof":True,
    }
    META.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2),flush=True)
    print(pred[["game_id","projected_away","projected_home","projected_total",
                 "away_qb_name","home_qb_name"]].to_string(index=False),flush=True)

if __name__=="__main__":
    main()
