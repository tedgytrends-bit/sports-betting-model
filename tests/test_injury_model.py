import unittest
from unittest.mock import patch
import pandas as pd

from injury_model import add_injury_features, injury_coverage_diagnostics, _normalize_reports, _snapshot_capture_time


class InjuryModelTests(unittest.TestCase):
    def test_injury_features_use_only_pregame_rows_and_deduplicate_players(self):
        schedule = pd.DataFrame([
            {
                "game_id": "HIST1", "season": 2025, "week": 3, "gameday": "2025-09-18",
                "gametime": "20:15", "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
                "home_score": 24, "away_score": 17,
            }
        ])
        dataset = pd.DataFrame([
            {
                "game_id": "HIST1", "season": 2025, "week": 3, "gameday": pd.Timestamp("2025-09-18"),
                "home_team": "BUF", "away_team": "MIA", "home_score": 24, "away_score": 17,
                "sample_feature": 1.0,
            }
        ])
        reports = pd.DataFrame([
            {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
             "player_name": "QB One", "report_status": "QUESTIONABLE", "practice_status": "LIMITED",
             "date_modified": "2025-09-18T15:00:00Z"},
            # Latest pregame update for the same player replaces the earlier row.
            {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
             "player_name": "QB One", "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
             "date_modified": "2025-09-18T18:00:00Z"},
            # This update happened after kickoff and must not leak into the features.
            {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
             "player_name": "QB Two", "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
             "date_modified": "2025-09-19T02:00:00Z"},
            {"season": 2025, "week": 3, "season_type": "REG", "team": "MIA", "position": "OT",
             "player_name": "Tackle One", "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
             "date_modified": "2025-09-18T18:00:00Z"},
        ])

        result = add_injury_features(dataset, schedule, reports).iloc[0]
        self.assertEqual(result["home_injury_report_available"], 1)
        self.assertEqual(result["away_injury_report_available"], 1)
        self.assertEqual(result["home_qb_out"], 1)
        self.assertEqual(result["home_qb_questionable"], 0)
        self.assertEqual(result["away_ol_out"], 1)
        self.assertEqual(result["home_inj_out"], 1)


    def test_game_type_is_used_when_season_type_is_absent(self):
        reports = pd.DataFrame([
            {"season": 2025, "week": 19, "game_type": "POST", "team": "BUF",
             "position": "QB", "player_name": "QB One", "report_status": "OUT",
             "practice_status": "DID NOT PARTICIPATE", "date_modified": "2026-01-10T12:00:00Z"}
        ])
        normalized = _normalize_reports(reports)
        self.assertEqual(normalized.loc[0, "season_type"], "POST")

    def test_game_type_fills_missing_season_type(self):
        reports = pd.DataFrame([
            {"season": 2025, "week": 19, "season_type": None, "game_type": "POST",
             "team": "BUF", "position": "QB", "player_name": "QB One",
             "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
             "date_modified": "2026-01-10T12:00:00Z"}
        ])
        normalized = _normalize_reports(reports)
        self.assertEqual(normalized.loc[0, "season_type"], "POST")



    def test_snapshot_filename_timestamp_is_parsed_as_utc(self):
        from pathlib import Path
        captured = _snapshot_capture_time(Path("injuries_2026_week_08_20261030T130813Z.csv"))
        self.assertEqual(captured, pd.Timestamp("2026-10-30T13:08:13Z"))

    def test_snapshot_without_timestamp_is_rejected(self):
        from pathlib import Path
        self.assertTrue(pd.isna(_snapshot_capture_time(Path("injuries_2026_week_08_latest.csv"))))


    def test_diagnostics_use_pregame_snapshot_for_team_counts(self):
        schedule = pd.DataFrame([{
            "game_id": "UPCOMING", "season": 2026, "week": 8, "gameday": "2026-11-01",
            "gametime": "13:00", "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
            "home_score": None, "away_score": None,
        }])
        reports = pd.DataFrame(columns=[
            "season", "week", "game_type", "team", "position", "player_name",
            "report_status", "practice_status", "date_modified",
        ])
        snapshot = pd.DataFrame([
            {"season": 2026, "week": 8, "season_type": "REG", "game_type": "REG",
             "team": "BUF", "position": "QB", "gsis_id": "QB1", "full_name": "QB One",
             "report_status": "OUT", "practice_status": "Did Not Participate In Practice",
             "snapshot_captured_at_utc": "2026-10-30T13:08:13Z",
             "_snapshot_captured_at_utc": pd.Timestamp("2026-10-30T13:08:13Z")},
            {"season": 2026, "week": 8, "season_type": "REG", "game_type": "REG",
             "team": "MIA", "position": "T", "gsis_id": "OT1", "full_name": "Tackle One",
             "report_status": "OUT", "practice_status": "Did Not Participate In Practice",
             "snapshot_captured_at_utc": "2026-10-30T13:08:13Z",
             "_snapshot_captured_at_utc": pd.Timestamp("2026-10-30T13:08:13Z")},
        ])
        with patch("injury_model._latest_snapshot_for", return_value=snapshot):
            result = injury_coverage_diagnostics(schedule, reports).iloc[0]
        self.assertEqual(result["Diagnostic source used"], "Saved snapshot")
        self.assertEqual(result["Home report rows"], 1)
        self.assertEqual(result["Away report rows"], 1)
        self.assertEqual(result["Home QB out"], 1)
        self.assertEqual(result["Away OL out"], 1)


    def test_snapshot_structural_validation(self):
        from injury_model import _snapshot_is_structurally_valid

        valid = pd.DataFrame([
            {"gsis_id": "P1", "team": "BUF"},
            {"gsis_id": "P2", "team": "MIA"},
        ])
        self.assertTrue(_snapshot_is_structurally_valid(valid))
        self.assertFalse(_snapshot_is_structurally_valid(valid.iloc[0:0]))
        self.assertFalse(_snapshot_is_structurally_valid(pd.DataFrame([{"team": "BUF"}])))
        self.assertFalse(_snapshot_is_structurally_valid(pd.DataFrame([
            {"gsis_id": None, "team": "BUF"}
        ])))
        self.assertFalse(_snapshot_is_structurally_valid(pd.DataFrame([
            {"gsis_id": " ", "team": "BUF"}
        ])))
        self.assertFalse(_snapshot_is_structurally_valid(pd.DataFrame([
            {"gsis_id": "P1", "team": "BUF"},
            {"gsis_id": "P1", "team": "BUF"},
        ])))
        self.assertFalse(_snapshot_is_structurally_valid(pd.DataFrame([
            {"gsis_id": "P1", "team": None}
        ])))


if __name__ == "__main__":
    unittest.main()
