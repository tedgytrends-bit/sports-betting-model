"""Publish today's ESPN matchups alongside identifiable archived model scores."""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cbb.espn_grade import URL, norm
from cbb.prospective import utc_date

MODELS = ("baseline", "player_v2", "player_opp_v3", "player_rot_v4", "player_all_v4")
ZONE = ZoneInfo("America/Chicago")


def main():
    root = Path("archive/cbb/prospective/2027")
    archive = json.loads((root / "latest.json").read_text())
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1,
                  status_forcelist=(429, 500, 502, 503, 504))))
    now = datetime.now(timezone.utc)
    day = now.astimezone(ZONE).date()
    response = session.get(URL, params={"dates": day.strftime("%Y%m%d"), "groups": 50,
                           "limit": 1000}, timeout=35)
    response.raise_for_status()
    events = response.json()["events"]
    if not 0 < len(events) < 1000:
        raise ValueError("Missing or truncated ESPN scoreboard")
    now = datetime.now(timezone.utc)
    rows = []
    ids = set()
    for event in events:
        c, = event["competitions"]
        tip = utc_date(c["date"])
        if tip.astimezone(ZONE).date() != day:
            continue
        if event["id"] in ids:
            raise ValueError("Duplicate ESPN event")
        ids.add(event["id"])
        sides = {s["homeAway"]: s["team"] for s in c["competitors"]}
        names = {k: {norm(v.get(n)) for n in ("location", "displayName", "shortDisplayName")}
                 for k,v in sides.items()}
        scheduled = c["status"]["type"]["state"] == "pre" and tip > now
        matches = [g for g in archive["games"] if abs((utc_date(g["tip_utc"])-tip).total_seconds()) <= 7200
                   and all(norm(g[k]) in names[k] for k in ("home","away"))]
        odds = next(iter(c.get("odds") or []), {}) if scheduled else {}
        spread = odds.get("pointSpread", {}).get("home", {}).get("close", {}).get("line")
        spread = float(spread) if spread is not None else None
        total = odds.get("overUnder")
        forecasts = {}
        if len(matches) == 1 and utc_date(archive["capture_utc"]) < tip:
            for model in MODELS:
                projection = matches[0].get(model)
                if projection:
                    forecasts[model] = {k: projection[k] for k in ("projected_away_points","projected_home_points",
                                        "projected_margin_home","projected_total")}
                    forecasts[model]["ats_edge_home"] = None if spread is None else round(projection["projected_margin_home"]+spread,3)
                    forecasts[model]["total_edge_over"] = None if total is None else round(projection["projected_total"]-total,3)
        rows.append(dict(id=event["id"], tip=c["date"], away=sides["away"]["displayName"], home=sides["home"]["displayName"],
                         status=c["status"]["type"]["name"], home_spread=spread, total=total, forecasts=forecasts,
                         provider=odds.get("provider",{}).get("name")))
    if not rows:
        raise ValueError("No matchups on the requested Central date")
    target = root / "research" / f"{day}-espn-board.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(dict(espn_capture_utc=now.isoformat(), forecast_capture_utc=archive["capture_utc"],
                           forecast_snapshot=archive["snapshot_path"], rows=rows),indent=2,allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
