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

    game_parts = game_id.split("_")
    requested_away, requested_home = game_parts[-2], game_parts[-1]

    captured = datetime.now(timezone.utc).replace(microsecond=0)
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json={"game_id": game_id},
        timeout=(10, 45),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"EndzoneAPI returned HTTP {response.status_code}: {response.text[:1000]}")
    try:
        envelope = response.json()
    except ValueError:
        raise RuntimeError(f"EndzoneAPI returned non-JSON content: {response.text[:500]}")

    # The REST endpoint may wrap its documented result in a top-level "data".
    payload = envelope.get("data") if isinstance(envelope, dict) and "data" in envelope else envelope
    if isinstance(payload, list):
        matching = [
            item for item in payload
            if isinstance(item, dict)
            and str(item.get("away_team", "")).upper() == requested_away
            and str(item.get("home_team", "")).upper() == requested_home
        ]
        if len(matching) == 1:
            payload = matching[0]
        elif len(payload) == 1 and isinstance(payload[0], dict):
            payload = payload[0]
        else:
            raise RuntimeError(
                "EndzoneAPI returned a data list that could not be uniquely matched to the requested teams. "
                f"Items={len(payload)}; no snapshot saved."
            )

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Unexpected EndzoneAPI data type: {type(payload).__name__}; no snapshot saved."
        )
    if payload.get("error"):
        raise RuntimeError(f"EndzoneAPI reported an error: {str(payload.get('error'))[:800]}")

    returned_away = str(payload.get("away_team", "")).upper()
    returned_home = str(payload.get("home_team", "")).upper()
    if returned_away != requested_away or returned_home != requested_home:
        raise RuntimeError(
            "EndzoneAPI data did not match requested teams. "
            f"Requested away/home={requested_away}/{requested_home}; "
            f"returned away/home={returned_away or 'missing'}/{returned_home or 'missing'}; "
            f"data keys={','.join(sorted(payload.keys()))}. No snapshot saved."
        )

    provider_game_id = str(payload.get("game_id", "") or "")
    if provider_game_id and provider_game_id != game_id:
        print(
            f"Note: provider game_id {provider_game_id!r} differs from requested ID "
            f"{game_id!r}, but both team codes match; retaining both identifiers."
        )

    books = payload.get("books", [])
    if not isinstance(books, list) or not books:
        raise RuntimeError(
            "No bookmaker rows returned; no snapshot saved. "
            f"Data keys={','.join(sorted(payload.keys()))}; "
            f"provider game_id={provider_game_id or 'missing'}."
        )

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
                "game_id": game_id,
                "provider_game_id": provider_game_id,
                "kickoff_utc": payload.get("kickoff", ""),
                "away_team": returned_away,
                "home_team": returned_home,
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
