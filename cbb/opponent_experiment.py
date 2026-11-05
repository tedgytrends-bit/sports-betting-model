"""Compare opponent-adjusted v3 versus both original CBB baselines.

Research experiment only. Existing 2026-27 frozen records and live shadow
models are NOT replaced. No model/hyperparameter choice based on a single
season's ROI.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from cbb.cli import save
from cbb.engine import FEATURES, choose_lines, grade, pregame_rows, predict, number
from cbb.ingest import load_seasons
from cbb.opponent_adjusted import ADJ_FEATURES, attach_adjustments, pregame_opponent_adjustments
from cbb.player_adjusted import PLAYER_FEATURES, extend_rows, player_predictions, roster_priors
from cbb.player_ingest import load_player_inputs


def fitted_predictions(rows, season, odds, columns, alpha, label):
    training = [
        r for r in rows if r["season"] < season
        and r["home_points"] is not None and r["away_points"] is not None
    ]
    test = [r for r in rows if r["season"] == season]
    if not test:
        return []
    if len(training) < 30:
        raise ValueError(f"Insufficient training data for {season}")
    x = np.asarray([[r[k] for k in columns] for r in training], dtype=float)
    xx = np.asarray([[r[k] for k in columns] for r in test], dtype=float)
    margins = np.asarray([r["home_points"] - r["away_points"] for r in training])
    totals = np.asarray([r["home_points"] + r["away_points"] for r in training])
    pred = []
    for values in (margins, totals):
        pipeline = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        pipeline.fit(x, values)
        pred.append(pipeline.predict(xx))
    output = []
    for r, margin, total in zip(test, *pred):
        market = odds.get(r["id"], {})
        spread = number(market.get("home_spread"))
        over_under = number(market.get("market_total"))
        ats_edge = float(margin) + spread if spread is not None else None
        total_edge = float(total) - over_under if over_under is not None else None
        output.append({
            **r, **market, "model": label, "training_games": len(training),
            "projected_margin_home": round(float(margin), 3),
            "projected_total": round(float(total), 3),
            "projected_home_points": round(float((margin + total) / 2), 2),
            "projected_away_points": round(float((total - margin) / 2), 2),
            "ats_edge": round(ats_edge, 3) if ats_edge is not None else None,
            "total_edge": round(total_edge, 3) if total_edge is not None else None,
            "ats_lean": ("home" if ats_edge > 0 else "away" if ats_edge < 0 else "none")
                        if ats_edge is not None else "",
            "total_lean": ("over" if total_edge > 0 else "under" if total_edge < 0 else "none")
                          if total_edge is not None else "",
        })
    return output


def run(args):
    data = load_seasons(args.seasons, root=args.raw_dir)
    base = pregame_rows(data["games"], data["boxes"])
    odds = choose_lines(data["lines"])
    adjusted_features = pregame_opponent_adjustments(data["games"], data["boxes"])
    adjusted = attach_adjustments(base, adjusted_features)
    priors, coverage = roster_priors(load_player_inputs(args.seasons, root=args.raw_dir))
    player_rows = extend_rows(base, data["games"], priors)
    player_adjusted = attach_adjustments(player_rows, adjusted_features)

    directory = Path(args.out_dir)
    save(directory / "player_roster_coverage.csv", coverage)

    summary = []
    for year in args.test_seasons:
        forecasts = (
            ("team_baseline", predict(base, year, odds)),
            ("team_opp_v3", fitted_predictions(adjusted, year, odds, FEATURES + ADJ_FEATURES, 150, "team_opp_v3")),
            ("player_v2", player_predictions(player_rows, year, odds)),
            ("player_opp_v3", fitted_predictions(
                player_adjusted, year, odds, PLAYER_FEATURES + ADJ_FEATURES, 250, "player_opp_v3"
            )),
        )
        ids = None
        for name, predictions in forecasts:
            current = {p["id"] for p in predictions}
            if len(current) != len(predictions):
                raise ValueError(f"Duplicate prediction game IDs for {name}/{year}")
            if ids is not None and current != ids:
                raise ValueError(f"Different evaluation samples for {name}/{year}")
            ids = current
            finished = [x for x in predictions if x["status"] == "final"]
            save(directory / f"{name}_games_{year}.csv", finished)
            for metric in ("ats", "total"):
                for threshold in (0, 2.5, 3.5, 4.5, 5.5):
                    results = {"season": year, "model": name, **grade(finished, threshold, metric)}
                    summary.append(results)
                    print("V3_RESULT", results)
    save(directory / "v3_model_comparison.csv", summary)

    # Aggregate ALL directional leans, explicitly not cherry-picked by edge.
    for model in ("team_baseline", "team_opp_v3", "player_v2", "player_opp_v3"):
        for metric in ("ats", "total"):
            eligible = [row for row in summary if row["model"] == model
                        and row["market"] == metric and row["threshold"] == 0]
            w, l, p = [sum(row[col] for row in eligible) for col in ("wins", "losses", "pushes")]
            n = w + l + p
            roi = (w * 100 / 110 - l) / n if n else None
            print("V3_AGGREGATE", dict(model=model, market=metric, wins=w, losses=l, pushes=p,
                                       win_rate=w / (w + l) if w + l else None, roi_minus_110=roi))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--test-seasons", nargs="+", type=int, default=[2024, 2025, 2026])
    ap.add_argument("--raw-dir", default="cbb/data/raw")
    ap.add_argument("--out-dir", default="cbb/outputs/opponent_v3")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
