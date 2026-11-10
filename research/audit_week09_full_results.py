#!/usr/bin/env python3
"""Research-only, reproducible audit of completed 2026 Week 9 NFL games.

Uses ONLY games with independently recorded final scores; NEVER refits a model.
The official public projection is the Nov 5 pre-kickoff Injury QB-EPA release
for completed TNF and the Nov 7/8 frozen final Injury release for Sunday/Monday.
Research model comparator files are Nov 4 pregame snapshots. Odds are the last
documented Bovada quote in the archive BEFORE EACH kickoff. This is a partial
complete Week 9 research report, not an update to public betting results.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from pathlib import Path
import json
import math

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
OUT=DATA/"week09_review"
INPUT=OUT/"verified_completed_scores_week09_20261110.csv"
KICKOFF=DATA/"public_snapshots/nfl_week09_kickoffs_2026.csv"
BOVADA=DATA/"bovada_lines.csv"
SUN=DATA/"public_snapshots/nfl_week09_final_injury_2026-11-08.csv"
TNF=DATA/"public_snapshots/nfl_week09_injury_qb_epa_margin_2026-11-05.csv"
RESEARCH=DATA/"public_snapshots/nfl_week_09_six_model_research_2026-11-04.csv"
GRADE=OUT/"week09_full_ats_totals_grade.csv"
REPORT=OUT/"week09_full_summary.json"
MD=OUT/"week09_full_findings.md"
MODELS=["official_injury","baseline_research","injury_legacy_research","efficiency_research","combined_research"]

def read(path):
    with path.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    if not rows or any(not row.get("game_id") for row in rows if "game_id" in rows[0]):
        raise ValueError(f"Empty or invalid file: {path}")
    return rows

def n(x):
    val=float(x)
    if not math.isfinite(val):raise ValueError(f"Invalid numerical value: {x}")
    return val

def parse_time(x):
    d=datetime.fromisoformat(x.strip().replace("Z","+00:00"))
    if d.tzinfo is None:raise ValueError(f"Naive timestamp: {x}")
    return d.astimezone(timezone.utc)

def record(rows, field):
    counts=Counter(x[field] for x in rows)
    return {"wins":counts["W"],"losses":counts["L"],"pushes":counts["P"],
            "no_lean":counts["NO_LEAN"],
            "win_pct_ex_push":round(100*counts["W"]/(counts["W"]+counts["L"]),2)
            if counts["W"]+counts["L"] else None}

def grade(estimate,real):
    if abs(estimate)<1e-10:return "NO_LEAN"
    if abs(real)<1e-10:return "P"
    return "W" if estimate*real>0 else "L"

def main():
    scores=read(INPUT)
    if len(scores)!=15 or len({x["game_id"] for x in scores})!=15:
        raise ValueError("Must have exactly 15 unique final games (TNF + 13 Sunday + Monday)")
    if any(x["final_status"]!="FINAL" for x in scores):
        raise ValueError("A game in the score list is not final")
    kickoff=read(KICKOFF)
    kickoffs={x["game_id"]:parse_time(x["kickoff_utc"]) for x in kickoff}
    if len(kickoffs)!=15 or len({x["game_id"] for x in kickoff})!=15:
        raise ValueError("Expected the complete 15-game Week 9 schedule")
    if set(kickoffs)!={x["game_id"] for x in scores}:
        raise ValueError("Complete 15-game Week 9 score cohort does not match schedule")
    quotes=read(BOVADA)
    markets={}
    for row in quotes:
        if str(row["season"])!="2026" or str(row["week"])!="9":continue
        key=(str(row["away_team"]).replace("LAR","LA"),
             str(row["home_team"]).replace("LAR","LA"))
        date=parse_time(row["captured_at_utc"])
        if key not in markets:markets[key]=[]
        markets[key].append((date,row))
    def pick_market(game_id):
        away,home=game_id.split("_",2)[2].split("_")
        options=[(dt,row) for dt,row in markets.get((away,home),[])
                 if dt<kickoffs[game_id] and row["source"]=="Bovada"]
        if not options:raise ValueError(f"No archived pre-kickoff Bovada quote for {game_id}")
        return sorted(options,key=lambda pair:pair[0])[-1]
    final=read(SUN)
    tnf=read(TNF)
    old=read(RESEARCH)
    official={}
    for row in final:
        if row["game_id"] in official:raise ValueError("Duplicated final forecast")
        if row["publication_status"]!="FINAL_PREGAME_2026_WEEK09_SUN_MON":
            raise ValueError("Invalid final release status")
        official[row["game_id"]]=row
    if len(official)!=14 or "2026_09_JAX_BAL" in official:
        raise ValueError("Invalid final Sunday/Monday release")
    tnf_rows=[x for x in tnf if x["game_id"]=="2026_09_JAX_BAL" and x["model"]=="injury"]
    if len(tnf_rows)!=1:raise ValueError("Thursday pregame Injury release must be unique")
    official["2026_09_JAX_BAL"]=tnf_rows[0]
    research={}
    for row in old:
        if row["model"] in ("baseline","injury","efficiency","combined"):
            key=(row["game_id"],row["model"])
            if key in research:raise ValueError(f"Duplicate research model row: {key}")
            research[key]=row
    expected_ids={row["game_id"] for row in scores}
    if not expected_ids.issubset(official):raise ValueError("Missing official game")
    if any(parse_time(official[g]["published_at_utc"])>=kickoffs[g] for g in expected_ids):
        raise ValueError("An official forecast was published after kickoff")
    for g in expected_ids:
        for model in ("baseline","injury","efficiency","combined"):
            if (g,model) not in research:raise ValueError(f"Missing research model {g} {model}")

    grade_rows=[]
    for result in sorted(scores,key=lambda row:kickoffs[row["game_id"]]):
        game_id=result["game_id"]
        away,home=game_id.split("_",2)[2].split("_")
        actual_away=n(result["actual_away_score"])
        actual_home=n(result["actual_home_score"])
        market_time,quote=pick_market(game_id)
        market_home=n(quote["home_favorite_spread"])
        market_total=n(quote["total_line"])
        actual_margin=actual_home-actual_away
        total=actual_home+actual_away
        for model in MODELS:
            row=official[game_id] if model=="official_injury" else research[(game_id,{"baseline_research":"baseline","injury_legacy_research":"injury","efficiency_research":"efficiency","combined_research":"combined"}[model])]
            predicted_away=n(row["projected_away"])
            predicted_home=n(row["projected_home"])
            predicted_total=n(row["projected_total"])
            if abs(predicted_away+predicted_home-predicted_total)>.035:
                raise ValueError(f"Projected total does not sum for {game_id} {model}")
            pred_margin=predicted_home-predicted_away
            edge=pred_margin-market_home
            t_edge=predicted_total-market_total
            ats=grade(edge,actual_margin-market_home)
            ts=grade(t_edge,total-market_total)
            favorite_team=home if market_home>0 else away if market_home<0 else "PICKEM"
            ats_team=home if edge>1e-10 else away if edge< -1e-10 else "NO_LEAN"
            favored_pick=ats_team==favorite_team
            grade_rows.append({
                "game_id":game_id,"away_team":away,"home_team":home,
                "kickoff_utc":kickoffs[game_id].isoformat(),"model":model,
                "snapshot_published_at_utc":row.get("published_at_utc") or row.get("captured_at_utc"),
                "model_away":round(predicted_away,4),"model_home":round(predicted_home,4),
                "model_total":round(predicted_total,4),
                "model_home_margin":round(pred_margin,4),
                "bovada_quote_time_utc":market_time.isoformat(),
                "bovada_home_favorite_spread":market_home,"bovada_total":market_total,
                "actual_away":actual_away,"actual_home":actual_home,
                "actual_total":total,"actual_home_margin":actual_margin,
                "ats_pick":ats_team,"ats_pick_market_favorite":int(favored_pick),
                "ats_edge_abs":round(abs(edge),4),"ats_result":ats,
                "total_pick":"Over" if t_edge>1e-10 else "Under" if t_edge< -1e-10 else "NO_LEAN",
                "total_edge_abs":round(abs(t_edge),4),"total_result":ts,
                "margin_abs_error":round(abs(pred_margin-actual_margin),4),
                "total_abs_error":round(abs(predicted_total-total),4),
                "research_only_comparator":model!="official_injury",
                "score_source_url":result["source_url"],
            })
    out={}
    for model in MODELS:
        rows=[r for r in grade_rows if r["model"]==model]
        if len(rows)!=15:raise ValueError(f"Incomplete model {model}")
        ats_thresholds={}
        totals_thresholds={}
        for limit in (2,3,3.5,4,5):
            ats_thresholds[str(limit)]=record([r for r in rows if r["ats_edge_abs"]>=limit],"ats_result")
            totals_thresholds[str(limit)]=record([r for r in rows if r["total_edge_abs"]>=limit],"total_result")
        out[model]={
            "games":len(rows),
            "ats_all_games":record(rows,"ats_result"),
            "totals_all_games":record(rows,"total_result"),
            "ats_edge_thresholds":ats_thresholds,
            "totals_edge_thresholds":totals_thresholds,
            "margin_mae":round(sum(r["margin_abs_error"] for r in rows)/len(rows),3),
            "margin_rmse":round((sum(r["margin_abs_error"]**2 for r in rows)/len(rows))**.5,3),
            "total_mae":round(sum(r["total_abs_error"] for r in rows)/len(rows),3),
            "total_rmse":round((sum(r["total_abs_error"]**2 for r in rows)/len(rows))**.5,3),
            "avg_abs_predicted_margin":round(sum(abs(r["model_home_margin"]) for r in rows)/len(rows),3),
            "mean_model_home_margin":round(sum(r["model_home_margin"] for r in rows)/len(rows),3),
            "mean_actual_home_margin":round(sum(r["actual_home_margin"] for r in rows)/len(rows),3),
            "favorite_picks":record([r for r in rows if r["ats_pick_market_favorite"]==1],"ats_result"),
            "underdog_picks":record([r for r in rows if r["ats_pick_market_favorite"]==0],"ats_result"),
            "highest_margin_errors":sorted(
                [{"game":r["game_id"],"mae":r["margin_abs_error"],"ATS":r["ats_result"]}
                 for r in rows],key=lambda r:r["mae"],reverse=True)[:5],
        }
    officials={r["game_id"]:r for r in grade_rows if r["model"]=="official_injury"}
    baseline={r["game_id"]:r for r in grade_rows if r["model"]=="baseline_research"}
    flips=[]
    for key,r in officials.items():
        other=baseline[key]
        if r["ats_pick"]!=other["ats_pick"]:
            flips.append({
                "game_id":key,
                "baseline_ats_pick":other["ats_pick"],"baseline_ats_result":other["ats_result"],
                "official_ats_pick":r["ats_pick"],"official_ats_result":r["ats_result"],
                "margin_change_home":round(r["model_home_margin"]-other["model_home_margin"],3),
            })
    fav_wlp=Counter()
    for r in officials.values():
        margin=r["actual_home_margin"];line=r["bovada_home_favorite_spread"]
        favored=margin-line if line>0 else line-margin if line<0 else 0
        fav_wlp["P" if abs(favored)<1e-10 else "W" if favored>0 else "L"]+=1
    # Same-vintage injury-model ablation: Nov 7/8 frozen *non-QB* score
    # compared with its QB-EPA overlay at the identical archived Bovada quote.
    # Thursday's original pregame projection is separate; never replace it.
    qb_overlay_flips=[]
    qb_overlay_games=[]
    for r in final:
        g=r["game_id"]
        if g not in officials:continue
        o=officials[g]
        old_margin=n(r["original_non_qb_home"])-n(r["original_non_qb_away"])
        final_margin=o["model_home_margin"]
        market=o["bovada_home_favorite_spread"]
        actual=o["actual_home_margin"]
        old_edge=old_margin-market
        new_edge=final_margin-market
        if abs((old_margin+n(r["qb_margin_adjustment"]))-final_margin)>.0002:
            raise ValueError(f"Saved QB overlay failed to reconcile game {g}")
        if abs(n(r["projected_total"])-(n(r["original_non_qb_home"])+n(r["original_non_qb_away"])))>.0002:
            raise ValueError(f"QB overlay modified totals at game {g}")
        old_pick=o["home_team"] if old_edge>0 else o["away_team"] if old_edge<0 else "NO_LEAN"
        new_pick=o["ats_pick"]
        evidence={
            "home":r.get("home_qb_starter_source",""),
            "away":r.get("away_qb_starter_source",""),
        }
        item={
            "game_id":g,
            "pregame_nonqb_home_margin":round(old_margin,3),
            "qb_margin_shift":round(n(r["qb_margin_adjustment"]),3),
            "published_injury_home_margin":round(final_margin,3),
            "market_home_margin":market,
            "nonqb_ats_pick":old_pick,
            "nonqb_ats_result":grade(old_edge,actual-market),
            "published_ats_pick":new_pick,
            "published_ats_result":o["ats_result"],
            "starter_evidence":evidence,
        }
        qb_overlay_games.append(item)
        if old_pick!=new_pick:qb_overlay_flips.append(item)
    if len(qb_overlay_games)!=14:
        raise ValueError(f"Expected 14 non-QB-vs-QB ablations, got {len(qb_overlay_games)}")
    unverified_games=sum(any(source!="verified_pregame" for source in r["starter_evidence"].values())
                          for r in qb_overlay_games)
    report={
        "audit":"WEEK09_COMPLETED_FULL_RESEARCH",
        "scope":"All completed Week 9 games: TNF Nov 5, 13 on Sunday Nov 8, MNF Nov 9 (15 games).",
        "official_source_rules":"Nov 5 original published Injury for TNF; Nov 7/8 frozen Injury for 13 Sunday games and Monday BUF@MIN.",
        "score_source":"https://www.nfl.com/schedules/2026/by-week/week-9",
        "market_policy":"Latest source-labeled Bovada quote archived before each game's kickoff; screenshot timestamp can be approximate.",
        "official_result_status":"FULL_WEEK_RESEARCH_ONLY_NO_PUBLIC_LEDGER_CHANGE",
        "only_unsettled_game":None,
        "results":out,
        "market_benchmark":{
            "favorite_ats_cover_record":{"wins":fav_wlp["W"],"losses":fav_wlp["L"],"pushes":fav_wlp["P"]},
            "market_margin_mae":round(sum(abs(r["actual_home_margin"]-r["bovada_home_favorite_spread"]) for r in officials.values())/15,3),
            "avg_abs_market_spread":round(sum(abs(r["bovada_home_favorite_spread"]) for r in officials.values())/15,3),
            "avg_abs_actual_margin":round(sum(abs(r["actual_home_margin"]) for r in officials.values())/15,3),
        },
        "official_vs_original_baseline_direction_flips":flips,
        "same_vintage_qb_overlay":{
            "games_compared":len(qb_overlay_games),
            "ats_pick_flips":qb_overlay_flips,
            "unverified_at_least_one_QB_games":unverified_games,
            "all_games":qb_overlay_games,
        },
        "interpretation_caveats":[
            "Single Week 9 sample: 15 games is not enough to optimize weights or infer systematic bias.",
            "Research-model vintages are Nov 4; Sunday/Monday official forecasts are Nov 7/8 after final reported injuries. Same game/odds/result set but different forecast vintages.",
            "A market favorite-heavy week may make aggressive underdog models look particularly bad even without stable long-run dog bias.",
            "The published model scores and public official results are untouched; this is diagnostic only.",
            "Directional totals results do not establish calibrated point totals: report total MAE separately.",
            "Testing 2/3/4/5 edge buckets post-hoc is exploratory, not an independently validated wagering rule.",
        ],
        "next_week_10_research":[
            "Backtest season-by-season 2022-2025, then hold out 2026 pre-Week9, to test prediction-margin shrinkage and benchmark against market MAE.",
            "Audit injury coefficient sensitivity, player-value/role weighting and replacement value; prevent double-counting with QB adjustment.",
            "Compare Baseline vs Injury ATS sign flips and require pregame evidence before making injury-driven side changes.",
            "Test standardized numeric inputs and conditional market-residual models in chronological walk-forward folds; do not make post-hoc Week9 tuning official.",
            "Preserve totals independently and compare directional accuracy together with total MAE and edge calibration.",
            "Week 9 is complete; keep all 15 official forecasts immutable during Week 10 research.",
        ],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    with GRADE.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(grade_rows[0]))
        w.writeheader();w.writerows(grade_rows)
    REPORT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    official=out["official_injury"]
    summary_lines=[
        "# 2026 NFL Week 9 — final full-slate model performance audit",
        "",
        "**Research only, all 15 completed games** (Thursday + 13 Sunday + MNF).",
        "All grades use committed pregame projections and separately archived Bovada prices.",
        "Do not interpret the market quotes as confirmed executable closing lines.",
        "",
        "## Same-game ATS and totals records",
        "",
        "| Model | ATS | Totals | Margin MAE | Total MAE |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        m=out[model];a=m["ats_all_games"];t=m["totals_all_games"]
        summary_lines.append(
            f"| {model} | {a['wins']}–{a['losses']}–{a['pushes']} | "
            f"{t['wins']}–{t['losses']}–{t['pushes']} | {m['margin_mae']:.2f} | {m['total_mae']:.2f} |"
        )
    summary_lines.extend([
        "",
        "## Flagged findings",
        "",
        f"- Official ATS edge ≥3: {official['ats_edge_thresholds']['3']['wins']}–{official['ats_edge_thresholds']['3']['losses']}–{official['ats_edge_thresholds']['3']['pushes']}; assess calibration, not just hit rate.",
        f"- Official totals edge ≥3: {official['totals_edge_thresholds']['3']['wins']}–{official['totals_edge_thresholds']['3']['losses']}–{official['totals_edge_thresholds']['3']['pushes']}.",
        f"- Official ATS when siding with a favorite: {official['favorite_picks']['wins']}–{official['favorite_picks']['losses']}–{official['favorite_picks']['pushes']}.",
        f"- Official ATS when siding with an underdog: {official['underdog_picks']['wins']}–{official['underdog_picks']['losses']}–{official['underdog_picks']['pushes']}.",
        f"- The sportsbook favorite covered {fav_wlp['W']} games, lost ATS in {fav_wlp['L']}, and pushed {fav_wlp['P']}; unusual chalk-heavy week.",
        f"- Mean absolute winning margin: model {official['avg_abs_predicted_margin']:.2f}, market {report['market_benchmark']['avg_abs_market_spread']:.2f}, actual {report['market_benchmark']['avg_abs_actual_margin']:.2f}.",
        f"- Model margin MAE {official['margin_mae']:.2f} vs market spread MAE {report['market_benchmark']['market_margin_mae']:.2f}; model didn't outperform the market on margin accuracy.",
        "- ATS side flips from Baseline to the final Injury model on previously completed games: "+", ".join(f["game_id"] for f in flips)+".",
        f"- Same-vintage QB overlay flipped {len(qb_overlay_flips)} ATS directions; "+"; ".join(f"{x['game_id']} {x['nonqb_ats_pick']} ({x['nonqb_ats_result']}) → {x['published_ats_pick']} ({x['published_ats_result']})" for x in qb_overlay_flips)+".",
        f"- At least one QB source was not independently verified in {unverified_games}/14 Sunday/Monday games.",
        "",
        "## Week 10 research gates",
        "",
        "1. Freeze all 15 Week 9 official forecasts and research-only results.",
        "2. Walk-forward test market-relative margin calibration and model overconfidence in underdogs against 2022–2025 and holdout 2026 games.",
        "3. Run player-role and replacement-value injury experiments separately from unmodified Baseline.",
        "4. Compare score MAE, total MAE, ATS by edge bucket, and prospective stability before making any live changes.",
        "5. Preserve the currently published Week 10 model as a pregame snapshot once validated, rather than retroactively changing past picks.",
        "",
        "**Data lineage:** "+str(INPUT.relative_to(ROOT))+"; "+str(SUN.relative_to(ROOT))+"; "+str(TNF.relative_to(ROOT))+"; "+str(BOVADA.relative_to(ROOT))+"; "+str(KICKOFF.relative_to(ROOT))+".",
        "",
    ])
    MD.write_text("\n".join(summary_lines),encoding="utf-8")
    print(json.dumps({
        "official":official,"market":report["market_benchmark"],
        "comparison":{m:{k:out[m][k] for k in ("ats_all_games","totals_all_games","margin_mae","total_mae")} for m in MODELS},
        "flips":flips,"outputs":[str(x.relative_to(ROOT)) for x in (GRADE,REPORT,MD)]
    },indent=2))

if __name__=="__main__":
    main()
