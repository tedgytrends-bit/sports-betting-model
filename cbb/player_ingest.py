"""CBBD roster/transfer/recruiting/prior-season player ingestion.

All prior-player performances come from season S-1, never target season S.
Roster membership needs explicit seasonal filtering in downstream features;
CBBD responses can contain historical/future player affiliations.
"""
import json
import os
import time
from pathlib import Path

import requests

API = "https://api.collegebasketballdata.com"

ENDPOINTS = (
    ("rosters", "/teams/roster", lambda s: {"season": s}),
    ("prior_players", "/stats/player/season", lambda s: {"season": s - 1}),
    ("portal", "/recruiting/portal", lambda s: {"year": s - 1}),
    ("recruits", "/recruiting/players", lambda s: {"year": s - 1}),
)


def get_collection(session, path, params, api_key):
    for attempt in range(5):
        try:
            response = session.get(
                API + path, params=params, timeout=90,
                headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
            )
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, list):
                raise TypeError(f"{path} expected list; got {type(result).__name__}")
            return result
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not fetch {path}")


def player_inputs(season, root="cbb/data/raw", refresh=False, refresh_roster_only=False):
    if season < 2022:
        raise ValueError("Player priors are supported from 2022 onward")
    folder = Path(root) / str(season)
    folder.mkdir(parents=True, exist_ok=True)
    key = os.getenv("CBBD_API_KEY")
    session = requests.Session()
    out = {}
    for name, endpoint, selector in ENDPOINTS:
        path = folder / (name + ".json")
        refresh_this = refresh or (refresh_roster_only and name == "rosters")
        if path.exists() and not refresh_this:
            out[name] = json.loads(path.read_text(encoding="utf-8"))
            continue
        if not key:
            raise RuntimeError("CBBD_API_KEY missing. Add as a repository Actions secret.")
        data = get_collection(session, endpoint, selector(season), key)
        out[name] = data
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        print(f"Roster inputs season={season}, {name}: {len(data)} records")
    return out


def load_player_inputs(seasons, root="cbb/data/raw"):
    return {s: player_inputs(s, root=root) for s in seasons}
