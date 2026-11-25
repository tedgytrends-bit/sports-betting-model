"""Recover existing frozen results without CBBD or new market data."""
import argparse
import os
from pathlib import Path
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cbb.prospective_grade import execute, iso_weeks_between, FIRST_CAPTURE_UTC
from cbb.prospective import utc_date
from cbb.finals_source import fetch_finals_day
from cbb.prospective_publish import GitHubStore

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

def norm(s):
    normalized = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())

    aliases = {"lancasterbiblecollege": "lancasterbible", "alicelloydcollege": "alicelloyd",
               "indianasouthbend": "iusouthbend", "dickinsonstatend": "dickinsonstate",
               "fredoniastate": "sunyfredonia", "carolinachristiancollege": "carolinachristian",
               "stthomasminnesota": "stthomas"}
    return aliases.get(normalized, normalized)

def match(game, events):
    candidates = []
    for event in events:
        for c in event.get("competitions", []):
            status = c.get("status", {}).get("type", {})
            if status.get("name") != "STATUS_FINAL" or not status.get("completed"):
                continue
            try:
                tip = utc_date(c["date"])
                if abs(tip - utc_date(game["tip_utc"])) > timedelta(hours=6):
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
                    "finalScoreSource": event.get("source","ESPN"), "sourceEventId": str(event["id"]),
                    **({"espnId": str(event["id"])} if "source" not in event else {})}))
            except (KeyError, TypeError, ValueError):
                continue
    unique = {i: g for i, g in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--publish", action="store_true")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--checkout", action="store_true")
    args = p.parse_args()
    if args.checkout:
        from cbb.espn_capture_release import CheckoutStore
        store = CheckoutStore()
    else:
        store = GitHubStore(os.environ["GITHUB_REPOSITORY"], "cbb-prospective", os.environ["GITHUB_TOKEN"])
    root = "cbb/prospective/2027"
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    if args.checkout:
        tree = {"tree": [{"path": str(p.relative_to("archive"))}
                         for p in (Path("archive") / root / "frozen").glob("*.json")]}
    else:
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
    official_ids = {}
    for item in tree["tree"]:
        path = item["path"]
        if not path.startswith(root + "/frozen/") or not path.endswith(".json"):
            continue
        ident = path.rsplit("/", 1)[-1][:-5]
        if ident in known and not args.checkout:
            continue
        frozen = store.read_json(path)
        g = frozen["game"]
        tip = utc_date(g["tip_utc"])
        if not cutoff <= tip < now:
            continue
        if ident in known and tip.date() < datetime(2026, 11, 23).date():
            continue
        if g.get("espn_id"):
            official_ids[str(g["espn_id"])] = ident
        day = tip.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
        if day not in dates:
            dates[day] = fetch_finals_day(session,day)
            if len(dates[day]) >= 1000:
                raise RuntimeError("Incomplete ESPN scoreboard")
        final = match(g, dates[day])
        if final:
            official_ids[final["sourceEventId"]] = ident
            if ident not in known:
                rows.append(final)
            print("MATCH", ident, g["away"], g["home"], final["awayPoints"], final["homePoints"], final["sourceEventId"])
        else:
            unmatched.append(ident)
            print("UNMATCHED", ident, g["away"], g["home"], g["tip_utc"])
            for event in dates[day]:
                for c in event.get("competitions", []):
                    names = [x.get("team", {}).get("location", "") for x in c.get("competitors", [])]
                    if any(norm(g[k]) == norm(n) for k in ("home", "away") for n in names):
                        print("CANDIDATE", ident, event.get("id"), c.get("date"), c.get("status", {}).get("type", {}).get("name"), names)
    print("ESPN_RECOVERY", len(rows), "matched;", len(unmatched), "unmatched")
    # An archived forecast can identify a game even when no first-freeze exists.
    # Hand the final to the original grader; it alone decides official eligibility.
    recovery = store.read_json(root + "/research/2026-11-22-to-24.json") or {}
    pending = {str(g["id"]):g for g in rows}
    for recovered in recovery.get("rows", []):
        final = recovered.get("final")
        if final and final.get("espnId"):
            official_ids[str(final["espnId"])] = str(final["id"])
        if final and str(final["id"]) not in known:
            pending.setdefault(str(final["id"]), final)
    if args.publish:
        # Keep verified finals even when the outage left no forecast to grade.
        first_day = max(cutoff.date(), datetime(2026, 11, 22).date())
        day = first_day
        while day <= now.astimezone(ZoneInfo("America/New_York")).date():
            key = day.strftime("%Y%m%d")
            if key not in dates:
                dates[key] = fetch_finals_day(session,key)
            if len(dates[key]) >= 1000:
                raise ValueError("ESPN finals inventory truncated")
            finals = {}
            for event in dates[key]:
                competition, = event["competitions"]
                status = competition["status"]["type"]
                if status["name"]!="STATUS_FINAL" or not status["completed"]:
                    continue
                sides = {s["homeAway"]:s for s in competition["competitors"]}
                if set(sides)!={"away","home"}:
                    raise ValueError("Malformed final")
                result = {"source":event.get("source","ESPN"),"event_id":event["id"],"tip_utc":competition["date"],
                          "central_date":utc_date(competition["date"]).astimezone(ZoneInfo("America/Chicago")).date().isoformat()}
                for side, competitor in sides.items():
                    result[side] = competitor["team"]["displayName"]
                    result[side+"_points"] = int(competitor["score"])
                if result["home_points"] == result["away_points"] or event["id"] in finals:
                    raise ValueError("Invalid ESPN final or duplicate event")
                if result["central_date"] >= "2026-11-23" and result["source"] == "ESPN":
                    ident = official_ids.get(str(event["id"]), "espn-"+str(event["id"]))
                    result["model_game_id"] = ident
                    if ident not in known and ident not in pending:
                        # Only use synthetic event IDs to inventory games with no freeze.
                        # Known freezes require the independent two-team identity check above.
                        if ident.startswith("espn-") and store.read_json(f"{root}/frozen/{ident}.json") is None:
                            pending[ident] = dict(id=ident,status="final",season=2027,startDate=competition["date"],
                                                  homePoints=result["home_points"],awayPoints=result["away_points"])
                finals[event["id"]] = result
            filename = f"{root}/finals/{key}.json"
            previous = store.read_json(filename) or []
            incoming = list(finals.values())
            # Keep previously verified finals through a short or partial provider response.
            aliases = {(r["tip_utc"],norm(r["away"]),norm(r["home"])) for r in incoming}
            for r in previous:
                if str(r["event_id"]) in finals:
                    continue
                if (r["tip_utc"],norm(r["away"]),norm(r["home"])) in aliases:
                    continue
                if incoming and r.get("source") != incoming[0].get("source"):
                    # Preserve separate provider observations until identity is verified.
                    store.put_json(f"{root}/finals/source-observations/{key}-{r['event_id']}.json",r,immutable=True)
                else:
                    incoming.append(r)
            store.put_json(filename,sorted(incoming,key=lambda r:(r["tip_utc"],r["event_id"])),immutable=False)
            day += timedelta(days=1)
        execute(store, list(pending.values()), 2027)

if __name__ == "__main__":
    main()
