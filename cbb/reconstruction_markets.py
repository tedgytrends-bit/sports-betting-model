"""Grade retrospective ESPN closing quotes only in the research output."""
from collections import defaultdict
from math import isfinite
from cbb.espn_grade import norm, URL
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MODELS = ("baseline", "player_v2", "player_opp_v3", "player_rot_v4", "player_all_v4")


def closing_quote(row, event):
    comp, = event["competitions"]
    sides = {s["homeAway"]: s["team"] for s in comp["competitors"]}
    def matches(side):
        return norm(row["home"]) in {norm(sides[side].get(k, "")) for k in
                                    ("location", "displayName", "shortDisplayName", "name")}
    orientation = [s for s in sides if matches(s)]
    if len(orientation) != 1:
        return {}
    for odds in comp.get("odds") or []:
        side = odds.get("pointSpread", {}).get(orientation[0], {}).get("close", {})
        over = odds.get("total", {}).get("over", {}).get("close", {})
        def numeric(value):
            try:
                n = float(str(value).lower().removeprefix("o"))
                return n if isfinite(n) else None
            except ValueError:
                return None
        spread, total = numeric(side.get("line")), numeric(over.get("line"))
        if spread is not None or total is not None:
            return {"home_spread": spread, "total": total, "provider": odds["provider"]["name"],
                    "source": "ESPN closing quote retrieved after final"}
    return {}


def summarize(rows, events):
    lookup = {str(e["id"]): e for e in events}
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1, status_forcelist=(429,500,502,503,504))))
    counts = defaultdict(lambda: dict(W=0, L=0, P=0))
    for row in rows:
        final = row.get("final")
        if not final:
            continue
        event = lookup[final["espnId"]]
        comp, = event["competitions"]
        if not comp.get("odds") and any(row["market"].get(k) is None for k in ("home_spread","total")):
            response = session.get(URL.rsplit("/",1)[0]+"/summary",params={"event":final["espnId"]},timeout=30)
            response.raise_for_status()
            summary = response.json()
            if str(summary["header"]["id"]) != final["espnId"]:
                raise ValueError("ESPN market summary identity mismatch")
            comp["odds"] = summary.get("pickcenter") or []
        closing = closing_quote(row, event)
        row["retrospective_close"] = closing
        for market, key in (("ats","home_spread"), ("total","total")):
            line = row["market"].get(key)
            if line is None:
                line = closing.get(key)
            if line is None:
                continue
            for model in MODELS:
                forecast = row.get(model) or {}
                base = forecast.get("projected_margin_home" if market=="ats" else "projected_total")
                if base is None:
                    continue
                home, away = final["homePoints"], final["awayPoints"]
                edge = base+line if market=="ats" else base-line
                actual = home-away+line if market=="ats" else home+away-line
                if not edge:
                    continue
                for threshold in (0,3.5):
                    if abs(edge)>=threshold:
                        for period in (row["date"], "combined"):
                            record = counts[f"{period}|{model}|{market}|{threshold}"]
                            record["P" if actual==0 else "W" if actual*edge>0 else "L"] += 1
    for r in counts.values():
        stake = r["W"]+r["L"]+r["P"]
        r["roi_pct_flat_minus110"] = round(100*(r["W"]*10/11-r["L"])/stake,3)
    return dict(counts)
