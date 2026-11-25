"""Prospective CBB performance review from *graded immutable pretip records*.

This module never reads or infers a sportsbook line or model projection from
completed games, current boards, or historical model training outputs.
Only grade_frozen()'s verified results enter the prospective record.

Games are organized into Central Time dates for intuitive daily review,
with rolling exact 48-hour and 7-day windows plus the entire tracked season.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from cbb.prospective import utc_date
from cbb.prospective_grade import FIRST_CAPTURE_UTC, MODELS

CENTRAL = ZoneInfo("America/Chicago")
CUTOFFS = (0, 3.5)


def scorecard(games: list[dict], model: str, market: str, cutoff: float) -> dict:
    if market not in ("ats", "total"):
        raise ValueError("market must be ats or total")
    edge_key = "ats_edge" if market == "ats" else "total_edge"
    error_key = "margin_mae" if market == "ats" else "total_mae"
    with_model = [g for g in games if model in g.get("models", {})]
    eligible = []
    for game in with_model:
        result = game["models"][model]
        edge = result.get(edge_key)
        outcome = result.get(market)
        if outcome not in ("W", "L", "P") or edge is None:
            continue
        if edge == 0 or abs(edge) < cutoff:
            continue
        eligible.append(outcome)

    wins, losses, pushes = (eligible.count(x) for x in ("W", "L", "P"))
    n = len(eligible)
    decided = wins + losses
    mae_samples = [float(g["models"][model][error_key]) for g in with_model
                   if g["models"][model].get(error_key) is not None]
    return {
        "games_with_model": len(with_model),
        "selections": n,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "decided_win_rate_pct": round(100 * wins / decided, 2) if decided else None,
        "roi_minus_110_pct": round(
            100 * (wins * 100 / 110 - losses) / n, 2
        ) if n else None,
        "model_mae_points": round(mean(mae_samples), 3) if mae_samples else None,
    }


def portfolio(games: list[dict]) -> dict:
    return {
        model: {
            kind: {
                str(cutoff): scorecard(games, model, kind, cutoff)
                for cutoff in CUTOFFS
            }
            for kind in ("ats", "total")
        }
        for model in MODELS
    }


def head_to_head(games: list[dict]) -> list[dict]:
    """Paired accuracy only on games where BOTH models were truly frozen."""
    comparisons = []
    for model in MODELS:
        if model == "baseline":
            continue
        matched = [
            g for g in games if "baseline" in g["models"]
            and model in g["models"]
        ]
        if not matched:
            comparisons.append({
                "model": model,
                "paired_games": 0,
                "ats_mae_improvement_vs_baseline": None,
                "total_mae_improvement_vs_baseline": None,
            })
            continue

        def improvement(metric):
            key = "margin_mae" if metric == "ats" else "total_mae"
            return round(mean(g["models"]["baseline"][key] -
                              g["models"][model][key] for g in matched), 3)

        comparisons.append({
            "model": model, "paired_games": len(matched),
            "ats_mae_improvement_vs_baseline": improvement("ats"),
            "total_mae_improvement_vs_baseline": improvement("total"),
            "note": "Positive = lower player-model forecast error on identical frozen games.",
        })
    return comparisons


def central_date(game: dict) -> str:
    return utc_date(game["tip_utc"]).astimezone(CENTRAL).date().isoformat()


def generate_performance_report(
    entries: list[dict],
    untracked: int,
    invalid: int,
    captured_utc: datetime | None = None,
) -> dict:
    """Generate all report fields without side effects or network requests."""
    now = captured_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Review capture must be timezone aware")
    now = now.astimezone(timezone.utc)
    if len({str(g["id"]) for g in entries}) != len(entries):
        raise ValueError("Duplicate graded game IDs: refuse to double-count picks")
    if any(utc_date(g["tip_utc"]) > now for g in entries):
        raise ValueError("Future game cannot already have a final grade")
    if any(utc_date(g["captured_utc"]) >= utc_date(g["tip_utc"])
           for g in entries):
        raise ValueError("At least one graded pick was not frozen pretip")

    ordered = sorted(entries, key=lambda g: (g["tip_utc"], g["id"]))
    days = defaultdict(list)
    for game in ordered:
        days[central_date(game)].append(game)

    all_time = portfolio(ordered)
    last48 = [g for g in ordered
              if now - timedelta(hours=48) <= utc_date(g["tip_utc"]) <= now]
    last7 = [g for g in ordered
             if now - timedelta(days=7) <= utc_date(g["tip_utc"]) <= now]

    daily = [
        {
            "date_central": date,
            "completed_tracked_games": len(day_games),
            "models": portfolio(day_games),
        }
        for date, day_games in sorted(days.items())
    ]

    detail = []
    for g in reversed(ordered[-60:]):
        detail.append({
            "game_id": str(g["id"]),
            "tip_utc": g["tip_utc"],
            "date_central": central_date(g),
            "game": str(g.get("away") or "") + " @ " + str(g.get("home") or ""),
            "final_score": str(g["away_points"]) + "-" + str(g["home_points"]),
            "frozen_utc": g["captured_utc"],
            "book": g.get("market_provider"),
            "frozen_home_spread": g.get("home_spread"),
            "frozen_total": g.get("market_total"),
            "models": {
                model: {
                    "ats": observed.get("ats"), "total": observed.get("total"),
                    "ats_edge": observed.get("ats_edge"),
                    "total_edge": observed.get("total_edge"),
                    "margin_mae": observed.get("margin_mae"),
                    "total_mae": observed.get("total_mae"),
                }
                for model, observed in g["models"].items()
            },
        })

    reporting_span = {
        "first_frozen_capture_utc":
            FIRST_CAPTURE_UTC.isoformat().replace("+00:00", "Z"),
        "first_graded_tip_utc": ordered[0]["tip_utc"] if ordered else None,
        "latest_graded_tip_utc": ordered[-1]["tip_utc"] if ordered else None,
        "as_of_utc": now.isoformat().replace("+00:00", "Z"),
        "local_reporting_timezone": "America/Chicago",
    }
    provider_breakdown = dict(Counter(
        g.get("market_provider") or "unknown" for g in ordered
    ))
    return {
        "type": "cbb_prospective_research_performance",
        "season": 2027,
        "version": 1,
        **reporting_span,
        "tracked_games": len(ordered),
        "completed_untracked_since_first_capture": untracked,
        "invalid_frozen_records": invalid,
        "frozen_market_provider_counts": provider_breakdown,
        "all_tracked": all_time,
        "last_48_hours": {
            "tracked_games": len(last48),
            "models": portfolio(last48),
        },
        "last_7_days": {
            "tracked_games": len(last7),
            "models": portfolio(last7),
        },
        "daily_by_central_date": daily,
        "paired_model_accuracy_vs_baseline": head_to_head(ordered),
        "most_recent_60_games": detail,
        "interpretation": {
            "all_directional": "Edge cutoff zero means every non-tied directional lean on a frozen market line.",
            "edge_threshold": "3.5-point threshold is retrospective descriptive reporting, not a promise of profit.",
            "roi": "Hypothetical $110 risk to win $100, pushes refunded; n includes pushes.",
            "incomplete_model": "Later-developed models are counted only where present in the actual original frozen file.",
            "coverage": "Untracked and invalid games do not enter win-loss/ROI and are disclosed separately.",
            "bookmaker": "Provider-specific historical lines can differ; do not infer an independently verified close.",
            "safety": "This is a research-only model shadow record, not user's personal wagers.",
        },
    }
