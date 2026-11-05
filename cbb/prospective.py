"""Real pre-tip 2026-27 CBB projection captures; research shadow only.

Never synthesize past "official" picks from history. Freeze only from an
observed UTC snapshot at least one minute BEFORE the actual scheduled tip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cbb.engine import choose_lines, pregame_rows, predict
from cbb.ingest import load_seasons
from cbb.player_adjusted import PLAYER_FEATURES, roster_priors, extend_rows, player_predictions
from cbb.opponent_adjusted import ADJ_FEATURES, attach_adjustments, pregame_opponent_adjustments
from cbb.opponent_experiment import fitted_predictions
from cbb.player_ingest import load_player_inputs
from cbb.rotation_features import ROTATION_FEATURES, pregame_rotation_features, attach_rotations
from cbb.rotation_ingest import load_player_boxes
from cbb.live_rotation import load_live_player_boxes


def utc_date(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp must include UTC offset: {value}")
    return dt.astimezone(timezone.utc)


def model_fields(row: dict) -> dict:
    return {name: row.get(name) for name in (
        "projected_margin_home", "projected_total",
        "projected_home_points", "projected_away_points",
        "ats_edge", "total_edge", "ats_lean", "total_lean",
        "training_games",
    )}


def source_digests(root: str, season: int) -> dict:
    folder = Path(root) / str(season)
    paths = ("games.json", "boxes.json", "lines.json", "rosters.json",
             "prior_players.json", "portal.json", "recruits.json")
    digest = {}
    for name in paths:
        item = folder / name
        if not item.exists():
            raise FileNotFoundError(f"Missing source snapshot: {item}")
        digest[name] = hashlib.sha256(item.read_bytes()).hexdigest()
    return digest


def build_capture(
    baseline: list[dict],
    player: list[dict],
    games: list[dict],
    priors: dict,
    captured_utc: datetime,
    season: int = 2027,
    horizon_days: int = 8,
    freeze_hours: int = 24,
    fingerprints: dict | None = None,
    model_commit: str = "",
    opponent_player: list[dict] | None = None,
    rotation_player: list[dict] | None = None,
    combined_player: list[dict] | None = None,
) -> dict:
    """Pure function: future-only, timestamped, one immutable candidate/game."""
    if captured_utc.tzinfo is None:
        raise ValueError("Captured timestamp must be timezone-aware")
    now = captured_utc.astimezone(timezone.utc)
    by_baseline = {r["id"]: r for r in baseline}
    by_player = {r["id"]: r for r in player}
    by_opponent = None if opponent_player is None else {r["id"]: r for r in opponent_player}
    optional = {
        "player_rot_v4": rotation_player,
        "player_all_v4": combined_player,
    }
    by_new_models = {}
    for label, forecasts in optional.items():
        if forecasts is None:
            continue
        indexed = {r["id"]: r for r in forecasts}
        if len(indexed) != len(forecasts) or set(indexed) != set(by_baseline):
            raise ValueError(f"{label} must cover exactly the same unique game IDs")
        by_new_models[label] = indexed
    if len(by_baseline) != len(baseline) or len(by_player) != len(player):
        raise ValueError("Duplicate game IDs in model outputs")
    if set(by_baseline) != set(by_player):
        raise ValueError("Player and baseline projections must cover the same games")
    if by_opponent is not None and (
        len(by_opponent) != len(opponent_player) or set(by_opponent) != set(by_baseline)
    ):
        raise ValueError("Opponent-adjusted player model must cover exactly the same game IDs")
    by_game = {str(g["id"]): g for g in games if int(g.get("season") or 0) == season}
    records = []
    for ident, b in by_baseline.items():
        if b.get("status") != "scheduled":
            continue
        tip = utc_date(b["start_date"])
        # Critical guard: CBBD has sometimes returned past games still marked "scheduled".
        if tip <= now + timedelta(minutes=1) or tip > now + timedelta(days=horizon_days):
            continue
        g = by_game.get(ident)
        if g is None:
            raise ValueError(f"Projected game {ident} absent in game source")
        p = by_player[ident]
        if g.get("status") != "scheduled":
            continue
        provider = b.get("provider") or p.get("provider")
        home_spread = b.get("home_spread")
        market_total = b.get("market_total")
        home_id = str(g.get("homeTeamId")) if g.get("homeTeamId") is not None else ""
        away_id = str(g.get("awayTeamId")) if g.get("awayTeamId") is not None else ""
        home_prior = priors.get((season, home_id), {})
        away_prior = priors.get((season, away_id), {})
        record = {
            "id": ident,
            "season": season,
            "tip_utc": tip.isoformat().replace("+00:00", "Z"),
            "away": b["away"], "home": b["home"],
            "away_team_id": away_id, "home_team_id": home_id,
            "neutral_site": bool(b.get("neutral")),
            "market": {
                "provider": provider, "home_spread": home_spread,
                "total": market_total,
                "as_of_utc": now.isoformat().replace("+00:00", "Z"),
            },
            "baseline": model_fields(b),
            "player_v2": model_fields(p),
            "coverage": {
                "home_prior_matched": int(home_prior.get("matched_players", 0)),
                "away_prior_matched": int(away_prior.get("matched_players", 0)),
                "home_roster_eligible": int(home_prior.get("eligible_players", 0)),
                "away_roster_eligible": int(away_prior.get("eligible_players", 0)),
                "home_verified_portal": int(home_prior.get("portal_verified", 0)),
                "away_verified_portal": int(away_prior.get("portal_verified", 0)),
                "home_elite_recruits": int(home_prior.get("elite_freshmen", 0)),
                "away_elite_recruits": int(away_prior.get("elite_freshmen", 0)),
                "home_games_played": int(b.get("home_games", 0)),
                "away_games_played": int(b.get("away_games", 0)),
            },
        }
        # v3 is an optional *new-capture-only* research shadow.
        # NEVER add it retroactively to existing immutable frozen games.
        if by_opponent is not None:
            record["player_opp_v3"] = model_fields(by_opponent[ident])
        for label, indexed in by_new_models.items():
            record[label] = model_fields(indexed[ident])
        if "player_rot_v4" in by_new_models:
            from_row = by_new_models["player_rot_v4"][ident]
            record["rotation_coverage"] = {
                side: {
                    "past_game_boxes": int(from_row.get(side + "_rotation_source_games", 0)),
                    "box_coverage": from_row.get(side + "_rotation_box_coverage"),
                    "last_box_present": bool(from_row.get(side + "_rotation_last_box_present")),
                    "prior_key_minutes_missing":
                        from_row.get(side + "_rotation_key_minutes_missing"),
                }
                for side in ("home", "away")
            }
        cov = record["coverage"]
        record["research_quality"] = (
            "adequate"
            if (cov["home_prior_matched"] >= 3 or cov["home_games_played"] >= 5)
            and (cov["away_prior_matched"] >= 3 or cov["away_games_played"] >= 5)
            else "limited"
        )
        hours_until_tip = (tip - now).total_seconds() / 3600
        record["freeze_candidate"] = (
            hours_until_tip <= freeze_hours
            and (home_spread is not None or market_total is not None)
        )
        records.append(record)
    records.sort(key=lambda x: (x["tip_utc"], x["id"]))
    return {
        "capture_version": 1,
        "season": season,
        "capture_utc": now.isoformat().replace("+00:00", "Z"),
        "capture_type": "research_shadow",
        "model_commit": model_commit,
        "source": "CollegeBasketballData API as received at capture time",
        "source_sha256": fingerprints or {},
        "freeze_window_hours": freeze_hours,
        "games": records,
        "counts": {
            "upcoming": len(records),
            "with_ats_line": sum(g["market"]["home_spread"] is not None for g in records),
            "with_total_line": sum(g["market"]["total"] is not None for g in records),
            "freeze_candidates": sum(g["freeze_candidate"] for g in records),
            "quality_limited": sum(g["research_quality"] == "limited" for g in records),
        },
    }


def run(args):
    seasons = list(range(2022, args.season + 1))
    data = load_seasons(seasons, args.raw_dir)
    rows = pregame_rows(data["games"], data["boxes"])
    lines = choose_lines(data["lines"])
    priors, _ = roster_priors(load_player_inputs(seasons, args.raw_dir))
    enriched = extend_rows(rows, data["games"], priors)
    opponent_features = pregame_opponent_adjustments(data["games"], data["boxes"])
    v3_rows = attach_adjustments(enriched, opponent_features)
    v3_predictions = fitted_predictions(
        v3_rows, args.season, lines, PLAYER_FEATURES + ADJ_FEATURES, 250,
        "player_opp_v3",
    )
    # The historical player boxes are only training data. The current season
    # archive is built and timestamped by the preceding live capture step.
    rotation_boxes = (
        load_player_boxes(seasons[:-1], root=args.rotation_history_dir)
        + load_live_player_boxes(args.season, root=args.rotation_live_dir)
    )
    rotation_map = pregame_rotation_features(data["games"], rotation_boxes)
    rotation_rows = attach_rotations(enriched, rotation_map)
    rotation_plus_opp = attach_adjustments(rotation_rows, opponent_features)
    v4_rotation = fitted_predictions(
        rotation_rows, args.season, lines, PLAYER_FEATURES + ROTATION_FEATURES,
        250, "player_rot_v4",
    )
    v4_all = fitted_predictions(
        rotation_plus_opp, args.season, lines,
        PLAYER_FEATURES + ADJ_FEATURES + ROTATION_FEATURES,
        250, "player_all_v4",
    )
    captured = datetime.now(timezone.utc)
    fingerprints = source_digests(args.raw_dir, args.season)
    live_archive = Path(args.rotation_live_dir) / f"{args.season}_game_players.json.gz"
    fingerprints["live_game_players_gzip"] = hashlib.sha256(live_archive.read_bytes()).hexdigest()
    for history_season in seasons[:-1]:
        history_archive = Path(args.rotation_history_dir) / f"{history_season}_game_players.json.gz"
        fingerprints[f"historical_game_players_{history_season}_gzip"] = (
            hashlib.sha256(history_archive.read_bytes()).hexdigest()
        )
    board = build_capture(
        baseline=predict(rows, args.season, lines),
        player=player_predictions(enriched, args.season, lines),
        games=data["games"], priors=priors,
        captured_utc=captured, season=args.season,
        horizon_days=args.horizon_days, freeze_hours=args.freeze_hours,
        fingerprints=fingerprints,
        model_commit=os.getenv("GITHUB_SHA", ""),
        opponent_player=v3_predictions,
        rotation_player=v4_rotation,
        combined_player=v4_all,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    print("CBB_SNAPSHOT_CAPTURE", json.dumps({
        "time": board["capture_utc"], **board["counts"], "output": str(out),
    }))
    return board


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2027)
    ap.add_argument("--horizon-days", type=int, default=8)
    ap.add_argument("--freeze-hours", type=int, default=24)
    ap.add_argument("--raw-dir", default="cbb/data/raw")
    ap.add_argument("--rotation-history-dir", default="cbb/data/rotation")
    ap.add_argument("--rotation-live-dir", default="cbb/data/rotation_live")
    ap.add_argument("--out", default="cbb/outputs/prospective/latest_capture.json")
    args = ap.parse_args()
    if args.horizon_days < 1 or not 1 <= args.freeze_hours <= 72:
        raise ValueError("Invalid capture horizon")
    run(args)


if __name__ == "__main__":
    main()
