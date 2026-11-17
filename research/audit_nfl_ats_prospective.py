#!/usr/bin/env python3
"""Read-only prospective ATS diagnostic. Never modifies public records.

Run: python research/audit_nfl_ats_prospective.py
Uses only pre-existing published Injury forecasts and frozen Bovada lines.
Market spread convention: positive home_favored_spread means home is favored.
No model is promoted by this script; all evaluations are retrospective.
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/public_results/nfl_2026_graded_games.csv"
BUCKETS = [(0, 1.5), (1.5, 3), (3, 5), (5, math.inf)]

def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "n/a"

def roi(w, l, p):
    return (w / 1.1 - l) / (w + l + p) if w + l + p else float("nan")

def summarize(label, rows):
    w = sum(r["win"] for r in rows)
    l = sum(r["loss"] for r in rows)
    p = sum(r["push"] for r in rows)
    err = sum(abs(r["actual_margin"] - r["pred_margin"]) for r in rows) / len(rows) if rows else float("nan")
    market_err = sum(abs(r["actual_margin"] - r["market_margin"]) for r in rows) / len(rows) if rows else float("nan")
    print(f"{label:34} n={len(rows):2} W-L-P={w}-{l}-{p} win={pct(w,w+l):>6} ROI={pct(roi(w,l,p),1):>7} model_MAE={err:.2f} market_MAE={market_err:.2f}")

def main():
    with SOURCE.open(newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))
    rows = []
    seen = set()
    for r in raw:
        if r["model"] != "injury" or r["record_class"] != "PUBLIC_PUBLISHED" or r["score_status"] != "FINAL":
            continue
        key = r["game_id"]
        if key in seen:
            raise ValueError(f"duplicate Injury game: {key}")
        seen.add(key)
        try:
            actual = float(r["actual_home"]) - float(r["actual_away"])
            pred = float(r["projected_home"]) - float(r["projected_away"])
            market = float(r["home_favored_spread"])
            edge = pred - market
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid numeric fields: {key}") from exc
        if not all(map(math.isfinite, (actual, pred, market, edge))):
            raise ValueError(f"non-finite: {key}")
        # A zero ATS edge should not be retrospectively awarded a direction.
        if edge == 0:
            raise ValueError(f"zero-edge ATS direction needs provenance: {key}")
        actual_vs_line = actual - market
        win = int(actual_vs_line * edge > 0)
        loss = int(actual_vs_line * edge < 0)
        push = int(actual_vs_line == 0)
        if (win, loss, push) != (int(r["ats_result"] == "Win"), int(r["ats_result"] == "Loss"), int(r["ats_result"] == "Push")):
            raise ValueError(f"independent ATS grading mismatch: {key}")
        rows.append(dict(game=key, week=int(r["week"]), actual_margin=actual, pred_margin=pred,
                         market_margin=market, edge=edge, win=win, loss=loss, push=push,
                         away=r["away_team"], home=r["home_team"]))
    print("PUBLIC INJURY ATS — frozen published forecasts; no retrospective selection")
    summarize("ALL", rows)
    for week in sorted({r["week"] for r in rows}):
        summarize(f"Week {week}", [r for r in rows if r["week"] == week])
    print("\nEdge buckets (absolute point difference from frozen market):")
    for lo, hi in BUCKETS:
        summarize(f"{lo:g} to {hi:g} points", [r for r in rows if lo <= abs(r["edge"]) < hi])
    print("\nUnderdog vs favorite picks (market-based; pick side inferred from edge):")
    for group in ("underdog", "favorite"):
        subset = []
        for r in rows:
            # market_margin >0: home favored, <0: away favored
            selected_home = r["edge"] > 0
            selected_favorite = (selected_home and r["market_margin"] > 0) or (not selected_home and r["market_margin"] < 0)
            if (group == "favorite") == selected_favorite:
                subset.append(r)
        summarize(group, subset)
    print("\nMarket anchoring sensitivity — no side changes for positive shrinkage; MAE only:")
    for alpha in (0, .25, .5, .75, 1):
        mae = sum(abs(r["actual_margin"] - (r["market_margin"] + alpha*r["edge"])) for r in rows) / len(rows)
        print(f"  alpha={alpha:.2f} margin_MAE={mae:.3f}")
    print("\nWeek 10 largest ATS misses by actual margin minus model margin:")
    for r in sorted((r for r in rows if r["week"] == 10), key=lambda x: abs(x["actual_margin"]-x["pred_margin"]), reverse=True)[:8]:
        print(f"  {r['away']} @ {r['home']}: model_home_margin={r['pred_margin']:+.1f}, market_home_margin={r['market_margin']:+.1f}, actual_home_margin={r['actual_margin']:+.1f}, ATS={'W' if r['win'] else 'P' if r['push'] else 'L'}")
    print("\nCAUTION: n=43 prospective games is insufficient for parameter promotion; use historical chronological holdout before modifying official model.")

if __name__ == "__main__":
    main()
