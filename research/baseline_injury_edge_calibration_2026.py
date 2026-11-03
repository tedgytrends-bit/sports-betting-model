"""Research-only 2026 Weeks 1-8 ATS edge calibration for Baseline and Injury.

Uses the validated 121-game four-model reconstruction. Tests whether larger
absolute ATS edges correspond to better directional accuracy and simulated -110
ROI. Does not alter production projections or official prospective records.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/four_model_2026_weeks01_08/four_model_2026_weeks01_08_games.csv"
OUT = ROOT / "data/four_model_2026_weeks01_08/edge_calibration"
MODELS = ("baseline", "injury")
BREAK_EVEN = 110.0 / 210.0


def result_summary(frame: pd.DataFrame, result_col: str) -> dict:
    wins = int((frame[result_col] == "Win").sum())
    losses = int((frame[result_col] == "Loss").sum())
    pushes = int((frame[result_col] == "Push").sum())
    graded = wins + losses
    profit = wins * (100.0 / 110.0) - losses
    risked = graded + pushes
    p_gt_break_even = (
        float(binomtest(wins, graded, BREAK_EVEN, alternative="greater").pvalue)
        if graded else None
    )
    return {
        "games": int(len(frame)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "graded_ex_pushes": graded,
        "accuracy_pct_ex_pushes": round(100.0 * wins / graded, 3) if graded else None,
        "profit_units_at_minus110": round(profit, 4),
        "roi_pct_at_minus110": round(100.0 * profit / risked, 3) if risked else None,
        "one_sided_p_vs_minus110_break_even": round(p_gt_break_even, 6) if p_gt_break_even is not None else None,
    }


def edge_band(value: float) -> str:
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


def ats_direction(pick: object) -> str:
    text = str(pick)
    # In the validated dataset, a negative line is the favorite and a positive line is the dog.
    return "favorite" if " -" in text else "underdog"


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(INPUT)
    games = pd.read_csv(INPUT)
    if len(games) != 121:
        raise RuntimeError(f"Expected validated 121-game sample, found {len(games)}")

    report = {
        "status": "RESEARCH_ONLY_EDGE_CALIBRATION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "2026 Weeks 1-8 validated 121-game four-model reconstruction",
        "question": "Do larger absolute ATS edges for Baseline and Injury produce better directional results?",
        "minus110_break_even_pct": round(100.0 * BREAK_EVEN, 3),
        "models": {},
        "comparison": {},
        "cautions": [
            "Weeks 1-7 use archived nflverse schedule lines; Week 8 uses the user-verified Bovada board.",
            "This is retrospective analysis of the same 121-game sample, not a fresh holdout.",
            "Small edge bands can be highly unstable.",
            "Thresholds are descriptive and must not be selected solely from this sample for production betting rules.",
            "No production model or official prospective record is changed.",
        ],
    }
    rows = []

    for model in MODELS:
        edge_col = f"{model}_ats_edge"
        result_col = f"{model}_ats_result"
        pick_col = f"{model}_ats_pick"
        data = games.dropna(subset=[edge_col, result_col]).copy()
        data["abs_edge"] = pd.to_numeric(data[edge_col], errors="coerce").abs()
        data["edge_band"] = data[edge_col].map(edge_band)
        data["direction"] = data[pick_col].map(ats_direction)

        graded = data[data[result_col].isin(["Win", "Loss"])].copy()
        graded["win"] = graded[result_col].eq("Win").astype(int)
        rho, rho_p = spearmanr(graded["abs_edge"], graded["win"])

        bands = []
        for band in ("0_to_1", "1_to_2", "2_to_3", "3_to_4", "4_plus"):
            subset = data[data["edge_band"].eq(band)].copy()
            s = result_summary(subset, result_col)
            s["edge_band"] = band
            s["mean_abs_edge"] = round(float(subset["abs_edge"].mean()), 3) if len(subset) else None
            bands.append(s)
            rows.append({"model": model, "analysis": "exclusive_band", "bucket": band, **s})

        cumulative = []
        for threshold in (0.0, 1.0, 2.0, 3.0, 4.0):
            subset = data[data["abs_edge"] >= threshold].copy()
            s = result_summary(subset, result_col)
            s["minimum_abs_edge"] = threshold
            s["mean_abs_edge"] = round(float(subset["abs_edge"].mean()), 3) if len(subset) else None
            cumulative.append(s)
            rows.append({"model": model, "analysis": "cumulative_threshold", "bucket": f">={threshold:g}", **s})

        directions = {}
        for direction in ("favorite", "underdog"):
            subset = data[data["direction"].eq(direction)].copy()
            directions[direction] = result_summary(subset, result_col)

        by_week = []
        for week, subset in data.groupby("week", sort=True):
            s = result_summary(subset, result_col)
            s["week"] = int(week)
            s["mean_abs_edge"] = round(float(subset["abs_edge"].mean()), 3)
            by_week.append(s)

        report["models"][model] = {
            "overall": result_summary(data, result_col),
            "exclusive_edge_bands": bands,
            "cumulative_thresholds": cumulative,
            "direction": directions,
            "by_week": by_week,
            "edge_strength_vs_win_spearman_rho": round(float(rho), 4),
            "edge_strength_vs_win_spearman_p": round(float(rho_p), 6),
        }

    # Same-game comparison of which model has the larger absolute edge and whether that model is more often correct.
    paired = games.copy()
    paired["baseline_abs_edge"] = pd.to_numeric(paired["baseline_ats_edge"], errors="coerce").abs()
    paired["injury_abs_edge"] = pd.to_numeric(paired["injury_ats_edge"], errors="coerce").abs()
    paired = paired[
        paired["baseline_ats_result"].isin(["Win", "Loss"])
        & paired["injury_ats_result"].isin(["Win", "Loss"])
    ].copy()
    unequal = paired[~np.isclose(paired["baseline_abs_edge"], paired["injury_abs_edge"])].copy()
    unequal["larger_edge_model"] = np.where(
        unequal["baseline_abs_edge"] > unequal["injury_abs_edge"], "baseline", "injury"
    )
    unequal["larger_edge_correct"] = np.where(
        unequal["larger_edge_model"].eq("baseline"),
        unequal["baseline_ats_result"].eq("Win"),
        unequal["injury_ats_result"].eq("Win"),
    )
    report["comparison"] = {
        "common_graded_games": int(len(paired)),
        "games_with_unequal_abs_edge": int(len(unequal)),
        "larger_edge_model_correct_games": int(unequal["larger_edge_correct"].sum()),
        "larger_edge_model_accuracy_pct": round(100.0 * unequal["larger_edge_correct"].mean(), 3) if len(unequal) else None,
        "baseline_has_larger_edge_games": int(unequal["larger_edge_model"].eq("baseline").sum()),
        "injury_has_larger_edge_games": int(unequal["larger_edge_model"].eq("injury").sum()),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "baseline_injury_edge_calibration_2026.json"
    table_path = OUT / "baseline_injury_edge_calibration_2026.csv"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(table_path, index=False)
    print(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")
    print(f"Wrote {table_path}")


if __name__ == "__main__":
    main()
