"""Paired audit of recency-weighted ATS predictions versus equal weighting."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "four_model_2026_weeks01_08" / "recency_weighting" / "baseline_injury_recency_weighting_predictions.csv"
OUT = ROOT / "data" / "four_model_2026_weeks01_08" / "recency_weighting" / "baseline_injury_recency_weighting_paired_audit.json"
SCHEMES = ("half_life_4_seasons", "half_life_2_seasons", "half_life_1_season")
MODELS = ("baseline", "injury")


def compare(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    cols = ["game_id", "ats_outcome", "ats_direction", "ats_edge"]
    x = a[cols].rename(columns={c: f"equal_{c}" for c in cols if c != "game_id"})
    y = b[cols].rename(columns={c: f"weighted_{c}" for c in cols if c != "game_id"})
    m = x.merge(y, on="game_id", how="inner")
    flips = m[m["equal_ats_direction"] != m["weighted_ats_direction"]].copy()
    helped = int(((flips["equal_ats_outcome"] == "Loss") & (flips["weighted_ats_outcome"] == "Win")).sum())
    hurt = int(((flips["equal_ats_outcome"] == "Win") & (flips["weighted_ats_outcome"] == "Loss")).sum())
    other = int(len(flips) - helped - hurt)
    decisive = helped + hurt
    p = float(binomtest(min(helped, hurt), decisive, 0.5, alternative="two-sided").pvalue) if decisive else None
    return {
        "common_games": int(len(m)),
        "direction_flip_games": int(len(flips)),
        "weighted_helped": helped,
        "weighted_hurt": hurt,
        "push_or_other": other,
        "net_help_minus_hurt": helped - hurt,
        "decisive_flips": decisive,
        "exact_binomial_two_sided_p": round(p, 6) if p is not None else None,
    }


def main() -> None:
    df = pd.read_csv(IN)
    result = {
        "status": "RESEARCH_ONLY_RECENCY_WEIGHTING_PAIRED_AUDIT",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison": "Each weighted scheme versus equal weighting on the same games.",
        "by_season": {},
        "regimes": {},
    }
    for season in (2023, 2024, 2025, 2026):
        result["by_season"][str(season)] = {}
        s = df[pd.to_numeric(df["season"], errors="coerce").eq(season)]
        for model in MODELS:
            result["by_season"][str(season)][model] = {}
            equal = s[(s["model"] == model) & (s["decay_scheme"] == "equal_weight")]
            for scheme in SCHEMES:
                weighted = s[(s["model"] == model) & (s["decay_scheme"] == scheme)]
                result["by_season"][str(season)][model][scheme] = compare(equal, weighted)

    for name, seasons in {"2023_2025": (2023, 2024, 2025), "2025_2026": (2025, 2026), "2023_2026": (2023, 2024, 2025, 2026)}.items():
        result["regimes"][name] = {}
        s = df[pd.to_numeric(df["season"], errors="coerce").isin(seasons)]
        for model in MODELS:
            result["regimes"][name][model] = {}
            equal = s[(s["model"] == model) & (s["decay_scheme"] == "equal_weight")]
            for scheme in SCHEMES:
                weighted = s[(s["model"] == model) & (s["decay_scheme"] == scheme)]
                result["regimes"][name][model][scheme] = compare(equal, weighted)

    result["cautions"] = [
        "This is paired retrospective attribution, not a fresh holdout.",
        "Multiple weighting schemes are evaluated; p-values are descriptive and not corrected for multiple comparisons.",
        "No production model or official prospective record is modified.",
    ]
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
