"""Build a transparent Week 8 four-model comparison without rewriting the original public snapshot.

Baseline/injury values for the 12 originally published games are read verbatim from
the immutable Nov. 1 public CSV. Efficiency/combined are chronological predictions
trained only on games before the Week 8 test window. Bears-Seahawks is a separately
labeled late addition using the saved Nov. 2 four-model forecast.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import build_efficiency_model_dataset, load_pbp, load_schedule_data
from injury_model import add_injury_features, load_injury_reports
from research.efficiency_feature_experiments import (
    _fit_weekly, _team_split_history, _pregame_split_features,
)
from research.four_model_comparison import _feature_columns

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
WEEK = 8
SEASON = 2026
ALPHA = 10.0
MIN_TRAIN_GAMES = 500
SNAPSHOT = ROOT / "data/public_snapshots/nfl_week_08_public_2026-11-01.csv"
OUT = ROOT / "data/four_model_week08"

# User-verified Week 8 Bovada lines override the older snapshot values.
MARKETS = {
    "NE @ MIA": ("NE", 7.0, 42.0), "KC @ DEN": ("KC", 1.0, 41.0),
    "LAC @ LA": ("LA", 6.5, 46.0), "TEN @ CIN": ("CIN", 13.0, 45.5),
    "MIN @ DET": ("DET", 3.5, 45.5), "CLE @ PIT": ("PIT", 3.5, 39.0),
    "IND @ JAX": ("JAX", 10.5, 46.0), "BAL @ BUF": ("BUF", 3.0, 55.0),
    "ATL @ TB": ("TB", 2.0, 43.0), "ARI @ DAL": ("DAL", 7.0, 54.5),
    "PHI @ WAS": ("WAS", 6.0, 40.5), "LV @ NYJ": ("NYJ", 2.0, 46.5),
    "CAR @ GB": ("GB", 3.5, 47.0), "CHI @ SEA": ("SEA", 3.0, 46.5),
}

# Frozen late-add forecast from the Nov. 2 pregame four-model run.
# It is intentionally kept separate from the Nov. 1 public snapshot.
LATE_ADD = {
    "CHI @ SEA": {
        "market_favorite": "SEA", "market_spread": 3.0, "market_total": 46.5,
        "baseline": {"away": 22.18, "home": 24.19},
        "injury": {"away": 23.28, "home": 21.72},
        "efficiency": {"away": 21.11, "home": 23.71},
        "combined": {"away": 22.15, "home": 21.56},
        "forecast_created_at": "2026-11-02 pregame research forecast",
    }
}
ALIASES = {"LA": "LAR", "JAC": "JAX", "OAK": "LV", "SD": "LAC"}


def norm_team(value: object) -> str:
    team = str(value).strip().upper()
    return ALIASES.get(team, team)


def parse_score_pair(value: str, away: str, home: str) -> tuple[float, float]:
    matches = re.findall(r"([A-Z]{2,3})\s+(-?\d+(?:\.\d+)?)", str(value).upper())
    scores = {norm_team(team): float(score) for team, score in matches}
    if norm_team(away) not in scores or norm_team(home) not in scores:
        raise ValueError(f"Could not parse score projection {value!r} for {away}@{home}")
    return scores[norm_team(away)], scores[norm_team(home)]


def parse_market_spread(value: str) -> tuple[str, float]:
    match = re.search(r"([A-Z]{2,3})\s+(-?\d+(?:\.\d+)?)", str(value).upper())
    if not match:
        raise ValueError(f"Could not parse market spread: {value!r}")
    team, line = norm_team(match.group(1)), float(match.group(2))
    return team, abs(line)


def lean_ats(home: str, away: str, pred_home: float, pred_away: float,
             favorite: str, spread: float) -> tuple[str, float]:
    # favorite is quoted at -spread; the other side is +spread.
    home_market_line = -spread if norm_team(favorite) == norm_team(home) else spread
    edge = (pred_home - pred_away) + home_market_line
    if abs(edge) < 1e-9:
        return "No edge", edge
    if edge > 0:
        pick = f"{norm_team(home)} {home_market_line:+g}"
    else:
        away_line = -home_market_line
        pick = f"{norm_team(away)} {away_line:+g}"
    return f"Lean {pick}", edge


def lean_total(pred_total: float, market_total: float) -> tuple[str, float]:
    edge = pred_total - market_total
    if abs(edge) < 1e-9:
        return "No edge", edge
    return ("Over" if edge > 0 else "Under"), edge


def add_model_fields(row: dict, name: str, away_score: float, home_score: float,
                     favorite: str, spread: float, total_line: float,
                     away: str, home: str) -> None:
    ats, ats_edge = lean_ats(home, away, home_score, away_score, favorite, spread)
    total = away_score + home_score
    total_pick, total_edge = lean_total(total, total_line)
    row[f"{name}_away_score"] = round(away_score, 2)
    row[f"{name}_home_score"] = round(home_score, 2)
    row[f"{name}_projected_total"] = round(total, 2)
    row[f"{name}_ats_pick"] = ats
    row[f"{name}_ats_edge"] = round(ats_edge, 2)
    row[f"{name}_total_pick"] = total_pick
    row[f"{name}_total_edge"] = round(total_edge, 2)


def main() -> None:
    if not SNAPSHOT.exists():
        raise FileNotFoundError(f"Immutable Week 8 public snapshot missing: {SNAPSHOT}")
    public = pd.read_csv(SNAPSHOT)
    schedule = load_schedule_data()
    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)

    baseline = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    injury_frame = add_injury_features(baseline, schedule, reports)
    split = _pregame_split_features(schedule, _team_split_history(pbp, schedule))
    injury_cols = [
        c for c in injury_frame.columns
        if c.startswith(("home_injury_", "away_injury_", "home_inj_", "away_inj_",
                         "home_qb_", "away_qb_", "home_ol_", "away_ol_",
                         "home_skill_", "away_skill_", "home_defense_", "away_defense_"))
    ]
    passing_cols = [c for c in split.columns if c != "game_id"]
    data = baseline.merge(split, on="game_id", how="left", validate="one_to_one")
    data = data.merge(injury_frame[["game_id"] + injury_cols], on="game_id",
                      how="left", validate="one_to_one")
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")
    variants = _feature_columns(data, list(baseline.columns), passing_cols, injury_cols)

    predictions = {}
    for variant in ("baseline_only", "injury_only_added", "efficiency_only_added", "combined_efficiency_plus_injury"):
        print(f"Generating chronological Week 8 predictions: {variant}")
        pred = _fit_weekly(data, variants[variant], alpha=ALPHA)
        pred = pred[
            pd.to_numeric(pred["season"], errors="coerce").eq(SEASON)
            & pd.to_numeric(pred["week"], errors="coerce").eq(WEEK)
        ].copy()
        if pred.empty:
            raise RuntimeError(f"No 2026 Week {WEEK} predictions generated for {variant}.")
        predictions[variant] = pred.set_index("game_id")

    week_schedule = schedule[
        pd.to_numeric(schedule["season"], errors="coerce").eq(SEASON)
        & pd.to_numeric(schedule["week"], errors="coerce").eq(WEEK)
    ].copy()
    week_schedule = week_schedule.drop_duplicates("game_id")
    rows = []
    matched_snapshot_games = set()
    schedule_rows = week_schedule.to_dict("records")

    def find_schedule_game(away: str, home: str, label: str) -> dict:
        matches = [
            g for g in schedule_rows
            if norm_team(g["away_team"]) == norm_team(away)
            and norm_team(g["home_team"]) == norm_team(home)
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected exactly one Week {WEEK} schedule row for snapshot matchup "
                f"{label}; found {len(matches)}."
            )
        return matches[0]

    def actual_fields(game: dict) -> dict:
        away_score, home_score = game.get("away_score"), game.get("home_score")
        complete = pd.notna(away_score) and pd.notna(home_score)
        return {
            "actual_away_score": away_score if complete else np.nan,
            "actual_home_score": home_score if complete else np.nan,
            "actual_total": float(away_score) + float(home_score) if complete else np.nan,
        }

    # Build the original-public section from the immutable snapshot itself.
    # Schedule-only games are intentionally not fabricated into the public board.
    for _, s in public.iterrows():
        parts = str(s["Game"]).upper().split("@")
        if len(parts) != 2:
            raise RuntimeError(f"Invalid matchup label in frozen snapshot: {s['Game']!r}")
        away, home = norm_team(parts[0]), norm_team(parts[1])
        matchup = f"{away} @ {home}"
        game = find_schedule_game(away, home, str(s["Game"]))
        game_id = game["game_id"]
        matched_snapshot_games.add(str(s["Game"]))
        if matchup not in MARKETS:
            raise RuntimeError(f"Missing user-verified Bovada line for {matchup}.")
        favorite, spread, total_line = MARKETS[matchup]
        row = {
            "season": SEASON, "week": WEEK, "game_id": str(game_id),
            "date": str(pd.Timestamp(game["gameday"]).date()) if pd.notna(game.get("gameday")) else "",
            "matchup": matchup, "away_team": away, "home_team": home,
            **actual_fields(game),
            "publication_status": "Original Nov. 1 public snapshot",
            "market_source": "Frozen Bovada line in Nov. 1 public snapshot",
            "market_favorite": favorite, "market_spread_points": spread,
            "market_total": total_line,
        }

        for name, score_col, total_col, ats_col in (
            ("baseline", "Baseline Score Projection", "Baseline Total Projection", "Baseline ATS Projection"),
            ("injury", "Injury Score Projection", "Injury Total Projection", "Injury ATS Projection"),
        ):
            away_score, home_score = parse_score_pair(s[score_col], away, home)
            add_model_fields(row, name, away_score, home_score,
                             favorite, spread, total_line, away, home)
            # Keep the originally published ATS and total calls verbatim.
            row[f"{name}_ats_pick"] = str(s[ats_col])
            published_total = float(s[total_col])
            published_total_pick, published_total_edge = lean_total(published_total, total_line)
            row[f"{name}_projected_total"] = published_total
            row[f"{name}_total_pick"] = published_total_pick
            row[f"{name}_total_edge"] = round(published_total_edge, 2)
            row[f"{name}_published_total"] = published_total

        for variant, name in (
            ("efficiency_only_added", "efficiency"),
            ("combined_efficiency_plus_injury", "combined"),
        ):
            if game_id not in predictions[variant].index:
                raise RuntimeError(f"Missing chronological prediction for {matchup} / {variant}.")
            p = predictions[variant].loc[game_id]
            add_model_fields(row, name, float(p["pred_away"]), float(p["pred_home"]),
                             favorite, spread, total_line, away, home)
        rows.append(row)

    if len(matched_snapshot_games) != len(public):
        raise RuntimeError(
            f"Snapshot-to-schedule matching incomplete: matched {len(matched_snapshot_games)} "
            f"of {len(public)} original public games."
        )

    # Add Bears-Seahawks as a separate late addition, without requiring it to exist
    # in the original public snapshot.
    for matchup, late in LATE_ADD.items():
        away, home = [norm_team(x) for x in matchup.split("@")]
        game = find_schedule_game(away, home, matchup)
        game_id = game["game_id"]
        favorite, spread, total_line = MARKETS[matchup]
        row = {
            "season": SEASON, "week": WEEK, "game_id": str(game_id),
            "date": str(pd.Timestamp(game["gameday"]).date()) if pd.notna(game.get("gameday")) else "",
            "matchup": matchup, "away_team": away, "home_team": home,
            **actual_fields(game),
            "publication_status": "Late-added Nov. 2 research forecast — not on original public board",
            "market_source": "Bovada line recorded Nov. 2 pregame",
            "market_favorite": favorite, "market_spread_points": spread,
            "market_total": total_line,
        }
        for name in ("baseline", "injury", "efficiency", "combined"):
            scores = late[name]
            add_model_fields(row, name, scores["away"], scores["home"],
                             favorite, spread, total_line, away, home)
        rows.append(row)

    # Add every remaining Week 8 matchup absent from the original public snapshot.
    # Panthers-Packers is reconstructed chronologically for all four variants.
    represented_ids = {str(r["game_id"]) for r in rows}
    variant_names = {
        "baseline_only": "baseline", "injury_only_added": "injury",
        "efficiency_only_added": "efficiency",
        "combined_efficiency_plus_injury": "combined",
    }
    for game in schedule_rows:
        game_id = str(game["game_id"])
        if game_id in represented_ids:
            continue
        away, home = norm_team(game["away_team"]), norm_team(game["home_team"])
        matchup = f"{away} @ {home}"
        if matchup not in MARKETS:
            raise RuntimeError(f"Missing user-verified Bovada line for scheduled game {matchup}.")
        favorite, spread, total_line = MARKETS[matchup]
        row = {
            "season": SEASON, "week": WEEK, "game_id": game_id,
            "date": str(pd.Timestamp(game["gameday"]).date()) if pd.notna(game.get("gameday")) else "",
            "matchup": matchup, "away_team": away, "home_team": home,
            **actual_fields(game),
            "publication_status": "Chronological reconstruction",
            "market_source": "User-verified Bovada Week 8 slate",
            "market_favorite": favorite, "market_spread_points": spread,
            "market_total": total_line,
        }
        for variant, name in variant_names.items():
            if game_id not in predictions[variant].index:
                raise RuntimeError(f"Missing chronological prediction for {matchup} / {variant}.")
            pred = predictions[variant].loc[game_id]
            add_model_fields(row, name, float(pred["pred_away"]), float(pred["pred_home"]),
                             favorite, spread, total_line, away, home)
        rows.append(row)

    # Report schedule games that were not part of the frozen public board.
    represented_ids = {str(r["game_id"]) for r in rows}
    schedule_only_games = []
    for game in schedule_rows:
        if str(game["game_id"]) not in represented_ids:
            schedule_only_games.append(
                f'{norm_team(game["away_team"])} @ {norm_team(game["home_team"])}'
            )
    schedule_only_games = sorted(set(schedule_only_games))
    result = pd.DataFrame(rows).sort_values(["date", "matchup"])

    def grade_ats_pick(row: pd.Series, pick: str) -> str:
        if pd.isna(row.get("actual_away_score")) or pd.isna(row.get("actual_home_score")):
            return "Pending"
        match = re.search(r"([A-Z]{2,3})\s+([+-]\d+(?:\.\d+)?)", str(pick).upper())
        if not match:
            return "No bet"
        team, points = norm_team(match.group(1)), float(match.group(2))
        away_score, home_score = float(row["actual_away_score"]), float(row["actual_home_score"])
        if team == norm_team(row["away_team"]):
            margin = away_score + points - home_score
        elif team == norm_team(row["home_team"]):
            margin = home_score + points - away_score
        else:
            return "Invalid pick"
        if abs(margin) < 1e-9:
            return "Push"
        return "Win" if margin > 0 else "Loss"

    def grade_total_pick(row: pd.Series, pick: str) -> str:
        if pd.isna(row.get("actual_total")):
            return "Pending"
        side = str(pick).strip().lower()
        if side not in ("over", "under"):
            return "No bet"
        diff = float(row["actual_total"]) - float(row["market_total"])
        if abs(diff) < 1e-9:
            return "Push"
        return "Win" if ((side == "over" and diff > 0) or (side == "under" and diff < 0)) else "Loss"

    for model in ("baseline", "injury", "efficiency", "combined"):
        result[f"{model}_ats_result"] = result.apply(
            lambda r: grade_ats_pick(r, r[f"{model}_ats_pick"]), axis=1
        )
        result[f"{model}_total_result"] = result.apply(
            lambda r: grade_total_pick(r, r[f"{model}_total_pick"]), axis=1
        )
    # Snapshot completeness check: every originally published game remains represented.
    if len(matched_snapshot_games) != len(public):
        missing = sorted(set(public["Game"].astype(str)) - matched_snapshot_games)
        raise RuntimeError(f"Not all original public games matched the schedule: {missing}")

    summaries = {}
    for name in ("baseline", "injury", "efficiency", "combined"):
        summaries[name] = {}
        for market in ("ats", "total"):
            col = f"{name}_{market}_result"
            graded = result[result[col].isin(["Win", "Loss"])]
            summaries[name][market] = {
                "wins": int((graded[col] == "Win").sum()),
                "losses": int((graded[col] == "Loss").sum()),
                "pushes": int((result[col] == "Push").sum()),
                "pending": int((result[col] == "Pending").sum()),
                "accuracy_pct_ex_pushes": (
                    round(100 * (graded[col] == "Win").mean(), 2) if len(graded) else None
                ),
            }

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT / "week08_four_model_comparison.csv"
    json_path = OUT / "week08_four_model_summary.json"
    result.to_csv(csv_path, index=False)
    report = {
        "status": "RESEARCH_ONLY_TRANSPARENT_RECONSTRUCTION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "original_snapshot": str(SNAPSHOT.relative_to(ROOT)),
        "original_snapshot_rows": int(len(public)),
        "schedule_week_rows": int(len(week_schedule)),
        "comparison_rows": int(len(result)),
        "schedule_games_not_on_original_board": schedule_only_games,
        "late_added_games": result.loc[
            result["publication_status"].str.startswith("Late-added"), "matchup"
        ].tolist(),
        "method": (
            "Baseline and injury score projections for the 12 originally published games "
            "are parsed from the immutable Nov. 1 public snapshot. Efficiency and combined "
            "predictions are chronological weekly-fold projections with training strictly "
            "before the Week 8 test week. Bears-Seahawks uses the frozen Nov. 2 pregame "
            "four-model forecast and is explicitly labeled late-added."
        ),
        "summaries": summaries,
        "cautions": [
            "This comparison does not retroactively make the late-added Bears-Seahawks forecast public before kickoff.",
            "The Efficiency and Combined columns are reconstructed research forecasts, not original Nov. 1 public posts.",
            "The original Baseline and Injury values are preserved from the immutable snapshot.",
            "Schedule-only games absent from the frozen public snapshot are listed in schedule_games_not_on_original_board and are not assigned invented projections.",
            "No official prospective record or production model is changed.",
        ],
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
