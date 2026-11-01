#!/usr/bin/env python3
"""Research-only validation using the QB who actually handled the passing workload.

Identifies the primary passer from target-game PBP, then values that QB using
strictly prior weekly stats. Target-game PBP is used only to identify who played;
no target-game performance enters the pregame player valuation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "player_injury_backtests"
DECAY_GAMES = 24.0
MIN_OPPORTUNITY = 40.0
MIN_REPLACEMENT_GAMES = 3
MIN_PASSER_DROPBACKS = 5


def latest(pattern: str) -> Path:
    files = sorted(DATA.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found for {pattern}")
    return files[-1]


def prior_qb_rate(stats: pd.DataFrame, player_id: str, cutoff: int,
                  population_mean: float) -> dict:
    prior = stats[
        stats["player_id"].astype(str).eq(str(player_id))
        & stats["sort_key"].lt(cutoff)
        & stats["position_group"].eq("QB")
    ].copy()
    if prior.empty:
        return {"games": 0, "weighted_dropbacks": 0.0, "rate": np.nan}
    prior["epa_numerator"] = prior["passing_epa"].fillna(0.0)
    weekly = prior.groupby("sort_key", as_index=False).agg(
        dropbacks=("opportunity", "sum"), epa=("epa_numerator", "sum")
    ).sort_values("sort_key")
    weekly["age"] = np.arange(len(weekly) - 1, -1, -1)
    weekly["decay"] = np.exp(-np.log(2) * weekly["age"] / DECAY_GAMES)
    weighted_opp = float((weekly["dropbacks"] * weekly["decay"]).sum())
    raw = (float((weekly["epa"] * weekly["decay"]).sum() / weighted_opp)
           if weighted_opp > 0 else population_mean)
    reliability = weighted_opp / (weighted_opp + MIN_OPPORTUNITY * 3.0)
    return {
        "games": int(weekly["sort_key"].nunique()),
        "weighted_dropbacks": weighted_opp,
        "rate": float(reliability * raw + (1.0 - reliability) * population_mean),
    }


def corr(frame: pd.DataFrame) -> dict:
    x = frame[["impact_actual_replacement", "score_residual"]].dropna()
    if len(x) < 5:
        return {"n": int(len(x)), "pearson_r": None, "spearman_r": None, "slope": None}
    return {
        "n": int(len(x)),
        "pearson_r": float(x.iloc[:, 0].corr(x.iloc[:, 1])),
        "spearman_r": float(x.iloc[:, 0].corr(x.iloc[:, 1], method="spearman")),
        "slope": float(np.polyfit(x.iloc[:, 0], x.iloc[:, 1], 1)[0]),
    }


def main() -> None:
    from build_longitudinal_player_value_audit import prepare_stats
    from model import load_pbp

    impact_path = latest("qb_point_impact_audit_*.csv")
    paired_path = latest("player_injury_paired_predictions_*.csv")
    impacts = pd.read_csv(impact_path, dtype={"injured_qb_id": "string",
                                               "replacement_qb_id": "string"})
    paired = pd.read_csv(paired_path)
    needed = {"game_id", "season", "week", "team", "report_status",
              "depth_chart_rank", "replacement_history_same_team",
              "replacement_prior_games", "expected_team_dropbacks_trailing_10_games",
              "injured_qb_id"}
    missing = needed - set(impacts.columns)
    if missing:
        raise ValueError(f"Impact file missing fields: {sorted(missing)}")

    for col in ("season", "week", "depth_chart_rank", "replacement_prior_games",
                "expected_team_dropbacks_trailing_10_games"):
        impacts[col] = pd.to_numeric(impacts[col], errors="coerce")
    impacts["same_team_history"] = impacts["replacement_history_same_team"].astype(str).str.lower().eq("true")
    candidates = impacts[
        impacts["report_status"].astype(str).str.upper().eq("OUT")
        & impacts["depth_chart_rank"].eq(1)
        & impacts["same_team_history"]
        & impacts["replacement_prior_games"].ge(MIN_REPLACEMENT_GAMES)
    ].copy()
    candidates["team"] = candidates["team"].astype(str).str.upper().str.strip()
    candidates["injured_qb_id"] = candidates["injured_qb_id"].astype(str).str.strip()

    pbp = load_pbp()
    required_pbp = {"game_id", "season", "posteam", "passer_player_id"}
    missing_pbp = required_pbp - set(pbp.columns)
    if missing_pbp:
        raise ValueError(f"PBP missing fields: {sorted(missing_pbp)}")
    passers = pbp.dropna(subset=["game_id", "posteam", "passer_player_id"]).copy()
    passers["posteam"] = passers["posteam"].astype(str).str.upper().str.strip()
    passers["passer_player_id"] = passers["passer_player_id"].astype(str).str.strip()
    counts = (passers.groupby(["game_id", "posteam", "passer_player_id"])
              .size().rename("passer_dropbacks").reset_index())
    counts = counts.sort_values(
        ["game_id", "posteam", "passer_dropbacks", "passer_player_id"],
        ascending=[True, True, False, True]
    )
    primary = counts.drop_duplicates(["game_id", "posteam"], keep="first")
    primary = primary.rename(columns={
        "posteam": "team", "passer_player_id": "actual_primary_qb_id"
    })
    candidates = candidates.merge(
        primary[["game_id", "team", "actual_primary_qb_id", "passer_dropbacks"]],
        on=["game_id", "team"], how="inner", validate="many_to_one"
    )
    candidates = candidates[
        candidates["passer_dropbacks"].ge(MIN_PASSER_DROPBACKS)
        & candidates["actual_primary_qb_id"].ne(candidates["injured_qb_id"])
    ].copy()

    stats = prepare_stats()
    stats["player_id"] = stats["player_id"].astype(str).str.strip()
    stats["sort_key"] = stats["season"] * 100 + stats["week"]
    stats["opportunity"] = stats["attempts"] + stats["sacks_suffered"]
    records = []
    cache = {}
    pop_cache = {}
    for row in candidates.itertuples(index=False):
        cutoff = int(row.season) * 100 + int(row.week)
        if cutoff not in pop_cache:
            prior_pop = stats[(stats["sort_key"] < cutoff) & stats["opportunity"].gt(0)]
            denom = float(prior_pop["opportunity"].sum())
            pop_cache[cutoff] = float(prior_pop["passing_epa"].sum() / denom) if denom else 0.0
        mean = pop_cache[cutoff]
        for pid in (row.injured_qb_id, row.actual_primary_qb_id):
            key = (cutoff, str(pid))
            if key not in cache:
                cache[key] = prior_qb_rate(stats, str(pid), cutoff, mean)
        injured = cache[(cutoff, str(row.injured_qb_id))]
        actual = cache[(cutoff, str(row.actual_primary_qb_id))]
        if injured["games"] < MIN_REPLACEMENT_GAMES or actual["games"] < MIN_REPLACEMENT_GAMES:
            continue
        dropbacks = row.expected_team_dropbacks_trailing_10_games
        gap = injured["rate"] - actual["rate"]
        records.append({
            "game_id": row.game_id, "season": int(row.season), "week": int(row.week),
            "team": row.team, "injured_qb_id": row.injured_qb_id,
            "actual_primary_qb_id": row.actual_primary_qb_id,
            "listed_replacement_qb_id": getattr(row, "replacement_qb_id", None),
            "actual_qb_matches_listed_replacement": str(row.actual_primary_qb_id) == str(getattr(row, "replacement_qb_id", "")),
            "actual_primary_passer_dropbacks": int(row.passer_dropbacks),
            "injured_prior_games": injured["games"], "actual_qb_prior_games": actual["games"],
            "injured_prior_epa_per_dropback": injured["rate"],
            "actual_qb_prior_epa_per_dropback": actual["rate"],
            "epa_gap_injured_minus_actual_qb": gap,
            "expected_team_dropbacks": float(dropbacks) if pd.notna(dropbacks) else None,
            "impact_actual_replacement": float(gap * dropbacks) if pd.notna(dropbacks) else None,
        })
    result = pd.DataFrame(records)
    if result.empty:
        raise RuntimeError("No actual-QB replacement cases met the strict history and participation filters.")

    home = paired[["game_id", "season", "home_team", "home_score", "pred_home_score_baseline"]].rename(
        columns={"home_team": "team", "home_score": "actual_score", "pred_home_score_baseline": "predicted_score"})
    away = paired[["game_id", "season", "away_team", "away_score", "pred_away_score_baseline"]].rename(
        columns={"away_team": "team", "away_score": "actual_score", "pred_away_score_baseline": "predicted_score"})
    scores = pd.concat([home, away], ignore_index=True)
    scores["team"] = scores["team"].astype(str).str.upper().str.strip()
    scores["score_residual"] = scores["actual_score"] - scores["predicted_score"]
    result = result.merge(scores[["game_id", "season", "team", "score_residual"]],
                          on=["game_id", "season", "team"], how="inner", validate="many_to_one")
    result = result.drop_duplicates(["game_id", "team"], keep="first")
    dev = result[result["season"].le(2023)]
    hold = result[result["season"].ge(2024)]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RESEARCH_ONLY_ACTUAL_QB_REPLACEMENT_VALIDATION",
        "impact_source": impact_path.name,
        "paired_prediction_source": paired_path.name,
        "candidate_out_qb1_rows": int(len(candidates)),
        "eligible_actual_qb_team_games": int(len(result)),
        "development_2021_2023": corr(dev),
        "untouched_holdout_2024_2026": corr(hold),
        "actual_primary_qb_matches_listed_replacement_rate": float(result["actual_qb_matches_listed_replacement"].mean()),
        "actual_primary_qb_median_prior_games": float(result["actual_qb_prior_games"].median()),
        "holdout_mean_score_residual": float(hold["score_residual"].mean()) if len(hold) else None,
        "holdout_mean_absolute_score_residual": float(hold["score_residual"].abs().mean()) if len(hold) else None,
        "limitations": [
            "Actual primary QB is identified by target-game passer dropback counts; this is retrospective participation evidence, not a pregame depth-chart input.",
            "All QB valuation statistics are strictly prior to the target season/week; target-game outcomes are not used in player ratings.",
            "Only QB1 OUT cases with same-team prior history for the listed replacement are candidates; actual primary passer must have at least three prior games.",
            "Passer IDs may not capture every QB snap, and the most frequent passer is not necessarily the only QB who played.",
            "Small, nonrandom injury samples and correlation do not establish causal point value.",
            "Research only; no production projections or prospective records are modified."
        ]
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    DATA.mkdir(parents=True, exist_ok=True)
    csv_path = DATA / f"qb_actual_replacement_validation_{stamp}.csv"
    json_path = DATA / f"qb_actual_replacement_validation_{stamp}.json"
    result.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved {csv_path}")
    print(f"Saved {json_path}")


if __name__ == "__main__":
    main()
