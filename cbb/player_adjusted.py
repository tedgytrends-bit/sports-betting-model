"""Player-adjusted CBB model with strict previous-season player performance.

Historical rosters are retrospectively retrieved, not timestamped preseason
snapshots. This is a research approximation; DO NOT label it point-in-time
verified until archival rosters/transfer timestamps have been validated.
"""
from collections import defaultdict
from math import exp
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from cbb.engine import FEATURES, number


PRIORS = (
    "return_minutes_share", "incoming_minutes_share", "known_minutes_share",
    "prior_offense", "prior_defense", "prior_scoring", "prior_winshares",
    "prior_usage", "recruit_stars", "elite_freshmen", "transfer_count",
    "matched_players", "eligible_players", "portal_verified",
)
PLAYER_FEATURES = FEATURES + tuple(side + "_" + col for side in ("home","away") for col in PRIORS)


def eligible(player, season):
    """CBBD affiliations use ENDING-year season IDs (e.g. 2026=2025-26).

    Cross-checked 2025 and 2026 roster cohorts against actual same-season
    individual box scores: startSeason==season players are genuine current-
    season participants, including transfers and freshmen. Exclude only
    those starting AFTER target season or ending BEFORE target season.
    Historical membership is retrospective and not a pregame timestamp.
    """
    first, last = number(player.get("startSeason")), number(player.get("endSeason"))
    return first is not None and last is not None and first <= season <= last


def normalized(s):
    return "".join(c for c in str(s or "").casefold() if c.isalnum())


def _previous_stats(data):
    by_id = {}
    by_source = {}
    team_minutes = defaultdict(float)
    for row in data:
        mid = number(row.get("minutes")) or 0
        team_id = row.get("teamId")
        if team_id is not None and mid > 0:
            team_minutes[str(team_id)] += mid
        if mid < 25 or (number(row.get("games")) or 0) < 2:
            continue
        for index, value in ((by_id, row.get("athleteId")),
                             (by_source, row.get("athleteSourceId"))):
            if value is None:
                continue
            value = str(value)
            if value not in index or (number(index[value].get("minutes")) or 0) < mid:
                index[value] = row
    return by_id, by_source, team_minutes


def _team_prior(roster, season, previous, portal, recruits):
    team_id = str(roster["teamId"])
    selected = {}
    for player in roster.get("players") or []:
        if not eligible(player, season):
            continue
        identifier = player.get("id")
        if identifier is None:
            continue
        selected[str(identifier)] = player
    players = list(selected.values())
    by_id, by_source, prev_team_minutes = previous
    # Recruiting class is the calendar year before the season ending year.
    team_recruits = {}
    for r in recruits:
        dest = r.get("committedTo") or {}
        if str(dest.get("id")) != team_id or number(r.get("year")) != season - 1:
            continue
        pkey = str(r["athleteId"]) if r.get("athleteId") is not None else None
        if pkey:
            team_recruits[pkey] = r
        else:
            team_recruits["name:" + normalized(r.get("name"))] = r
    portal_names = set()
    for r in portal:
        dest = r.get("destination") or {}
        if str(dest.get("id")) == team_id and number(r.get("year")) == season - 1:
            portal_names.add(normalized((r.get("firstName") or "") + " " + (r.get("lastName") or "")))

    known = []
    returning = incoming = 0.0
    stars = 0.0
    elite = 0
    verified_portal = 0
    freshman_ids = set()
    for player in players:
        player_id = str(player["id"])
        rec = team_recruits.get(player_id) or team_recruits.get("name:" + normalized(player.get("name")))
        if rec and player_id not in freshman_ids:
            freshman_ids.add(player_id)
            rating = number(rec.get("stars")) or 0
            stars += min(max(rating - 2.0, 0.0), 3.0)
            elite += int(rating >= 4)
        stats = by_id.get(player_id)
        if stats is None and player.get("sourceId") is not None:
            stats = by_source.get(str(player["sourceId"]))
        if stats is None:
            continue
        if stats.get("athleteSourceId") and player.get("sourceId") and str(stats["athleteSourceId"]) != str(player["sourceId"]):
            continue
        minutes = number(stats.get("minutes")) or 0
        if minutes <= 0:
            continue
        minutes = min(minutes, 1350)
        prior_team = str(stats.get("teamId"))
        if prior_team == team_id:
            returning += minutes
        else:
            incoming += minutes
            if normalized(player.get("name")) in portal_names:
                verified_portal += 1
        known.append((stats, minutes))

    weighted = sum(minutes for _, minutes in known)
    def mean(key, default=0, minimum=-1e4, maximum=1e4):
        if not weighted:
            return default
        return sum(min(max(number(s.get(key)) if number(s.get(key)) is not None else default, minimum), maximum) * mins
                   for s, mins in known) / weighted

    # Count only rostered players and use archived past-season performance.
    total_points = sum((number(x.get("points")) or 0) for x,_ in known)
    raw_minutes = sum((number(x.get("minutes")) or 0) for x,_ in known)
    scoring = 40 * total_points / max(raw_minutes, 1)
    prior_total = prev_team_minutes.get(team_id, 0)
    return {
        "return_minutes_share": min(returning / max(prior_total, 1), 1.2),
        "incoming_minutes_share": min(incoming / 6000, 1.2),
        "known_minutes_share": min(weighted / 6000, 1.5),
        "prior_offense": mean("offensiveRating", 100, 60, 150) - 100,
        "prior_defense": mean("defensiveRating", 100, 60, 150) - 100,
        "prior_scoring": min(scoring, 32) - 12 if known else 0,
        "prior_winshares": mean("PORPAG", 0, -5, 10),
        "prior_usage": mean("usage", 20, 5, 45) - 20,
        "recruit_stars": min(stars, 18),
        "elite_freshmen": min(elite, 6),
        "transfer_count": sum(1 for s,_ in known if str(s.get("teamId")) != team_id),
        "matched_players": len(known),
        "eligible_players": len(players),
        "portal_verified": verified_portal,
    }


