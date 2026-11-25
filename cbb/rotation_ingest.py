"""Fetch player-game box scores from CBBD in bounded weekly date windows.

CBBD /games/players returns one team box object per game/team, containing
players with actual minutes, starters and advanced player metrics. Its API
returns data for at most 1,000 *games* per call; monthly windows can exceed
the cap. This importer uses seven-day windows and rejects likely truncation.

The key is never written to disk. Raw responses are stored in gzipped JSON.
All writes are atomic; a failed partial season cannot poison a prior cache.
"""
from __future__ import annotations

import gzip
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests

ENDPOINT = "https://api.collegebasketballdata.com/games/players"


def rotation_windows(season: int) -> Iterable[tuple[str, str]]:
    """Season=2026 means the year ending in 2026 (2025-26 schedule)."""
    if not 2013 <= season <= 2050:
        raise ValueError("Unexpected basketball season")
    cursor = datetime(season - 1, 10, 1, tzinfo=timezone.utc)
    stop = datetime(season, 6, 1, tzinfo=timezone.utc)
    while cursor < stop:
        next_date = min(cursor + timedelta(days=7), stop)
        yield (cursor.isoformat().replace("+00:00", "Z"),
               next_date.isoformat().replace("+00:00", "Z"))
        cursor = next_date


def get_week(session, season: int, start: str, end: str, token: str,
             attempts: int = 5) -> list[dict]:
    for attempt in range(attempts):
        try:
            response = session.get(
                ENDPOINT,
                params={"season": season, "startDateRange": start, "endDateRange": end},
                headers={"Authorization": "Bearer " + token,
                         "Accept": "application/json"},
                timeout=120,
            )
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < attempts - 1:
                    time.sleep(2 ** min(attempt, 5))
                    continue
            response.raise_for_status()
            records = response.json()
            if not isinstance(records, list):
                raise ValueError("Unexpected CBBD player-game response shape")
            count_games = len({str(row.get("gameId")) for row in records})
            if count_games >= 1000:
                raise ValueError(f"Possible truncation: {season} {start} contains "
                                 f"{count_games} distinct games; reduce window")
            if any(row.get("gameId") is None or row.get("teamId") is None
                   or not isinstance(row.get("players"), list)
                   for row in records):
                raise ValueError(f"Malformed /games/players records {season} {start}")
            return records
        except requests.RequestException:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** min(attempt, 5))
    raise RuntimeError("Exhausted player box-score retries")


def player_box_season(season: int, root: str = "cbb/data/rotation",
                      refresh: bool = False) -> list[dict]:
    folder = Path(root)
    folder.mkdir(parents=True, exist_ok=True)
    cache = folder / f"{season}_game_players.json.gz"
    if cache.is_file() and not refresh:
        with gzip.open(cache, "rt", encoding="utf-8") as file:
            records = json.load(file)
        if not isinstance(records, list):
            raise ValueError(f"Invalid cached player-game records: {cache}")
        print(f"ROTATION_CACHE {season}: {len(records)} team-game boxes")
        return records

    token = os.getenv("CBBD_API_KEY")
    if not token:
        raise RuntimeError("CBBD_API_KEY missing: add GitHub Actions secret")
    indexed: dict[tuple[str, str], dict] = {}
    session = requests.Session()
    requests_made = 0
    for start, end in rotation_windows(season):
        response = get_week(session, season, start, end, token)
        requests_made += 1
        for row in response:
            if int(row.get("season") or 0) != season:
                raise ValueError(f"Wrong-season player-game row {row.get('gameId')}")
            ident = (str(row["gameId"]), str(row["teamId"]))
            indexed[ident] = row
    rows = list(indexed.values())
    tmp = cache.with_suffix(cache.suffix + ".tmp")
    try:
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as file:
            json.dump(rows, file, separators=(",", ":"), ensure_ascii=False)
        tmp.replace(cache)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f"ROTATION_FETCH {season} unique_game_teams={len(rows)} "
          f"distinct_games={len({str(row['gameId']) for row in rows})} "
          f"api_requests={requests_made} cache={cache}")
    return rows


def load_player_boxes(seasons: list[int], root: str = "cbb/data/rotation") -> list[dict]:
    output = []
    for season in seasons:
        output.extend(player_box_season(season, root=root))
    return output


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int,
                        default=[2022, 2023, 2024, 2025, 2026])
    parser.add_argument("--root", default="cbb/data/rotation")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    for season in args.seasons:
        player_box_season(season, args.root, args.refresh)


if __name__ == "__main__":
    main()
