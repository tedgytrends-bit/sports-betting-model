"""Recover existing frozen results without CBBD or new market data."""
import argparse
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cbb.prospective_grade import execute, iso_weeks_between, FIRST_CAPTURE_UTC
from cbb.prospective import utc_date
from cbb.prospective_publish import GitHubStore

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

def norm(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())

def match(game, events):
    candidates = []
    for event in events:
        for c in event.get("competitions", []):
            status = c.get("status", {}).get("type", {})
            if status.get("name") != "STATUS_FINAL" or not status.get("completed"):
                continue
            try:
                tip = utc_date(c["date"])
                if abs(tip - utc_date(game["tip_utc"])) > timedelta(hours=2):
                    continue
                sides = {x["homeAway"]: x for x in c["competitors"]}
                if len(c["competitors"]) != 2 or set(sides) != {"home", "away"}:
                    continue
                if game.get("neutral_site") and c.get("neutralSite"):
                    if norm(game["home"]) in {norm(sides["away"]["team"].get(n, "")) for n in ("location", "displayName", "shortDisplayName")}:
                        sides = {"home": sides["away"], "away": sides["home"]}
                if not all(norm(game[k]) in {norm(sides[k]["team"].get(n, "")) for n in
                           ("location", "displayName", "shortDisplayName", "name")}
                           for k in ("home", "away")):
                    continue
                hp, ap = int(sides["home"]["score"]), int(sides["away"]["score"])
                if min(hp, ap) < 0 or hp == ap:
                    continue
                candidates.append((str(event["id"]), {
                    "id": game["id"], "season": game["season"], "startDate": c["date"],
                    "status": "final", "homePoints": hp, "awayPoints": ap,
                    "homeTeamId": game["home_team_id"], "awayTeamId": game["away_team_id"],
                    "finalScoreSource": "ESPN", "espnId": str(event["id"])}))
            except (KeyError, TypeError, ValueError):
                continue
    unique = {i: g for i, g in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--publish", action="store_true")
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    store = GitHubStore(os.environ["GITHUB_REPOSITORY"], "cbb-prospective", os.environ["GITHUB_TOKEN"])
    root = "cbb/prospective/2027"
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    # Enumerate the git tree rather than the 1000-entry contents listing.
    base = "https://api.github.com/repos/" + store.repository
    r = store.session.get(base + "/git/trees/" + store.branch, params={"recursive": "1"}, timeout=60)
    r.raise_for_status()
    tree = r.json()
    if tree.get("truncated"):
        raise RuntimeError("Incomplete frozen inventory")
    known = set()
    for week in iso_weeks_between(FIRST_CAPTURE_UTC.date(), now.date()):
        journal = store.read_json(f"{root}/graded/{week}.json") or {}
        known.update(journal.get("results", {}))
        known.update(journal.get("invalid", {}))
        known.update(journal.get("untracked", {}))
    dates = {}
    rows = []
    unmatched = []
    session = requests.Session()
    retries = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    for item in tree["tree"]:
        path = item["path"]
        if not path.startswith(root + "/frozen/") or not path.endswith(".json"):
            continue
        ident = path.rsplit("/", 1)[-1][:-5]
        if ident in known:
            continue
        frozen = store.read_json(path)
        g = frozen["game"]
        tip = utc_date(g["tip_utc"])
        if not cutoff <= tip < now:
            continue
        day = tip.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
        if day not in dates:
            response = session.get(URL, params={"dates": day, "groups": 50, "limit": 1000}, timeout=45)
            response.raise_for_status()
            dates[day] = response.json()["events"]
            if len(dates[day]) >= 1000:
                raise RuntimeError("Incomplete ESPN scoreboard")
        final = match(g, dates[day])
        if final:
            rows.append(final)
            print("MATCH", ident, g["away"], g["home"], final["awayPoints"], final["homePoints"], final["espnId"])
        else:
            unmatched.append(ident)
            print("UNMATCHED", ident, g["away"], g["home"], g["tip_utc"])
            for event in dates[day]:
                for c in event.get("competitions", []):
                    names = [x.get("team", {}).get("location", "") for x in c.get("competitors", [])]
                    if any(norm(g[k]) == norm(n) for k in ("home", "away") for n in names):
                        print("CANDIDATE", ident, event.get("id"), c.get("date"), c.get("status", {}).get("type", {}).get("name"), names)
    print("ESPN_RECOVERY", len(rows), "matched;", len(unmatched), "unmatched")
    if args.publish and rows:
        execute(store, rows, 2027)

if __name__ == "__main__":
    main()
