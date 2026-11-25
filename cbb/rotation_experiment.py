"""Evaluate player rotation research features on identical chronological seasons.

Four independent historical variants:
  player_v2       roster prior + team efficiency
  player_opp_v3   roster prior + team + opponent-adjusted efficiency
  player_rot_v4   roster prior + team + past-game player rotation
  player_all_v4   roster prior + team + opponent + past-game rotation

No model is promoted to prospective captures by this script. All train
seasons strictly precede the evaluated season, and all player observations
are only from previous days. This is *retrospective* not verified pregame
injury data, and odds histories do not include as-of timestamp guarantees.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from cbb.cli import save
from cbb.engine import choose_lines, grade, pregame_rows
from cbb.ingest import load_seasons
from cbb.opponent_adjusted import ADJ_FEATURES, attach_adjustments, pregame_opponent_adjustments
from cbb.opponent_experiment import fitted_predictions
from cbb.player_adjusted import PLAYER_FEATURES, extend_rows, player_predictions, roster_priors
from cbb.player_ingest import load_player_inputs
from cbb.rotation_features import ROTATION_FEATURES, attach_rotations, pregame_rotation_features
from cbb.rotation_ingest import load_player_boxes


def coverage_audit(games: list[dict], boxes: list[dict], test_seasons: list[int]):
    lookup = {(str(b["gameId"]), str(b["teamId"])) for b in boxes}
    by_season = defaultdict(lambda: [0, 0])
    for g in games:
        if g.get("status") != "final" or int(g.get("season") or 0) not in test_seasons:
            continue
        season = int(g["season"])
        for side in ("home", "away"):
            team = g.get(side + "TeamId")
            if team is None:
                continue
            by_season[season][1] += 1
            by_season[season][0] += (str(g["id"]), str(team)) in lookup
    for season, (matched, total) in sorted(by_season.items()):
        ratio = matched / total if total else 0
        print("ROTATION_COVERAGE", {
            "season": season, "team_game_boxes": matched,
            "final_team_games": total, "coverage": round(ratio, 4)
        })
        if ratio < 0.75:
            raise ValueError(
                f"Insufficient game-player box coverage {season}: {ratio:.1%}"
            )
    return by_season


def execute(args):
    data = load_seasons(args.seasons, args.raw_dir)
    game_boxes = load_player_boxes(args.seasons, args.rotation_dir)
    coverage_audit(data["games"], game_boxes, args.test_seasons)

    base = pregame_rows(data["games"], data["boxes"])
    odds = choose_lines(data["lines"])
    roster_priors_by_team, roster_coverage = roster_priors(
        load_player_inputs(args.seasons, args.raw_dir)
    )
    player = extend_rows(base, data["games"], roster_priors_by_team)
    opp = pregame_opponent_adjustments(data["games"], data["boxes"])
    player_opp = attach_adjustments(player, opp)

    player_rotation = pregame_rotation_features(data["games"], game_boxes)
    rot = attach_rotations(player, player_rotation)
    both = attach_adjustments(rot, opp)

    out = Path(args.out_dir)
    save(out / "roster_coverage.csv", roster_coverage)
    summary = []
    variants = (
        ("player_v2", player, PLAYER_FEATURES),
        ("player_opp_v3", player_opp, PLAYER_FEATURES + ADJ_FEATURES),
        ("player_rot_v4", rot, PLAYER_FEATURES + ROTATION_FEATURES),
        ("player_all_v4", both, PLAYER_FEATURES + ADJ_FEATURES + ROTATION_FEATURES),
    )
    for season in args.test_seasons:
        expected_ids = None
        for name, features, columns in variants:
            if name == "player_v2":
                predictions = player_predictions(features, season, odds)
            else:
                predictions = fitted_predictions(
                    features, season, odds, columns, 250, name
                )
            ids = [g["id"] for g in predictions]
            if len(set(ids)) != len(ids):
                raise ValueError(f"Duplicate game predictions for {name}/{season}")
            if expected_ids is None:
                expected_ids = set(ids)
            elif set(ids) != expected_ids:
                raise ValueError(f"Inconsistent game samples for {name}/{season}")
            completed = [r for r in predictions if r["status"] == "final"]
            save(out / f"{name}_{season}.csv", completed)
            for kind in ("ats", "total"):
                for threshold in (0, 2.5, 3.5, 4.5, 5.5):
                    grade_row = {
                        "season": season, "model": name,
                        **grade(completed, threshold, kind)
                    }
                    summary.append(grade_row)
                    if threshold in (0, 3.5):
                        print("ROTATION_RESULT", grade_row)

    save(out / "rotation_v4_comparison.csv", summary)
    for name, _, _ in variants:
        for kind in ("ats", "total"):
            grouped = [r for r in summary
                       if r["model"] == name and r["market"] == kind
                       and r["threshold"] == 0]
            w = sum(r["wins"] for r in grouped)
            l = sum(r["losses"] for r in grouped)
            p = sum(r["pushes"] for r in grouped)
            n = w + l + p
            print("ROTATION_AGGREGATE", {
                "model": name, "market": kind,
                "wins": w, "losses": l, "pushes": p,
                "win_pct": round(w / (w+l) * 100, 2) if (w+l) else None,
                "roi_minus_110_pct": round((w*100/110-l)/n*100, 2) if n else None,
            })
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int,
                    default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--test-seasons", nargs="+", type=int,
                    default=[2024, 2025, 2026])
    ap.add_argument("--raw-dir", default="cbb/data/raw")
    ap.add_argument("--rotation-dir", default="cbb/data/rotation")
    ap.add_argument("--out-dir", default="cbb/outputs/rotation_v4")
    args = ap.parse_args()
    execute(args)


if __name__ == "__main__":
    main()
