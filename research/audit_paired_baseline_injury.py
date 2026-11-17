#!/usr/bin/env python3
"""Paired published Baseline vs Injury ATS audit; read-only, no retrospective picks.

Run: python research/audit_paired_baseline_injury.py
"""
import csv
from collections import defaultdict
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/"data/public_results/nfl_2026_graded_games.csv"

def summarize(rows, model):
    grades=[x[model]["ats_result"] for x in rows]
    return f'{grades.count("Win")}-{grades.count("Loss")}-{grades.count("Push")}'

def mae(rows,model):
    def error(x):
        original=x["injury"]
        actual=float(original["actual_home"])-float(original["actual_away"])
        predicted=(float(original["home_favored_spread"]) if model=="market"
                   else float(x[model]["projected_home"])-float(x[model]["projected_away"]))
        return abs(actual-predicted)
    return sum(error(x) for x in rows)/len(rows)

def main():
    with SOURCE.open(newline="",encoding="utf-8") as f:
        raw=list(csv.DictReader(f))
    paired=defaultdict(dict)
    for row in raw:
        if row["model"] in ("baseline","injury") and row["record_class"] in ("PUBLIC_PUBLISHED","RESEARCH_COMPARATOR"):
            if row["model"] in paired[row["game_id"]]:
                raise ValueError("Duplicate model/game")
            paired[row["game_id"]][row["model"]]=row
    games=[x for x in paired.values() if set(x)=={"baseline","injury"} and x["injury"]["score_status"]=="FINAL"]
    if len(games)!=43:
        raise ValueError(f"Expected 43 paired completed published games, got {len(games)}")
    for x in games:
        if x["baseline"]["score_status"]!="FINAL" or any(x["baseline"][k]!=x["injury"][k]
                for k in ("actual_home","actual_away","home_favored_spread","bovada_total")):
            raise ValueError("Mismatched market or final scores")
        if x["baseline"]["ats_result"] not in ("Win","Loss","Push") or x["injury"]["ats_result"] not in ("Win","Loss","Push"):
            raise ValueError("Unsettled grade")
    print("Paired archived forecasts: 43 completed NFL games, Weeks 8–10")
    for name,subset in [("all",games),("flip",[x for x in games if x["baseline"]["ats_pick"]!=x["injury"]["ats_pick"]]),
                        ("same",[x for x in games if x["baseline"]["ats_pick"]==x["injury"]["ats_pick"]])]:
        print(f"{name}: N={len(subset)} baseline={summarize(subset,'baseline')} injury={summarize(subset,'injury')}"
              + (f" MAE baseline={mae(subset,'baseline'):.3f} injury={mae(subset,'injury'):.3f} market={mae(subset,'market'):.3f}" if subset else ""))
    for week in (8,9,10):
        subset=[x for x in games if int(x["injury"]["week"])==week]
        print(f"week {week}: N={len(subset)} baseline={summarize(subset,'baseline')} injury={summarize(subset,'injury')}"
              f" MAE baseline={mae(subset,'baseline'):.3f} injury={mae(subset,'injury'):.3f}")
    print("NOTE: Baseline is a published model comparator, not a counterfactual injury-feature ablation.")
    print("Neither result is evidence of positive expected betting returns.")

if __name__=="__main__":
    main()
