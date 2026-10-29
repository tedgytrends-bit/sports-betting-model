"""Pure helper for grading frozen model predictions at recorded American odds.

Research only: this grades hypothetical outcomes and does not verify that a quote
was executable. The caller is responsible for selecting timing-eligible snapshots.
"""
import math

import pandas as pd


def american_profit_per_unit(american_odds):
    """Return net profit on one unit risked, or NaN for an invalid price."""
    if pd.isna(american_odds):
        return float("nan")
    odds = float(american_odds)
    # American odds must be at least +100 or at most -100. Values between
    # -100 and +100 (including zero) are not valid American odds.
    if not math.isfinite(odds) or abs(odds) < 100:
        return float("nan")
    return odds / 100.0 if odds > 0 else 100.0 / abs(odds)


def grade_actual_price(row, market, edge_threshold=3.5):
    """Grade one eligible quote row for ATS or totals; return result and units.

    Expected fields are the same as the prospective audit's odds DataFrame.
    Home handicap is signed: home cover margin = actual home margin + handicap.
    """
    if market not in {"ATS", "Totals"}:
        raise ValueError("market must be 'ATS' or 'Totals'")

    if (
        not bool(row["final_available"])
        or not bool(row["timing_eligible"])
        or not bool(row.get("score_team_match", True))
    ):
        return {"result": "Pending/Not eligible", "net_units": float("nan"), "units_risked": float("nan")}

    if market == "ATS":
        edge = row["endzone_ats_edge"]
        line = row["spread_home"]
        price = row["spread_home_odds"] if pd.notna(edge) and edge > 0 else row["spread_away_odds"]
        margin = row["actual_home_margin"] + line if pd.notna(line) and pd.notna(row["actual_home_margin"]) else float("nan")
    else:
        edge = row["endzone_total_edge"]
        line = row["total"]
        price = row["total_over_odds"] if pd.notna(edge) and edge > 0 else row["total_under_odds"]
        margin = row["actual_total"] - line if pd.notna(line) and pd.notna(row["actual_total"]) else float("nan")

    if pd.isna(edge) or pd.isna(line) or pd.isna(price) or pd.isna(margin) or edge == 0:
        return {"result": "Not gradable", "net_units": float("nan"), "units_risked": float("nan")}
    profit_per_unit = american_profit_per_unit(price)
    if pd.isna(profit_per_unit):
        return {"result": "Not gradable", "net_units": float("nan"), "units_risked": float("nan")}
    if abs(float(edge)) < edge_threshold:
        return {
            "result": f"Below {edge_threshold:.1f}-point threshold",
            "net_units": float("nan"),
            "units_risked": float("nan"),
        }

    directional_margin = float(margin) * (1 if edge > 0 else -1)
    if directional_margin == 0:
        result, net = "Push", 0.0
    elif directional_margin > 0:
        result, net = "Win", profit_per_unit
    else:
        result, net = "Loss", -1.0
    return {"result": result, "net_units": net, "units_risked": 1.0}
