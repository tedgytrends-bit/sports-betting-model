import importlib.util
from pathlib import Path

import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_injury_snapshots.py"
SPEC = importlib.util.spec_from_file_location("audit_injury_snapshots", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _row(player_id, practice_status="Full Participation in Practice", report_status=""):
    return {
        "gsis_id": player_id,
        "position": "WR",
        "full_name": f"Player {player_id}",
        "report_primary_injury": "",
        "report_secondary_injury": "",
        "report_status": report_status,
        "practice_primary_injury": "",
        "practice_secondary_injury": "",
        "practice_status": practice_status,
    }


def test_snapshot_pair_detects_practice_change_and_feed_membership():
    previous = pd.DataFrame([
        _row("p1", "Limited Participation in Practice"),
        _row("p2"),
    ])
    current = pd.DataFrame([
        _row("p1", "Full Participation in Practice"),
        _row("p3"),
    ])

    changes = audit.compare_snapshot_pair(previous, current)

    assert ("p1", "practice_status", "Limited Participation in Practice",
            "Full Participation in Practice") in changes
    assert ("p2", "feed_membership", "present", "not_present") in changes
    assert ("p3", "feed_membership", "not_present", "present") in changes


def test_snapshot_pair_ignores_unchanged_rows():
    previous = pd.DataFrame([_row("p1")])
    current = pd.DataFrame([_row("p1")])
    assert audit.compare_snapshot_pair(previous, current) == []


def test_kickoff_conversion_respects_eastern_daylight_time():
    schedule = pd.DataFrame([{
        "season": 2026, "week": 8, "gameday": "2026-10-29",
        "gametime": "20:15", "home_team": "MIA", "away_team": "BAL",
    }])
    lookup = audit.build_kickoff_lookup(schedule)
    assert lookup[(2026, 8, "MIA")] == pd.Timestamp("2026-10-30T00:15:00Z")
    assert lookup[(2026, 8, "BAL")] == pd.Timestamp("2026-10-30T00:15:00Z")


def test_kickoff_conversion_respects_standard_time_after_dst():
    schedule = pd.DataFrame([{
        "season": 2026, "week": 10, "gameday": "2026-11-12",
        "gametime": "20:15", "home_team": "MIA", "away_team": "BAL",
    }])
    lookup = audit.build_kickoff_lookup(schedule)
    assert lookup[(2026, 10, "MIA")] == pd.Timestamp("2026-11-13T01:15:00Z")