def roster_priors(seasons_inputs):
    """Keyed by (season, team ID), never by potentially ambiguous team name."""
    all_data={}
    coverage=[]
    for season, data in sorted(seasons_inputs.items()):
        prior_index = _previous_stats(data["prior_players"])
        grouped=defaultdict(lambda: {"teamId": None, "players": []})
        for entry in data["rosters"]:
            if int(number(entry.get("season")) or 0) != season or entry.get("teamId") is None:
                continue
            team_id=str(entry["teamId"])
            grouped[team_id]["teamId"]=team_id
            grouped[team_id]["players"].extend(entry.get("players") or [])
        for team_id, roster in grouped.items():
            pr=_team_prior(roster,season,prior_index,data["portal"],data["recruits"])
            all_data[(season,team_id)]=pr
            coverage.append({"season":season,"team_id":team_id,**pr})
    return all_data,coverage


def extend_rows(rows, games, priors):
    games_by_id={str(g["id"]):g for g in games}
    out=[]
    for r in rows:
        g=games_by_id[r["id"]]
        values={}
        for side in ("home","away"):
            tid=g.get(side+"TeamId")
            prior=priors.get((r["season"],str(tid)), {})
            # Prior-season signal fades as fresh games accumulate.
            age=int(r[side+"_games"])
            weight=exp(-age / 12)
            for feature in PRIORS:
                values[side+"_"+feature]=round(float(prior.get(feature, 0))*weight, 6)
        out.append({**r,**values})
    return out


def player_predictions(rows, season, odds):
    training=[r for r in rows if r["season"]<season and r["home_points"] is not None and r["away_points"] is not None]
    testing=[r for r in rows if r["season"]==season]
    if len(training)<30:
        raise ValueError(f"Insufficient prior training games for {season}")
    if not testing:
        return []
    x=np.array([[r[k] for k in PLAYER_FEATURES] for r in training],dtype=float)
    xx=np.array([[r[k] for k in PLAYER_FEATURES] for r in testing],dtype=float)
    outputs=[]
    for outcome in ("margin","total"):
        ys=np.array([r["home_points"]-r["away_points"] if outcome=="margin" else r["home_points"]+r["away_points"] for r in training])
        model=make_pipeline(StandardScaler(), Ridge(alpha=250))
        model.fit(x,ys)
        outputs.append(model.predict(xx))
    rows_out=[]
    for r,margin,total in zip(testing,*outputs):
        line=odds.get(r["id"],{})
        spread,market_total=line.get("home_spread"),line.get("market_total")
        edge=float(margin)+spread if spread is not None else None
        tedge=float(total)-market_total if market_total is not None else None
        rows_out.append({**r,**line,"model":"player_v2",
            "training_games":len(training),
            "projected_margin_home":round(float(margin),3),
            "projected_total":round(float(total),3),
            "projected_home_points":round(float((total+margin)/2),2),
            "projected_away_points":round(float((total-margin)/2),2),
            "ats_edge":round(edge,3) if edge is not None else None,
            "total_edge":round(tedge,3) if tedge is not None else None,
            "ats_lean":("home" if edge>0 else "away" if edge<0 else "none") if edge is not None else "",
            "total_lean":("over" if tedge>0 else "under" if tedge<0 else "none") if tedge is not None else ""})
    return rows_out
