"""Read-only ESPN data acquisition probe; isolated from production model inputs."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests
from cbb.espn_grade import URL

SUMMARY = URL.rsplit("/", 1)[0] + "/summary"

def fetch(session, url, params):
    r = session.get(url, params=params, timeout=45)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("Expected ESPN object")
    return data

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=2)
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--root", default="cbb/data/espn_shadow")
    a = p.parse_args()
    root = Path(a.root)
    session = requests.Session()
    count = team_boxes = player_boxes = 0
    for offset in range(1, a.days + 1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y%m%d")
        board = fetch(session, URL, {"dates":day,"groups":50,"limit":1000})
        events = board["events"]
        if len(events) >= 1000:
            raise ValueError("Potential scoreboard truncation")
        save(root / "scoreboards" / (day+".json"), board)
        for event in events:
            if count >= a.limit:
                break
            if event.get("status", {}).get("type", {}).get("name") != "STATUS_FINAL":
                continue
            ident = str(event["id"])
            if not ident.isdigit():
                raise ValueError("Invalid ESPN event ID")
            path = root / "summaries" / (ident+".json")
            data = json.loads(path.read_text()) if path.exists() else fetch(session, SUMMARY, {"event":ident})
            header = data.get("header", {})
            if str(header.get("id")) != ident:
                raise ValueError("Summary identity mismatch")
            box = data.get("boxscore", {})
            teams = box.get("teams", [])
            players = box.get("players", [])
            if len(teams) == 2 and len(players) == 2:
                save(path, data)
            count += 1
            team_boxes += len(teams)
            player_boxes += len(players)
            print("ESPN_BOX", ident, "teams", len(teams), "players", len(players),
                  "team_labels", [s.get("name") for t in teams[:1] for s in t.get("statistics", [])],
                  "player_labels", [s.get("labels") for t in players[:1] for s in t.get("statistics", [])])
    print("ESPN_PROBE", count, team_boxes, player_boxes)
    if not count or not team_boxes or not player_boxes:
        raise RuntimeError("No usable box score coverage")

if __name__ == "__main__":
    main()
