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
    payload = json.dumps(dict(espn_capture_utc=now.isoformat(), forecast_capture_utc=archive["capture_utc"],
                           forecast_snapshot=archive["snapshot_path"], rows=rows),indent=2,allow_nan=False)+"\n"
    snapshot = target.parent / "espn-boards" / (now.strftime("%Y%m%dT%H%M%S%fZ")+".json")
    snapshot.parent.mkdir(exist_ok=True)
    with snapshot.open("x") as handle:
        handle.write(payload)
    target.write_text(payload)
    lines = ["# Tedgy Trends CBB daily board", "",
             f"ESPN markets observed {now.isoformat()}. Model scores from {archive['capture_utc']}.",
             "", "Player + rotation v4. All times Central. A dash means the input was unavailable.",
             "", "| Tip | Away at home | Projected score | ATS lean | Total lean |",
             "|---|---|---|---|---|"]
    for r in sorted(rows,key=lambda x:x["tip"]):
        f = r["forecasts"].get("player_rot_v4",{})
        score = ats = totals = "—"
        if f:
            score = f'{f["projected_away_points"]:.1f}–{f["projected_home_points"]:.1f}'
            edge = f["ats_edge_home"]
            if edge is not None:
                ats = ("Even" if edge == 0 else
                       f'{r["home"]} {r["home_spread"]:+g}' if edge>0 else
                       f'{r["away"]} {-r["home_spread"]:+g}')
            edge = f["total_edge_over"]
            if edge is not None:
                totals = "Even" if edge==0 else f'{"Over" if edge>0 else "Under"} {r["total"]:g}'
        tip = utc_date(r["tip"]).astimezone(ZONE).strftime("%I:%M %p")
        lines.append(f'| {tip} | {r["away"]} at {r["home"]} | {score} | {ats} | {totals} |')
    lines.extend(["",f"[All five models and coverage]({target.name})"])
    target.with_suffix(".md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()
