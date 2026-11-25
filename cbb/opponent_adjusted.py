"""Pregame-only opponent-adjusted college basketball efficiencies.

For each calendar day, ratings are inferred from games ending on *prior*
calendar dates only. All games played on a date receive the same frozen
prior-day ratings; no same-day result may influence another game.

For each past game, team offensive efficiency is observed points / possessions
x100. Opponent offense/defense effects are deconvolved using a shrinkage
fixed-point iteration fit only to previous games of that season.

This is an experimental research feature, not a market beating claim.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite

from cbb.engine import key, number, possessions

BASE_EFF = 100.0
BASE_PACE = 69.0
SHRINK_GAMES = 6.0
ITERATIONS = 5

ADJ_FEATURES = (
    "home_adj_off", "home_adj_def", "home_adj_pace", "home_adj_net",
    "home_opponent_net",
    "away_adj_off", "away_adj_def", "away_adj_pace", "away_adj_net",
    "away_opponent_net",
)


def _clamp(value: float, low: float, high: float) -> float:
    if not isfinite(value):
        raise ValueError("Non-finite adjusted rating")
    return min(high, max(low, value))


def fit_ratings(observations: dict) -> dict:
    """Fit ratings to completed observations available at evaluation time.

    observation: (opponent_id, points_per_100, points_allowed_per_100, pace)
    """
    base = (BASE_EFF, BASE_EFF, BASE_PACE)
    ratings = {team: base for team in observations}
    for _ in range(ITERATIONS):
        next_ratings = {}
        for team, obs in observations.items():
            if not obs:
                next_ratings[team] = base
                continue
            off_sum = def_sum = pace_sum = 0.0
            for opponent, offense, defense, pace in obs:
                opp_off, opp_def, opp_pace = ratings.get(opponent, base)
                off_sum += offense - (opp_def - BASE_EFF)
                def_sum += defense - (opp_off - BASE_EFF)
                pace_sum += pace - 0.5 * (opp_pace - BASE_PACE)
            n = SHRINK_GAMES + len(obs)
            next_ratings[team] = (
                _clamp((BASE_EFF * SHRINK_GAMES + off_sum) / n, 55, 160),
                _clamp((BASE_EFF * SHRINK_GAMES + def_sum) / n, 55, 160),
                _clamp((BASE_PACE * SHRINK_GAMES + pace_sum) / n, 48, 100),
            )
        ratings = next_ratings
    return ratings


def _schedule_net(team: str, observations: dict, ratings: dict) -> float:
    seen = observations.get(team) or []
    if not seen:
        return 0.0
    opponents = set(opponent for opponent, _, _, _ in seen)
    values = [ratings[opponent][0] - ratings[opponent][1]
              for opponent in opponents if opponent in ratings]
    return sum(values) / len(values) if values else 0.0


def pregame_opponent_adjustments(games: list[dict], boxes: list[dict] | None = None) -> dict[str, dict]:
    """Return feature mapping by game ID, never using a current/future result."""
    lookup = {(str(b.get("gameId")), str(b.get("teamId") or b.get("team"))): b
              for b in (boxes or [])}
    by_day: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for g in games:
        if g.get("status") in ("final", "scheduled"):
            by_day[(int(g["season"]), str(g["startDate"])[:10])].append(g)

    output = {}
    observed: dict[str, list] = defaultdict(list)
    current_season = None

    for (season, _), todays_games in sorted(by_day.items()):
        if current_season != season:
            observed = defaultdict(list)
            current_season = season
        ratings = fit_ratings(observed)
        for g in todays_games:
            ident = str(g["id"])
            if ident in output:
                raise ValueError(f"Duplicate game ID in opponent features: {ident}")
            features = {}
            for side in ("home", "away"):
                team = key(g, side)
                off, defense, pace = ratings.get(team, (BASE_EFF, BASE_EFF, BASE_PACE))
                features[side + "_adj_off"] = off
                features[side + "_adj_def"] = defense
                features[side + "_adj_pace"] = pace
                features[side + "_adj_net"] = off - defense
                features[side + "_opponent_net"] = _schedule_net(team, observed, ratings)
            output[ident] = features

        # Apply all completed results only AFTER every game's feature freeze.
        for g in todays_games:
            if g.get("status") != "final":
                continue
            hp, ap = number(g.get("homePoints")), number(g.get("awayPoints"))
            if hp is None or ap is None:
                continue
            hid, aid = key(g, "home"), key(g, "away")
            hbox = lookup.get((str(g["id"]), hid))
            abox = lookup.get((str(g["id"]), aid))
            poss = (possessions(hbox) + possessions(abox)) / 2
            home_off = _clamp(100 * hp / poss, 40, 180)
            away_off = _clamp(100 * ap / poss, 40, 180)
            observed[hid].append((aid, home_off, away_off, poss))
            observed[aid].append((hid, away_off, home_off, poss))
    return output


def attach_adjustments(rows: list[dict], adjustments: dict[str, dict]) -> list[dict]:
    out = []
    for row in rows:
        feats = adjustments.get(row["id"])
        if feats is None:
            raise ValueError(f"Missing opponent adjustments for {row['id']}")
        if any(k not in feats for k in ADJ_FEATURES):
            raise ValueError(f"Missing opponent features for {row['id']}")
        out.append({**row, **feats})
    return out
