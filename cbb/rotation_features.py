"""Chronological, pregame-only player participation and rotation features.

Inputs are *completed past games' player box scores*, not this game's box.
Same-day scores, current-game starters, actual inactives and current minutes
are never features. A missing source box is UNKNOWN, not player absence.

The absence indicators measure recent missing minutes from established
contributors; they are NOT verified injuries or official inactive reports.
"""
from __future__ import annotations

from collections import defaultdict, deque

from cbb.engine import key, number

WINDOW = 8
RECENT = 5

METRICS = (
    "rotation_source_games",
    "rotation_box_coverage",
    "rotation_last_box_present",
    "rotation_top5_minutes_share",
    "rotation_top8_minutes_share",
    "rotation_players_10min",
    "rotation_starting_five_stability",
    "rotation_top5_scoring_share",
    "rotation_recent_points_per40",
    "rotation_usage_minus20",
    "rotation_player_net_efficiency",
    "rotation_key_minutes_missing",
    "rotation_key_usage_missing",
)
ROTATION_FEATURES = tuple(f"{side}_{metric}" for side in ("home", "away")
                          for metric in METRICS)


def _athlete_key(p: dict) -> str | None:
    ident = p.get("athleteId")
    if ident is not None:
        return f"athlete:{ident}"
    source = p.get("athleteSourceId")
    return f"source:{source}" if source else None


def _game_box(box: dict | None) -> dict | None:
    """Accept only sufficiently complete team participation distributions."""
    if not isinstance(box, dict) or not isinstance(box.get("players"), list):
        return None
    players = {}
    for p in box["players"]:
        ident = _athlete_key(p)
        mins = number(p.get("minutes"))
        if ident is None or mins is None or mins <= 0 or mins > 65:
            continue
        players[ident] = {
            "minutes": mins,
            "starter": p.get("starter") is True,
            "points": number(p.get("points")) or 0.0,
            "usage": number(p.get("usage")),
            "off": number(p.get("offensiveRating")),
            "def": number(p.get("defensiveRating")),
        }
    total_minutes = sum(p["minutes"] for p in players.values())
    starter_count = sum(p["starter"] for p in players.values())
    # CBBD usually records 200 team minutes (or >200 with OT).
    # Reject empty, truncated or structurally implausible box scores.
    if not 175 <= total_minutes <= 400 or not 4 <= starter_count <= 6:
        return None
    return {"players": players, "minutes_total": total_minutes}


def _mean(values: list[float], neutral: float = 0.0) -> float:
    return sum(values) / len(values) if values else neutral


