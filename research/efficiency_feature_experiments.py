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
from scipy.stats import binomtest
from sklearn.linear_model import Ridge

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data

OUT = Path("data/efficiency_feature_experiments")
MIN_TRAIN_GAMES = 500
ALPHA = 10.0
THRESHOLDS = (1.5, 2.5, 3.5)
PRIMARY_BASELINE = "baseline_frozen_features"
PRIMARY_PASSING = "baseline_plus_all_passing"


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
        row["expected_game_plays"] = (
            h.get("off_plays_pass", np.nan) + h.get("off_plays_rush", np.nan)
            + a.get("off_plays_pass", np.nan) + a.get("off_plays_rush", np.nan)
        )
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


def _feature_sets(data: pd.DataFrame, baseline_columns: list[str], experimental_columns: list[str]) -> dict[str, list[str]]:
    """Build controlled passing-feature ablations from the frozen baseline."""
    excluded = {"game_id", "gameday", "season", "week", "home_team", "away_team",
                "home_score", "away_score", "spread_line", "total_line"}
    base = [c for c in baseline_columns if c in data.columns and c not in excluded
            and pd.api.types.is_numeric_dtype(data[c])]
    split = [c for c in experimental_columns if c in data.columns and c not in excluded
             and "_shrunk_" not in c and c != "expected_game_plays"]
    passing = [c for c in split if "_pass" in c or "pass_" in c]
    pass_efficiency = [c for c in passing if ("_epa_" in c or "_epa_matchup" in c)]
    pass_success = [c for c in passing if "_success_" in c or "_success_matchup" in c]
    pass_volume = [c for c in passing if "_plays_" in c or "plays_faced_pass" in c]
    if not base:
        raise RuntimeError("Frozen baseline feature list is empty.")
    return {
        "baseline_frozen_features": base,
        "baseline_plus_pass_efficiency_only": list(dict.fromkeys(base + pass_efficiency)),
        "baseline_plus_pass_success_only": list(dict.fromkeys(base + pass_success)),
        "baseline_plus_pass_volume_only": list(dict.fromkeys(base + pass_volume)),
        "baseline_plus_all_passing": list(dict.fromkeys(base + passing)),
    }


def _fit_weekly(data: pd.DataFrame, features: list[str], alpha: float = ALPHA) -> pd.DataFrame:
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
            model = Ridge(alpha=alpha)
            model.fit(x_train, train[target])
            test[output] = model.predict(x_test)
        predictions.append(test)
    if not predictions:
        return pd.DataFrame()
    return pd.concat(predictions, ignore_index=True).drop_duplicates("game_id")


def _directional_summary(frame: pd.DataFrame, edge_col: str, actual_col: str) -> dict:
    eligible = frame.dropna(subset=[edge_col, actual_col]).copy()
    eligible = eligible[eligible[edge_col] != 0].copy()
    wins = int(((eligible[edge_col] * eligible[actual_col]) > 0).sum())
    pushes = int((eligible[actual_col] == 0).sum())
    losses = int(len(eligible) - wins - pushes)
    no_lean = int((frame[edge_col] == 0).sum())
    return {
        "games_evaluated": int(len(frame)), "directional_picks": int(len(eligible)),
        "wins": wins, "losses": losses, "pushes": pushes, "no_lean": no_lean,
        "accuracy_pct_ex_pushes": round(100 * wins / (wins + losses), 3) if wins + losses else None,
    }


