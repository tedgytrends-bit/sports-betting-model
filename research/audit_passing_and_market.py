"""Compare passing forecasts, archived Bovada moves, and an existing QB pair."""

from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.metrics import brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def at_quote(forecasts, quotes):
    candidates = quotes.merge(forecasts, on="game_id", validate="one_to_many")
    before = candidates.captured_at_utc.le(candidates.quote_at_utc)
    pregame = candidates.quote_at_utc.lt(candidates.kickoff_utc)
    return candidates.loc[before & pregame].sort_values("captured_at_utc").drop_duplicates("game_id", keep="last")


def grade(frame, margin, spread="home_favored_spread"):
    direction = np.sign((frame[margin] - frame[spread]).round(8))
    outcome = direction * np.sign(frame.actual_margin - frame[spread])
    return [int(outcome.eq(1).sum()), int(outcome.eq(-1).sum()),
            int((outcome.eq(0) & direction.ne(0)).sum())]


def conditional_backtest():
    data = pd.read_csv("data/efficiency_feature_experiments/efficiency_feature_predictions_20261102T210739Z.csv",
                       usecols=["game_id", "season", "variant", "spread_line", "actual_ats_margin", "pred_home_margin"])
    base = data.loc[data.variant.eq("baseline_frozen_features_alpha_10")].copy()
    passing = data.loc[data.variant.eq("baseline_plus_all_passing_alpha_10"), ["game_id", "pred_home_margin"]]
    data = base.merge(passing, on="game_id", suffixes=("_base", "_pass"), validate="one_to_one")
    data = data.dropna(subset=["spread_line", "actual_ats_margin", "pred_home_margin_base", "pred_home_margin_pass"])
    data = data.loc[data.actual_ats_margin.ne(0)].copy()
    data["spread_size"] = data.spread_line.abs()
    data["home_favorite"] = np.sign(data.spread_line)
    data["base_edge"] = data.pred_home_margin_base - data.spread_line
    data["passing_delta"] = data.pred_home_margin_pass - data.pred_home_margin_base
    data["covers"] = data.actual_ats_margin.gt(0)
    controls = ["spread_size", "home_favorite"]
    for season in (2024, 2025, 2026):
        train, test = data.loc[data.season.lt(season)], data.loc[data.season.eq(season)]
        for name, columns in {
            "market": controls, "market+baseline": [*controls, "base_edge"],
            "market+baseline+passing delta": [*controls, "base_edge", "passing_delta"],
        }.items():
            model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0))
            model.fit(train[columns], train.covers)
            prob = model.predict_proba(test[columns])[:, 1]
            print(season, len(test), name, f"Brier {brier_score_loss(test.covers, prob):.5f}",
                  f"log loss {log_loss(test.covers, prob):.5f}")


def main():
    root = Path("data")
    forecasts = pd.concat([pd.read_csv(path) for path in sorted(
        (root / "prospective_passing_shadow").glob("passing_shadow_projection_*.csv")
    )], ignore_index=True)
    baseline = "baseline_predicted_home_margin"
    passing = "passing_predicted_home_margin"
    forecasts = forecasts[["game_id", "captured_at_utc", baseline, passing]].copy()
    forecasts["captured_at_utc"] = pd.to_datetime(forecasts.captured_at_utc, utc=True)
    finals = pd.read_csv(root / "public_results/nfl_2026_graded_games.csv")
    finals = finals.loc[finals.model.eq("injury") & finals.score_status.eq("FINAL")].copy()
    finals["actual_margin"] = finals.actual_home - finals.actual_away
    for column in ("kickoff_utc", "quote_at_utc"):
        finals[column] = pd.to_datetime(finals[column], utc=True)
    matched = at_quote(forecasts, finals)
    for week, block in matched.groupby("week"):
        print("Frozen Bovada", week, "games", len(block))
        for arm in ("home_favored_spread", baseline, passing):
            print(arm, grade(block, arm), "MAE", round((block[arm] - block.actual_margin).abs().mean(), 4))
        print("flips", int(np.sign(block[baseline] - block.home_favored_spread).ne(
            np.sign(block[passing] - block.home_favored_spread)).sum()))

    quotes = {}
    for label, pattern in (("early", "nfl_week10_bovada_initial_*.csv"),
                           ("late", "nfl_week10_bovada_sunday_*.csv")):
        path, = (root / "public_snapshots").glob(pattern)
        q = pd.read_csv(path)
        q["game_id"] = q.season.astype(str) + "_" + q.week.astype(str).str.zfill(2) + "_" + q.away_team + "_" + q.home_team
        q["quote_at_utc"] = pd.to_datetime(q.captured_at_utc, utc=True)
        quotes[label] = q[["game_id", "quote_at_utc", "home_favorite_spread",
                           "away_spread_price", "home_spread_price"]]
    early = quotes["early"].merge(finals[["game_id", "kickoff_utc", "actual_margin"]], validate="one_to_one")
    early = at_quote(forecasts, early)
    move = early.merge(quotes["late"], on="game_id", suffixes=("", "_late"), validate="one_to_one")
    move = move.loc[move.quote_at_utc.lt(move.quote_at_utc_late) & move.quote_at_utc_late.lt(move.kickoff_utc)]
    delta = move.home_favorite_spread_late - move.home_favorite_spread
    for arm in (baseline, passing):
        direction = np.sign(move[arm] - move.home_favorite_spread)
        correct = direction * np.sign(delta)
        outcome = direction * np.sign(move.actual_margin - move.home_favorite_spread)
        price = np.where(direction.gt(0), move.home_spread_price, move.away_spread_price)
        payout = np.where(price > 0, price / 100, -100 / price)
        roi = np.where(outcome.eq(1), payout, np.where(outcome.eq(-1), -1, 0)).sum() / direction.ne(0).sum()
        print("Week 10 two Bovada captures", arm, "N", len(move), "aligned/opposed/flat",
              [int(correct.eq(value).sum()) for value in (1, -1, 0)], "mean line value",
              round((direction * delta).mean(), 4), "ATS", grade(move, arm, "home_favorite_spread"),
              "actual captured price ROI", round(100 * roi, 2))

    path, = (root / "public_snapshots").glob("nfl_week10_initial_projections_*.csv")
    qb = pd.read_csv(path)
    qb = qb.loc[qb.model.eq("injury")].merge(
        finals[["game_id", "actual_margin", "kickoff_utc"]], on="game_id",
        suffixes=("", "_actual"), validate="one_to_one"
    )
    qb = qb.loc[pd.to_datetime(qb.published_at_utc, utc=True).lt(qb.kickoff_utc_actual)
                & pd.to_datetime(qb.bovada_snapshot_at_utc, utc=True).lt(qb.kickoff_utc_actual)].copy()
    qb["QB off"] = qb.original_non_qb_home - qb.original_non_qb_away
    qb["QB on"] = qb.projected_home - qb.projected_away
    np.testing.assert_allclose(qb["QB on"] - qb["QB off"], qb.qb_margin_adjustment, atol=3e-6)
    print("Week 10 initial QB pair", len(qb))
    for arm in ("QB off", "QB on"):
        print(arm, grade(qb, arm, "bovada_home_favored_spread_initial"),
              "MAE", round((qb[arm] - qb.actual_margin).abs().mean(), 4))
    print("QB arm flips", int(np.sign(qb["QB on"] - qb.bovada_home_favored_spread_initial).ne(
        np.sign(qb["QB off"] - qb.bovada_home_favored_spread_initial)).sum()))
    conditional_backtest()


if __name__ == "__main__":
    main()
