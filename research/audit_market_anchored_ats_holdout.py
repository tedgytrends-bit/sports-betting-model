#!/usr/bin/env python3
"""Shadow market-anchored ATS model from four archived chronological NFL models.

PURPOSE: Diagnose why extreme Week 9 directional ATS edges failed. No code,
predictions, or records used by the public site are changed.

Data: 1,021 historical *pre-game* chronological per-model predictions, from
2022 W16 through 2026 W8. The 2025 test trains only on 2022-24 games. The 2026
test trains only on 2022-25 games. 2026 W9 actual scores, injuries, and live
odds are entirely excluded. The historical odds come from nflverse closing
lines; these are not verified, executable Bovada wagers.

We compare:
  - raw Baseline, legacy Injury, Efficiency and Combined margins
  - untrained simple four-model consensus
  - market + half of the consensus edge (ATS side unchanged, lower edge)
  - Ridge residual model using four pre-game model edges and recorded market
    spread, with train-only StandardScaler and fixed alpha=100.
The same completed games and lines are used in every evaluation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv"
OUTDIR = ROOT / "data/week09_review"
JSON_OUT = OUTDIR / "ats_market_anchored_holdout_20261109.json"
CSV_OUT = OUTDIR / "ats_market_anchored_holdout_20261109.csv"
MARKDOWN = OUTDIR / "ats_market_anchored_holdout_20261109.md"

MODELS = ("baseline", "injury_legacy", "efficiency", "combined_legacy")
ALPHA = 100.0  # Chosen before seeing the sealed 2025 and 2026 holdouts.
EDGE_GATES = (0.0, 1.5, 2.5, 3.5)
MIN_TRAIN = 500
IDENTITY = ["game_id", "gameday", "season", "week", "home_score", "away_score", "spread_line"]


def load_common_games():
    frame = pd.read_csv(INPUT, low_memory=False)
    needed = set(IDENTITY + ["model", "pred_home", "pred_away"])
    if not needed.issubset(frame.columns):
        raise ValueError(f"Archive missing {needed-set(frame.columns)}")
    if set(frame.model.unique()) != set(MODELS):
        raise ValueError(f"Model sets changed: {set(frame.model.unique())}")
    if frame.duplicated(["game_id", "model"]).any():
        raise ValueError("Duplicate model per game")
    counts = frame.groupby("game_id").model.nunique()
    if len(counts) != 1021 or not counts.eq(4).all():
        raise ValueError("Expected 1021 identical 4-model game sets")
    ref = frame.loc[frame.model.eq("baseline"), IDENTITY].copy()
    ref["gameday"] = pd.to_datetime(ref.gameday)
    ref["actual_home_margin"] = ref.home_score - ref.away_score
    ref = ref.rename(columns={"spread_line": "market_home_margin"})
    data = ref.copy()
    for model in MODELS:
        tmp = frame.loc[frame.model.eq(model), ["game_id", "pred_home", "pred_away"]].copy()
        tmp[model] = tmp.pred_home - tmp.pred_away
        data = data.merge(tmp[["game_id", model]], on="game_id", how="inner", validate="one_to_one")
    if data.isna().any().any() or not np.isfinite(data.select_dtypes(include="number").to_numpy()).all():
        raise ValueError("Missing or non-finite input data")
    if data.season.min() != 2022 or data.season.max() != 2026 or data.loc[data.season.eq(2026), "week"].max() > 8:
        raise ValueError("Unexpected chronology or possible Week 9 leakage")
    per_year = data.groupby("season").size().to_dict()
    if per_year != {2022: 45, 2023: 285, 2024: 285, 2025: 285, 2026: 121}:
        raise ValueError(f"Unexpected year breakdown {per_year}")
    data["consensus_margin"] = data[list(MODELS)].mean(axis=1)
    data["half_market_consensus"] = (
        data.market_home_margin + 0.5*(data.consensus_margin-data.market_home_margin)
    )
    data["market_edge_actual"] = data.actual_home_margin - data.market_home_margin
    for model in MODELS:
        data[f"{model}_market_edge"] = data[model]-data.market_home_margin
    # A small shared feature set, all available before kickoff. No player,
    # opponent, or outcome data is used beyond archived pregame model margins.
    features = [f"{model}_market_edge" for model in MODELS] + ["market_home_margin"]
    return data, features


def metrics(frame, pred_column, minimum_edge=0.0):
    margin = pd.to_numeric(frame[pred_column], errors="raise").to_numpy(dtype=float)
    actual = frame.actual_home_margin.to_numpy(dtype=float)
    line = frame.market_home_margin.to_numpy(dtype=float)
    deviations = margin - line
    actual_deviations = actual-line
    # Zero predicted market edge yields a PASS, not a fabricated wager.
    mask = (np.abs(deviations) > max(1e-9, minimum_edge))
    selected = mask.sum()
    valid = (np.abs(actual_deviations) > 1e-9)
    wins = int((mask & valid & ((deviations * actual_deviations) > 0)).sum())
    losses = int((mask & valid & ((deviations * actual_deviations) < 0)).sum())
    pushes = int((mask & ~valid).sum())
    if wins+losses+pushes != selected:
        raise ValueError("Unaccounted ATS outcome")
    profit = wins*100/110-losses  # 1 unit risked at synthetic -110
    return {
        "games":int(len(frame)),
        "min_abs_ats_edge":minimum_edge,
        "bets":int(selected),
        "wins":wins,"losses":losses,"pushes":pushes,
        "win_rate_ex_push":round(100*wins/(wins+losses),3) if wins+losses else None,
        "net_units_minus110":round(profit,3),
        "roi_pct_minus110":round(100*profit/selected,3) if selected else None,
        "margin_mae":round(float(np.abs(margin-actual).mean()),3),
        "margin_rmse":round(float(np.sqrt(np.square(margin-actual).mean())),3),
        "avg_abs_margin":round(float(np.abs(margin).mean()),3),
        "avg_abs_edge":round(float(np.abs(deviations).mean()),3),
    }


def evaluate_holdout(train, test, features, name):
    if len(train) < MIN_TRAIN or len(test) < 100:
        raise ValueError(f"Unexpected train/test sample: {name}")
    # Strictly preceding years, and no 2026 Week 9.
    if train.gameday.max() >= test.gameday.min():
        raise ValueError("Time leakage: training overlaps holdout")
    model = make_pipeline(StandardScaler(), Ridge(alpha=ALPHA))
    model.fit(train[features], train.market_edge_actual)
    tested = test.copy()
    tested["market_anchored_ridge"] = (
        tested.market_home_margin+model.predict(tested[features])
    )
    tested["market_only"] = tested.market_home_margin
    output_cols = ["market_only",*MODELS,"consensus_margin",
                   "half_market_consensus","market_anchored_ridge"]
    comparisons = {}
    for column in output_cols:
        comparisons[column] = {
            str(threshold):metrics(tested, column, threshold)
            for threshold in EDGE_GATES
        }
    predictor = model.named_steps["ridge"]
    scaler = model.named_steps["standardscaler"]
    return tested, {
        "name":name,
        "train_years":sorted(int(x) for x in train.season.unique()),
        "test_years":sorted(int(x) for x in test.season.unique()),
        "train_games":int(len(train)),
        "test_games":int(len(test)),
        "features":features,
        "estimator":"StandardScaler(train only) + Ridge(alpha=100), target=actual_margin - market_margin",
        "standardized_feature_coefficients":{f:round(float(w),6) for f,w in zip(features,predictor.coef_)},
        "scaler_mean":[round(float(v),5) for v in scaler.mean_],
        "model_intercept":round(float(predictor.intercept_),6),
        "comparisons":comparisons,
    }


def main():
    data,features = load_common_games()
    train1=data[data.season.le(2024)].copy()
    test1=data[data.season.eq(2025)].copy()
    train2=data[data.season.le(2025)].copy()
    test2=data[data.season.eq(2026)].copy()
    test_2025,report_2025=evaluate_holdout(train1,test1,features,"2025_independent_holdout")
    test_2026,report_2026=evaluate_holdout(train2,test2,features,"2026_weeks01_08_independent_holdout")
    out = pd.concat([test_2025,test_2026], ignore_index=True)
    if len(out)!=406 or out.duplicated("game_id").any():
        raise ValueError("Incorrect holdout sizes or duplicate predictions")
    out["holdout"] = np.where(out.season.eq(2025),"2025_holdout","2026_w1_8_holdout")
    fields=["holdout","game_id","gameday","season","week","home_score","away_score",
            "actual_home_margin","market_home_margin",*MODELS,
            "consensus_margin","half_market_consensus","market_anchored_ridge"]
    OUTDIR.mkdir(parents=True,exist_ok=True)
    out[fields].to_csv(CSV_OUT,index=False)
    reports = [report_2025,report_2026]
    status = {
        "status":"RESEARCH_ONLY_HELDOUT_PRE_MNF_NO_PUBLIC_CHANGES",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "source":str(INPUT.relative_to(ROOT)),
        "models":"Four historical Ridge model margins, pregame, common games; not prospective current QB-EPA Injury version",
        "evaluation":"Chronological season-level train/test; 2022 partial (late-season) in training",
        "odds":"nflverse historical closing lines, not confirmed Bovada executable prices",
        "2026_week09_used":False,
        "total_models_unchanged":True,
        "alpha_fixed_before_test":ALPHA,
        "holdouts":reports,
        "warnings":[
            "Research hypotheses conceived after observing 2026 Week 9 failures, so even old holdouts are not fully untouched prospective proof.",
            "The 4 archived models may share correlated errors: ensemble performance is not independent evidence.",
            "Market blending preserves the raw ATS side of the consensus; lower MAE does not necessarily improve W/L.",
            "Ridge can improve margin MAE without creating profitable ATS edges; report number of bets and ROI.",
            "At alpha=100, low residual forecasts may produce zero >=3.5-point bets; this is informative, not an error.",
            "No official Week 8/9 data, website, injury model or betting ledger was changed.",
        ],
    }
    JSON_OUT.write_text(json.dumps(status,indent=2)+"\n",encoding="utf-8")
    labels=["# Market-anchored NFL ATS — historical holdout experiment","",
            "Research only. No Week 9 results or game-day injuries used; public projections and totals are untouched.","",
            "The market-only baseline makes **no ATS wagers** by definition; compare margin MAE separately.",
            "The 50% consensus-to-market blend can reduce margin error but **cannot change the ATS side**.",
            "Ridge predicts the signed ATS residual on the past year's data, using only historical pregame model edges.",
            ""]
    for item in reports:
        labels.extend([f"## {item['name']}",f"Train years {item['train_years']} ({item['train_games']} games); evaluate {item['test_years']} ({item['test_games']} games).","",
                       "| Candidate | Margin MAE | ATS all games (W-L-P) | ATS ≥2.5 (W-L-P) | ATS ≥3.5 (W-L-P) | Bets ≥3.5 | ROI ≥3.5 |",
                       "|---|---:|---:|---:|---:|---:|---:|"])
        for candidate,bygate in item["comparisons"].items():
            allg=bygate["0.0"];g25=bygate["2.5"];g35=bygate["3.5"]
            wlp=lambda x:f"{x['wins']}-{x['losses']}-{x['pushes']}"
            labels.append(
                f"| {candidate} | {allg['margin_mae']:.2f} | {wlp(allg)} | "
                f"{wlp(g25)} | {wlp(g35)} | {g35['bets']} | "
                f"{g35['roi_pct_minus110'] if g35['roi_pct_minus110'] is not None else 'N/A'}% |"
            )
        labels.append("")
    labels.extend(["## Research decision","",
                   "Do not replace the live ATS model until a candidate improves both forecast quality and reproducible out-of-sample edge behavior, without retroactive Week 9 tuning.",
                   "The totals model is deliberately excluded from this experiment.",
                   ""])
    MARKDOWN.write_text("\n".join(labels),encoding="utf-8")
    print(json.dumps({
        "validation":"PASS","train_sizes":[len(train1),len(train2)],"test_sizes":[len(test1),len(test2)],
        "ridge_2025":report_2025["comparisons"]["market_anchored_ridge"],
        "ridge_2026":report_2026["comparisons"]["market_anchored_ridge"],
        "files":[str(x.relative_to(ROOT)) for x in (JSON_OUT,CSV_OUT,MARKDOWN)]
    },indent=2))


if __name__=="__main__":
    main()
