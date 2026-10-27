#!/usr/bin/env python3
"""Capture bookmaker-specific NFL odds snapshots from The Odds API v4.

Requires ODDS_API_KEY. This collector is intentionally separate from the
nflverse schedule-feed collector: schedule lines are not sportsbook quotes.
Each returned bookmaker/market/outcome is stored with the local capture time
and API snapshot timestamp (when provided). Capture time is not proof of when
a sportsbook first posted a line or that a wager was executable.
"""
from datetime import datetime, timezone
from pathlib import Path
import os

import pandas as pd
import requests

API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
OUT = Path("data/prospective_ats_tracking")
REGIONS = os.getenv("ODDS_API_REGIONS", "us")
MARKETS = os.getenv("ODDS_API_MARKETS", "spreads,totals")
ODDS_FORMAT = "american"
TIME_FORMAT = "iso"


def main():
    api_key = os.getenv("ODDS_API_KEY", "").strip()
    if not api_key:
        print("ODDS_API_KEY is not configured; sportsbook odds capture skipped.")
        return

    captured = datetime.now(timezone.utc).replace(microsecond=0)
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": TIME_FORMAT,
    }
    response = requests.get(API_URL, params=params, timeout=(10, 45))
    response.raise_for_status()
    events = response.json()
    if not isinstance(events, list):
        raise RuntimeError("Odds API response was not a list of events.")

    records = []
    for event in events:
        for bookmaker in event.get("bookmakers", []) or []:
            for market in bookmaker.get("markets", []) or []:
                if market.get("key") not in {"spreads", "totals"}:
                    continue
                for outcome in market.get("outcomes", []) or []:
                    records.append({
                        "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
                        "source_snapshot_at_utc": bookmaker.get("last_update") or market.get("last_update") or "",
                        "source_timestamp_available": bool(bookmaker.get("last_update") or market.get("last_update")),
                        "source": "The Odds API v4",
                        "source_type": "third_party_bookmaker_odds_feed",
                        "event_id": event.get("id", ""),
                        "commence_time_utc": event.get("commence_time", ""),
                        "home_team": event.get("home_team", ""),
                        "away_team": event.get("away_team", ""),
                        "bookmaker_key": bookmaker.get("key", ""),
                        "bookmaker_title": bookmaker.get("title", ""),
                        "market_key": market.get("key", ""),
                        "market_last_update_utc": market.get("last_update", ""),
                        "outcome_name": outcome.get("name", ""),
                        "outcome_point": outcome.get("point", float("nan")),
                        "odds_price_american": outcome.get("price", float("nan")),
                        "note": "Third-party odds feed snapshot; not proof of account-specific availability or guaranteed execution. Preserve source timestamps and compare only like-for-like markets.",
                    })

    OUT.mkdir(parents=True, exist_ok=True)
    if not records:
        print("API returned no bookmaker spread/total outcomes; no file saved.")
        return
    path = OUT / f"sportsbook_odds_{captured.strftime('%Y%m%dT%H%M%SZ')}.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    print(f"Saved {len(records)} bookmaker/market/outcome rows across {len(events)} events: {path}")
    print(f"Capture time UTC: {captured.isoformat()}")
    print(f"Regions: {REGIONS}; markets: {MARKETS}")
    print("Quota headers: " + ", ".join(
        f"{key}={response.headers[key]}" for key in
        ("x-requests-remaining", "x-requests-used", "x-requests-last")
        if key in response.headers
    ))


if __name__ == "__main__":
    main()