def _features(prior_games: deque) -> dict:
    recent_history = list(prior_games)
    available = [x for x in recent_history if x is not None][-RECENT:]
    complete_n = len(available)
    coverage = sum(x is not None for x in recent_history) / len(recent_history) if recent_history else 0.0

    feats = {
        "rotation_source_games": min(complete_n, RECENT),
        "rotation_box_coverage": coverage,
        "rotation_last_box_present": int(bool(recent_history and recent_history[-1] is not None)),
        "rotation_top5_minutes_share": 0.0,
        "rotation_top8_minutes_share": 0.0,
        "rotation_players_10min": 0.0,
        "rotation_starting_five_stability": 0.0,
        "rotation_top5_scoring_share": 0.0,
        "rotation_recent_points_per40": 0.0,
        "rotation_usage_minus20": 0.0,
        "rotation_player_net_efficiency": 0.0,
        "rotation_key_minutes_missing": 0.0,
        "rotation_key_usage_missing": 0.0,
    }
    if not available:
        return feats

    by_player = defaultdict(lambda: {"minutes": 0.0, "points": 0.0,
                                    "weighted_usage": 0.0, "usage_minutes": 0.0,
                                    "net_eff": 0.0, "rating_minutes": 0.0})
    depth = []
    starts = []
    for box in available:
        depth.append(sum(p["minutes"] >= 10 for p in box["players"].values()))
        starters = {pid for pid, p in box["players"].items() if p["starter"]}
        starts.append(starters)
        for pid, p in box["players"].items():
            agg = by_player[pid]
            agg["minutes"] += p["minutes"]
            agg["points"] += p["points"]
            if p["usage"] is not None:
                agg["usage_minutes"] += p["minutes"]
                agg["weighted_usage"] += p["minutes"] * p["usage"]
            if p["off"] is not None and p["def"] is not None:
                agg["rating_minutes"] += p["minutes"]
                agg["net_eff"] += p["minutes"] * (p["off"] - p["def"])

    ranked = sorted(by_player.values(), key=lambda p: p["minutes"], reverse=True)
    total_minutes = sum(p["minutes"] for p in ranked)
    total_points = sum(p["points"] for p in ranked)
    usage_minutes = sum(p["usage_minutes"] for p in ranked)
    rating_minutes = sum(p["rating_minutes"] for p in ranked)
    stability = []
    for earlier, later in zip(starts, starts[1:]):
        union = earlier | later
        if union:
            stability.append(len(earlier & later) / len(union))

    feats.update({
        "rotation_top5_minutes_share": sum(p["minutes"] for p in ranked[:5]) / total_minutes,
        "rotation_top8_minutes_share": sum(p["minutes"] for p in ranked[:8]) / total_minutes,
        "rotation_players_10min": _mean(depth),
        "rotation_starting_five_stability": _mean(stability),
        "rotation_top5_scoring_share":
            sum(p["points"] for p in ranked[:5]) / total_points if total_points else 0.0,
        "rotation_recent_points_per40": 40 * total_points / total_minutes,
        "rotation_usage_minus20":
            sum(p["weighted_usage"] for p in ranked) / usage_minutes - 20
            if usage_minutes else 0.0,
        "rotation_player_net_efficiency":
            sum(p["net_eff"] for p in ranked) / rating_minutes
            if rating_minutes else 0.0,
    })

    # A key player "missing" is defined only from previous games; no access
    # to the current game. Must have been a meaningful, regular contributor.
    # Unknown preceding player-game data never counts as absence.
    if recent_history and recent_history[-1] is not None:
        earlier = [x for x in recent_history[-6:-1] if x is not None]
        if len(earlier) >= 3:
            incumbent = defaultdict(lambda: [0.0, 0, 0.0, 0.0])
            for game in earlier:
                for pid, p in game["players"].items():
                    entry = incumbent[pid]
                    entry[0] += p["minutes"]
                    entry[1] += 1
                    if p["usage"] is not None:
                        entry[2] += p["usage"] * p["minutes"]
                        entry[3] += p["minutes"]
            missing_minutes = missing_usage = 0.0
            recent_players = recent_history[-1]["players"]
            for pid, (minutes, appearances, usage_sum, usage_mins) in incumbent.items():
                average = minutes / len(earlier)
                if appearances < 2 or average < 18.0:
                    continue
                current_minutes = recent_players.get(pid, {}).get("minutes", 0)
                if current_minutes > 4:
                    continue
                missing_minutes += average
                weighted_usage = usage_sum / usage_mins if usage_mins else 20
                missing_usage += average * max(weighted_usage - 15, 0) / 20
            feats["rotation_key_minutes_missing"] = min(missing_minutes / 200, 0.75)
            feats["rotation_key_usage_missing"] = min(missing_usage / 200, 0.75)
    return feats


def pregame_rotation_features(
    games: list[dict], boxes: list[dict]
) -> dict[str, dict[str, float]]:
    """Feature map for all games. Every day's results applied only afterward."""
    lookup = {}
    for b in boxes:
        if b.get("gameId") is None or b.get("teamId") is None:
            raise ValueError("Malformed game-player box identity")
        ident = (str(b["gameId"]), str(b["teamId"]))
        if ident in lookup:
            raise ValueError(f"Duplicate rotation team-game box: {ident}")
        lookup[ident] = _game_box(b)

    by_day = defaultdict(list)
    for g in games:
        if g.get("status") in ("final", "scheduled"):
            by_day[(int(g["season"]), str(g["startDate"])[:10])].append(g)

    state = defaultdict(lambda: deque(maxlen=WINDOW))
    output = {}
    last_season = None
    for (season, _), todays in sorted(by_day.items()):
        if season != last_season:
            state = defaultdict(lambda: deque(maxlen=WINDOW))
            last_season = season
        for game in todays:
            ident = str(game["id"])
            if ident in output:
                raise ValueError(f"Duplicate game ID in rotation features: {ident}")
            values = {}
            for side in ("home", "away"):
                team_id = key(game, side)
                snapshot = _features(state[team_id])
                values.update({f"{side}_{label}": val for label, val in snapshot.items()})
            output[ident] = values
        # Freeze every game first, THEN apply today's completed participation.
        for game in todays:
            if game.get("status") != "final":
                continue
            for side in ("home", "away"):
                team_id = key(game, side)
                state[team_id].append(lookup.get((str(game["id"]), team_id)))
    return output


def attach_rotations(rows: list[dict], rotation: dict[str, dict]) -> list[dict]:
    out = []
    for row in rows:
        values = rotation.get(str(row["id"]))
        if values is None or any(k not in values for k in ROTATION_FEATURES):
            raise ValueError(f"Incomplete rotation features for game {row['id']}")
        out.append({**row, **values})
    return out
