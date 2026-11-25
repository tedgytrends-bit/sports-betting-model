"""Incrementally cache current-season schedules, markets, rosters and completed boxes."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from threading import local

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cbb.espn_grade import URL

ROOT = Path("cbb/data/espn_season")
API = URL.rsplit("/", 1)[0]
LOCAL = local()


def read_resource(url, path, params=None, immutable=False):
    if immutable and path.exists():
        return json.loads(path.read_text())
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        retry = Retry(total=4, backoff_factor=1, status_forcelist=(429,500,502,503,504))
        LOCAL.session.mount("https://", HTTPAdapter(max_retries=retry))
    response = LOCAL.session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",",":")))
    tmp.replace(path)


def update_box(event_id):
    path = ROOT / "summaries" / f"{event_id}.json"
    data = read_resource(API+"/summary", path, {"event": event_id}, immutable=True)
    box = data.get("boxscore", {})
    if str(data.get("header",{}).get("id")) != event_id:
        raise ValueError(f"Wrong summary for {event_id}")
    if len(box.get("teams", [])) != 2 or len(box.get("players", [])) != 2:
        return False
    if not path.exists():
        save(path,data)
    return True


def update_roster(team_id):
    path = ROOT / "rosters" / f"{team_id}.json"
    try:
        data = read_resource(f"{API}/teams/{team_id}/roster", path)
    except requests.HTTPError as exc:
        if exc.response.status_code in (400, 404):
            return False
        raise
    if str(data.get("team",{}).get("id")) != team_id or not data.get("athletes"):
        return False
    save(path,data)
    return True


def main():
    now = datetime.now(ZoneInfo("America/Chicago"))
    today = now.date()
    year = today.year if today.month >= 10 else today.year-1
    day = today.replace(year=year, month=11, day=1)
    teams, finals = set(), set()
    while day <= today+timedelta(days=8):
        path = ROOT / "scoreboards" / f"{day}.json"
        cached = path.exists() and day < today-timedelta(days=3)
        data = read_resource(URL, path, {"dates": day.strftime("%Y%m%d"), "groups":50, "limit":1000}, cached)
        events = data["events"]
        if len(events)>=1000 or len({e["id"] for e in events})!=len(events):
            raise ValueError(f"Invalid scoreboard on {day}")
        for e in events:
            c, = e["competitions"]
            teams.update(str(s["team"]["id"]) for s in c["competitors"])
            if c["status"]["type"]["name"]=="STATUS_FINAL":
                finals.add(str(e["id"]))
        if not cached:
            save(path, data)
        day += timedelta(days=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        boxes = sum(pool.map(update_box, sorted(finals)))
        rosters = sum(pool.map(update_roster, sorted(teams)))
    audit = dict(as_of=now.isoformat(), final_games=len(finals), usable_boxes=boxes,
                 teams=len(teams), usable_rosters=rosters)
    print(audit,flush=True)
    if not boxes or not rosters:
        raise ValueError("No usable team/player coverage")
    save(ROOT / "coverage.json",audit)


if __name__=="__main__":
    main()
