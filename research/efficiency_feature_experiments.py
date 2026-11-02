"""Research-only NFL efficiency feature experiments.

Compares the frozen model.py feature set with passing/rushing splits,
opponent matchup features, prior-season shrinkage, and pace variants.
No production files or official prospective records are modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from model import (
    build_efficiency_model_dataset,
    load_pbp,
    load_schedule_data,
)

OUT = Path("data/efficiency_feature_experiments")
MIN_TRAIN_GAMES = 500
ALPHA = 10.0
THRESHOLDS = (1.5, 2.5, 3.5)


def _team_split_history(pbp: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Game/team passing and rushing efficiency, with game dates attached."""
    plays = pbp.copy()
    plays = plays[
        plays["play_type"].isin(["pass", "run"])
        & plays["posteam"].notna()
        & plays["defteam"].notna()
    ].copy()
    plays["epa"] = pd.to_numeric(plays["epa"], errors="coerce")
    plays["success"] = pd.to_numeric(plays["success"], errors="coerce")
    keys = ["game_id", "season", "week", "posteam", "play_type"]
    off = plays.groupby(keys, dropna=False).agg(
        epa=("epa", "mean"), success=("success", "mean"), plays=("play_type", "size")
    ).reset_index()
    off["unit"] = np.where(off["play_type"].eq("pass"), "pass", "rush")
    off = off.pivot_table(
        index=["game_id", "season", "week", "posteam"],
        columns="unit", values=["epa", "success", "plays"], aggfunc="first"
    )
    off.columns = [f"off_{metric}_{unit}" for metric, unit in off.columns]
    off = off.reset_index().rename(columns={"posteam": "team"})

    def_keys = ["game_id", "season", "week", "defteam", "play_type"]
    deff = plays.groupby(def_keys, dropna=False).agg(
        epa_allowed=("epa", "mean"), success_allowed=("success", "mean"),
        plays_faced=("play_type", "size")
    ).reset_index()
    deff["unit"] = np.where(deff["play_type"].eq("pass"), "pass", "rush")
    deff = deff.pivot_table(
        index=["game_id", "season", "week", "defteam"],
        columns="unit", values=["epa_allowed", "success_allowed", "plays_faced"],
        aggfunc="first"
    )
    deff.columns = [f"def_{metric}_{unit}" for metric, unit in deff.columns]
    deff = deff.reset_index().rename(columns={"defteam": "team"})
    out = off.merge(deff, on=["game_id", "season", "week", "team"], how="outer")
    dates = schedule[["game_id", "gameday"]].copy()
    dates["gameday"] = pd.to_datetime(dates["gameday"], errors="coerce")
    return out.merge(dates, on="game_id", how="left")


