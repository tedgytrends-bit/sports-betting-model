#!/usr/bin/env python3
"""Historical Efficiency ATS directional bias diagnostics, research only.

Run: python research/audit_historical_ats_side_bias.py
Uses existing precomputed historical predictions, not the player-aware Injury model.
Never changes published records or model coefficients.
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/"research/reports/automated_score_model_predictions.csv"

def classify(row):
    market=float(row["spread_line"])
    edge=float(row["ats_edge_score_model"])
    actual=float(row["actual_ats_cover_margin"])
    if not all(map(math.isfinite,(market,edge,actual))):
        raise ValueError("Nonfinite margin")
    if market == 0 or edge == 0:
        return "pickem_or_zero"
    # home favorite when market home margin positive; home pick when edge positive.
    return "favorite" if (market > 0)==(edge > 0) else "underdog"

def describe(rows):
    n=len(rows)
    w=sum(float(x["ats_edge_score_model"])*float(x["actual_ats_cover_margin"])>0 for x in rows)
    l=sum(float(x["ats_edge_score_model"])*float(x["actual_ats_cover_margin"])<0 for x in rows)
    p=n-w-l
    return f"n={n} W-L-P={w}-{l}-{p} win={w/(w+l)*100:.1f}% roi={((w/1.1-l)/n*100):+.1f}%" if n and w+l else f"n={n}"

def main():
    with SOURCE.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=1050 or len(set(x["game_id"] for x in rows))!=len(rows):
        raise ValueError("Historical cohort mismatch")
    print("HISTORICAL EFFICIENCY MODEL (not player-aware Injury), 1050 games")
    for season in sorted(set(x["season"] for x in rows)):
        subset=[x for x in rows if x["season"]==season]
        print(f"\n{season}:")
        for group in ("underdog","favorite","pickem_or_zero"):
            s=[x for x in subset if classify(x)==group]
            print(f"  {group:15} {describe(s)}")
    print("\nAll years:")
    for group in ("underdog","favorite","pickem_or_zero"):
        s=[x for x in rows if classify(x)==group]
        print(f"  {group:15} {describe(s)}")
    print("\nImportant: repeated season patterns do not establish the cause of the bias.")
    print("Require a paired pregame injury-vs-no-injury forecast dataset to test injury feature ablation.")

if __name__=="__main__":
    main()
