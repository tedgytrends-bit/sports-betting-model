#!/usr/bin/env python3
"""Four-model, same-game, week-by-week chronological NFL research audit.

This reproduces the four ORIGINAL model configurations:
  baseline   = frozen 24-feature efficiency scoring model
  injury     = baseline + 32 historical injury features (legacy, pre QB EPA)
  efficiency = baseline + 57 passing/rushing split, matchup and pace features
  combined   = both extra feature groups

IMPORTANT: The current QB-EPA Injury v1 is NOT the 'injury' column here.
Historical pregame identities for QB replacements are not verified for this
full-period audit. Do not retrofit the QB-EPA v1 2026-tuned model as if it had
been used in 2022-2025. All games/lines are from nflverse historical schedule.
The public prospective record is entirely separate and unchanged.
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

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
from injury_model import load_injury_reports, add_injury_features
from research.efficiency_feature_experiments import (
    _team_split_history, _pregame_split_features, _fit_weekly
)

OUT = ROOT / "data" / "four_model_historical"
TRAIN_MIN = 500
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
REPORT_SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
EXCLUDE = {"game_id", "gameday", "season", "week", "home_team", "away_team",
           "home_score", "away_score", "spread_line", "total_line"}

def features(df):
    return [
        c for c in df.columns if c not in EXCLUDE
        and pd.api.types.is_numeric_dtype(df[c])
    ]


def grade(frame):
    result = {"games": int(len(frame))}
    margin = frame["pred_home"] - frame["pred_away"]
    actual = frame["home_score"] - frame["away_score"]
    line = pd.to_numeric(frame["spread_line"], errors="coerce")
    valid = line.notna() & margin.notna() & actual.notna()
    graded = frame.loc[valid].copy()
    predicted_edge = margin.loc[valid] - line.loc[valid]
    actual_cover = actual.loc[valid] - line.loc[valid]
    # A projected tie with market has no directional pick and must not be
    # assigned an arbitrary winner. A market push is always a push.
    nonzero = predicted_edge.ne(0)
    wins = int(((predicted_edge * actual_cover) > 0).sum())
    losses = int(((predicted_edge * actual_cover) < 0).sum())
    pushes = int((actual_cover.eq(0) & nonzero).sum())
    no_lean = int((~nonzero).sum())
    missing = int(len(frame) - len(graded))
    assert wins + losses + pushes + no_lean == len(graded)
    result.update({
        "market_coverage": int(len(graded)), "missing_market_line": missing,
        "wins": wins, "losses": losses, "pushes": pushes, "no_lean": no_lean,
        "win_pct_ex_push": round(100*wins/(wins+losses), 3) if wins+losses else None,
        "margin_mae": round(float(np.abs(margin - actual).mean()), 4),
    })
    return result


def main():
    print("Load historical schedule, PBP, and timestamp-filtered injury reports",flush=True)
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)
    base = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    original = features(base)
    if len(original) != 24:
        raise RuntimeError(f"Baseline should have 24 features, got {len(original)}")
    inj = add_injury_features(base, schedule, reports)
    inj_extra = [c for c in features(inj) if c not in original]
    split = _pregame_split_features(schedule, _team_split_history(pbp, schedule))
    extra = [c for c in split.columns if c != "game_id"]
    eff = base.merge(split, on="game_id", how="left", validate="one_to_one")
    eff_extra = [c for c in features(eff) if c not in original]
    combined = inj.merge(split, on="game_id", how="left", validate="one_to_one")
    chosen = {
        "baseline": (base, original),
        "injury_legacy": (inj, original + inj_extra),
        "efficiency": (eff, original + eff_extra),
        "combined_legacy": (combined, original + inj_extra + eff_extra),
    }
    counts = {name: len(cols) for name, (_df, cols) in chosen.items()}
    if counts != {"baseline":24,"injury_legacy":56,"efficiency":81,"combined_legacy":113}:
        raise RuntimeError(f"Feature sets don't match Week 9: {counts}")
    common_cols = ["game_id", "gameday", "season", "week", "home_team", "away_team",
                   "home_score", "away_score"]
    market = schedule[["game_id","spread_line","total_line"]].drop_duplicates("game_id")
    predictions = []
    for name, (dataset, cols) in chosen.items():
        print(f"Fitting weekly {name}: {len(cols)} features",flush=True)
        frame = dataset[common_cols+cols].copy()
        frame["gameday"] = pd.to_datetime(frame["gameday"], errors="coerce")
        p = _fit_weekly(frame, cols)
        if p.empty or p.game_id.duplicated().any():
            raise ValueError(f"Missing or duplicate predictions for {name}")
        p["model"]=name
        predictions.append(p[common_cols+["model","pred_home","pred_away"]])
    out = pd.concat(predictions,ignore_index=True)
    common = set.intersection(*[set(x.game_id) for x in predictions])
    out = out[out.game_id.isin(common)].merge(
        market,on="game_id",how="left",validate="many_to_one"
    )
    counts_by_model=out.groupby("model")["game_id"].nunique()
    if counts_by_model.nunique()!=1 or out.duplicated(["game_id","model"]).any():
        raise ValueError("Nonidentical or duplicate game sets")
    out["season"]=pd.to_numeric(out["season"],errors="coerce")
    out=out[out.season.isin(REPORT_SEASONS)].copy()
    if not out.season.between(2022,2026).all():
        raise ValueError("Unexpected season in holdout")
    results=[]
    for model,g in out.groupby("model"):
        results.append({"season":"All evaluated","model":model,**grade(g)})
        for season, sub in g.groupby("season"):
            results.append({"season":int(season),"model":model,**grade(sub)})
    results=pd.DataFrame(results)
    results=results.sort_values(["season","model"],key=lambda c:c.astype(str))
    # Guard: same actual game set and same lines for all four.
    schedule_set=out.groupby(["season","model"])["game_id"].nunique().unstack()
    if not schedule_set.notna().all().all() or not (schedule_set.nunique(axis=1)==1).all():
        raise ValueError("Season-level game samples are not identical")
    # For the 2022-2025 request, the 2021 season is training only.
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(parents=True,exist_ok=True)
    preds=OUT / f"four_model_all_game_predictions_{stamp}.csv"
    summ=OUT / f"four_model_ats_by_season_{stamp}.csv"
    report=OUT / f"four_model_ats_manifest_{stamp}.json"
    out.to_csv(preds,index=False)
    results.to_csv(summ,index=False)
    msg={
        "status":"RESEARCH_ONLY_CHRONOLOGICAL_RECONSTRUCTION",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "season_2021":"TRAINING ONLY; no evaluated games at 500-game min train",
        "models":counts,
        "injury_warning":"Legacy Injury used in the historical 4-way comparison. This is not the QB-EPA Injury v1 developed during 2026.",
        "market_warning":"Uses nflverse schedule spread_line as the one common historical market reference, not verified live Bovada executable prices.",
        "train_scheme":"Chronological calendar-week blocks. Train only on prior dates with >=500 completed games. Ridge alpha 10; identical weekly folds.",
        "training_seasons":list(SEASONS),
        "record_rule":"Grade each game's directional ATS lean, no edge minimum; pushes excluded from win pct; projection exactly on spread has no lean.",
        "comparison_games":int(len(common)),
        "csv_predictions":str(preds.relative_to(ROOT)),
        "csv_summary":str(summ.relative_to(ROOT)),
        "public_record":"Untouched (starts Week 8, 2026).",
    }
    report.write_text(json.dumps(msg,indent=2)+"\n")
    print(results.to_string(index=False),flush=True)
    print(json.dumps(msg,indent=2),flush=True)

if __name__=="__main__":
    main()
