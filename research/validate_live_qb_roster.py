"""Fail-closed current-week QB availability guard using the public nflverse roster.

This checks ACTIVE ROSTER status, not who will start. Starting-QB identity
still requires a separately documented contemporary source/roster crosscheck.
Unlike weekly practice injury reports, the roster explicitly contains
RES/IR-type unavailable players. No bookmaker or paid injury API is used.

Call this on *new current-week* pregame forecasts. Do not call retrospectively
to modify a previously frozen prospectively published prediction.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata

import pandas as pd
import requests


def _norm(name:object)->str:
    s=unicodedata.normalize("NFKD",str(name)).encode("ascii","ignore").decode().lower()
    s=re.sub(r"[^a-z0-9 ]","",s)
    s=re.sub(r"\b(jr|ii|iii|iv|sr)\b","",s)
    return " ".join(s.split())


def fetch_roster(season:int, *,timeout:int=55)->tuple[pd.DataFrame,str,str]:
    if not 2020<=season<=2100:
        raise ValueError("Unsupported roster season")
    url=f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.csv"
    response=requests.get(url,timeout=timeout)
    response.raise_for_status()
    payload=response.content
    if len(payload)<1000:
        raise ValueError("Roster download too small to trust")
    return pd.read_csv(io.BytesIO(payload),low_memory=False),url,hashlib.sha256(payload).hexdigest()


def enforce_active_roster_qbs(qb_board:pd.DataFrame, roster:pd.DataFrame, *,season:int,week:int)->pd.DataFrame:
    """Block RES/CUT/SUS/unknown selected QBs even if older PBP suggests them.

    Must have a current exact player ID on the current week's active roster;
    source week can never be after requested week. If roster feed is stale or
    missing identities, refuse to publish instead of guessing.
    """
    required_qb={"game_id","team","side","qb_id","qb_name"}
    required_roster={"team","full_name","gsis_id","position","status","week"}
    if not required_qb.issubset(qb_board.columns):
        raise ValueError("QB board lacks key fields: "+str(sorted(required_qb-set(qb_board.columns))))
    if not required_roster.issubset(roster.columns):
        raise ValueError("Roster source lacks key fields: "+str(sorted(required_roster-set(roster.columns))))
    if qb_board.empty or qb_board.duplicated(["game_id","team"]).any():
        raise ValueError("Missing/duplicated quarterback assignments")
    if (qb_board.groupby("game_id").size()!=2).any():
        raise ValueError("QB board must contain exactly two team QBs per game")
    live=roster.copy()
    if "season" in live.columns:
        live=live.loc[pd.to_numeric(live.season,errors="coerce").eq(season)]
    live["week"]=pd.to_numeric(live.week,errors="coerce")
    live=live.loc[live.week.between(1,week)].copy()
    if live.empty or int(live.week.max())<week:
        raise ValueError(f"Roster source has not reached requested season={season}, week={week}; cannot certify active list")
    live["team"]=live.team.astype(str).str.upper().replace({"LAR":"LA"})
    live["gsis_id"]=live.gsis_id.astype(str)
    live["full_name"]=live.full_name.astype(str)
    live["position"]=live.position.astype(str).str.upper()
    live["status"]=live.status.astype(str).str.upper()
    live=live.sort_values(["week","team","gsis_id"]).drop_duplicates(["team","gsis_id"],keep="last")
    audit=[]
    for q in qb_board.itertuples(index=False):
        team=str(q.team).upper().replace("LAR","LA")
        qb_id=str(q.qb_id)
        match=live.loc[
            live.team.eq(team) & live.gsis_id.eq(qb_id) & live.position.eq("QB")
        ]
        if len(match)!=1:
            raise ValueError(
                f"QB roster ID/team/position not found: {q.game_id} {team} {q.qb_name} {qb_id}"
            )
        r=match.iloc[0]
        if int(r.week)!=week:
            raise ValueError(
                f"QB roster source not current Week {week}: {q.game_id} {team} {q.qb_name} source Week {r.week}"
            )
        if _norm(r.full_name)!=_norm(q.qb_name):
            raise ValueError(
                f"QB name and GSIS disagree: {q.game_id} {team}: model={q.qb_name}, roster={r.full_name}"
            )
        if r.status!="ACT":
            raise ValueError(
                f"QB not on active roster: {q.game_id} {team} {q.qb_name} {qb_id} source status={r.status}"
            )
        audit.append({
            "game_id":str(q.game_id),"team":team,"qb_name":str(q.qb_name),
            "qb_id":qb_id,"roster_week":int(r.week),"roster_status":r.status,
            "roster_validation":"ACTIVE_ROSTER_NOT_PROOF_OF_STARTER",
        })
    if len(audit)!=len(qb_board):
        raise AssertionError("Missing active-roster result for a QB")
    return pd.DataFrame(audit)
