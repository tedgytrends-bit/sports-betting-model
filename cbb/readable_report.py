"""Human-readable CBB research scorecard generated from verified frozen grades.

No data access, odds lookup or retroactive model evaluation occurs here.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

NAMES = (
    ("baseline", "Team baseline"),
    ("player_v2", "Player v2"),
    ("player_opp_v3", "Player + opponent v3"),
    ("player_rot_v4", "Player + rotation v4"),
    ("player_all_v4", "Player + opponent + rotation v4"),
)


def safe(value: object) -> str:
    return (str(value) if value is not None else "—").replace("|", "\\|").replace(
        "\n", " "
    )[:140]


def pick_record(card: dict) -> str:
    if not card or not card.get("selections"):
        return "—"
    w, l, p = (card[k] for k in ("wins", "losses", "pushes"))
    return f"{w}-{l}-{p}" if p else f"{w}-{l}"


def roi(card: dict) -> str:
    value = card.get("roi_minus_110_pct") if card else None
    return f"{value:+.2f}%" if value is not None else "—"


def _score(report, model, market, edge="0"):
    return report[model][market][edge]


def render_markdown(report: dict) -> str:
    if report.get("type") != "cbb_prospective_research_performance":
        raise ValueError("Unsupported prospective performance report")
    now = datetime.fromisoformat(report["as_of_utc"].replace("Z", "+00:00"))
    local = now.astimezone(ZoneInfo("America/Chicago"))
    lines = [
        "# Tedgy Trends CBB — Prospective Research Results",
        "",
        f"**As of {local.strftime('%B %d, %Y, %I:%M %p')} Central Time**",
        "",
        "Research-only performance from projections **actually frozen before tipoff**. "
        "No historical picks are retroactively inserted.",
        "",
        f"**Tracked completed games:** {report['tracked_games']} · "
        f"**Completed without valid frozen record:** "
        f"{report['completed_untracked_since_first_capture']} · "
        f"**Invalid frozen records:** {report['invalid_frozen_records']}",
        "",
        "## Season-to-date — all directional leans (no edge threshold)",
        "",
        "| Model | ATS W–L–P | ATS ROI | ATS point error | Totals W–L–P | Totals ROI | Total point error |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model, title in NAMES:
        row = report["all_tracked"][model]
        ats, total = row["ats"]["0"], row["total"]["0"]
        aerr = ats["model_mae_points"]
        terr = total["model_mae_points"]
        lines.append(
            f"| {title} | {pick_record(ats)} | {roi(ats)} | "
            f"{f'{aerr:.2f}' if aerr is not None else '—'} | "
            f"{pick_record(total)} | {roi(total)} | "
            f"{f'{terr:.2f}' if terr is not None else '—'} |"
        )
    lines += [
        "",
        "## ATS results when projected edge is at least 3.5 points",
        "",
        "| Model | ATS record | Hypothetical ROI | Number of selected games |",
        "|---|---:|---:|---:|",
    ]
    for model, title in NAMES:
        row = _score(report["all_tracked"], model, "ats", "3.5")
        lines.append(
            f"| {title} | {pick_record(row)} | {roi(row)} | "
            f"{row['selections']} |"
        )
    lines += [
        "",
        "## Recent tracking windows",
        "",
        "| Window | Tracked completed games | Player v2 ATS | Player v2 ATS ROI | Player v2 totals | Player v2 totals ROI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, title in (("last_48_hours", "Past 48 hours"),
                       ("last_7_days", "Past 7 days")):
        block = report[key]
        ats = block["models"]["player_v2"]["ats"]["0"]
        total = block["models"]["player_v2"]["total"]["0"]
        lines.append(
            f"| {title} | {block['tracked_games']} | {pick_record(ats)} | "
            f"{roi(ats)} | {pick_record(total)} | {roi(total)} |"
        )
    lines += [
        "",
        "## By game date (Central Time)",
        "",
        "| Date | Tracked games | Player v2 ATS | Player v2 totals |",
        "|---|---:|---:|---:|",
    ]
    for day in reversed(report["daily_by_central_date"][-14:]):
        block = day["models"]["player_v2"]
        lines.append(
            f"| {day['date_central']} | {day['completed_tracked_games']} | "
            f"{pick_record(block['ats']['0'])} | {pick_record(block['total']['0'])} |"
        )
    lines += [
        "",
        "## Matched-game spread error relative to team baseline",
        "",
        "Positive = the additional model reduced average point error **on identical frozen games**.",
        "",
        "| Model | Matched games | ATS error reduction | Totals error reduction |",
        "|---|---:|---:|---:|",
    ]
    by_model = {row["model"]: row for row in report["paired_model_accuracy_vs_baseline"]}
    for model, title in NAMES:
        if model == "baseline":
            continue
        row = by_model[model]
        def difference(key):
            value = row[key]
            return f"{value:+.3f}" if value is not None else "—"
        lines.append(
            f"| {title} | {row['paired_games']} | "
            f"{difference('ats_mae_improvement_vs_baseline')} | "
            f"{difference('total_mae_improvement_vs_baseline')} |"
        )

    lines += [
        "",
        "## Most recently completed tracked games",
        "",
        "| Date (Central) | Matchup | Final (away–home) | Frozen home spread | Frozen total | Player v2 ATS | Player v2 total |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for g in report["most_recent_60_games"][:20]:
        pv2 = g["models"].get("player_v2") or {}
        lines.append(
            f"| {safe(g['date_central'])} | {safe(g['game'])} | "
            f"{safe(g['final_score'])} | {safe(g['frozen_home_spread'])} | "
            f"{safe(g['frozen_total'])} | {safe(pv2.get('ats'))} | "
            f"{safe(pv2.get('total'))} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- All returns assume **−110 odds** for every tracked game with a frozen market line. "
        "Pushes are refunded, and are included in the denominator of ROI.",
        "- Models v3/v4 were added after some early-season games had already been frozen; "
        "**—** means no genuinely frozen selection, not a loss or a missing result.",
        "- Untracked completed games and invalid records are disclosed, never credited as wins or losses.",
        "- This is a short-sample research record. Results do not establish positive expected value.",
        "",
        "[Upcoming projections, projected scores and ATS/totals leans](PROJECTIONS.md) · "
        "[Machine-readable review](performance_report.json) · "
        "[Full threshold scorecard](season_results.json) · "
        "[Original frozen games](frozen/) · [Weekly audit](graded/)",
        "",
    ]
    return "\n".join(lines)
