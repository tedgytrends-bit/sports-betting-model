"""2026 Week 9 six-model pre-TNF research projection, no production writes.

No user-supplied Bovada line exists for this week yet. Nflverse schedule spreads
and totals are reference values ONLY, not Bovada quotes or official grading lines.
Baltimore QB Joe Fagnano is confirmed to start versus Jacksonville. Two inactive
QBs are also represented in a separately labeled, uncalibrated count scenario;
position-count features do NOT estimate a player-specific replacement value.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import load_schedule_data, load_pbp, build_efficiency_model_dataset
from injury_model import load_injury_reports, add_injury_features, injury_coverage_diagnostics, _normalize_reports, _counts_for_team
from research.efficiency_feature_experiments import _team_split_history, _pregame_split_features
from research.four_model_comparison import _feature_columns
from research.baseline_injury_recency_weighting import _weights_for_fold, _effective_sample_size

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
ALPHA = 10.0
MIN_TRAIN_GAMES = 500
TARGET_SEASON = 2026
TARGET_WEEK = 9
OUT = ROOT / "data" / "research_week09_2026_six_model"
TNF_KICKOFF_UTC = pd.Timestamp("2026-11-06T01:15:00Z")
ALIASES = {"LA": "LAR", "JAC": "JAX"}
EXPECTED_TNF_ID = "2026_09_JAX_BAL"
MODELS = (
    ("baseline", "baseline_only", None, "original"),
    ("injury", "injury_only_added", None, "original"),
    ("efficiency", "efficiency_only_added", None, "original"),
    ("combined", "combined_efficiency_plus_injury", None, "original"),
    ("baseline_hl1", "baseline_only", 1.0, "research_shadow"),
    ("injury_hl4", "injury_only_added", 4.0, "research_shadow"),
)


def norm_team(value):
    name = str(value).strip().upper()
    return ALIASES.get(name, name)


def safe_float(value, precision=4):
    return None if pd.isna(value) else round(float(value), precision)


def project(data, features, target, half_life=None):
    train = data[
        data["gameday"].notna()
        & data["gameday"].lt(target["gameday"])
        & data["home_score"].notna()
        & data["away_score"].notna()
    ].copy()
    if len(train) < MIN_TRAIN_GAMES:
        raise RuntimeError(f"Only {len(train)} prior completed games, min {MIN_TRAIN_GAMES}.")
    active = [c for c in features if c in train.columns and train[c].notna().any()]
    if not active:
        raise RuntimeError("Model has no active training features.")
    medians = train[active].median(numeric_only=True).fillna(0)
    x_train = train[active].apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0)
    x_target = pd.DataFrame([target[active].to_dict()], columns=active)
    x_target = x_target.apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0)
    weights = None if half_life is None else _weights_for_fold(train, target["gameday"], half_life)
    result = {}
    for score, output in (("home_score", "home"), ("away_score", "away")):
        estimator = Ridge(alpha=ALPHA)
        estimator.fit(x_train, train[score], sample_weight=weights)
        result[output] = float(estimator.predict(x_target)[0])
    result["total"] = result["home"] + result["away"]
    result["margin_home"] = result["home"] - result["away"]
    result["train_games"] = int(len(train))
    result["active_features"] = int(len(active))
    result["effective_train_games"] = (
        safe_float(_effective_sample_size(weights)) if weights is not None else int(len(train))
    )
    return result


def main():
    captured = datetime.now(timezone.utc)
    if pd.Timestamp(captured) >= TNF_KICKOFF_UTC:
        raise RuntimeError("Pre-TNF research freeze cannot be generated after TNF kickoff.")
    print("Initial Week 9 research freeze at", captured.isoformat(), flush=True)
    schedule = load_schedule_data()
    games = schedule[
        pd.to_numeric(schedule["season"], errors="coerce").eq(TARGET_SEASON)
        & pd.to_numeric(schedule["week"], errors="coerce").eq(TARGET_WEEK)
    ].copy()
    if len(games) != 15 or games["game_id"].duplicated().any():
        raise RuntimeError(f"Expected 15 distinct 2026 Week 9 games, found {len(games)}.")
    if EXPECTED_TNF_ID not in set(games["game_id"].astype(str)):
        raise RuntimeError("The expected TNF Jaguars@Ravens game is absent.")
    if games[["home_score", "away_score"]].notna().any().any():
        raise RuntimeError("Week 9 outcomes already populated; pregame freeze forbidden.")

    pbp = load_pbp(SEASONS)
    reports = load_injury_reports(SEASONS)
    base = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    injury = add_injury_features(base, schedule, reports)
    split_history = _team_split_history(pbp, schedule)
    split = _pregame_split_features(schedule, split_history)
    injury_columns = [
        c for c in injury.columns
        if c.startswith(("home_injury_", "away_injury_", "home_inj_", "away_inj_",
                         "home_qb_", "away_qb_", "home_ol_", "away_ol_",
                         "home_skill_", "away_skill_", "home_defense_", "away_defense_"))
    ]
    passing_columns = [c for c in split.columns if c != "game_id"]
    data = base.merge(split, on="game_id", how="left", validate="one_to_one")
    data = data.merge(injury[["game_id"] + injury_columns], on="game_id", how="left", validate="one_to_one")
    data["gameday"] = pd.to_datetime(data["gameday"], errors="coerce")

    # Explicitly reconcile the known pre-TNF saved report, which the generic
    # upcoming-game feature feed can otherwise classify as unavailable even when
    # its independent timing diagnostic finds the snapshot pregame-eligible.
    # This fixes a research INPUT, not a model prediction or production code.
    saved_path = ROOT / "data/injury_snapshots/injuries_2026_week_09_20261105T012126Z.csv"
    if not saved_path.exists():
        raise RuntimeError("The fixed pre-TNF injury snapshot is missing.")
    snapshot = pd.read_csv(saved_path, low_memory=False)
    captured_snapshot_utc = pd.to_datetime(snapshot["snapshot_captured_at_utc"], errors="coerce", utc=True)
    if captured_snapshot_utc.isna().any() or not captured_snapshot_utc.eq(captured_snapshot_utc.iloc[0]).all():
        raise RuntimeError("Pregame injury snapshot has missing/inconsistent capture timestamps.")
    if not captured_snapshot_utc.iloc[0] < TNF_KICKOFF_UTC:
        raise RuntimeError("TNF injury snapshot was not captured before kickoff.")
    if snapshot["gsis_id"].astype(str).duplicated().any():
        raise RuntimeError("Week 9 snapshot has duplicate player IDs.")
    typed_snapshot = _normalize_reports(snapshot)
    typed_snapshot = typed_snapshot[
        typed_snapshot["season"].eq(2026) & typed_snapshot["week"].eq(9)
        & typed_snapshot["season_type"].eq("REG")
    ]
    target_mask = data["game_id"].eq(EXPECTED_TNF_ID)
    if int(target_mask.sum()) != 1:
        raise RuntimeError("Could not apply TNF injury snapshot to one game.")
    audit_snapshot_counts = {}
    for side, team in (("home", "BAL"), ("away", "JAX")):
        report_rows = typed_snapshot[typed_snapshot["team"].eq(team)]
        if report_rows.empty:
            raise RuntimeError(f"Pregame snapshot has no {team} rows.")
        counts = _counts_for_team(report_rows)
        if counts["injury_report_available"] != 1.0:
            raise RuntimeError("Snapshot report availability flag missing.")
        for key, value in counts.items():
            col = f"{side}_{key}"
            # Preserve the exact historical four-model feature family:
            # practice-status counts were not part of its selected 56 features.
            if col not in data.columns and key.startswith("practice_"):
                continue
            if col not in data.columns:
                raise RuntimeError(f"Missing model feature for supplied snapshot: {col}")
            data.loc[target_mask, col] = value
        audit_snapshot_counts[team] = int(len(report_rows))
    if not (data.loc[target_mask, "home_injury_report_available"].iloc[0] == 1.0
            and data.loc[target_mask, "away_injury_report_available"].iloc[0] == 1.0):
        raise RuntimeError("Snapshot reconciliation failed input coverage assertion.")
    print("TNF snapshot reconciled:", audit_snapshot_counts,
          "BAL qb_out=", data.loc[target_mask, "home_qb_out"].iloc[0], flush=True)

    variants = _feature_columns(data, list(base.columns), passing_columns, injury_columns)
    if sorted(variants) != sorted((
        "baseline_only", "injury_only_added", "efficiency_only_added",
        "combined_efficiency_plus_injury"
    )):
        raise RuntimeError("Feature families were not loaded as expected.")

    tnf = data[data["game_id"].eq(EXPECTED_TNF_ID)]
    if len(tnf) != 1:
        raise RuntimeError("TNF game feature row missing/duplicated.")
    tnf = tnf.iloc[0]
    normal_qb_out = safe_float(tnf.get("home_qb_out", np.nan))
    print("BAL initial qb_out feature:", normal_qb_out, flush=True)
    diag = injury_coverage_diagnostics(games[games["game_id"].eq(EXPECTED_TNF_ID)], reports)
    audit = {
        "starter": "Joe Fagnano",
        "starter_source": "Baltimore Ravens official news, 2026-11-03; user confirmed 2026-11-04",
        "known_unavailable": ["Lamar Jackson - thumb", "Tyler Huntley - toe"],
        "fagnano_injury": "ankle; latest saved Week 9 practice row says full participant",
        "snapshot": "injuries_2026_week_09_20261105T012126Z.csv",
        "snapshot_feature_reconciliation": "Explicit pre-TNF saved snapshot counts injected into research feature row after validating capture timestamp and both teams.",
        "raw_home_qb_out_feature": normal_qb_out,
        "scenario_home_qb_out_feature": 2.0,
        "feature_warning": (
            "The original Injury estimator uses position-level injury counts, not named QB starter "
            "or player replacement valuation. Undated blank official game-status fields can yield "
            "qb_out=0 even when Jackson/Huntley are confirmed unavailable. A count override "
            "is uncalibrated and cannot be interpreted as Fagnano's true point impact."
        ),
        "feed_diagnostics": diag.to_dict(orient="records"),
    }

    rows = []
    for _, game in games.sort_values(["gameday", "game_id"]).iterrows():
        frame = data[data["game_id"].eq(game["game_id"])]
        if len(frame) != 1:
            raise RuntimeError(f"Feature row mismatch for {game['game_id']}")
        target = frame.iloc[0]
        spread = pd.to_numeric(pd.Series([game.get("spread_line")]), errors="coerce").iloc[0]
        total_line = pd.to_numeric(pd.Series([game.get("total_line")]), errors="coerce").iloc[0]
        for name, family, half_life, model_status in MODELS:
            raw = project(data, variants[family], target, half_life)
            margin_edge = raw["margin_home"] - spread if pd.notna(spread) else np.nan
            total_edge = raw["total"] - total_line if pd.notna(total_line) else np.nan
            if pd.notna(margin_edge) and margin_edge != 0:
                side = (
                    f"{norm_team(game['home_team'])} {(-spread):+g}" if margin_edge > 0
                    else f"{norm_team(game['away_team'])} {spread:+g}"
                )
            else:
                side = "Unavailable / no edge"
            rows.append({
                "captured_at_utc": captured.isoformat(),
                "status": "RESEARCH_ONLY_NOT_OFFICIAL",
                "game_id": str(game["game_id"]), "season": TARGET_SEASON, "week": TARGET_WEEK,
                "gameday": str(pd.Timestamp(game["gameday"]).date()),
                "away_team": norm_team(game["away_team"]), "home_team": norm_team(game["home_team"]),
                "model": name, "model_status": model_status, "qb_scenario": ("pre_tnf_saved_snapshot" if str(game["game_id"]) == EXPECTED_TNF_ID and name in ("injury", "combined", "injury_hl4") else "raw_injury_feed"),
                "projected_away": round(raw["away"], 3), "projected_home": round(raw["home"], 3),
                "projected_total": round(raw["total"], 3),
                "projected_home_margin": round(raw["margin_home"], 3),
                "market_home_favored_spread_reference": safe_float(spread),
                "market_total_reference": safe_float(total_line),
                "market_source": "nflverse schedule; NOT a verified Bovada line",
                "ats_edge_vs_reference": safe_float(margin_edge),
                "ats_lean_vs_reference": side,
                "total_edge_vs_reference": safe_float(total_edge),
                "total_lean_vs_reference": (
                    "Over" if pd.notna(total_edge) and total_edge > 0 else
                    "Under" if pd.notna(total_edge) and total_edge < 0 else "Unavailable"
                ),
                "training_games": raw["train_games"], "active_features": raw["active_features"],
                "effective_train_games": raw["effective_train_games"],
                "home_injury_report_available": safe_float(target.get("home_injury_report_available", np.nan)),
                "away_injury_report_available": safe_float(target.get("away_injury_report_available", np.nan)),
                "home_qb_out_feature": safe_float(target.get("home_qb_out", np.nan)),
                "away_qb_out_feature": safe_float(target.get("away_qb_out", np.nan)),
            })
            if str(game["game_id"]) == EXPECTED_TNF_ID and name in ("injury", "combined", "injury_hl4"):
                scenario_target = target.copy()
                scenario_target["home_qb_out"] = 2.0
                if "home_inj_out" in scenario_target.index:
                    orig_out = pd.to_numeric(pd.Series([scenario_target["home_inj_out"]]), errors="coerce").iloc[0]
                    scenario_target["home_inj_out"] = max(float(orig_out), 0.0) + 2.0 if pd.notna(orig_out) else 2.0
                scenario = project(data, variants[family], scenario_target, half_life)
                sr = dict(rows[-1])
                sr["model"] = name + "_qbcount_scenario"
                sr["model_status"] = "uncalibrated_research_scenario"
                sr["qb_scenario"] = "confirmed_Jackson_Huntley_out; Fagnano_start"
                sr["projected_away"] = round(scenario["away"], 3)
                sr["projected_home"] = round(scenario["home"], 3)
                sr["projected_total"] = round(scenario["total"], 3)
                sr["projected_home_margin"] = round(scenario["margin_home"], 3)
                sr["home_qb_out_feature"] = 2.0
                scenario_ats_edge = scenario["margin_home"] - spread if pd.notna(spread) else np.nan
                scenario_total_edge = scenario["total"] - total_line if pd.notna(total_line) else np.nan
                sr["ats_edge_vs_reference"] = safe_float(scenario_ats_edge)
                sr["total_edge_vs_reference"] = safe_float(scenario_total_edge)
                sr["ats_lean_vs_reference"] = (
                    f"{norm_team(game['home_team'])} {(-spread):+g}" if scenario_ats_edge > 0
                    else f"{norm_team(game['away_team'])} {spread:+g}"
                ) if pd.notna(scenario_ats_edge) and scenario_ats_edge != 0 else "Unavailable"
                sr["total_lean_vs_reference"] = (
                    "Over" if pd.notna(scenario_total_edge) and scenario_total_edge > 0 else
                    "Under" if pd.notna(scenario_total_edge) and scenario_total_edge < 0 else "Unavailable"
                )
                rows.append(sr)

    result = pd.DataFrame(rows)
    expected_n = len(games) * len(MODELS) + 3
    if len(result) != expected_n:
        raise RuntimeError(f"Unexpected model scenario rows: {len(result)} vs {expected_n}.")
    if result[["game_id", "model"]].duplicated().any():
        raise RuntimeError("Duplicate game/model result keys.")
    if result[["projected_home", "projected_away", "projected_total"]].isna().any().any():
        raise RuntimeError("Missing model score projection.")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT / f"week09_six_model_pregame_{stamp}.csv"
    json_path = OUT / f"week09_six_model_pregame_{stamp}.json"
    result.to_csv(csv_path, index=False)
    report = {
        "status": "RESEARCH_ONLY_NOT_OFFICIAL",
        "captured_at_utc": captured.isoformat(),
        "season": TARGET_SEASON,
        "week": TARGET_WEEK,
        "games": len(games),
        "rows": len(result),
        "model_names": [n for n, _, _, _ in MODELS],
        "training": "Ridge alpha=10; median imputation from pregame completed training only; same research feature sets.",
        "market_policy": "nflverse schedule line reference only; no user-verified Week 9 Bovada lines supplied.",
        "tnf_qb_starter_audit": audit,
        "comparison_warning": (
            "This is a research snapshot. It does not freeze the official production record. "
            "The confirmed-out scenario changes QB injury counts, not the starter's individual expected value; "
            "it is exploratory and should not be reported as an official injury-corrected projection."
        ),
        "snapshot_file": str(csv_path.relative_to(ROOT)),
    }
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("Snapshot:", csv_path, flush=True)
    print(result[result["game_id"].eq(EXPECTED_TNF_ID)][[
        "model", "projected_away", "projected_home", "projected_total",
        "projected_home_margin", "home_qb_out_feature",
        "ats_lean_vs_reference", "total_lean_vs_reference"
    ]].to_string(index=False), flush=True)
    print("TOTAL GAMES", len(games), "ROWS", len(result), flush=True)


if __name__ == "__main__":
    main()
