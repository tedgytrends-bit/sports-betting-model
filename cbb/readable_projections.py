"""Render human-readable future-only CBB forecasts from the latest as-of capture.

Never treat updated projections as originally frozen pregame picks.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
MODELS = (
    ("baseline", "Team baseline"),
    ("player_v2", "Player v2"),
    ("player_opp_v3", "Player + opponent v3"),
    ("player_rot_v4", "Player + rotation v4"),
    ("player_all_v4", "Player + opponent + rotation v4"),
)


def utc(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timestamp lacks timezone")
    return d.astimezone(timezone.utc)


def txt(value):
    return str(value or "Unknown").replace("|", "\\|").replace("\n", " ")[:85]


def num(value, sign=False):
    if value is None:
        return "—"
    return f"{float(value):+.1f}" if sign and float(value) else f"{float(value):.1f}"


def ats_lean(game, pred):
    spread = game.get("market", {}).get("home_spread")
    edge = pred.get("ats_edge")
    side = pred.get("ats_lean")
    if spread is None or edge is None or side not in ("home", "away"):
        return "—"
    team = game["home"] if side == "home" else game["away"]
    selection_spread = spread if side == "home" else -float(spread)
    return f"{txt(team)} {num(selection_spread, sign=True)} ({abs(float(edge)):.1f} pt)"


def total_lean(game, pred):
    total = game.get("market", {}).get("total")
    edge = pred.get("total_edge")
    side = pred.get("total_lean")
    if total is None or edge is None or side not in ("over", "under"):
        return "—"
    return f"{side.title()} {num(total)} ({abs(float(edge)):.1f} pt)"


def render_projections(board):
    if board.get("capture_type") != "research_shadow":
        raise ValueError("Capture is not a CBB research shadow")
    captured = utc(board["capture_utc"])
    records = list(board.get("games", []))
    if len(set(str(g["id"]) for g in records)) != len(records):
        raise ValueError("Duplicate game IDs")
    if any(utc(g["tip_utc"]) <= captured for g in records):
        raise ValueError("Cannot display past game as upcoming")
    market_games = [g for g in records if
                    g.get("market", {}).get("home_spread") is not None or
                    g.get("market", {}).get("total") is not None]
    updated_ct = captured.astimezone(CENTRAL).strftime("%B %d, %Y, %I:%M %p CT")
    lines = [
        "# Tedgy Trends CBB — Upcoming Projections",
        "",
        f"**Updated: {updated_ct}**",
        "",
        "**Latest projections** update with new results, roster inputs and observed sportsbook lines. "
        "The originally frozen pretip forecasts used for the official research scorecard never change.",
        "",
        f"**Next eight days:** {len(records)} upcoming games · "
        f"**With market lines:** {len(market_games)} · "
        f"**Without market lines:** {len(records)-len(market_games)}",
        "",
        "[Results and ROI](README.md) · "
        "[Frozen pretip picks](frozen/) · "
        "[All upcoming forecasts as JSON](latest.json)",
        "",
        "## Upcoming games with market lines",
        "",
        "All times Central. ATS leans show **which team and spread** the model favors; "
        "parentheses show model-vs-market edge in points, not probability.",
        "",
    ]
    if not market_games:
        lines.extend([
            "No games had a usable spread or total at the most recent capture.",
            "Games without lines still have projected scores in the latest JSON.",
            "",
        ])
        return "\n".join(lines)

    days = defaultdict(list)
    for game in market_games:
        tip = utc(game["tip_utc"]).astimezone(CENTRAL)
        days[tip.date().isoformat()].append((tip, game))

    for date in sorted(days):
        lines.extend([
            "### " + datetime.fromisoformat(date).strftime("%A, %B %d, %Y"),
            "",
            "| Tip / matchup | Market at capture | Model | Projected score (away / home) | Projected total | ATS lean | Total lean |",
            "|---|---|---|---|---:|---|---|",
        ])
        for tip, game in sorted(days[date], key=lambda p:(p[0],str(p[1]["id"]))):
            odds = game.get("market") or {}
            home_spread = odds.get("home_spread")
            market = (
                txt(game["home"]) + " " +
                num(home_spread, sign=True) + " / Total " +
                num(odds.get("total")) + " (" + txt(odds.get("provider") or "Unknown source") + ")"
            )
            matchup = (
                tip.strftime("%I:%M %p") + " · **" +
                txt(game["away"]) + " @ " + txt(game["home"]) + "**"
            )
            first = True
            for model, title in MODELS:
                pred = game.get(model)
                if pred is None:
                    continue
                score = (
                    txt(game["away"]) + " " + num(pred.get("projected_away_points"))
                    + " / " + txt(game["home"]) + " " + num(pred.get("projected_home_points"))
                )
                lines.append(
                    "| " + (matchup if first else "") + " | " +
                    (market if first else "") + " | " + title + " | " +
                    score + " | " + num(pred.get("projected_total")) + " | " +
                    ats_lean(game, pred) + " | " + total_lean(game, pred) + " |"
                )
                first = False
        lines.append("")

    lines.extend([
        "## How to read this board",
        "",
        "- These are **latest** projections, not frozen records. Season wins, losses and ROI are graded "
        "against the original timestamped pretip frozen forecasts linked above.",
        "- Market lines are the sportsbook numbers observed **at the capture timestamp**, not live quotes.",
        "- When there is no market spread or total, a corresponding ATS or total lean cannot be determined. "
        "Such games are kept in the full JSON projection board.",
        "- All five models are experimental. No model has established reliable profitability across "
        "all historical directional predictions. This is research, not betting advice.",
        "- Captures are scheduled at 13:05 UTC each day November–April; GitHub Actions can start late.",
        "",
    ])
    return "\n".join(lines)
