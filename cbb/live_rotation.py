"""Quota-conscious 2026-27 player-box capture for prospective research.

Persist season-to-date observed player-game boxes in Actions cache. Each
new capture refetches a seven-day overlap and all dates missed since the
previous capture, not the entire year. Historical backtest game-player
boxes remain cached separately and are not touched.

Data are read only *as observed before the new capture*. If the cache is
missing, fetch the elapsed season from October; no performance is claimed
for previous dates that were not captured prospectively.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from cbb.rotation_ingest import get_week


def aware(iso: str) -> datetime:
    value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Naive timestamp is not allowed")
    return value.astimezone(timezone.utc)


def elapsed_windows(start: datetime, end: datetime):
    """Only seven-day partitions; never request player stats after capture."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("UTC offsets required")
    step = start
    while step < end:
        target = min(step + timedelta(days=7), end)
        yield (step.isoformat().replace("+00:00", "Z"),
               target.isoformat().replace("+00:00", "Z"))
        step = target


def live_paths(root, season):
    directory = Path(root)
    return (directory / f"{season}_game_players.json.gz",
            directory / f"{season}_manifest.json")


def load_live_player_boxes(season=2027, root="cbb/data/rotation_live"):
    archive, _ = live_paths(root, season)
    if not archive.exists():
        raise FileNotFoundError(
            f"Live player boxes unavailable: {archive}; refresh before projecting"
        )
    with gzip.open(archive, "rt", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("Expected list of observed player game team records")
    return records


def refresh_live_player_boxes(season=2027,
                              root="cbb/data/rotation_live",
                              captured_utc=None):
    now = captured_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Capture time must be timezone-aware")
    now = now.astimezone(timezone.utc)
    season_start = datetime(season - 1, 10, 1, tzinfo=timezone.utc)
    if now < season_start:
        raise ValueError("The basketball season has not yet begun")
    archive, manifest_path = live_paths(root, season)
    archive.parent.mkdir(parents=True, exist_ok=True)
    previous = []
    if archive.exists():
        previous = load_live_player_boxes(season, root=root)
    old_meta = {}
    if previous and manifest_path.exists():
        old_meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_refresh = old_meta.get("capture_utc")
    start = max(
        season_start,
        aware(previous_refresh) - timedelta(days=7)
        if previous_refresh and previous else season_start,
    )
    # Protect future-game leakage in the event of a malformed cache.
    indexed = {}
    for box in previous:
        if box.get("gameId") is None or box.get("teamId") is None:
            raise ValueError("Malformed cached game player box")
        if int(box.get("season") or 0) != season:
            raise ValueError("Cached game-player row belongs to wrong season")
        if aware(box["startDate"]) > now:
            continue
        indexed[(str(box["gameId"]), str(box["teamId"]))] = box

    token = os.getenv("CBBD_API_KEY")
    if not token:
        raise RuntimeError("CBBD_API_KEY missing")
    session = requests.Session()
    calls = 0
    for left, right in elapsed_windows(start, now):
        newly_observed = get_week(session, season, left, right, token)
        calls += 1
        for row in newly_observed:
            if int(row.get("season") or 0) != season:
                raise ValueError("Unexpected season in live rotation refresh")
            if aware(row["startDate"]) > now:
                continue
            indexed[(str(row["gameId"]), str(row["teamId"]))] = row

    records = sorted(indexed.values(),
                     key=lambda row: (row["startDate"], str(row["gameId"]), str(row["teamId"])))
    temp = archive.with_suffix(archive.suffix + ".tmp")
    try:
        with gzip.open(temp, "wt", encoding="utf-8", compresslevel=6) as handle:
            json.dump(records, handle, separators=(",", ":"), ensure_ascii=False)
        temp.replace(archive)
    finally:
        if temp.exists():
            temp.unlink()
    manifest = {
        "season": season,
        "capture_utc": now.isoformat().replace("+00:00", "Z"),
        "earliest_refreshed_utc": start.isoformat().replace("+00:00", "Z"),
        "rows": len(records),
        "unique_games": len({str(x["gameId"]) for x in records}),
        "api_requests": calls,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("CBB_LIVE_ROTATION", json.dumps(manifest))
    return records, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2027)
    parser.add_argument("--root", default="cbb/data/rotation_live")
    args = parser.parse_args()
    refresh_live_player_boxes(args.season, args.root)


if __name__ == "__main__":
    main()
