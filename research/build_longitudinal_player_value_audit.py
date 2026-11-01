#!/usr/bin/env python3
"""Build point-in-time player-value snapshots for injury reports (research only).

Uses weekly player production strictly before each injury-report week. Produces
position-specific player ratings and a same-team positional benchmark. The latter
is NOT asserted to be the actual active backup; depth-chart/availability evidence
is required before converting it into a replacement penalty.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
HEADERS = {"User-Agent": "sports-betting-model-longitudinal-player-value/1.0"}
TIMEOUT = (15, 120)
DECAY_GAMES = 24.0
MIN_OPPORTUNITY = {"QB": 40, "RB": 25, "WR": 20, "TE": 15, "DEF": 10}
POSITION_GROUP = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "CB": "DEF", "S": "DEF", "FS": "DEF", "SS": "DEF", "SAF": "DEF",
    "LB": "DEF", "ILB": "DEF", "OLB": "DEF", "DE": "DEF", "DT": "DEF",
    "NT": "DEF", "DL": "DEF", "DB": "DEF",
}


def load_stats(season: int) -> pd.DataFrame:
    url = ("https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
           f"stats_player_week_{season}.parquet")
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return pd.read_parquet(BytesIO(response.content), engine="pyarrow")


def num(frame: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(frame[col], errors="coerce").fillna(0.0) if col in frame else pd.Series(0.0, index=frame.index)


def prepare_stats() -> pd.DataFrame:
    frames = [load_stats(s) for s in SEASONS]
    data = pd.concat(frames, ignore_index=True, sort=False)
    for col in ("season", "week"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["player_id"] = data["player_id"].astype("string").str.strip()
    data["team"] = data["team"].astype("string").str.upper().str.strip()
    data["position"] = data["position"].astype("string").str.upper().str.strip()
    data["position_group"] = data["position"].map(POSITION_GROUP)
    data = data.dropna(subset=["season", "week", "player_id", "team", "position_group"]).copy()
    data["season"] = data["season"].astype(int)
    data["week"] = data["week"].astype(int)

    # Aggregate multiple rows for a player/week/team before deriving rates.
    sum_cols = [
        "attempts", "completions", "passing_epa", "passing_cpoe", "sacks_suffered",
        "carries", "rushing_epa", "targets", "receptions", "receiving_epa",
        "def_sacks", "def_qb_hits", "def_interceptions", "def_pass_defended",
        "def_tackles_solo", "def_tackles_with_assist", "def_tackles_for_loss",
    ]
    for col in sum_cols:
        data[col] = num(data, col)
    keys = ["player_id", "player_name", "position", "position_group", "season", "week", "team"]
    data = data.groupby(keys, dropna=False, as_index=False)[sum_cols].sum()
    data["opportunity"] = 0.0
    data["raw_rate"] = np.nan
    data["volume"] = 0.0

    for group, idx in data.groupby("position_group").groups.items():
        d = data.loc[idx]
        if group == "QB":
            opp = d["attempts"] + d["sacks_suffered"]
            rate = d["passing_epa"] / opp.clip(lower=1) + 0.04 * d["passing_cpoe"]
            volume = opp
        elif group == "RB":
            opp = d["carries"] + d["targets"]
            rate = (d["rushing_epa"] + d["receiving_epa"]) / opp.clip(lower=1)
            volume = opp
        elif group in ("WR", "TE"):
            opp = d["targets"]
            rate = d["receiving_epa"] / opp.clip(lower=1)
            volume = opp
        else:
            opp = d["def_sacks"] + d["def_qb_hits"] + d["def_interceptions"] + d["def_pass_defended"] + 0.15 * (d["def_tackles_solo"] + d["def_tackles_with_assist"] + d["def_tackles_for_loss"])
            rate = (d["def_sacks"] * 2.0 + d["def_qb_hits"] * 0.6 + d["def_interceptions"] * 2.5 + d["def_pass_defended"] * 0.8 + d["def_tackles_for_loss"] * 0.5) / opp.clip(lower=1)
            volume = opp
        data.loc[idx, "opportunity"] = opp
        data.loc[idx, "raw_rate"] = rate.replace([np.inf, -np.inf], np.nan)
        data.loc[idx, "volume"] = volume
    data["sort_key"] = data["season"] * 100 + data["week"]
    return data


def main() -> None:
    from injury_model import load_injury_reports, _normalize_reports

    stats = prepare_stats()
    reports = _normalize_reports(load_injury_reports(SEASONS))
    reports["season"] = pd.to_numeric(reports["season"], errors="coerce")
    reports["week"] = pd.to_numeric(reports["week"], errors="coerce")
    reports["gsis_id"] = reports["gsis_id"].astype("string").str.strip()
    reports["team"] = reports["team"].astype("string").str.upper().str.strip()
    reports["position"] = reports["position"].astype("string").str.upper().str.strip()
    reports["position_group"] = reports["position"].map(POSITION_GROUP)
    reports = reports.dropna(subset=["season", "week", "gsis_id", "team", "position_group"]).copy()
    reports["season"] = reports["season"].astype(int)
    reports["week"] = reports["week"].astype(int)
    reports["sort_key"] = reports["season"] * 100 + reports["week"]

    # Collapse duplicate report updates to one player/team/week record. This is a
    # valuation audit; the point-in-time status-selection logic remains separate.
    reports = reports.sort_values("sort_key").drop_duplicates(
        ["gsis_id", "season", "week", "team"], keep="last"
    )
    records = []
    # Process each historical cutoff once; avoids rescanning the full stats table
    # separately for every injured player row.
    for cutoff, cutoff_reports in reports.groupby("sort_key", sort=True):
        cutoff = int(cutoff)
        prior = stats[stats["sort_key"] < cutoff].copy()
        if prior.empty:
            for report in cutoff_reports.itertuples(index=False):
                records.append({
                    "player_id": report.gsis_id, "season": report.season, "week": report.week,
                    "team": report.team, "position": report.position, "position_group": report.position_group,
                    "historical_games": 0, "historical_opportunities": 0,
                    "player_value_score": np.nan, "replacement_benchmark_score": np.nan,
                    "value_gap": np.nan, "valuation_status": "no_prior_player_stats",
                })
            continue

        # Exponentially decay older player-week observations. This produces a
        # pregame player rating with multi-season carryover and no target-week leakage.
        prior = prior.sort_values(["player_id", "sort_key"])
        prior["age"] = prior.groupby("player_id").cumcount(ascending=False)
        prior["recency_weight"] = np.exp(-np.log(2) * prior["age"] / DECAY_GAMES)
        prior["weighted_opportunity"] = prior["opportunity"] * prior["recency_weight"]
        prior["weighted_rate"] = prior["raw_rate"].fillna(0) * prior["recency_weight"]
        latest_team = prior.sort_values("sort_key").drop_duplicates(
            ["player_id", "position_group"], keep="last"
        )[["player_id", "position_group", "team"]]
        player_hist = prior.groupby(
            ["player_id", "position_group"], as_index=False
        ).agg(
            historical_games=("sort_key", "nunique"),
            historical_opportunities=("weighted_opportunity", "sum"),
            weighted_rate_sum=("weighted_rate", "sum"),
            weight_sum=("recency_weight", "sum"),
        )
        player_hist = player_hist.merge(
            latest_team, on=["player_id", "position_group"], how="left", validate="one_to_one"
        )
        player_hist["weighted_raw_rate"] = (
            player_hist["weighted_rate_sum"] / player_hist["weight_sum"].clip(lower=1e-9)
        )
        prior_means = prior.groupby("position_group")["raw_rate"].mean().to_dict()
        player_hist["position_prior_mean"] = player_hist["position_group"].map(prior_means).fillna(0.0)
        player_hist["reliability"] = player_hist.apply(
            lambda r: r["historical_opportunities"] /
            (r["historical_opportunities"] + MIN_OPPORTUNITY.get(r["position_group"], 10) * 3.0),
            axis=1,
        )
        player_hist["player_value_score"] = (
            player_hist["reliability"] * player_hist["weighted_raw_rate"] +
            (1.0 - player_hist["reliability"]) * player_hist["position_prior_mean"]
        )

        # Provisional same-team positional benchmark. This is not claimed to be
        # the active backup; it only measures the best other historically observed
        # teammate in that broad position group.
        peer = player_hist.sort_values("player_value_score", ascending=False).drop_duplicates(
            ["team", "position_group"]
        )[["team", "position_group", "player_id", "player_value_score"]].rename(
            columns={"player_id": "benchmark_player_id", "player_value_score": "replacement_benchmark_score"}
        )
        for report in cutoff_reports.itertuples(index=False):
            match = player_hist[
                (player_hist["player_id"] == str(report.gsis_id)) &
                (player_hist["position_group"] == str(report.position_group))
            ]
            if match.empty:
                records.append({
                    "player_id": report.gsis_id, "season": report.season, "week": report.week,
                    "team": report.team, "position": report.position, "position_group": report.position_group,
                    "historical_games": 0, "historical_opportunities": 0,
                    "player_value_score": np.nan, "replacement_benchmark_score": np.nan,
                    "value_gap": np.nan, "valuation_status": "no_prior_player_stats",
                })
                continue
            p = match.iloc[-1]
            candidates = peer[
                (peer["team"] == str(report.team)) &
                (peer["position_group"] == str(report.position_group)) &
                (peer["benchmark_player_id"] != str(report.gsis_id))
            ]
            replacement = float(candidates.iloc[0]["replacement_benchmark_score"]) if not candidates.empty else np.nan
            records.append({
                "player_id": report.gsis_id, "season": report.season, "week": report.week,
                "team": report.team, "position": report.position, "position_group": report.position_group,
                "historical_games": int(p["historical_games"]),
                "historical_opportunities": float(p["historical_opportunities"]),
                "weighted_raw_rate": float(p["weighted_raw_rate"]),
                "position_prior_mean": float(p["position_prior_mean"]),
                "player_value_score": float(p["player_value_score"]),
                "replacement_benchmark_score": replacement,
                "value_gap": float(p["player_value_score"] - replacement) if np.isfinite(replacement) else np.nan,
                "valuation_status": "valued_with_prior_history",
            })

    result = pd.DataFrame(records)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_csv = OUT / f"longitudinal_player_value_audit_{stamp}.csv"
    out_json = OUT / f"longitudinal_player_value_audit_{stamp}.json"
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "RESEARCH_AUDIT_ONLY_NO_MODEL_CHANGES",
        "injury_player_week_rows": int(len(result)),
        "rows_with_prior_player_stats": int(result["historical_games"].gt(0).sum()),
        "rows_with_same_team_positional_benchmark": int(result["replacement_benchmark_score"].notna().sum()),
        "rows_with_value_gap": int(result["value_gap"].notna().sum()),
        "position_group_coverage": result.groupby("position_group", dropna=False).agg(
            rows=("player_id", "size"),
            prior_history=("historical_games", lambda x: int(x.gt(0).sum())),
            replacement_benchmark=("replacement_benchmark_score", lambda x: int(x.notna().sum())),
        ).reset_index().to_dict(orient="records"),
        "limitations": [
            "Metrics are position-group-specific historical production proxies, not calibrated points or win probability.",
            "Historical observations are restricted to prior season/week; current target-week performance is excluded.",
            "The same-team positional benchmark is not verified as the next active player or actual backup.",
            "Defensive production is noisy and heavily requires validation before use.",
            "Offensive-line players are not individually valued by this source and remain outside this audit.",
            "This script does not create model features or alter official projections.",
        ],
    }
    result.to_csv(out_csv, index=False)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved {out_csv}")
    print(f"Saved {out_json}")


if __name__ == "__main__":
    main()
