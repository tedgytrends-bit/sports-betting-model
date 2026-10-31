import importlib.util
from pathlib import Path
import unittest

import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_injury_snapshots.py"
SPEC = importlib.util.spec_from_file_location("audit_injury_snapshots", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _row(player_id, practice_status="Full Participation in Practice", report_status=""):
    return {
        "gsis_id": player_id,
        "team": "KC",
        "position": "WR",
        "full_name": f"Player {player_id}",
        "report_primary_injury": "",
        "report_secondary_injury": "",
        "report_status": report_status,
        "practice_primary_injury": "",
        "practice_secondary_injury": "",
        "practice_status": practice_status,
    }


class TestInjurySnapshotAudit(unittest.TestCase):
    def test_snapshot_pair_detects_practice_change_and_feed_membership(self):
        previous = pd.DataFrame([
            _row("p1", "Limited Participation in Practice"),
            _row("p2"),
        ])
        current = pd.DataFrame([
            _row("p1", "Full Participation in Practice"),
            _row("p3"),
        ])
        changes = audit.compare_snapshot_pair(previous, current)
        self.assertIn(("p1", "practice_status", "Limited Participation in Practice",
                       "Full Participation in Practice"), changes)
        self.assertIn(("p2", "feed_membership", "present", "not_present"), changes)
        self.assertIn(("p3", "feed_membership", "not_present", "present"), changes)

    def test_snapshot_pair_ignores_unchanged_rows(self):
        previous = pd.DataFrame([_row("p1")])
        current = pd.DataFrame([_row("p1")])
        self.assertEqual(audit.compare_snapshot_pair(previous, current), [])

    def test_valid_partial_team_coverage_is_not_mislabeled_as_invalid(self):
        # nflverse exports listed players, not a guaranteed row for every NFL team.
        # A low team count is a coverage observation, not a structural failure.
        snapshot = pd.DataFrame([_row("p1"), _row("p2")])
        result = audit.validate_snapshot(snapshot, "partial.csv")
        self.assertTrue(result["comparison_eligible"])
        self.assertEqual(result["structural_status"], "valid_structure")
        self.assertEqual(result["teams_observed"], 1)
        self.assertIn("not certified", result["quality_note"])

    def test_missing_player_ids_make_snapshot_ineligible(self):
        snapshot = pd.DataFrame([_row("p1"), _row(pd.NA)])
        result = audit.validate_snapshot(snapshot, "missing-id.csv")
        self.assertFalse(result["comparison_eligible"])
        self.assertEqual(result["missing_player_ids"], 1)
        self.assertEqual(result["structural_status"], "invalid_structure")

    def test_duplicate_player_ids_make_snapshot_ineligible(self):
        snapshot = pd.DataFrame([_row("p1"), _row("p1")])
        result = audit.validate_snapshot(snapshot, "duplicate-id.csv")
        self.assertFalse(result["comparison_eligible"])
        self.assertEqual(result["duplicate_player_ids"], 2)

    def test_missing_team_makes_snapshot_ineligible(self):
        row = _row("p1")
        row["team"] = None
        result = audit.validate_snapshot(pd.DataFrame([row]), "missing-team.csv")
        self.assertFalse(result["comparison_eligible"])
        self.assertIn("missing team", result["quality_note"])

    def test_empty_snapshot_is_ineligible(self):
        snapshot = pd.DataFrame(columns=["gsis_id", "team"])
        result = audit.validate_snapshot(snapshot, "empty.csv")
        self.assertFalse(result["comparison_eligible"])
        self.assertEqual(result["structural_status"], "invalid_structure")

    def test_kickoff_conversion_respects_eastern_daylight_time(self):
        schedule = pd.DataFrame([{
            "season": 2026, "week": 8, "gameday": "2026-10-29",
            "gametime": "20:15", "home_team": "MIA", "away_team": "BAL",
        }])
        lookup = audit.build_kickoff_lookup(schedule)
        expected = pd.Timestamp("2026-10-30T00:15:00Z")
        self.assertEqual(lookup[(2026, 8, "MIA")], expected)
        self.assertEqual(lookup[(2026, 8, "BAL")], expected)

    def test_kickoff_conversion_respects_standard_time_after_dst(self):
        schedule = pd.DataFrame([{
            "season": 2026, "week": 10, "gameday": "2026-11-12",
            "gametime": "20:15", "home_team": "MIA", "away_team": "BAL",
        }])
        lookup = audit.build_kickoff_lookup(schedule)
        expected = pd.Timestamp("2026-11-13T01:15:00Z")
        self.assertEqual(lookup[(2026, 10, "MIA")], expected)


if __name__ == "__main__":
    unittest.main()