def _pregame_split_features(schedule: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    """Create strictly pregame rolling team features and matchup deltas."""
    rows = []
    metrics = [
        "off_epa_pass", "off_success_pass", "off_plays_pass",
        "off_epa_rush", "off_success_rush", "off_plays_rush",
        "def_epa_allowed_pass", "def_success_allowed_pass", "def_plays_faced_pass",
        "def_epa_allowed_rush", "def_success_allowed_rush", "def_plays_faced_rush",
    ]
    history = team_games.copy()
    history["gameday"] = pd.to_datetime(history["gameday"], errors="coerce")
    for game in schedule.sort_values("gameday").itertuples(index=False):
        date = pd.to_datetime(game.gameday, errors="coerce")
        if pd.isna(date):
            continue
        prior = history[history["gameday"] < date]
        sides = {}
        for side, team in (("home", game.home_team), ("away", game.away_team)):
            th = prior[prior["team"].eq(team)].sort_values("gameday")
            recent = th.tail(10)
            if recent.empty:
                sides[side] = {}
                continue
            vals = {}
            for metric in metrics:
                vals[metric] = pd.to_numeric(recent[metric], errors="coerce").mean() if metric in recent else np.nan
            # Opponent-adjusted matchup components: offense vs opposing defense.
            sides[side] = vals
        h, a = sides["home"], sides["away"]
        if not h or not a:
            continue
        row = {"game_id": game.game_id}
        for metric in metrics:
            row[f"home_{metric}"] = h.get(metric, np.nan)
            row[f"away_{metric}"] = a.get(metric, np.nan)
        for unit in ("pass", "rush"):
            row[f"home_{unit}_epa_matchup"] = (
                h.get(f"off_epa_{unit}", np.nan) - a.get(f"def_epa_allowed_{unit}", np.nan)
            )
            row[f"away_{unit}_epa_matchup"] = (
                a.get(f"off_epa_{unit}", np.nan) - h.get(f"def_epa_allowed_{unit}", np.nan)
            )
            row[f"home_{unit}_success_matchup"] = (
                h.get(f"off_success_{unit}", np.nan) - a.get(f"def_success_allowed_{unit}", np.nan)
            )
            row[f"away_{unit}_success_matchup"] = (
                a.get(f"off_success_{unit}", np.nan) - h.get(f"def_success_allowed_{unit}", np.nan)
            )
        # Expected game play volume is a pace proxy, not a possession forecast.
        row["expected_game_plays"] = (
            h.get("off_plays_pass", np.nan) + h.get("off_plays_rush", np.nan)
            + a.get("off_plays_pass", np.nan) + a.get("off_plays_rush", np.nan)
        )
        # Prior-season shrinkage: blend current rolling values with that team's
        # most recent completed prior-season mean, using four pseudo-games.
        for side, team in (("home", game.home_team), ("away", game.away_team)):
            prior_team = prior[prior["team"].eq(team)].copy()
            if not prior_team.empty:
                current_season = int(game.season)
                prev_season = prior_team[pd.to_numeric(prior_team["season"], errors="coerce") < current_season]
                if not prev_season.empty:
                    prev_year = pd.to_numeric(prev_season["season"], errors="coerce").max()
                    prev_season = prev_season[pd.to_numeric(prev_season["season"], errors="coerce").eq(prev_year)]
                for metric in metrics:
                    current_val = sides[side].get(metric, np.nan)
                    prior_val = pd.to_numeric(prev_season[metric], errors="coerce").mean() if not prev_season.empty and metric in prev_season else np.nan
                    n_recent = min(len(prior_team[prior_team["gameday"] >= date - pd.Timedelta(days=365)]), 10)
                    if pd.notna(current_val) and pd.notna(prior_val):
                        row[f"{side}_shrunk_{metric}"] = (n_recent * current_val + 4.0 * prior_val) / (n_recent + 4.0)
                    else:
                        row[f"{side}_shrunk_{metric}"] = current_val
        rows.append(row)
    return pd.DataFrame(rows)


def _feature_sets(data: pd.DataFrame) -> dict[str, list[str]]:
    excluded = {
        "game_id", "gameday", "season", "week", "home_team", "away_team",
        "home_score", "away_score",
    }
    base = [c for c in data if c not in excluded and pd.api.types.is_numeric_dtype(data[c])]
    split = [c for c in data if (
        c.startswith(("home_off_", "away_off_", "home_def_", "away_def_"))
        or "_epa_matchup" in c or "_success_matchup" in c
    )]
    shrink = [c for c in data if "_shrunk_" in c]
    pace = [c for c in data if c == "expected_game_plays"]
    return {
        "baseline_frozen_features": base,
        "baseline_plus_pass_rush_matchups": list(dict.fromkeys(base + split)),
        "pass_rush_plus_prior_season_shrinkage": list(dict.fromkeys(base + split + shrink)),
        "pass_rush_shrinkage_plus_pace": list(dict.fromkeys(base + split + shrink + pace)),
    }


def _fit_weekly(data: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    data = data.dropna(subset=["gameday", "home_score", "away_score"]).sort_values("gameday").copy()
    data["test_week"] = data["gameday"].dt.to_period("W").astype(str)
    predictions = []
    for week in data["test_week"].drop_duplicates():
        test = data[data["test_week"].eq(week)].copy()
        train = data[data["gameday"] < test["gameday"].min()].copy()
        if len(train) < MIN_TRAIN_GAMES:
            continue
        active = [c for c in features if c in train and train[c].notna().any()]
        if not active:
            continue
        medians = train[active].median(numeric_only=True).fillna(0)
        x_train = train[active].fillna(medians).fillna(0)
        x_test = test[active].fillna(medians).fillna(0)
        for target, output in (("home_score", "pred_home"), ("away_score", "pred_away")):
            model = Ridge(alpha=ALPHA)
            model.fit(x_train, train[target])
            test[output] = model.predict(x_test)
        predictions.append(test)
    if not predictions:
        return pd.DataFrame()
    return pd.concat(predictions, ignore_index=True).drop_duplicates("game_id")


def _roi_summary(frame: pd.DataFrame, edge_col: str, actual_col: str, label: str) -> dict:
    result = {"variant": label, "n_games": int(len(frame))}
    for threshold in THRESHOLDS:
        bets = frame[frame[edge_col].abs() >= threshold].copy()
        # Zero ATS/total margin is a push. Stakes are flat 1 unit at -110.
        wins = ((bets[edge_col] * bets[actual_col]) > 0).sum()
        pushes = (bets[actual_col] == 0).sum()
        losses = len(bets) - wins - pushes
        units = wins * (100 / 110) - losses
        result[f"threshold_{threshold:.1f}"] = {
            "bets": int(len(bets)), "wins": int(wins), "losses": int(losses),
            "pushes": int(pushes), "units": round(float(units), 4),
            "roi_pct": round(float(100 * units / len(bets)), 3) if len(bets) else None,
        }
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading validated schedule and PBP...")
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    split_history = _team_split_history(pbp, schedule)
    split_features = _pregame_split_features(schedule, split_history)
    data = baseline.merge(split_features, on="game_id", how="left", validate="one_to_one")
    lines = schedule[["game_id", "spread_line", "total_line"]].copy()
    data = data.merge(lines, on="game_id", how="left", validate="one_to_one")
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    variants = _feature_sets(data)

    summaries = []
    prediction_frames = []
    for name, features in variants.items():
        print(f"Running {name} ({len(features)} candidate features)...")
        pred = _fit_weekly(data, features)
        if pred.empty:
            raise RuntimeError(f"No chronological predictions generated for {name}")
        pred["variant"] = name
        pred["actual_total"] = pred["home_score"] + pred["away_score"]
        pred["pred_total"] = pred["pred_home"] + pred["pred_away"]
        pred["actual_home_margin"] = pred["home_score"] - pred["away_score"]
        pred["pred_home_margin"] = pred["pred_home"] - pred["pred_away"]
        pred["ats_edge"] = pred["pred_home_margin"] - pred["spread_line"]
        pred["actual_ats_margin"] = pred["actual_home_margin"] - pred["spread_line"]
        pred["total_edge"] = pred["pred_total"] - pred["total_line"]
        pred["actual_total_margin"] = pred["actual_total"] - pred["total_line"]
        prediction_frames.append(pred)
    all_preds = pd.concat(prediction_frames, ignore_index=True)
    # Fair comparison: intersection of game IDs predicted by every variant.
    common = set.intersection(*[
        set(g["game_id"]) for _, g in all_preds.groupby("variant")
    ])
    all_preds = all_preds[all_preds["game_id"].isin(common)].copy()
    for name, group in all_preds.groupby("variant"):
        ats = group.dropna(subset=["ats_edge", "actual_ats_margin"])
        totals = group.dropna(subset=["total_edge", "actual_total_margin"])
        summaries.append({
            "variant": name, "common_games": int(len(group)),
            "ats_margin_mae": round(float((ats["pred_home_margin"] - ats["actual_home_margin"]).abs().mean()), 4),
            "total_mae": round(float((totals["pred_total"] - totals["actual_total"]).abs().mean()), 4),
            "ats_directional_accuracy_pct": round(float(((ats["ats_edge"] > 0) == (ats["actual_ats_margin"] > 0))[ats["actual_ats_margin"] != 0].mean() * 100), 3),
            "totals_directional_accuracy_pct": round(float(((totals["total_edge"] > 0) == (totals["actual_total_margin"] > 0))[totals["actual_total_margin"] != 0].mean() * 100), 3),
            "ats_fixed_thresholds": _roi_summary(ats, "ats_edge", "actual_ats_margin", name),
            "totals_fixed_thresholds": _roi_summary(totals, "total_edge", "actual_total_margin", name),
        })
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT / f"efficiency_feature_predictions_{stamp}.csv"
    json_path = OUT / f"efficiency_feature_report_{stamp}.json"
    all_preds.to_csv(csv_path, index=False)
    report = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_model_version": "0.8.0",
        "minimum_training_games": MIN_TRAIN_GAMES,
        "ridge_alpha": ALPHA,
        "comparison_rule": "Same intersection of weekly chronological out-of-sample game IDs across every variant.",
        "market_line_warning": "spread_line and total_line come from nflverse schedule data; they are not verified executable sportsbook quotes.",
        "thresholds": list(THRESHOLDS),
        "variants": summaries,
        "prediction_csv": str(csv_path),
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {csv_path} and {json_path}")


if __name__ == "__main__":
    main()
