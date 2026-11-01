#!/usr/bin/env python3
"""Join pregame QB depth-chart candidates to strictly prior player performance.

Research-only: player scores are production proxies, not points or win probability.
The script uses the same longitudinal QB metric/shrinkage approach as the broader
player-value audit, but computes values for both injured QBs and listed replacements.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "player_injury_backtests"
DECAY_GAMES = 24.0
MIN_OPPORTUNITY = 40.0


def score_player(stats: pd.DataFrame, player_id: str, cutoff: int, population_mean: float) -> dict:
    prior = stats[
        stats["player_id"].astype(str).eq(str(player_id))
        & stats["sort_key"].lt(cutoff)
        & stats["position_group"].eq("QB")
    ].sort_values("sort_key").copy()
    if prior.empty:
        return {
            "historical_games": 0, "historical_opportunities": 0.0,
            "weighted_raw_rate": np.nan, "position_prior_mean": np.nan,
            "player_value_score": np.nan, "latest_prior_team": None,
        }

    prior["age"] = np.arange(len(prior) - 1, -1, -1)
    prior["recency_weight"] = np.exp(-np.log(2) * prior["age"] / DECAY_GAMES)
    weighted_opp = float((prior["opportunity"] * prior["recency_weight"]).sum())
    weights = prior["recency_weight"].to_numpy()
    rates = prior["raw_rate"].fillna(0.0).to_numpy()
    weighted_rate = float(np.sum(rates * weights) / max(float(weights.sum()), 1e-9))

    reliability = weighted_opp / (weighted_opp + MIN_OPPORTUNITY * 3.0)
    value = reliability * weighted_rate + (1.0 - reliability) * population_mean

    return {
        "historical_games": int(prior["sort_key"].nunique()),
        "historical_opportunities": weighted_opp,
        "weighted_raw_rate": weighted_rate,
        "position_prior_mean": population_mean,
        "player_value_score": float(value),
        "latest_prior_team": str(prior.iloc[-1]["team"]),
    }


def main() -> None:
    from build_longitudinal_player_value_audit import prepare_stats

    depth_files = sorted(OUT.glob("qb_depth_chart_replacement_audit_*.csv"))
    if not depth_files:
        raise FileNotFoundError("No QB depth-chart audit CSV found.")
    depth_path = depth_files[-1]
    depth = pd.read_csv(depth_path, dtype={"gsis_id": "string", "listed_replacement_id": "string"})
    required = {
        "season", "week", "team", "gsis_id", "listed_replacement_id",
        "injury_player_chart_rank", "depth_schema", "game_id",
    }
    missing = required - set(depth.columns)
    if missing:
        raise ValueError(f"Depth-chart audit missing fields: {sorted(missing)}")

    stats = prepare_stats()
    stats["player_id"] = stats["player_id"].astype("string").str.strip()
    records = []
    # Deduplicate repeated injury updates for the same QB/game before valuation.
    work = depth.dropna(subset=["season", "week", "gsis_id", "game_id"]).copy()
    work = work.drop_duplicates(["game_id", "team", "gsis_id"], keep="last")
    work["season"] = pd.to_numeric(work["season"], errors="coerce")
    work["week"] = pd.to_numeric(work["week"], errors="coerce")
    work = work.dropna(subset=["season", "week"])
    work["cutoff"] = work["season"].astype(int) * 100 + work["week"].astype(int)

    cache: dict[tuple[int, str], dict] = {}
    population_cache: dict[int, float] = {}
    for row in work.itertuples(index=False):
        cutoff = int(row.cutoff)
        if cutoff not in population_cache:
            population = stats[
                stats["sort_key"].lt(cutoff) & stats["position_group"].eq("QB")
            ]["raw_rate"].dropna()
            population_cache[cutoff] = float(population.mean()) if not population.empty else 0.0
        prior_mean = population_cache[cutoff]
        injured_id = str(row.gsis_id).strip()
        replacement_id = (
            str(row.listed_replacement_id).strip()
            if pd.notna(row.listed_replacement_id) else ""
        )
        key_i = (cutoff, injured_id)
        if key_i not in cache:
            cache[key_i] = score_player(stats, injured_id, cutoff, prior_mean)
        injured = cache[key_i]
        if replacement_id:
            key_r = (cutoff, replacement_id)
            if key_r not in cache:
                cache[key_r] = score_player(stats, replacement_id, cutoff, prior_mean)
            replacement = cache[key_r]
        else:
            replacement = {
                "historical_games": 0, "historical_opportunities": 0.0,
                "weighted_raw_rate": np.nan, "position_prior_mean": np.nan,
                "player_value_score": np.nan, "latest_prior_team": None,
            }

        iv = injured["player_value_score"]
        rv = replacement["player_value_score"]
        records.append({
            "game_id": row.game_id,
            "season": int(row.season),
            "week": int(row.week),
            "team": row.team,
            "injured_qb_id": injured_id,
            "injured_qb_name": getattr(row, "full_name", None),
            "injured_qb_status": getattr(row, "report_status", None),
            "depth_schema": row.depth_schema,
            "injured_qb_chart_rank": row.injury_player_chart_rank,
            "listed_replacement_id": replacement_id or None,
            "injured_historical_games": injured["historical_games"],
            "injured_weighted_opportunities": injured["historical_opportunities"],
            "injured_qb_value_score": iv,
            "injured_qb_latest_prior_team": injured["latest_prior_team"],
            "replacement_historical_games": replacement["historical_games"],
            "replacement_weighted_opportunities": replacement["historical_opportunities"],
            "replacement_value_score": rv,
            "replacement_latest_prior_team": replacement["latest_prior_team"],
            "qb_value_gap_injured_minus_replacement": (
                float(iv - rv) if pd.notna(iv) and pd.notna(rv) else np.nan
            ),
            "injured_qb_has_prior_history": bool(injured["historical_games"] > 0),
            "replacement_has_prior_history": bool(replacement["historical_games"] > 0),
            "same_team_prior_history_for_replacement": bool(
                replacement["latest_prior_team"] == str(row.team)
            ) if replacement["latest_prior_team"] else False,
            "strict_prior_week_cutoff": True,
        })

    result = pd.DataFrame(records)
    if result.empty:
        raise RuntimeError("No QB replacement valuation rows produced.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT / f"qb_replacement_value_audit_{stamp}.csv"
    json_path = OUT / f"qb_replacement_value_audit_{stamp}.json"
    OUT.mkdir(parents=True, exist_ok=True)

    modern = result[result["depth_schema"].eq("timestamped_espn_point_in_time")]
    legacy = result[result["depth_schema"].eq("weekly_legacy")]
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "RESEARCH_ONLY_QB_REPLACEMENT_VALUE_AUDIT_NO_MODEL_CHANGES",
        "source_depth_chart_file": depth_path.name,
        "rows": int(len(result)),
        "timestamped_2025_plus_rows": int(len(modern)),
        "legacy_2021_2024_rows": int(len(legacy)),
        "injured_qb_prior_history_rows": int(result["injured_qb_has_prior_history"].sum()),
        "replacement_candidate_rows": int(result["listed_replacement_id"].notna().sum()),
        "replacement_prior_history_rows": int(result["replacement_has_prior_history"].sum()),
        "replacement_same_team_latest_prior_history_rows": int(result["same_team_prior_history_for_replacement"].sum()),
        "rows_with_comparable_value_gap": int(result["qb_value_gap_injured_minus_replacement"].notna().sum()),
        "median_injured_qb_historical_games": float(result.loc[result["injured_historical_games"].gt(0), "injured_historical_games"].median()) if result["injured_historical_games"].gt(0).any() else None,
        "median_replacement_historical_games": float(result.loc[result["replacement_historical_games"].gt(0), "replacement_historical_games"].median()) if result["replacement_historical_games"].gt(0).any() else None,
        "limitations": [
            "QB value is a shrunk historical passing EPA per attempt/sack plus CPOE proxy, not calibrated points or win probability.",
            "Only player statistics from seasons/weeks strictly before the target game week are used.",
            "Replacement is the listed depth-chart candidate, not confirmed active or actual game participant.",
            "Historical player performance can include prior teams; latest prior team is reported as a provenance check.",
            "This is a coverage and valuation audit, not evidence that the score gap improves game predictions.",
            "No official model, projection, or prospective record is changed."
        ]
    }
    result.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved {csv_path}")
    print(f"Saved {json_path}")


if __name__ == "__main__":
    main()
