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
    edge = (pred_home - pred_away) - home_market_line
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
    for variant in ("efficiency_only_added", "combined_efficiency_plus_injury"):
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

    for _, game in week_schedule.iterrows():
        away, home = norm_team(game["away_team"]), norm_team(game["home_team"])
        matchup = f"{away} @ {home}"
        game_id = game["game_id"]
        row = {
            "season": SEASON, "week": WEEK, "game_id": str(game_id),
            "date": str(pd.Timestamp(game["gameday"]).date()) if pd.notna(game["gameday"]) else "",
            "matchup": matchup, "away_team": away, "home_team": home,
            "actual_away_score": game.get("away_score"),
            "actual_home_score": game.get("home_score"),
            "actual_total": (
                float(game["away_score"]) + float(game["home_score"])
                if pd.notna(game.get("away_score")) and pd.notna(game.get("home_score")) else np.nan
            ),
            "publication_status": "Original Nov. 1 public snapshot",
        }

        if matchup in LATE_ADD:
            late = LATE_ADD[matchup]
            favorite, spread, total_line = late["market_favorite"], late["market_spread"], late["market_total"]
            row["publication_status"] = "Late-added Nov. 2 research forecast — not on original public board"
            row["market_source"] = "Bovada line recorded Nov. 2 pregame"
            row["market_favorite"] = favorite
            row["market_spread_points"] = spread
            row["market_total"] = total_line
            for name in ("baseline", "injury", "efficiency", "combined"):
                scores = late[name]
                add_model_fields(row, name, scores["away"], scores["home"],
                                 favorite, spread, total_line, away, home)
        else:
            parsed_matchups = public["Game"].astype(str).apply(
                lambda value: tuple(norm_team(part) for part in value.upper().split("@"))
                if "@" in value else ("", "")
            )
            snap = public.loc[
                parsed_matchups.apply(lambda pair: pair == (away, home))
            ]
            if len(snap) != 1:
                raise RuntimeError(f"Expected exactly one frozen public row for {matchup}; found {len(snap)}.")
            s = snap.iloc[0]
            matched_snapshot_games.add(str(s["Game"]))
            favorite, spread = parse_market_spread(s["Official Bovada Spread"])
            total_line = float(s["Official Bovada Total"])
            row["market_source"] = "Frozen Bovada line in Nov. 1 public snapshot"
            row["market_favorite"] = favorite
            row["market_spread_points"] = spread
            row["market_total"] = total_line
            for name, score_col, total_col, ats_col in (
                ("baseline", "Baseline Score Projection", "Baseline Total Projection", "Baseline ATS Projection"),
                ("injury", "Injury Score Projection", "Injury Total Projection", "Injury ATS Projection"),
            ):
                away_score, home_score = parse_score_pair(s[score_col], away, home)
                add_model_fields(row, name, away_score, home_score,
                                 favorite, spread, total_line, away, home)
                # Preserve original public values exactly for the two published variants.
                row[f"{name}_ats_pick"] = str(s[ats_col])
                row[f"{name}_projected_total"] = float(s[total_col])
                row[f"{name}_published_total"] = float(s[total_col])

            for variant, name in (
                ("efficiency_only_added", "efficiency"),
                ("combined_efficiency_plus_injury", "combined"),
            ):
                if game_id not in predictions[variant].index:
                    raise RuntimeError(f"Missing chronological prediction for {matchup} / {variant}.")
                p = predictions[variant].loc[game_id]
                add_model_fields(row, name, float(p["pred_away"]), float(p["pred_home"]),
                                 favorite, spread, total_line, away, home)

        for name in ("baseline", "injury", "efficiency", "combined"):
            actual_away, actual_home = row["actual_away_score"], row["actual_home_score"]
            if pd.notna(actual_away) and pd.notna(actual_home):
                actual_margin = float(actual_home) - float(actual_away)
                pick_text = str(row[f"{name}_ats_pick"])
                pick_match = re.search(r"Lean\\s+([A-Z]{2,3})", pick_text.upper())
                picked_team = norm_team(pick_match.group(1)) if pick_match else ""
                if picked_team not in (home, away):
                    row[f"{name}_ats_result"] = "No pick"
                else:
                    picked_line = -spread if picked_team == norm_team(favorite) else spread
                    picked_margin = (
                        actual_margin if picked_team == home else -actual_margin
                    ) + picked_line
                    row[f"{name}_ats_result"] = (
                        "Push" if abs(picked_margin) < 1e-9
                        else ("Win" if picked_margin > 0 else "Loss")
                    )
                actual_total = float(actual_away) + float(actual_home)
                total_pick = str(row[f"{name}_total_pick"]).lower()
                total_margin = actual_total - total_line
                row[f"{name}_total_result"] = (
                    "Push" if abs(total_margin) < 1e-9
                    else ("Win" if ((total_pick == "over" and total_margin > 0)
                                    or (total_pick == "under" and total_margin < 0)) else "Loss")
                )
            else:
                row[f"{name}_ats_result"] = "Pending"
                row[f"{name}_total_result"] = "Pending"
        rows.append(row)

    result = pd.DataFrame(rows).sort_values(["date", "matchup"])
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
        "schedule_week_rows": int(len(result)),
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
            "No official prospective record or production model is changed.",
        ],
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
