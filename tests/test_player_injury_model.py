import unittest
from unittest.mock import patch
import pandas as pd

from player_injury_model import build_player_injury_features


class PlayerInjuryFeatureTests(unittest.TestCase):
    def test_player_identity_and_prior_usage_are_preserved(self):
        schedule = pd.DataFrame([{
            "game_id": "G1", "season": 2025, "week": 3, "gameday": "2025-09-21",
            "gametime": "13:00", "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
            "home_score": 24, "away_score": 20,
        }])
        pbp = pd.DataFrame([
            {"season": 2025, "week": 1, "posteam": "BUF", "defteam": "MIA",
             "passer_player_id": "QB1", "rusher_player_id": None, "receiver_player_id": "WR1",
             "solo_tackle_1_player_id": "DEF1"},
            {"season": 2025, "week": 2, "posteam": "BUF", "defteam": "MIA",
             "passer_player_id": "QB1", "rusher_player_id": "RB1", "receiver_player_id": "WR1",
             "solo_tackle_1_player_id": "DEF1"},
        ])
        reports = pd.DataFrame([
            {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
             "gsis_id": "QB1", "player_name": "Quarterback One", "report_status": "OUT",
             "practice_status": "DID NOT PARTICIPATE", "date_modified": "2025-09-20T12:00:00Z"},
            {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "WR",
             "gsis_id": "WR1", "player_name": "Receiver One", "report_status": "QUESTIONABLE",
             "practice_status": "LIMITED", "date_modified": "2025-09-20T12:00:00Z"},
        ])
        with patch("injury_model._latest_snapshot_for", return_value=None):
            features, detail = build_player_injury_features(schedule, pbp, reports)
        self.assertEqual(set(detail["player_id"]), {"QB1", "WR1"})
        qb = detail[detail["player_id"] == "QB1"].iloc[0]
        self.assertEqual(qb["valuation_status"], "valued_from_prior_pbp_usage")
        self.assertGreater(qb["player_impact_index"], 0)
        self.assertGreater(features.iloc[0]["home_player_qb_absence_index"], 0)
        self.assertEqual(features.iloc[0]["away_player_qb_absence_index"], 0)


if __name__ == "__main__":
    unittest.main()
