"""Analyze when added feature blocks flip 2026 Weeks 1-8 picks away from Baseline.

Research only. Reads the validated four-model game-level reconstruction and measures
whether Injury, Efficiency, and Combined flips improved or harmed directional results.
No production files or official prospective records are modified.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/four_model_2026_weeks01_08/four_model_2026_weeks01_08_games.csv"
OUT = ROOT / "data/four_model_2026_weeks01_08/disagreement_analysis"
CHALLENGERS = ("injury", "efficiency", "combined")
MARKETS = ("ats", "total")


def edge_bin(value: float) -> str:
    x = abs(float(value))
    if x < 1.0:
        return "0_to_1"
    if x < 2.0:
        return "1_to_2"
    if x < 3.0:
        return "2_to_3"
    if x < 4.0:
        return "3_to_4"
    return "4_plus"


def ats_side(pick: object) -> str:
    text = str(pick)
    if "+" in text:
        return "underdog"
    if "-" in text:
        return "favorite"
    return "other"


def result_class(baseline_result: str, challenger_result: str) -> str:
    b = str(baseline_result)
    c = str(challenger_result)
    if b == "Loss" and c == "Win":
        return "added_helped"
    if b == "Win" and c == "Loss":
        return "added_hurt"
    if b == "Push" and c == "Push":
        return "market_push"
    if b == "Push" and c == "Win":
        return "added_helped_vs_push"
    if b == "Win" and c == "Push":
        return "added_hurt_to_push"
    if b == "Loss" and c == "Push":
        return "added_helped_to_push"
    if b == "Push" and c == "Loss":
        return "added_hurt_vs_push"
    return "other"


def record(frame: pd.DataFrame, result_col: str) -> dict:
    counts = frame[result_col].value_counts(dropna=False)
    wins = int(counts.get("Win", 0))
    losses = int(counts.get("Loss", 0))
    pushes = int(counts.get("Push", 0))
    graded = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "graded_ex_pushes": graded,
        "accuracy_pct_ex_pushes": round(100.0 * wins / graded, 3) if graded else None,
    }


def flip_summary(frame: pd.DataFrame, challenger: str, market: str) -> dict:
    base_pick = f"baseline_{market}_pick"
    new_pick = f"{challenger}_{market}_pick"
    base_result = f"baseline_{market}_result"
    new_result = f"{challenger}_{market}_result"
    base_edge = f"baseline_{market}_edge"
    new_edge = f"{challenger}_{market}_edge"

    flips = frame[frame[base_pick].astype(str) != frame[new_pick].astype(str)].copy()
    agrees = frame[frame[base_pick].astype(str) == frame[new_pick].astype(str)].copy()
    flips["attribution"] = flips.apply(
        lambda r: result_class(r[base_result], r[new_result]), axis=1
    )
    helped = int((flips["attribution"] == "added_helped").sum())
    hurt = int((flips["attribution"] == "added_hurt").sum())
    decisive = helped + hurt
    p_value = float(binomtest(helped, decisive, 0.5, alternative="two-sided").pvalue) if decisive else None

    by_week = []
    for week, group in flips.groupby("week", sort=True):
        attr = group["attribution"].value_counts()
        by_week.append({
            "week": int(week),
            "flips": int(len(group)),
            "added_helped": int(attr.get("added_helped", 0)),
            "added_hurt": int(attr.get("added_hurt", 0)),
            "push_or_other": int(len(group) - attr.get("added_helped", 0) - attr.get("added_hurt", 0)),
        })

    by_baseline_edge = []
    for label in ("0_to_1", "1_to_2", "2_to_3", "3_to_4", "4_plus"):
        group = flips[flips[base_edge].map(edge_bin) == label] if len(flips) else flips
        attr = group["attribution"].value_counts() if len(group) else pd.Series(dtype=int)
        by_baseline_edge.append({
            "baseline_abs_edge_band": label,
            "flips": int(len(group)),
            "added_helped": int(attr.get("added_helped", 0)),
            "added_hurt": int(attr.get("added_hurt", 0)),
        })

    if market == "ats":
        flips["baseline_direction"] = flips[base_pick].map(ats_side)
        flips["challenger_direction"] = flips[new_pick].map(ats_side)
    else:
        flips["baseline_direction"] = flips[base_pick].astype(str)
        flips["challenger_direction"] = flips[new_pick].astype(str)

    direction = []
    for (bdir, ndir), group in flips.groupby(["baseline_direction", "challenger_direction"]):
        attr = group["attribution"].value_counts()
        direction.append({
            "baseline_direction": str(bdir),
            "challenger_direction": str(ndir),
            "flips": int(len(group)),
            "added_helped": int(attr.get("added_helped", 0)),
            "added_hurt": int(attr.get("added_hurt", 0)),
        })

    return {
        "challenger": challenger,
        "market": market,
        "games": int(len(frame)),
        "agree_games": int(len(agrees)),
        "flip_games": int(len(flips)),
        "flip_rate_pct": round(100.0 * len(flips) / len(frame), 3) if len(frame) else None,
        "baseline_record_when_agree": record(agrees, base_result),
        "baseline_record_on_flips": record(flips, base_result),
        "challenger_record_on_flips": record(flips, new_result),
        "added_helped": helped,
        "added_hurt": hurt,
        "net_help_minus_hurt": helped - hurt,
        "decisive_flips": decisive,
        "exact_binomial_two_sided_p": round(p_value, 6) if p_value is not None else None,
        "mean_baseline_abs_edge_on_flips": round(float(flips[base_edge].abs().mean()), 3) if len(flips) else None,
        "mean_challenger_abs_edge_on_flips": round(float(flips[new_edge].abs().mean()), 3) if len(flips) else None,
        "mean_edge_shift_points": round(float((flips[new_edge] - flips[base_edge]).abs().mean()), 3) if len(flips) else None,
        "by_week": by_week,
        "by_baseline_abs_edge": by_baseline_edge,
        "by_direction_change": direction,
    }


def combined_attribution(frame: pd.DataFrame, market: str) -> list[dict]:
    b = f"baseline_{market}_pick"
    i = f"injury_{market}_pick"
    e = f"efficiency_{market}_pick"
    c = f"combined_{market}_pick"
    br = f"baseline_{market}_result"
    cr = f"combined_{market}_result"
    flips = frame[frame[b].astype(str) != frame[c].astype(str)].copy()

    def source(row: pd.Series) -> str:
        injury_support = str(row[i]) == str(row[c])
        efficiency_support = str(row[e]) == str(row[c])
        if injury_support and efficiency_support:
            return "both_injury_and_efficiency_support_flip"
        if injury_support:
            return "injury_only_supports_flip"
        if efficiency_support:
            return "efficiency_only_supports_flip"
        return "combined_unique_flip"

    flips["source"] = flips.apply(source, axis=1)
    flips["outcome"] = flips.apply(lambda r: result_class(r[br], r[cr]), axis=1)
    out = []
    for source_name, group in flips.groupby("source", sort=True):
        counts = group["outcome"].value_counts()
        out.append({
            "source": source_name,
            "games": int(len(group)),
            "added_helped": int(counts.get("added_helped", 0)),
            "added_hurt": int(counts.get("added_hurt", 0)),
            "push_or_other": int(len(group) - counts.get("added_helped", 0) - counts.get("added_hurt", 0)),
        })
    return out


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(f"Missing validated Weeks 1-8 game dataset: {INPUT}")
    frame = pd.read_csv(INPUT)
    if len(frame) != 121:
        raise RuntimeError(f"Expected 121 games, found {len(frame)}")
    if sorted(pd.to_numeric(frame["week"], errors="coerce").dropna().astype(int).unique()) != list(range(1, 9)):
        raise RuntimeError("Input does not contain exactly Weeks 1-8.")

    OUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    flip_rows = []

    for challenger in CHALLENGERS:
        for market in MARKETS:
            summaries.append(flip_summary(frame, challenger, market))
            base_pick = f"baseline_{market}_pick"
            new_pick = f"{challenger}_{market}_pick"
            base_result = f"baseline_{market}_result"
            new_result = f"{challenger}_{market}_result"
            base_edge = f"baseline_{market}_edge"
            new_edge = f"{challenger}_{market}_edge"
            subset = frame[frame[base_pick].astype(str) != frame[new_pick].astype(str)].copy()
            for _, row in subset.iterrows():
                flip_rows.append({
                    "game_id": row["game_id"],
                    "week": int(row["week"]),
                    "away_team": row["away_team"],
                    "home_team": row["home_team"],
                    "market": market,
                    "challenger": challenger,
                    "baseline_pick": row[base_pick],
                    "challenger_pick": row[new_pick],
                    "baseline_result": row[base_result],
                    "challenger_result": row[new_result],
                    "attribution": result_class(row[base_result], row[new_result]),
                    "baseline_edge": row[base_edge],
                    "challenger_edge": row[new_edge],
                    "baseline_abs_edge_band": edge_bin(row[base_edge]),
                    "edge_shift_points": abs(float(row[new_edge]) - float(row[base_edge])),
                    "market_source": row["market_source"],
                })

    flip_df = pd.DataFrame(flip_rows).sort_values(["market", "challenger", "week", "game_id"])
    flip_df.to_csv(OUT / "four_model_2026_disagreement_flips.csv", index=False)

    compact_rows = []
    for item in summaries:
        compact_rows.append({
            "market": item["market"],
            "challenger": item["challenger"],
            "games": item["games"],
            "agree_games": item["agree_games"],
            "flip_games": item["flip_games"],
            "flip_rate_pct": item["flip_rate_pct"],
            "added_helped": item["added_helped"],
            "added_hurt": item["added_hurt"],
            "net_help_minus_hurt": item["net_help_minus_hurt"],
            "p_value": item["exact_binomial_two_sided_p"],
            "baseline_flip_accuracy_pct": item["baseline_record_on_flips"]["accuracy_pct_ex_pushes"],
            "challenger_flip_accuracy_pct": item["challenger_record_on_flips"]["accuracy_pct_ex_pushes"],
            "mean_baseline_abs_edge_on_flips": item["mean_baseline_abs_edge_on_flips"],
            "mean_edge_shift_points": item["mean_edge_shift_points"],
        })
    pd.DataFrame(compact_rows).to_csv(OUT / "four_model_2026_disagreement_summary.csv", index=False)

    report = {
        "status": "RESEARCH_ONLY_DISAGREEMENT_ATTRIBUTION",
        "scope": "2026 Weeks 1-8 validated 121-game four-model reconstruction",
        "question": "When an added feature block changes Baseline's directional pick, does that change help or hurt?",
        "definitions": {
            "added_helped": "Baseline lost and challenger won on a game where the picks differed.",
            "added_hurt": "Baseline won and challenger lost on a game where the picks differed.",
            "net_help_minus_hurt": "Positive means the added model improved more flips than it damaged; negative means it damaged more.",
            "p_value": "Exact two-sided binomial test of helped vs hurt among decisive flips; exploratory, not a model-selection threshold by itself.",
        },
        "comparisons": summaries,
        "combined_flip_attribution": {
            market: combined_attribution(frame, market) for market in MARKETS
        },
        "cautions": [
            "Weeks 1-7 still use archived nflverse schedule lines; Week 8 uses the user-verified Bovada board.",
            "This is retrospective feature attribution on the same 121-game sample, not a new independent holdout.",
            "Small disagreement subsets can produce unstable percentages.",
            "No production model or official prospective record is changed.",
        ],
    }
    (OUT / "four_model_2026_disagreement_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
