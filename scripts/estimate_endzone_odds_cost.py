#!/usr/bin/env python3
"""Estimate EndzoneAPI NFL odds-query costs without consuming credits.

Requires ENDZONE_API_KEY. This script only sends estimate_only=True requests.
"""
import json
import os
import sys

import requests

API_URL = "https://mcp.endzoneapi.com/v1/get_odds"


def estimate(payload, api_key):
    body = {**payload, "estimate_only": True}
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json=body,
        timeout=(10, 45),
    )
    response.raise_for_status()
    data = response.json()
    print(json.dumps({"request": body, "estimate_response": data}, indent=2))
    return data


def main():
    api_key = os.getenv("ENDZONE_API_KEY", "").strip()
    if not api_key:
        print(
            "ENDZONE_API_KEY is not configured for this GitHub workflow. "
            "No request was sent and no credits were used."
        )
        sys.exit(0)

    # Estimate a single 2026 DraftKings game query as the unit-cost baseline.
    # This request is explicitly estimate-only and does not retrieve odds.
    estimate(
        {
            "game_id": "2026_01_KC_BUF",
            "bookmaker": "draftkings",
        },
        api_key,
    )

    # Estimate the season-level request to reveal the cost before any data pull.
    # The endpoint's season mode may price by games returned, so this is the
    # key comparison for deciding whether to query a slate game-by-game.
    estimate(
        {
            "season": 2026,
            "bookmaker": "draftkings",
            "snapshot_type": "closing",
            "limit": 500,
        },
        api_key,
    )


if __name__ == "__main__":
    main()
