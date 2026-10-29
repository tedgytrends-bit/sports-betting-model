#!/usr/bin/env python3
"""Estimate EndzoneAPI NFL odds-query costs without consuming credits.

Requires the repository Actions secret ENDZONE_API_KEY. Both requests use
estimate_only=True, which EndzoneAPI documents as returning cost without
charging credits or running the query.
"""
import json
import os
import sys

import requests

API_URL = "https://mcp.endzoneapi.com/v1/get_odds"


def estimate(label, payload, api_key):
    body = {**payload, "estimate_only": True}
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json=body,
        timeout=(10, 45),
    )
    if not response.ok:
        print(f"{label}: HTTP {response.status_code}")
        print(response.text[:2000])
        response.raise_for_status()
    data = response.json()
    print(json.dumps({"scenario": label, "request": body, "estimate_response": data}, indent=2))
    return data


def main():
    api_key = os.getenv("ENDZONE_API_KEY", "").strip()
    if not api_key:
        print(
            "ENDZONE_API_KEY is not configured for this GitHub workflow. "
            "No request was sent and no credits were used. "
            "Add your existing EndzoneAPI key in GitHub: Settings > Secrets and variables > Actions > New repository secret; "
            "name it ENDZONE_API_KEY. Do not paste the key in code or logs."
        )
        # Fail the workflow so a skipped estimate cannot look like success.
        sys.exit(1)

    # Illustrative single-game estimate. This game ID is just a known-format
    # example; estimate_only means it does not retrieve or bill for the game.
    estimate("single game", {"game_id": "2026_01_KC_BUF", "bookmaker": "draftkings"}, api_key)

    # A season-level query returns per-book lines and is charged per game
    # returned, not a flat 10 credits. Estimating it lets us price one page
    # before retrieving any records.
    estimate(
        "2026 season page up to 500 games",
        {"season": 2026, "bookmaker": "draftkings", "snapshot_type": "closing", "limit": 500},
        api_key,
    )


if __name__ == "__main__":
    main()
