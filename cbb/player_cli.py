"""Run corrected player v2 versus fixed team-only baseline on matched games and lines."""
import argparse
from collections import defaultdict
from statistics import mean, median
from pathlib import Path

from cbb.cli import save
from cbb.engine import choose_lines, grade, pregame_rows, predict
from cbb.ingest import load_seasons
from cbb.player_adjusted import extend_rows, player_predictions, roster_priors
from cbb.player_ingest import load_player_inputs, player_inputs


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=("fetch","backtest","board"))
    ap.add_argument("--seasons",nargs="+",type=int,default=[2022,2023,2024,2025,2026])
    ap.add_argument("--test-seasons",nargs="+",type=int,default=[2024,2025,2026])
    ap.add_argument("--season",type=int,default=2027)
    ap.add_argument("--date",default=None)
    ap.add_argument("--raw-dir",default="cbb/data/raw")
    ap.add_argument("--out-dir",default="cbb/outputs/player_v2")
    ap.add_argument("--refresh",action="store_true")
    args=ap.parse_args()
    if args.command=="fetch":
        for year in args.seasons:
            player_inputs(year,args.raw_dir,args.refresh)
        return
    data=load_seasons(args.seasons,args.raw_dir)
    rows=pregame_rows(data["games"],data["boxes"])
    odds=choose_lines(data["lines"])
    priors,coverage=roster_priors(load_player_inputs(args.seasons,args.raw_dir))
    extended=extend_rows(rows,data["games"],priors)
    folder=Path(args.out_dir)
    save(folder/"roster_coverage.csv",coverage)
    groups=defaultdict(list)
    for record in coverage:
        groups[record["season"]].append(record)
    for season, recs in sorted(groups.items()):
        matched=sum(x["matched_players"] for x in recs)
        usable=sum(x["matched_players"]>=3 for x in recs)
        print(f"COVERAGE {season} teams={len(recs)} players_matched={matched}"
              f" median_matched_per_team={median(x['matched_players'] for x in recs):.1f}"
              f" teams_3plus={usable} share={usable/len(recs):.2%}")
        if season in args.test_seasons and (not recs or usable < 100):
            raise ValueError(f"Coverage too low for reliable player model in {season}: {usable} teams with 3+ matches")
    if args.command=="board":
        model=player_predictions(extended,args.season,odds)
        upcoming=[r for r in model if r["status"]=="scheduled"
                  and (args.date is None or r["date"]==args.date)]
        save(folder/f"player_board_{args.season}.csv",upcoming)
        return
    summary=[]
    for year in args.test_seasons:
        baseline=predict(rows,year,odds)
        player=player_predictions(extended,year,odds)
        if {r["id"] for r in baseline}!={r["id"] for r in player}:
            raise RuntimeError("Baseline/player game ID mismatch")
        for model,forecast in (("baseline",baseline),("player_v2",player)):
            completed=[r for r in forecast if r["status"]=="final"]
            save(folder/f"{model}_games_{year}.csv",completed)
            for kind in ("ats","total"):
                for threshold in (0,2.5,3.5,4.5,5.5):
                    row={"season":year,"model":model,**grade(completed,threshold,kind)}
                    summary.append(row)
                    print("RESULT",row)
    save(folder/"player_v2_vs_baseline_summary.csv",summary)


if __name__=="__main__":
    main()
