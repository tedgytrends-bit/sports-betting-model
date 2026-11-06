"""Grade final 2026-27 games ONLY against earlier, immutable frozen snapshots.

This is a research shadow ledger, not the user's wagers. A game without a
genuine pre-tip freeze is permanently marked untracked, never backfilled.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from cbb.engine import number
from cbb.prospective import utc_date
from cbb.prospective_publish import GitHubStore

FIRST_CAPTURE_UTC = utc_date("2026-11-05T21:29:14.641689Z")
THRESHOLDS = (0, 2.5, 3.5, 4.5, 5.5)
MODELS = ("baseline", "player_v2", "player_opp_v3", "player_rot_v4", "player_all_v4")


def iso_week(value: str) -> str:
    d = utc_date(value).date()
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def result_sign(value: float) -> str:
    return "W" if value > 0 else "L" if value < 0 else "P"


def grade_frozen(frozen: dict, final: dict) -> dict:
    captured = utc_date(frozen["capture_utc"])
    recorded = frozen["game"]
    scheduled_tip = utc_date(recorded["tip_utc"])
    final_tip = utc_date(final["startDate"])
    if final.get("status") != "final":
        raise ValueError("Refuse to grade non-final games")
    # Independently enforce genuine pre-tip observation. Do not trust a
    # historical "scheduled" flag or a later-revised game start time alone.
    if captured + timedelta(minutes=1) >= min(scheduled_tip, final_tip):
        raise ValueError("Frozen capture not before actual game tip")
    if str(recorded["id"]) != str(final["id"]):
        raise ValueError("Frozen ID doesn't match final score")
    hp, ap = number(final.get("homePoints")), number(final.get("awayPoints"))
    if hp is None or ap is None:
        raise ValueError("Final score missing")
    if str(final.get("homeTeamId")) != str(recorded.get("home_team_id")) or \
       str(final.get("awayTeamId")) != str(recorded.get("away_team_id")):
        raise ValueError("Team identities changed after freeze")
    actual_margin, actual_total = hp - ap, hp + ap
    line = recorded.get("market") or {}
    spread = number(line.get("home_spread"))
    total_line = number(line.get("total"))
    models = {}
    for name in MODELS:
        if name not in recorded and name not in ("baseline", "player_v2"):
            # Older frozen snapshots cannot be backfilled with newer models.
            continue
        p = recorded[name]
        am = p.get("ats_lean")
        tm = p.get("total_lean")
        ats = None
        under_over = None
        if spread is not None and am in ("home", "away"):
            delta = actual_margin + spread
            ats = result_sign(delta if am == "home" else -delta)
        if total_line is not None and tm in ("over", "under"):
            delta = actual_total - total_line
            under_over = result_sign(delta if tm == "over" else -delta)
        models[name] = {
            "ats_edge": number(p.get("ats_edge")),
            "total_edge": number(p.get("total_edge")),
            "ats": ats, "total": under_over,
            "margin_mae": round(abs(actual_margin - p["projected_margin_home"]), 3),
            "total_mae": round(abs(actual_total - p["projected_total"]), 3),
        }
    return {
        "id": str(final["id"]),
        "date": final_tip.date().isoformat(),
        "away": recorded.get("away"), "home": recorded.get("home"),
        "tip_utc": final_tip.isoformat().replace("+00:00", "Z"),
        "captured_utc": frozen["capture_utc"],
        "home_points": hp, "away_points": ap,
        "home_spread": spread, "market_total": total_line,
        "market_provider": line.get("provider"), "models": models,
        "source": "Frozen CBBD odds; hypothetical -110 stakes",
    }


def summarize(entries: list[dict], untracked: int) -> dict:
    summary = []
    for name in MODELS:
        for kind in ("ats", "total"):
            for cutoff in THRESHOLDS:
                decisions = []
                errors = []
                for g in entries:
                    model = g["models"].get(name)
                    if model is None:
                        # v3 intentionally absent from pre-deployment freezes.
                        continue
                    errors.append(model["margin_mae"] if kind == "ats" else model["total_mae"])
                    decision = model[kind]
                    edge = model["ats_edge"] if kind == "ats" else model["total_edge"]
                    if decision is None or edge is None or edge == 0 or abs(edge) < cutoff:
                        continue
                    decisions.append(decision)
                w, l, p = (decisions.count(z) for z in ("W", "L", "P"))
                n = len(decisions)
                summary.append({
                    "model": name, "market": kind, "threshold": cutoff,
                    "graded_games_with_model": sum(
                        name in g["models"] for g in entries
                    ),
                    "wins": w, "losses": l, "pushes": p, "tracked_leans": n,
                    "decided_win_pct": round(w / (w + l) * 100, 2) if w + l else None,
                    "roi_if_minus_110_pct": round((w * 100 / 110 - l) / n * 100, 2) if n else None,
                    "projection_mae": round(sum(errors) / len(errors), 3) if errors else None,
                })
    return {
        "record_type": "prospective_shadow_results",
        "season": 2027, "tracked_games": len(entries),
        "untracked_completed_games_since_first_capture": untracked,
        "grades": summary,
        "caution": "Hypothetical -110 returns, fixed frozen lines, not personal bets",
    }


def iso_weeks_between(start: date, end: date):
    """Enumerate EVERY touched ISO week, including partial first/last weeks.

    Previously anchored on the capture date's weekday (Thursday), which
    omitted the new ISO week until Thursday of the following week.
    """
    d = start - timedelta(days=start.weekday())
    while d <= end:
        year, week, _ = d.isocalendar()
        yield f"{year}-W{week:02d}"
        d += timedelta(days=7)


def execute(store: GitHubStore, data: list[dict], season: int = 2027) -> dict:
    root = f"cbb/prospective/{season}"
    eligible = defaultdict(list)
    for g in data:
        if g.get("status") != "final" or int(g.get("season") or 0) != season:
            continue
        try:
            tip = utc_date(g["startDate"])
        except (ValueError, TypeError, KeyError):
            continue
        if tip <= FIRST_CAPTURE_UTC:
            continue
        if number(g.get("homePoints")) is None or number(g.get("awayPoints")) is None:
            continue
        eligible[iso_week(g["startDate"])].append(g)
    # Only 1 GET per recorded week, and 1 frozen GET per newly final game.
    cached_weeks = {}
    new_grades, new_untracked, new_invalid = 0, 0, 0
    for week, games in sorted(eligible.items()):
        path = f"{root}/graded/{week}.json"
        journal = store.read_json(path) or {
            "week": week, "results": {}, "untracked": {}, "invalid": {}
        }
        changed = False
        for g in games:
            ident = str(g["id"])
            if ident in journal["results"] or ident in journal["untracked"] or ident in journal["invalid"]:
                continue
            frozen = store.read_json(f"{root}/frozen/{ident}.json")
            if frozen is None:
                journal["untracked"][ident] = "No pre-tip frozen observation"
                new_untracked += 1
            else:
                try:
                    journal["results"][ident] = grade_frozen(frozen, g)
                    new_grades += 1
                except (KeyError, TypeError, ValueError) as exc:
                    journal["invalid"][ident] = str(exc)
                    new_invalid += 1
            changed = True
        if changed:
            store.put_json(path, journal, immutable=False)
        cached_weeks[week] = journal

    all_entries = []
    untracked = 0
    invalid = 0
    today = datetime.now(timezone.utc).date()
    for week in iso_weeks_between(FIRST_CAPTURE_UTC.date(), today):
        journal = cached_weeks.get(week)
        if journal is None:
            journal = store.read_json(f"{root}/graded/{week}.json")
        if journal is None:
            continue
        all_entries.extend(journal.get("results", {}).values())
        untracked += len(journal.get("untracked", {}))
        invalid += len(journal.get("invalid", {}))
    summary = summarize(all_entries, untracked)
    summary["invalid_snapshots"] = invalid
    summary["updated_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary["newly_graded"] = new_grades
    summary["newly_untracked"] = new_untracked
    summary["newly_invalid"] = new_invalid
    store.put_json(f"{root}/season_results.json", summary, immutable=False)
    # Derived reports use ONLY the frozen-game grade journal above. They
    # never inspect new live prices or retrain a prediction after tipoff.
    from cbb.performance_report import generate_performance_report

    review = generate_performance_report(
        all_entries, untracked, invalid,
        captured_utc=datetime.now(timezone.utc),
    )
    store.put_json(f"{root}/performance_report.json", review, immutable=False)
    from cbb.readable_report import render_markdown

    store.put_text(f"{root}/README.md", render_markdown(review), immutable=False)
    print("CBB_PERFORMANCE_REPORT", json.dumps({
        "tracked_total": review["tracked_games"],
        "last_48h": review["last_48_hours"]["tracked_games"],
        "last_7d": review["last_7_days"]["tracked_games"],
        "daily_dates": len(review["daily_by_central_date"]),
        "as_of_utc": review["as_of_utc"],
        "path": f"{root}/performance_report.json",
    }))
    print("CBB_GRADE_RESULTS", json.dumps({
        "tracked_total": len(all_entries), "new_grades": new_grades,
        "untracked_total": untracked, "invalid": invalid,
        "season_results_path": f"{root}/season_results.json",
    }))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2027)
    ap.add_argument("--raw-dir", default="cbb/data/raw")
    args = ap.parse_args()
    folder = Path(args.raw_dir) / str(args.season) / "games.json"
    games = json.loads(folder.read_text(encoding="utf-8"))
    store = GitHubStore(
        os.getenv("GITHUB_REPOSITORY"),
        os.getenv("CBB_PUBLISH_BRANCH", "cbb-prospective"),
        os.getenv("GITHUB_TOKEN"),
    )
    execute(store, games, args.season)


if __name__ == "__main__":
    main()
