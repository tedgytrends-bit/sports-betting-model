"""Research-only 2026 Weeks 1-8 four-model chronological reconstruction.

This is a retrospective research comparison, not a record of forecasts that were
published before the games. All four variants are regenerated with the same
chronological fitting procedure and are evaluated on the same common games.

Market policy:
- Weeks 1-7: nflverse schedule spread_line / total_line. These are archived
  comparison lines; the exact executable sportsbook is not verified.
- Week 8: user-verified Bovada board supplied before the games.

No production projections or official prospective records are modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from injury_model import add_injury_features, load_injury_reports
from research.efficiency_feature_experiments import (
    _fit_weekly,
    _team_split_history,
    _pregame_split_features,
)
from research.four_model_comparison import _feature_columns

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
TARGET_SEASON = 2026
FIRST_WEEK = 1
LAST_WEEK = 8
ALPHA = 10.0
OUT = ROOT / "data" / "four_model_2026_weeks01_08"

VARIANTS = {
    "baseline_only": "baseline",
    "injury_only_added": "injury",
    "efficiency_only_added": "efficiency",
    "combined_efficiency_plus_injury": "combined",
}
MODEL_ORDER = tuple(VARIANTS.values())
ALIASES = {"LA": "LAR", "JAC": "JAX", "OAK": "LV", "SD": "LAC"}

# User-verified Bovada Week 8 board. Tuple = favorite, favorite spread, total.
WEEK8_BOVADA = {
    "CAR @ GB": ("GB", 3.5, 47.0),
    "ARI @ DAL": ("DAL", 7.0, 54.5),
    "ATL @ TB": ("TB", 2.0, 43.0),
    "BAL @ BUF": ("BUF", 3.0, 55.0),
    "CLE @ PIT": ("PIT", 3.5, 39.0),
    "IND @ JAX": ("JAX", 10.5, 46.0),
    "LV @ NYJ": ("NYJ", 2.0, 46.5),
    "MIN @ DET": ("DET", 3.5, 45.5),
    "TEN @ CIN": ("CIN", 13.0, 45.5),
    "LAC @ LAR": ("LAR", 6.5, 46.0),
    "KC @ DEN": ("KC", 1.0, 41.0),
    "NE @ MIA": ("NE", 7.0, 42.0),
    "PHI @ WAS": ("WAS", 6.0, 40.5),
    "CHI @ SEA": ("SEA", 3.0, 46.5),
}


def norm_team(value: object) -> str:
    team = str(value).strip().upper()
    return ALIASES.get(team, team)


def _market_for_row(row: pd.Series) -> tuple[float, float, str]:
    """Return home-favorite-positive spread convention, total, and source."""
    week = int(row["week"])
    away, home = norm_team(row["away_team"]), norm_team(row["home_team"])
    matchup = f"{away} @ {home}"
    if week == 8:
        if matchup not in WEEK8_BOVADA:
            raise RuntimeError(f"Missing user-verified Week 8 Bovada line for {matchup}.")
        favorite, points, total = WEEK8_BOVADA[matchup]
        spread_line = points if norm_team(favorite) == home else -points
        return float(spread_line), float(total), "User-verified Bovada Week 8 board"

    spread = pd.to_numeric(pd.Series([row.get("spread_line")]), errors="coerce").iloc[0]
    total = pd.to_numeric(pd.Series([row.get("total_line")]), errors="coerce").iloc[0]
    if pd.isna(spread) or pd.isna(total):
        raise RuntimeError(f"Missing nflverse schedule market line for {matchup}, Week {week}.")
    return float(spread), float(total), "nflverse schedule line (sportsbook not verified)"


def _grade(edge: float, actual_margin: float) -> str:
    if pd.isna(edge) or pd.isna(actual_margin):
        return "Pending"
    if abs(actual_margin) < 1e-9:
        return "Push"
    if abs(edge) < 1e-9:
        return "No lean"
    return "Win" if edge * actual_margin > 0 else "Loss"


def _ats_pick(row: pd.Series) -> str:
    edge = float(row["ats_edge"])
    spread = float(row["market_spread_line"])
    if abs(edge) < 1e-9:
        return "No lean"
    if edge > 0:
        return f"{norm_team(row['home_team'])} {-spread:+g}"
    return f"{norm_team(row['away_team'])} {spread:+g}"


def _total_pick(edge: float) -> str:
    if abs(edge) < 1e-9:
        return "No lean"
    return "Over" if edge > 0 else "Under"


def _record(frame: pd.DataFrame, result_col: str) -> dict:
    wins = int((frame[result_col] == "Win").sum())
    losses = int((frame[result_col] == "Loss").sum())
    pushes = int((frame[result_col] == "Push").sum())
    no_lean = int((frame[result_col] == "No lean").sum())
    pending = int((frame[result_col] == "Pending").sum())
    graded = wins + losses
    bets = wins + losses + pushes
    profit_units = wins * (100.0 / 110.0) - losses
    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "no_lean": no_lean,
        "pending": pending,
        "graded_ex_pushes": graded,
        "accuracy_pct_ex_pushes": round(100.0 * wins / graded, 3) if graded else None,
        "flat_profit_units_at_minus110": round(profit_units, 4),
        "flat_roi_pct_at_minus110": round(100.0 * profit_units / bets, 3) if bets else None,
    }


def _weekly_summary(long: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (week, model), group in long.groupby(["week", "model"], sort=True):
        ats = _record(group, "ats_result")
        total = _record(group, "total_result")
        rows.append({
            "season": TARGET_SEASON,
            "week": int(week),
            "model": model,
            "games": int(len(group)),
            "ats_wins": ats["wins"],
            "ats_losses": ats["losses"],
            "ats_pushes": ats["pushes"],
            "ats_accuracy_pct_ex_pushes": ats["accuracy_pct_ex_pushes"],
            "ats_roi_pct_at_minus110": ats["flat_roi_pct_at_minus110"],
            "total_wins": total["wins"],
            "total_losses": total["losses"],
            "total_pushes": total["pushes"],
            "total_accuracy_pct_ex_pushes": total["accuracy_pct_ex_pushes"],
            "total_roi_pct_at_minus110": total["flat_roi_pct_at_minus110"],
            "ats_margin_mae": round(float((group["pred_home_margin"] - group["actual_home_margin"]).abs().mean()), 4),
            "total_mae": round(float((group["pred_total"] - group["actual_total"]).abs().mean()), 4),
        })
    return pd.DataFrame(rows)


def _pairwise_tests(long: pd.DataFrame, market: str) -> list[dict]:
    result_col = f"{market}_result"
    rows: list[dict] = []
    indexed = {
        model: group.set_index("game_id")[result_col]
        for model, group in long.groupby("model")
    }
    for a, b in combinations(MODEL_ORDER, 2):
        joined = pd.concat([indexed[a].rename(a), indexed[b].rename(b)], axis=1, join="inner")
        joined = joined[joined[a].isin(["Win", "Loss"]) & joined[b].isin(["Win", "Loss"])]
        a_only = int(((joined[a] == "Win") & (joined[b] == "Loss")).sum())
        b_only = int(((joined[a] == "Loss") & (joined[b] == "Win")).sum())
        discordant = a_only + b_only
        p_value = float(binomtest(a_only, discordant, 0.5, alternative="two-sided").pvalue) if discordant else 1.0
        rows.append({
            "market": market,
            "model_a": a,
            "model_b": b,
            "common_graded_games": int(len(joined)),
            "model_a_only_correct": a_only,
            "model_b_only_correct": b_only,
            "discordant_games": discordant,
            "mcnemar_exact_two_sided_p": round(p_value, 6),
        })
    return rows


def _wide_games(long: pd.DataFrame) -> pd.DataFrame:
    base_cols = [
        "season", "week", "game_id", "gameday", "away_team", "home_team",
        "home_score", "away_score", "actual_home_margin", "actual_total",
        "market_spread_line", "market_total", "market_source",
    ]
    base = long[base_cols].drop_duplicates("game_id").set_index("game_id")
    fields = [
        "pred_home", "pred_away", "pred_home_margin", "pred_total",
        "ats_edge", "ats_pick", "ats_result", "total_edge", "total_pick", "total_result",
    ]
    for model in MODEL_ORDER:
        part = long[long["model"] == model].set_index("game_id")[fields].copy()
        part.columns = [f"{model}_{c}" for c in part.columns]
        base = base.join(part, how="left")

    def agreement(row: pd.Series, market: str) -> tuple[int, bool]:
        picks = [str(row[f"{m}_{market}_pick"]) for m in MODEL_ORDER]
        counts = pd.Series(picks).value_counts()
        max_count = int(counts.iloc[0]) if len(counts) else 0
        return max_count, max_count == len(MODEL_ORDER)

    ats_agree = base.apply(lambda r: agreement(r, "ats"), axis=1)
    total_agree = base.apply(lambda r: agreement(r, "total"), axis=1)
    base["ats_max_models_same_pick"] = [x[0] for x in ats_agree]
    base["ats_all_four_agree"] = [x[1] for x in ats_agree]
    base["total_max_models_same_pick"] = [x[0] for x in total_agree]
    base["total_all_four_agree"] = [x[1] for x in total_agree]
    return base.reset_index().sort_values(["week", "gameday", "game_id"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading schedule, play-by-play, and injury data...")
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)

    print("Building identical research feature frames for all four variants...")
    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    injury_frame = add_injury_features(baseline, schedule, reports)
    split = _pregame_split_features(schedule, _team_split_history(pbp, schedule))

    injury_cols = [
        c for c in injury_frame.columns
        if c.startswith((
            "home_injury_", "away_injury_", "home_inj_", "away_inj_",
            "home_qb_", "away_qb_", "home_ol_", "away_ol_",
            "home_skill_", "away_skill_", "home_defense_", "away_defense_",
        ))
    ]
    passing_cols = [c for c in split.columns if c != "game_id"]
    data = baseline.merge(split, on="game_id", how="left", validate="one_to_one")
    data = data.merge(
        injury_frame[["game_id"] + injury_cols],
        on="game_id", how="left", validate="one_to_one",
    )
    data = data.merge(
        schedule[["game_id", "spread_line", "total_line"]],
        on="game_id", how="left", validate="one_to_one",
    )
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    variants = _feature_columns(data, list(baseline.columns), passing_cols, injury_cols)

    frames: list[pd.DataFrame] = []
    for variant, model in VARIANTS.items():
        print(f"Generating chronological predictions: {model} ({len(variants[variant])} features)")
        pred = _fit_weekly(data, variants[variant], alpha=ALPHA)
        pred = pred[
            pd.to_numeric(pred["season"], errors="coerce").eq(TARGET_SEASON)
            & pd.to_numeric(pred["week"], errors="coerce").between(FIRST_WEEK, LAST_WEEK)
        ].copy()
        if pred.empty:
            raise RuntimeError(f"No 2026 Weeks 1-8 predictions generated for {model}.")
        pred["model"] = model
        frames.append(pred)

    # Compare only games generated by all four variants.
    common = set.intersection(*[set(frame["game_id"].astype(str)) for frame in frames])
    if not common:
        raise RuntimeError("No common 2026 Weeks 1-8 games across all four variants.")

    prepared: list[pd.DataFrame] = []
    for pred in frames:
        pred["game_id"] = pred["game_id"].astype(str)
        pred = pred[pred["game_id"].isin(common)].copy()
        pred[["market_spread_line", "market_total", "market_source"]] = pred.apply(
            lambda r: pd.Series(_market_for_row(r)), axis=1
        )
        pred["actual_total"] = pred["home_score"] + pred["away_score"]
        pred["actual_home_margin"] = pred["home_score"] - pred["away_score"]
        pred["pred_total"] = pred["pred_home"] + pred["pred_away"]
        pred["pred_home_margin"] = pred["pred_home"] - pred["pred_away"]
        pred["ats_edge"] = pred["pred_home_margin"] - pred["market_spread_line"]
        pred["actual_ats_margin"] = pred["actual_home_margin"] - pred["market_spread_line"]
        pred["total_edge"] = pred["pred_total"] - pred["market_total"]
        pred["actual_total_margin"] = pred["actual_total"] - pred["market_total"]
        pred["ats_pick"] = pred.apply(_ats_pick, axis=1)
        pred["total_pick"] = pred["total_edge"].map(_total_pick)
        pred["ats_result"] = pred.apply(lambda r: _grade(r["ats_edge"], r["actual_ats_margin"]), axis=1)
        pred["total_result"] = pred.apply(lambda r: _grade(r["total_edge"], r["actual_total_margin"]), axis=1)
        prepared.append(pred)

    long = pd.concat(prepared, ignore_index=True)
    compact_cols = [
        "season", "week", "game_id", "gameday", "away_team", "home_team",
        "home_score", "away_score", "model", "pred_home", "pred_away",
        "actual_home_margin", "pred_home_margin", "actual_total", "pred_total",
        "market_spread_line", "market_total", "market_source",
        "ats_edge", "actual_ats_margin", "ats_pick", "ats_result",
        "total_edge", "actual_total_margin", "total_pick", "total_result",
    ]
    long = long[compact_cols].sort_values(["week", "gameday", "game_id", "model"])

    counts = long.groupby("model")["game_id"].nunique().to_dict()
    if len(set(counts.values())) != 1:
        raise RuntimeError(f"Unequal common-game counts after preparation: {counts}")

    schedule_scope = schedule[
        pd.to_numeric(schedule["season"], errors="coerce").eq(TARGET_SEASON)
        & pd.to_numeric(schedule["week"], errors="coerce").between(FIRST_WEEK, LAST_WEEK)
        & pd.to_numeric(schedule["home_score"], errors="coerce").notna()
        & pd.to_numeric(schedule["away_score"], errors="coerce").notna()
    ].copy()
    completed_schedule_games = int(schedule_scope["game_id"].astype(str).nunique())
    missing_common = sorted(set(schedule_scope["game_id"].astype(str)) - common)

    overall = {}
    for model in MODEL_ORDER:
        group = long[long["model"] == model]
        overall[model] = {
            "games": int(group["game_id"].nunique()),
            "ats": _record(group, "ats_result"),
            "totals": _record(group, "total_result"),
            "ats_margin_mae": round(float((group["pred_home_margin"] - group["actual_home_margin"]).abs().mean()), 4),
            "total_mae": round(float((group["pred_total"] - group["actual_total"]).abs().mean()), 4),
        }

    weekly = _weekly_summary(long)
    games = _wide_games(long)
    pairwise = _pairwise_tests(long, "ats") + _pairwise_tests(long, "total")

    agreement = {
        "ats_all_four_agree_games": int(games["ats_all_four_agree"].sum()),
        "ats_disagreement_games": int((~games["ats_all_four_agree"]).sum()),
        "totals_all_four_agree_games": int(games["total_all_four_agree"].sum()),
        "totals_disagreement_games": int((~games["total_all_four_agree"]).sum()),
    }

    report = {
        "status": "RESEARCH_ONLY_RETROSPECTIVE_RECONSTRUCTION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "season": TARGET_SEASON,
            "weeks": [FIRST_WEEK, LAST_WEEK],
            "completed_schedule_games": completed_schedule_games,
            "common_games_all_four_models": int(len(common)),
            "missing_from_common_set": missing_common,
        },
        "method": {
            "variants": list(VARIANTS.keys()),
            "variant_labels": VARIANTS,
            "ridge_alpha": ALPHA,
            "chronology": "Same _fit_weekly procedure for all four models; training data precedes each calendar-week test fold.",
            "injury_timing": "Uses injury_model point-in-time rules already validated for the four-model research branch.",
            "weeks_1_7_market": "nflverse schedule spread_line and total_line; exact executable sportsbook not verified.",
            "week_8_market": "User-verified Bovada board supplied pregame.",
            "roi": "Every non-zero directional lean; flat 1-unit risk per game at -110. Win = +0.9091u, loss = -1u, push = 0u.",
            "official_status": "Retrospective research reconstruction only; not an official prospective forecast record.",
        },
        "feature_counts": {name: len(cols) for name, cols in variants.items()},
        "overall": overall,
        "agreement": agreement,
        "pairwise_mcnemar": pairwise,
        "cautions": [
            "Weeks 1-7 use nflverse archived schedule lines rather than verified Bovada quotes.",
            "Historical seasons used for training have already informed prior research and are not a pristine untouched holdout.",
            "These are retrospective chronological reconstructions, not necessarily the exact forecasts that were published at the time.",
            "Directional accuracy and simulated -110 ROI do not establish future profitability.",
            "No production model or official prospective record is changed by this analysis.",
        ],
    }

    long_path = OUT / "four_model_2026_weeks01_08_long.csv"
    games_path = OUT / "four_model_2026_weeks01_08_games.csv"
    weekly_path = OUT / "four_model_2026_weeks01_08_weekly.csv"
    summary_path = OUT / "four_model_2026_weeks01_08_summary.json"
    long.to_csv(long_path, index=False)
    games.to_csv(games_path, index=False)
    weekly.to_csv(weekly_path, index=False)
    summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "scope": report["scope"],
        "overall": overall,
        "agreement": agreement,
        "outputs": [str(long_path), str(games_path), str(weekly_path), str(summary_path)],
    }, indent=2))


if __name__ == "__main__":
    main()
