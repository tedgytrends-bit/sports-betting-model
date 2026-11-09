#!/usr/bin/env python3
"""Exploratory historical margin-scaling calibration without data leakage.

Choose multiplier from archived 2022-2024 games ONLY. Then score unmodified
and chosen multiplier on untouched 2025, 2026 W1-W8 separately. Week 9 is
never in this input dataset. This is a shadow research test, not a model change.
Pure standard library; all predictions and outcomes already archived.
"""
from collections import Counter
import csv
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv"
DIR=ROOT/"data/week09_review"
OUT=DIR/"margin_scaling_holdout_20261109.json"
MARKDOWN=DIR/"margin_scaling_holdout_20261109.md"
FACTORS=(0.5,0.75,1.0,1.1,1.25,1.5,1.75,2.0,2.25,2.5,3.0)
MODELS=("baseline","injury_legacy","efficiency","combined_legacy")

def evaluate(rows,factor):
    if not rows:raise ValueError("No valid rows")
    n=len(rows); abs_sum=0.0;sq_sum=0.0;book_abs=0.0
    grades=Counter();strong=Counter()
    for r in rows:
        pm=factor*r["pred_margin"]
        real=r["actual_margin"];market=r["market_margin"]
        abs_sum+=abs(pm-real)
        book_abs+=abs(market-real)
        sq_sum+=(pm-real)**2
        edge=pm-market
        if abs(edge)<1e-10:grade="NO_LEAN"
        elif abs(real-market)<1e-10:grade="P"
        else:grade="W" if edge*(real-market)>0 else "L"
        grades[grade]+=1
        if abs(edge)>=3:strong[grade]+=1
    return {
        "n":n,
        "margin_mae":round(abs_sum/n,4),
        "market_margin_mae":round(book_abs/n,4),
        "margin_rmse":round((sq_sum/n)**.5,4),
        "ats_w_l_p":[grades["W"],grades["L"],grades["P"]],
        "ats_min3_w_l_p":[strong["W"],strong["L"],strong["P"]],
        "ats_lean_count":n-grades["NO_LEAN"],
    }

def main():
    with SOURCE.open(newline="",encoding="utf-8") as f:input_rows=list(csv.DictReader(f))
    data=[]
    for row in input_rows:
        y=int(row["season"])
        if y<2022 or y>2026:raise ValueError("Unexpected training season")
        if row["model"] not in MODELS:raise ValueError("Unknown model type")
        if y==2026 and int(row["week"])>8:raise ValueError("Future 2026 Week 9 outcomes leaked into test")
        data.append({
            "season":y,"model":row["model"],"game_id":row["game_id"],
            "actual_margin":float(row["home_score"])-float(row["away_score"]),
            "pred_margin":float(row["pred_home"])-float(row["pred_away"]),
            "market_margin":float(row["spread_line"]),
        })
    output={}
    for model in MODELS:
        train=[r for r in data if r["model"]==model and r["season"]<=2024]
        val2025=[r for r in data if r["model"]==model and r["season"]==2025]
        val2026=[r for r in data if r["model"]==model and r["season"]==2026]
        if len(train)!=615 or len(val2025)!=285 or len(val2026)!=121:
            raise ValueError(f"Nonstandard fold size for {model}: {[len(train),len(val2025),len(val2026)]}")
        tr=[(factor,evaluate(train,factor)) for factor in FACTORS]
        # choose ONLY using train MAE; ties lean toward multiplier 1.
        factor,chosen=min(tr,key=lambda x:(x[1]["margin_mae"],abs(x[0]-1)))
        output[model]={
            "factor_chosen_on_2022_2024":factor,
            "training_2022_2024_no_scale":evaluate(train,1.0),
            "training_2022_2024_scaled":chosen,
            "holdout_2025_no_scale":evaluate(val2025,1.0),
            "holdout_2025_scaled":evaluate(val2025,factor),
            "holdout_2026_w1_8_no_scale":evaluate(val2026,1.0),
            "holdout_2026_w1_8_scaled":evaluate(val2026,factor),
        }
    result={
        "status":"RESEARCH_ONLY_CALIBRATION_HOLDOUT",
        "source":str(SOURCE.relative_to(ROOT)),
        "selection":"Multiplier grid optimized ONLY on 2022-2024 margin MAE; holdouts 2025 & 2026 W1-W8",
        "candidate_factors":list(FACTORS),
        "models":output,
        "conclusion":"Simple multiplier adjustments have weak or mixed holdout performance. Do not change live model based on Week 9.",
        "caveats":[
            "Reconstructed chronological predictions, not prospective wagers.",
            "2022 historical training cohort begins at Week 16.",
            "2026 historical fold includes Weeks 1-8 only, not official Week 9.",
            "Selections and study design are exploratory, motivated by Week 9 errors; future models require fresh holdouts.",
        ],
    }
    DIR.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    msg=["# Week 10 research: test historical score-margin compression",
        "",
        "**Exploratory and research-only.** Model scores and public pick records are unchanged.",
        "A multiplier is chosen on 2022–2024 only, then tested on 2025 and 2026 Weeks 1–8.",
        "We require a held-out improvement rather than blindly increasing predicted favorites.",
        "",
        "| Model | Trained factor | 2025 MAE unscaled → scaled | 2026 W1–8 MAE unscaled → scaled | 2025 ATS unscaled → scaled |",
        "|---|---:|---:|---:|---|"]
    for name,v in output.items():
        a=v["holdout_2025_no_scale"];b=v["holdout_2025_scaled"]
        c=v["holdout_2026_w1_8_no_scale"];d=v["holdout_2026_w1_8_scaled"]
        fmt=lambda x:"–".join(str(z) for z in x)
        msg.append(f"| {name} | {v['factor_chosen_on_2022_2024']}× | {a['margin_mae']:.2f} → {b['margin_mae']:.2f} | {c['margin_mae']:.2f} → {d['margin_mae']:.2f} | {fmt(a['ats_w_l_p'])} → {fmt(b['ats_w_l_p'])} |")
    msg.extend(["",
        "**Decision:** Do not apply blanket margin multiplication to live forecasts. Test richer",
        "team-strength features, standardized inputs and market-residual approaches in",
        "chronological backtests, preserving a fresh 2026 Week 10 prospective test.",
        ""])
    MARKDOWN.write_text("\n".join(msg),encoding="utf-8")
    print(json.dumps({"output":str(OUT.relative_to(ROOT)),"factors":{k:v["factor_chosen_on_2022_2024"] for k,v in output.items()}},indent=2))

if __name__=="__main__":main()
