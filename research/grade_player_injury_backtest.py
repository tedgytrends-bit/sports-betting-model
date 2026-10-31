
#!/usr/bin/env python3
"""Grade paired baseline vs player-injury predictions against historical NFL lines.

Research only. Uses historical nflverse closing lines and recorded odds where
available. Missing odds are excluded from ROI calculations, never replaced
with an assumed -110 price.

Does not modify the production model or official prospective record.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import load_schedule_data

DATA_DIR = ROOT / "data" / "player_injury_backtests"

# Predeclared sensitivity grid. Do not select a threshold solely because
# it happens to look best after examining these results.
ATS_THRESHOLDS = (1.5, 2.5, 3.5)
TOTAL_THRESHOLDS = (1.5, 2.5, 3.5)

MARKET_COLUMNS = [
    "game_id",
    "spread_line",
    "total_line",
    "home_spread_odds",
    "away_spread_odds",
    "over_odds",
    "under_odds",
]


def latest_paired_file() -> Path:
    files = sorted(DATA_DIR.glob("player_injury_paired_predictions_*.csv"))
    if not files:
        raise FileNotFoundError(
            "No paired prediction CSV found. Run the chronological player "
            "injury backtest workflow first."
        )
    return files[-1]


def american_profit_per_unit(odds: float) -> float:
    """Return net profit on a one-unit risk at American odds."""
    if not np.isfinite(odds) or odds == 0:
        raise ValueError(f"Invalid American odds: {odds}")

    if odds > 0:
        return float(odds / 100.0)

    return float(100.0 / abs(odds))


def normalize_numeric_columns(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def prepare_market_data(schedule: pd.DataFrame) -> pd.DataFrame:
    missing = set(MARKET_COLUMNS) - set(schedule.columns)
    if missing:
        raise ValueError(
            "Historical schedule data is missing required market fields: "
            f"{sorted(missing)}"
        )

    markets = schedule[MARKET_COLUMNS].copy()

    if markets["game_id"].duplicated().any():
        duplicates = int(markets["game_id"].duplicated().sum())
        raise ValueError(
            f"Historical schedule contains {duplicates} duplicate game IDs."
        )

    numeric_columns = [
        "spread_line",
        "total_line",
        "home_spread_odds",
        "away_spread_odds",
        "over_odds",
        "under_odds",
    ]
    return normalize_numeric_columns(markets, numeric_columns)


def prepare_paired_data(
    paired: pd.DataFrame,
    markets: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "game_id",
        "season",
        "home_score",
        "away_score",
        "pred_home_score_baseline",
        "pred_away_score_baseline",
        "pred_home_score_injury",
        "pred_away_score_injury",
    }

    missing = required - set(paired.columns)
    if missing:
        raise ValueError(
            f"Paired prediction file is missing columns: {sorted(missing)}"
        )

    if paired["game_id"].duplicated().any():
        raise ValueError("Duplicate game IDs found in paired predictions.")

    frame = paired.merge(
        markets,
        on="game_id",
        how="left",
        validate="one_to_one",
    )

    numeric_columns = [
        "home_score",
        "away_score",
        "pred_home_score_baseline",
        "pred_away_score_baseline",
        "pred_home_score_injury",
        "pred_away_score_injury",
        "spread_line",
        "total_line",
        "home_spread_odds",
        "away_spread_odds",
        "over_odds",
        "under_odds",
    ]
    frame = normalize_numeric_columns(frame, numeric_columns)

    frame["baseline_total"] = (
        frame["pred_home_score_baseline"]
        + frame["pred_away_score_baseline"]
    )
    frame["injury_total"] = (
        frame["pred_home_score_injury"]
        + frame["pred_away_score_injury"]
    )

    frame["baseline_home_margin"] = (
        frame["pred_home_score_baseline"]
        - frame["pred_away_score_baseline"]
    )
    frame["injury_home_margin"] = (
        frame["pred_home_score_injury"]
        - frame["pred_away_score_injury"]
    )

    frame["actual_total"] = frame["home_score"] + frame["away_score"]
    frame["actual_home_margin"] = frame["home_score"] - frame["away_score"]

    return frame


def grade_market(
    frame: pd.DataFrame,
    model_name: str,
    market: str,
    threshold: float,
) -> dict:
    """Grade directional picks and separately calculate ROI where odds exist."""

    if market == "ATS":
        # nflverse spread_line is treated as the home-team handicap:
        # negative = home favorite; positive = away favorite.
        # Positive edge selects home; negative edge selects away.
        edge = frame[f"{model_name}_home_margin"] + frame["spread_line"]
        actual = frame["actual_home_margin"] + frame["spread_line"]

        selected_odds = pd.Series(
            np.where(edge >= 0, frame["home_spread_odds"], frame["away_spread_odds"]),
            index=frame.index,
            dtype="float64",
        )

    elif market == "TOTAL":
        # Positive edge selects over; negative edge selects under.
        edge = frame[f"{model_name}_total"] - frame["total_line"]
        actual = frame["actual_total"] - frame["total_line"]

        selected_odds = pd.Series(
            np.where(edge >= 0, frame["over_odds"], frame["under_odds"]),
            index=frame.index,
            dtype="float64",
        )

    else:
        raise ValueError(f"Unknown market: {market}")

    valid = edge.notna() & actual.notna()
    edge = edge[valid]
    actual = actual[valid]
    selected_odds = selected_odds[valid]

    selected = edge.abs() >= threshold
    edge = edge[selected]
    actual = actual[selected]
    selected_odds = selected_odds[selected]

    # A push is a selected wager that lands exactly on the market line.
    pushes = actual.eq(0)

    # A win occurs when the actual result is in the model's selected direction.
    wins = (np.sign(edge) == np.sign(actual)) & ~pushes
    losses = (np.sign(edge) != np.sign(actual)) & ~pushes

    directional_bets = int(len(edge))
    directional_wins = int(wins.sum())
    directional_losses = int(losses.sum())
    directional_pushes = int(pushes.sum())
    directional_decisions = directional_wins + directional_losses

    # Actual odds are required for ROI. Do not assume -110 when missing.
    priced = selected_odds.notna() & selected_odds.ne(0)
    priced_wins = wins & priced
    priced_losses = losses & priced
    priced_pushes = pushes & priced

    priced_bets = int(priced.sum())
    missing_price_bets = directional_bets - priced_bets

    net_units = 0.0
    units_risked = float(priced_bets)

    for index in selected_odds.index[priced]:
        odds = float(selected_odds.loc[index])

        if bool(wins.loc[index]):
            net_units += american_profit_per_unit(odds)
        elif bool(losses.loc[index]):
            net_units -= 1.0
        # A push returns the stake and has zero net profit.

    priced_decisions = int(priced_wins.sum() + priced_losses.sum())

    return {
        "model": model_name,
        "market": market,
        "edge_threshold_points": threshold,

        "directional_bets": directional_bets,
        "directional_wins": directional_wins,
        "directional_losses": directional_losses,
        "directional_pushes": directional_pushes,
        "directional_win_rate_excluding_pushes": (
            directional_wins / directional_decisions
            if directional_decisions else None
        ),

        "bets_with_recorded_odds": priced_bets,
        "bets_missing_recorded_odds": missing_price_bets,
        "priced_wins": int(priced_wins.sum()),
        "priced_losses": int(priced_losses.sum()),
        "priced_pushes": int(priced_pushes.sum()),
        "priced_win_rate_excluding_pushes": (
            int(priced_wins.sum()) / priced_decisions
            if priced_decisions else None
        ),

        "net_units_using_recorded_odds": round(net_units, 4),
        "units_risked_including_pushes": round(units_risked, 4),
        "roi_percent_using_recorded_odds": (
            round(100.0 * net_units / units_risked, 2)
            if units_risked else None
        ),
    }


def grade_all(frame: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    overall: list[dict] = []
    by_season: list[dict] = []

    for market, thresholds in (
        ("ATS", ATS_THRESHOLDS),
        ("TOTAL", TOTAL_THRESHOLDS),
    ):
        for threshold in thresholds:
            for model_name in ("baseline", "injury"):
                overall.append(
                    grade_market(frame, model_name, market, threshold)
                )

                for season, season_frame in frame.groupby("season"):
                    result = grade_market(
                        season_frame,
                        model_name,
                        market,
                        threshold,
                    )
                    result["season"] = int(season)
                    by_season.append(result)

    return overall, by_season


def self_test() -> None:
    """Test ATS, totals, pushes, and actual American-odds calculations."""

    sample = pd.DataFrame({
        "baseline_home_margin": [7.0, -7.0, 4.5],
        "injury_home_margin": [7.0, -7.0, 4.5],
        "baseline_total": [50.0, 40.0, 48.0],
        "injury_total": [50.0, 40.0, 48.0],
        "actual_home_margin": [7.0, -7.0, 3.0],
        "actual_total": [50.0, 40.0, 45.0],
        "spread_line": [-3.0, 3.0, -3.0],
        "total_line": [47.0, 43.0, 45.0],
        "home_spread_odds": [-110.0, -110.0, -110.0],
        "away_spread_odds": [-110.0, -110.0, -110.0],
        "over_odds": [100.0, 100.0, 100.0],
        "under_odds": [-120.0, -120.0, -120.0],
    })

    ats = grade_market(sample, "baseline", "ATS", 1.0)
    assert (
        ats["directional_wins"],
        ats["directional_losses"],
        ats["directional_pushes"],
    ) == (2, 0, 1)

    totals = grade_market(sample, "baseline", "TOTAL", 1.0)
    assert (
        totals["directional_wins"],
        totals["directional_losses"],
        totals["directional_pushes"],
    ) == (2, 0, 1)

    # First totals pick wins at +100; second wins at -120.
    expected_profit = 1.0 + (100.0 / 120.0)
    assert abs(
        totals["net_units_using_recorded_odds"] - expected_profit
    ) < 0.0001

    # A missing price must not be replaced with -110.
    missing_price_sample = sample.iloc[[0]].copy()
    missing_price_sample["over_odds"] = np.nan

    missing_price_result = grade_market(
        missing_price_sample,
        "baseline",
        "TOTAL",
        1.0,
    )
    assert missing_price_result["bets_with_recorded_odds"] == 0
    assert missing_price_result["bets_missing_recorded_odds"] == 1
    assert missing_price_result["roi_percent_using_recorded_odds"] is None

    print("Betting-grade self-tests passed.")


def main() -> None:
    self_test()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    paired_path = latest_paired_file()
    paired = pd.read_csv(paired_path)

    schedule = load_schedule_data()
    markets = prepare_market_data(schedule)
    frame = prepare_paired_data(paired, markets)

    overall, by_season = grade_all(frame)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "paired_prediction_file": paired_path.name,
        "paired_games": int(len(frame)),

        "market_coverage": {
            "games_with_spread_line": int(frame["spread_line"].notna().sum()),
            "games_with_total_line": int(frame["total_line"].notna().sum()),
            "games_with_home_spread_odds": int(
                frame["home_spread_odds"].notna().sum()
            ),
            "games_with_away_spread_odds": int(
                frame["away_spread_odds"].notna().sum()
            ),
            "games_with_over_odds": int(frame["over_odds"].notna().sum()),
            "games_with_under_odds": int(frame["under_odds"].notna().sum()),
        },

        "pricing_method": (
            "Uses the historical odds recorded in the schedule data for the "
            "selected side. Missing or invalid prices are excluded from ROI. "
            "No default -110 assumption is applied."
        ),

        "line_convention": {
            "spread": (
                "Home-team handicap: negative spread_line indicates a home "
                "favorite. ATS edge = predicted home margin + spread_line. "
                "Positive edge selects home; negative edge selects away."
            ),
            "total": (
                "Totals edge = predicted total - total_line. "
                "Positive edge selects over; negative edge selects under."
            ),
        },

        "thresholds_tested": {
            "ats_points": list(ATS_THRESHOLDS),
            "totals_points": list(TOTAL_THRESHOLDS),
        },

        "overall_results": overall,
        "season_results": by_season,

        "limitations": [
            "Historical market lines and prices are schedule-source closing "
            "data, not verified Bovada or DraftKings prices.",
            "ROI is calculated only on wagers with a recorded valid price.",
            "Directional results include qualifying picks even when odds are "
            "missing; those picks are not included in ROI.",
            "Thresholds are a predeclared sensitivity grid, not proof that "
            "the best-performing threshold would have been selected in advance.",
            "Historical injury timestamps do not prove public availability "
            "at the exact timestamp.",
            "This research report does not change the production model or "
            "official prospective record.",
        ],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = DATA_DIR / f"player_injury_betting_report_{stamp}.json"
    results_path = DATA_DIR / f"player_injury_betting_results_{stamp}.csv"

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    pd.DataFrame(overall).to_csv(results_path, index=False)

    print(json.dumps(report, indent=2))
    print(f"Saved betting report: {report_path}")
    print(f"Saved overall results: {results_path}")
    print("No official model, projection, or prospective record was changed.")


if __name__ == "__main__":
    main()
