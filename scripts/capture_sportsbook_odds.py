#!/usr/bin/env python3
"""Capture one game's bookmaker-specific odds from EndzoneAPI.

Manual-only: each game request costs credits. Writes an immutable CSV with
local capture time and provider per-book snapshot timestamps.
"""
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import sys

import pandas as pd
import requests

API_URL = "https://mcp.endzoneapi.com/v1/get_odds"
OUT = Path("data/prospective_ats_tracking")
SNAPSHOT_TYPES = ("opening", "closing", "latest")


def main() -> int:
    api_key = os.getenv("ENDZONE_API_KEY", "").strip()
    game_id = os.getenv("ENDZONE_GAME_ID", "").strip()
    if not api_key:
        print("ENDZONE_API_KEY is not configured; no request sent and no credits used.")
        return 2
    if not re.fullmatch(r"\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}", game_id):
        print("ENDZONE_GAME_ID is missing or invalid. Expected format like 2026_09_KC_BUF.")
        return 2

    captured = datetime.now(timezone.utc).replace(microsecond=0)
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json={"game_id": game_id},
        timeout=(10, 45),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"EndzoneAPI returned HTTP {response.status_code}: {response.text[:1000]}")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("game_id") != game_id:
        raise RuntimeError("EndzoneAPI response did not match the requested game ID.")

    books = payload.get("books", [])
    if not isinstance(books, list) or not books:
        raise RuntimeError("No bookmaker rows returned; no snapshot saved.")

    records = []
    for book in books:
        if not isinstance(book, dict):
            continue
        for snapshot_type in SNAPSHOT_TYPES:
            snap = book.get(snapshot_type)
            if not isinstance(snap, dict):
                continue
            records.append({
                "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
                "game_id": payload.get("game_id"),
                "kickoff_utc": payload.get("kickoff", ""),
                "away_team": payload.get("away_team", ""),
                "home_team": payload.get("home_team", ""),
                "bookmaker": book.get("bookmaker", snap.get("bookmaker", "")),
                "snapshot_type": snapshot_type,
                "source_snapshot_at_utc": snap.get("captured_at", ""),
                "source": snap.get("source", ""),
                "spread_home": snap.get("spread_home"),
                "spread_home_odds": snap.get("spread_home_odds"),
                "spread_away": snap.get("spread_away"),
                "spread_away_odds": snap.get("spread_away_odds"),
                "total": snap.get("total"),
                "total_over_odds": snap.get("total_over_odds"),
                "total_under_odds": snap.get("total_under_odds"),
                "home_moneyline": snap.get("ml_home"),
                "away_moneyline": snap.get("ml_away"),
                "line_source": "EndzoneAPI bookmaker odds archive",
                "note": "Provider snapshot timestamp is distinct from this collector's capture time; verify it predates kickoff before grading as a prospective price.",
            })

    if not records:
        raise RuntimeError("Response had no recognizable opening/closing/latest snapshots.")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    path = OUT / f"endzone_odds_{game_id}_{stamp}.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    print(f"Saved {len(records)} bookmaker snapshot rows for {game_id}: {path}")
    print(f"Capture time UTC: {captured.isoformat()}")
    print(f"Bookmakers returned: {len({r['bookmaker'] for r in records})}")
    print("One game was requested; no season-wide request was made.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Odds capture failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
