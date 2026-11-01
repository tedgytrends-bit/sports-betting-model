#!/usr/bin/env python3
"""Research-only QB absence point-impact estimate using prior EPA/dropback.

This is an interpretable EPA-based scenario estimate, not a production feature.
For each QB injury/depth-chart record, estimate the difference between the
injured QB and listed replacement using only player stats before the target
season/week. Multiply that rate gap by the team's trailing expected dropbacks.
OUT cases are the primary cohort; QUESTIONABLE/DOUBTFUL are scenario-only.
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
TEAM_LOOKBACK_GAMES = 10


def player_epa_rate(stats: pd.DataFrame, player_id: str, cutoff: int,
                    population_mean: float) -> dict:
    prior = stats[
        stats["player_id"].astype(str).eq(str(player_id))
        & stats["sort_key"].lt(cutoff)
        & stats["position_group"].eq("QB")
    ].copy()
    if prior.empty:
        return {"games": 0, "weighted_dropbacks": 0.0, "epa_per_dropback": np.nan,
                "reliability": 0.0, "latest_team": None}

    prior["epa_numerator"] = prior["passing_epa"].fillna(0.0)
    weekly = prior.groupby("sort_key", as_index=False).agg(
        dropbacks=("opportunity", "sum"),
        epa=("epa_numerator", "sum"),
        team=("team", "last"),
    ).sort_values("sort_key")
    weekly["age"] = np.arange(len(weekly) - 1, -1, -1)
    weekly["decay"] = np.exp(-np.log(2) * weekly["age"] / DECAY_GAMES)
    weekly["weighted_dropbacks"] = weekly["dropbacks"] * weekly["decay"]
    weighted_dropbacks = float(weekly["weighted_dropbacks"].sum())
    raw = (float((weekly["epa"] * weekly["decay"]).sum() / weighted_dropbacks)
           if weighted_dropbacks > 0 else population_mean)
    reliability = weighted_dropbacks / (weighted_dropbacks + MIN_OPPORTUNITY * 3.0)
    estimate = reliability * raw + (1.0 - reliability) * population_mean
    return {
        "games": int(weekly["sort_key"].nunique()),
        "weighted_dropbacks": weighted_dropbacks,
        "epa_per_dropback": float(estimate),
        "reliability": float(reliability),
        "latest_team": str(weekly.iloc[-1]["team"]),
    }


def main() -> None:
    from build_longitudinal_player_value_audit import prepare_stats

    depth_files = sorted(OUT.glob("qb_depth_chart_replacement_audit_*.csv"))
    if not depth_files:
        raise FileNotFoundError("No QB depth-chart audit CSV found.")
    depth = pd.read_csv(depth_files[-1], dtype={"gsis_id": "string",
                                                 "listed_replacement_id": "string"})
    required = {"season", "week", "team", "gsis_id", "listed_replacement_id",
                "game_id", "report_status"}
    missing = required - set(depth.columns)
    if missing:
        raise ValueError(f"Depth-chart audit missing fields: {sorted(missing)}")

    stats = prepare_stats()
    stats["player_id"] = stats["player_id"].astype("string").str.strip()
    stats["team"] = stats["team"].astype("string").str.upper().str.strip()
    stats["sort_key"] = stats["season"] * 100 + stats["week"]
    stats["opportunity"] = stats["attempts"] + stats["sacks_suffered"]

    work = depth.dropna(subset=["season", "week", "gsis_id", "game_id"]).copy()
    work = work.drop_duplicates(["game_id", "team", "gsis_id"], keep="last")
    work["season"] = pd.to_numeric(work["season"], errors="coerce")
    work["week"] = pd.to_numeric(work["week"], errors="coerce")
    work = work.dropna(subset=["season", "week"])
    work["cutoff"] = work["season"].astype(int) * 100 + work["week"].astype(int)

    records = []
    player_cache = {}
    team_cache = {}
    population_cache = {}
    for row in work.itertuples(index=False):
        cutoff = int(row.cutoff)
        if cutoff not in population_cache:
            pop = stats[(stats["sort_key"] < cutoff) & stats["opportunity"].gt(0)]
            total_opp = float(pop["opportunity"].sum())
            population_cache[cutoff] = (float(pop["passing_epa"].sum() / total_opp)
                                        if total_opp else 0.0)
        mean = population_cache[cutoff]

        team_key = (cutoff, str(row.team).upper())
        if team_key not in team_cache:
            team_prior = stats[
                stats["team"].eq(str(row.team).upper())
                & stats["sort_key"].lt(cutoff)
            ]
            team_week = team_prior.groupby("sort_key", as_index=False)["opportunity"].sum()
            team_week = team_week.sort_values("sort_key").tail(TEAM_LOOKBACK_GAMES)
            team_cache[team_key] = (
                float(team_week["opportunity"].mean()) if not team_week.empty else np.nan,
                int(len(team_week)),
            )
        expected_dropbacks, team_games = team_cache[team_key]

        injured_id = str(row.gsis_id).strip()
        replacement_id = str(row.listed_replacement_id).strip() if pd.notna(row.listed_replacement_id) else ""
        ki = (cutoff, injured_id)
        if ki not in player_cache:
            player_cache[ki] = player_epa_rate(stats, injured_id, cutoff, mean)
        injured = player_cache[ki]
        if replacement_id:
            kr = (cutoff, replacement_id)
            if kr not in player_cache:
                player_cache[kr] = player_epa_rate(stats, replacement_id, cutoff, mean)
            replacement = player_cache[kr]
        else:
            replacement = {"games": 0, "weighted_dropbacks": 0.0,
                           "epa_per_dropback": np.nan, "reliability": 0.0,
                           "latest_team": None}

        gap = (injured["epa_per_dropback"] - replacement["epa_per_dropback"]
               if pd.notna(injured["epa_per_dropback"]) and
               pd.notna(replacement["epa_per_dropback"]) else np.nan)
        impact = gap * expected_dropbacks if pd.notna(gap) and pd.notna(expected_dropbacks) else np.nan
        status = str(row.report_status).upper().strip()
        records.append({
            "game_id": row.game_id, "season": int(row.season), "week": int(row.week),
            "team": str(row.team), "injured_qb_id": injured_id,
            "injured_qb_name": getattr(row, "full_name", None),
            "report_status": status, "depth_chart_rank": getattr(row, "injury_player_chart_rank", None),
            "replacement_qb_id": replacement_id or None,
            "injured_prior_games": injured["games"],
            "replacement_prior_games": replacement["games"],
            "injured_epa_per_dropback": injured["epa_per_dropback"],
            "replacement_epa_per_dropback": replacement["epa_per_dropback"],
            "injured_rate_reliability": injured["reliability"],
            "replacement_rate_reliability": replacement["reliability"],
            "epa_rate_gap_injured_minus_replacement": gap,
            "expected_team_dropbacks_trailing_10_games": expected_dropbacks,
            "team_games_available_for_dropback_average": team_games,
            "conditional_qb_absence_point_impact": impact,
            "replacement_latest_prior_team": replacement["latest_team"],
            "replacement_history_same_team": (
                replacement["latest_team"] == str(row.team).upper()
                if replacement["latest_team"] else False
            ),
            "strict_prior_week_cutoff": True,
            "interpretation": "OUT_primary" if status == "OUT" else "conditional_scenario_only",
        })

    result = pd.DataFrame(records)
    if result.empty:
        raise RuntimeError("No QB point-impact rows generated.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT / f"qb_point_impact_audit_{stamp}.csv"
    json_path = OUT / f"qb_point_impact_audit_{stamp}.json"
    OUT.mkdir(parents=True, exist_ok=True)

    comparable = result.dropna(subset=["conditional_qb_absence_point_impact"])
    out_rows = comparable[comparable["report_status"].eq("OUT")]
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "RESEARCH_ONLY_QB_EPA_POINT_IMPACT_SCENARIO_NO_MODEL_CHANGES",
        "rows": int(len(result)),
        "rows_with_comparable_point_impact": int(len(comparable)),
        "out_rows_with_comparable_point_impact": int(len(out_rows)),
        "median_conditional_impact_all_statuses": float(comparable["conditional_qb_absence_point_impact"].median()) if len(comparable) else None,
        "median_conditional_impact_out_only": float(out_rows["conditional_qb_absence_point_impact"].median()) if len(out_rows) else None,
        "out_only_impact_quantiles": {
            str(q): float(out_rows["conditional_qb_absence_point_impact"].quantile(q))
            for q in (0.1, 0.25, 0.5, 0.75, 0.9)
        } if len(out_rows) else {},
        "out_rows_same_team_replacement_history": int(out_rows["replacement_history_same_team"].sum()) if len(out_rows) else 0,
        "method": "Prior-only, opportunity-weighted, recency-decayed passing EPA per dropback; shrink player rates toward prior QB population mean; multiply injured-minus-listed-replacement EPA/dropback by trailing average team dropbacks over up to 10 prior games.",
        "limitations": [
            "EPA/dropback is an expected-points rate proxy; multiplying by expected dropbacks is a conditional scenario, not a causal estimate.",
            "Listed depth-chart replacement is not verified active or actual starter.",
            "OUT is the primary cohort; QUESTIONABLE and DOUBTFUL are conditional absence scenarios, not probabilities.",
            "Team dropback volume is estimated from up to 10 prior team games and may change with opponent, game script, or coaching.",
            "Historical stats are strictly prior to the target season/week; same-week player outcomes are excluded.",
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