def _wilson_interval(wins: int, trials: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if trials <= 0:
        return None, None
    p = wins / trials
    denom = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denom
    radius = z * np.sqrt((p * (1.0 - p) / trials) + (z * z / (4.0 * trials * trials))) / denom
    return round(100.0 * max(0.0, center - radius), 3), round(100.0 * min(1.0, center + radius), 3)


def _edge_band_summary(frame: pd.DataFrame, edge_col: str, actual_col: str) -> list[dict]:
    bands = [("0_to_1", 0.0, 1.0), ("1_to_2", 1.0, 2.0), ("2_to_3", 2.0, 3.0),
             ("3_to_4", 3.0, 4.0), ("4_plus", 4.0, float("inf"))]
    eligible = frame.dropna(subset=[edge_col, actual_col]).copy()
    eligible["abs_edge"] = eligible[edge_col].abs()
    results = []
    for label, lower, upper in bands:
        band = eligible[(eligible["abs_edge"] >= lower) & (eligible["abs_edge"] < upper)
                        & (eligible[edge_col] != 0)].copy()
        wins = int(((band[edge_col] * band[actual_col]) > 0).sum())
        pushes = int((band[actual_col] == 0).sum())
        losses = int(len(band) - wins - pushes)
        graded = wins + losses
        ci_low, ci_high = _wilson_interval(wins, graded)
        results.append({"edge_band_points": label, "games": int(len(band)), "wins": wins,
                        "losses": losses, "pushes": pushes, "graded_games_ex_pushes": graded,
                        "accuracy_pct_ex_pushes": round(100 * wins / graded, 3) if graded else None,
                        "accuracy_95pct_wilson_ci": [ci_low, ci_high]})
    zero_edge = eligible[eligible[edge_col] == 0]
    results.append({"edge_band_points": "zero_edge_no_lean", "games": int(len(zero_edge)),
                    "wins": 0, "losses": 0, "pushes": 0, "graded_games_ex_pushes": 0,
                    "accuracy_pct_ex_pushes": None, "accuracy_95pct_wilson_ci": [None, None]})
    return results


def _combined_band_summary(frame: pd.DataFrame, edge_col: str, actual_col: str) -> dict:
    eligible = frame.dropna(subset=[edge_col, actual_col]).copy()
    abs_edge = eligible[edge_col].abs()
    band = eligible[(abs_edge >= 2.0) & (abs_edge < 4.0) & (eligible[edge_col] != 0)]
    wins = int(((band[edge_col] * band[actual_col]) > 0).sum())
    pushes = int((band[actual_col] == 0).sum())
    losses = int(len(band) - wins - pushes)
    graded = wins + losses
    ci_low, ci_high = _wilson_interval(wins, graded)
    return {"edge_band_points": "2_to_4_combined", "games": int(len(band)),
            "wins": wins, "losses": losses, "pushes": pushes,
            "graded_games_ex_pushes": graded,
            "accuracy_pct_ex_pushes": round(100 * wins / graded, 3) if graded else None,
            "accuracy_95pct_wilson_ci": [ci_low, ci_high]}


def _roi_summary(frame: pd.DataFrame, edge_col: str, actual_col: str, label: str) -> dict:
    result = {"variant": label, "n_games": int(len(frame))}
    for threshold in THRESHOLDS:
        bets = frame[frame[edge_col].abs() >= threshold].copy()
        wins = ((bets[edge_col] * bets[actual_col]) > 0).sum()
        pushes = (bets[actual_col] == 0).sum()
        losses = len(bets) - wins - pushes
        units = wins * (100 / 110) - losses
        result[f"threshold_{threshold:.1f}"] = {
            "bets": int(len(bets)), "wins": int(wins), "losses": int(losses),
            "pushes": int(pushes), "units": round(float(units), 4),
            "roi_pct": round(float(100 * units / len(bets)), 3) if len(bets) else None}
    return result


def _exact_binomial_two_sided(k: int, n: int) -> float:
    """Exact two-sided binomial tail probability under p=0.5."""
    if n <= 0:
        return 1.0
    return float(binomtest(k, n, p=0.5, alternative="two-sided").pvalue)


def _mcnemar_p_value(baseline_only_correct: int, passing_only_correct: int) -> dict:
    """Exact conditional McNemar test using discordant paired outcomes."""
    b = int(baseline_only_correct)
    c = int(passing_only_correct)
    n = b + c
    return {
        "discordant_pairs": n,
        "baseline_only_correct": b,
        "passing_only_correct": c,
        "exact_two_sided_p_value": _exact_binomial_two_sided(min(b, c), n),
    }


def _matched_directional_comparison(
    predictions: pd.DataFrame,
    baseline_name: str = PRIMARY_BASELINE,
    passing_name: str = PRIMARY_PASSING,
) -> dict:
    """Paired same-game directional comparison, excluding outcome pushes and zero leans."""
    pair = predictions[predictions["variant"].isin([baseline_name, passing_name])].copy()
    if pair.empty:
        raise RuntimeError("Primary baseline/passing variants are absent from predictions.")
    if pair.duplicated(["game_id", "variant"]).any():
        raise RuntimeError("Duplicate game_id/variant rows detected; matched test is ambiguous.")
    results = {}
    for market, edge_col, actual_col in (
        ("ats", "ats_edge", "actual_ats_margin"),
        ("totals", "total_edge", "actual_total_margin"),
    ):
        market_pair = pair.pivot(
            index=["game_id", "season", "week", "gameday"],
            columns="variant",
            values=edge_col,
        )
        required = [baseline_name, passing_name]
        missing = [name for name in required if name not in market_pair.columns]
        if missing or actual_col not in pair.columns:
            raise RuntimeError(f"Missing paired columns for {market}: {missing}")
        actual_by_game = pair.drop_duplicates("game_id").set_index("game_id")[actual_col]
        market_pair = market_pair.join(actual_by_game.rename("actual_margin"), how="inner")
        b_edge = market_pair[baseline_name]
        p_edge = market_pair[passing_name]
        actual = market_pair["actual_margin"]
        complete = b_edge.notna() & p_edge.notna() & actual.notna()
        # No-lean predictions are not incorrect picks. Keep separate counts,
        # and only compare paired directions when both models actually lean.
        one_or_both_no_lean = complete & actual.ne(0) & (b_edge.eq(0) | p_edge.eq(0))
        # A push is not a correct or incorrect directional result.
        no_push = actual.ne(0)
        both_nonzero = b_edge.ne(0) & p_edge.ne(0)
        eligible = complete & no_push & both_nonzero
        # Grade directions only where both models make an actual lean.
        b_correct = np.sign(b_edge[eligible]) == np.sign(actual[eligible])
        p_correct = np.sign(p_edge[eligible]) == np.sign(actual[eligible])
        both_correct = int((b_correct & p_correct).sum())
        both_wrong = int((~b_correct & ~p_correct).sum())
        baseline_only = int((b_correct & ~p_correct).sum())
        passing_only = int((~b_correct & p_correct).sum())
        n = len(b_correct)
        pval = _mcnemar_p_value(baseline_only, passing_only)
        results[market] = {
            "matched_games_with_both_predictions": int(complete.sum()),
            "actual_market_pushes_excluded": int((complete & ~no_push).sum()),
            "either_model_no_lean_excluded": int(one_or_both_no_lean.sum()),
            "evaluated_paired_games": int(n),
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "baseline_only_correct": baseline_only,
            "passing_only_correct": passing_only,
            "baseline_accuracy_pct": round(100 * (both_correct + baseline_only) / n, 3) if n else None,
            "passing_accuracy_pct": round(100 * (both_correct + passing_only) / n, 3) if n else None,
            "accuracy_difference_percentage_points": round(100 * (passing_only - baseline_only) / n, 3) if n else None,
            "mcnemar_exact": pval,
            "interpretation": (
                "Tests whether the two models have different directional accuracy on the same paired games. "
                "Only discordant pairs drive the exact McNemar p-value; both-correct and both-wrong pairs do not. "
                "A small p-value is evidence of a difference, not proof of profitability."
            ),
        }
    return {
        "comparison": f"{baseline_name} vs {passing_name}",
        "grading": "Directional ATS side / over-under relative to the same nflverse spread_line and total_line; actual margin zero is a push.",
        "eligible_rule": "Both models must have a non-zero directional lean and a non-push actual result; no-lean cases are counted separately and omitted from McNemar.",
        "markets": results,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading validated schedule and PBP...")
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    split_history = _team_split_history(pbp, schedule)
    split_features = _pregame_split_features(schedule, split_history)
    baseline_columns = list(baseline.columns)
    experimental_columns = [c for c in split_features.columns if c != "game_id"]
    data = baseline.merge(split_features, on="game_id", how="left", validate="one_to_one")
    lines = schedule[["game_id", "spread_line", "total_line"]].copy()
    data = data.merge(lines, on="game_id", how="left", validate="one_to_one")
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    variants = _feature_sets(data, baseline_columns, experimental_columns)

    summaries, prediction_frames = [], []
    alpha_variants = {
        "baseline_frozen_features": variants["baseline_frozen_features"],
        "baseline_plus_all_passing": variants["baseline_plus_all_passing"],
    }
    runs = [(name, features, ALPHA) for name, features in variants.items()]
    for base_name, features in alpha_variants.items():
        for alpha in (3.0, 10.0, 30.0, 100.0):
            runs.append((f"{base_name}_alpha_{int(alpha)}", features, alpha))
    for name, features, alpha in runs:
        print(f"Running {name} ({len(features)} candidate features, alpha={alpha})...")
        pred = _fit_weekly(data, features, alpha=alpha)
        if pred.empty:
            raise RuntimeError(f"No chronological predictions generated for {name}")
        pred["variant"] = name
        pred["ridge_alpha"] = alpha
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
    # Same common game IDs across every variant, as before.
    common = set.intersection(*[set(g["game_id"]) for _, g in all_preds.groupby("variant")])
    all_preds = all_preds[all_preds["game_id"].isin(common)].copy()

    def metric_summary(group: pd.DataFrame, name: str) -> dict:
        ats = group.dropna(subset=["ats_edge", "actual_ats_margin"])
        totals = group.dropna(subset=["total_edge", "actual_total_margin"])
        return {
            "variant": name, "games": int(len(group)),
            "ats_margin_mae": round(float((ats["pred_home_margin"] - ats["actual_home_margin"]).abs().mean()), 4),
            "total_mae": round(float((totals["pred_total"] - totals["actual_total"]).abs().mean()), 4),
            "ats_directional_accuracy_pct": round(float(((ats["ats_edge"] > 0) == (ats["actual_ats_margin"] > 0))[ats["actual_ats_margin"] != 0].mean() * 100), 3),
            "totals_directional_accuracy_pct": round(float(((totals["total_edge"] > 0) == (totals["actual_total_margin"] > 0))[totals["actual_total_margin"] != 0].mean() * 100), 3),
            "ats_all_game_directional": _directional_summary(ats, "ats_edge", "actual_ats_margin"),
            "totals_all_game_directional": _directional_summary(totals, "total_edge", "actual_total_margin"),
            "ats_edge_bands": _edge_band_summary(ats, "ats_edge", "actual_ats_margin"),
            "totals_edge_bands": _edge_band_summary(totals, "total_edge", "actual_total_margin"),
            "ats_combined_2_to_4": _combined_band_summary(ats, "ats_edge", "actual_ats_margin"),
            "totals_combined_2_to_4": _combined_band_summary(totals, "total_edge", "actual_total_margin"),
            "ats_fixed_thresholds": _roi_summary(ats, "ats_edge", "actual_ats_margin", name),
            "totals_fixed_thresholds": _roi_summary(totals, "total_edge", "actual_total_margin", name),
        }

    for name, group in all_preds.groupby("variant"):
        summary = metric_summary(group, name)
        summary["common_games"] = summary.pop("games")
        summaries.append(summary)

    paired = _matched_directional_comparison(all_preds)
    season_summaries = []
    for (name, season), group in all_preds.groupby(["variant", "season"]):
        summary = metric_summary(group, name)
        summary["season"] = int(season)
        season_summaries.append(summary)
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
        "regularization_sensitivity_alphas": [3.0, 10.0, 30.0, 100.0],
        "regularization_warning": "Alpha sensitivity is descriptive on the same chronological test period; do not choose alpha from these results without a separate nested or later holdout.",
        "comparison_rule": "Same intersection of weekly chronological out-of-sample game IDs across every variant; primary paired comparison additionally uses baseline vs all-passing at alpha=10.",
        "market_line_warning": "spread_line and total_line come from nflverse schedule data; they are not verified executable sportsbook quotes.",
        "thresholds": list(THRESHOLDS),
        "feature_counts": {name: len(cols) for name, cols in variants.items()},
        "run_feature_counts": {name: len(cols) for name, cols, _alpha in runs},
        "feature_names": variants,
        "variants": summaries,
        "matched_directional_comparison": paired,
        "season_results": season_summaries,
        "season_comparison_warning": "Season-level samples are smaller and descriptive; do not select a feature set based on the best season or treat threshold ROI as independently validated.",
        "matched_test_warning": "Exact McNemar is an unadjusted two-sided paired test; it addresses directional correctness only, not betting profitability. These historical seasons have previously been inspected and are not a pristine holdout.",
        "prediction_csv": str(csv_path),
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {csv_path} and {json_path}")


if __name__ == "__main__":
    main()
