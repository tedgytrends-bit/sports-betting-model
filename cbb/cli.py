"""CLI: python -m cbb.cli fetch | backtest | board."""
import argparse
import csv
from pathlib import Path
from cbb.engine import choose_lines, grade, pregame_rows, predict
from cbb.ingest import fetch_season, load_seasons


def save(path,rows):
    if not rows:
        print(f"No output rows: {path}")
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=("fetch","backtest","board"))
    ap.add_argument("--seasons",nargs="+",type=int,default=[2022,2023,2024,2025,2026])
    ap.add_argument("--test-seasons",nargs="+",type=int,default=[2024,2025,2026])
    ap.add_argument("--season",type=int,default=2027)
    ap.add_argument("--date",default=None,help="YYYY-MM-DD; restrict today's board")
    ap.add_argument("--raw-dir",default="cbb/data/raw")
    ap.add_argument("--out-dir",default="cbb/outputs")
    ap.add_argument("--refresh",action="store_true")
    ap.add_argument("--through-days",type=int,default=None,help="When refreshing current season, fetch through this many days from UTC now (month bounded)")
    args=ap.parse_args()
    if args.command=="fetch":
        for year in args.seasons:
            fetch_season(year,args.raw_dir,args.refresh,through_days=args.through_days)
        return
    data=load_seasons(args.seasons,args.raw_dir)
    rows=pregame_rows(data["games"],data["boxes"])
    odds=choose_lines(data["lines"])
    output=Path(args.out_dir)
    if args.command=="backtest":
        summaries=[]
        for year in args.test_seasons:
            forecasts=predict(rows,year,odds)
            completed=[r for r in forecasts if r["status"]=="final"]
            save(output/f"cbb_backtest_games_{year}.csv",completed)
            for kind in ("ats","total"):
                for t in (0,2.5,3.5,4.5,5.5):
                    result={"season":year,**grade(completed,t,kind)}
                    summaries.append(result)
                    print(result)
        save(output/"cbb_backtest_summary.csv",summaries)
    else:
        forecasts=predict(rows,args.season,odds)
        upcoming=[r for r in forecasts if r["status"]=="scheduled"
                  and (not args.date or r["date"]==args.date)]
        save(output/f"cbb_board_{args.season}.csv",upcoming)


if __name__=="__main__":
    main()
