import unittest
import pandas as pd

from nflmeta_injury_analysis import (build_team_week_features, build_game_injury_features,\n                                     build_game_point_in_time_features)


class NFLMetaInjuryAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.injuries = pd.DataFrame([
            {"season_year": 2026, "week": 1, "team_abbr": "BUF", "player_id": 1,
             "position": "QB", "report_status": "Questionable", "game_status": "Inactive",
             "source_observed_at": "2026-09-10T12:00:00Z"},
            {"season_year": 2026, "week": 1, "team_abbr": "BUF", "player_id": 2,
             "position": "T", "report_status": "Out", "game_status": "Inactive",
             "source_observed_at": "2026-09-10T12:00:00Z"},
            {"season_year": 2026, "week": 1, "team_abbr": "MIA", "player_id": 3,
             "position": "WR", "report_status": "", "game_status": "",
             "source_observed_at": "2026-09-10T12:00:00Z"},
        ])
        self.practice = pd.DataFrame([
            {"season_year": 2026, "week": 1, "team_abbr": "BUF", "player_id": 1,
             "practice_date": "2026-09-09", "practice_status_code": "DNP",
             "first_observed_at": "2026-09-09T18:00:00Z", "historical_backfill": False},
            {"season_year": 2026, "week": 1, "team_abbr": "BUF", "player_id": 1,
             "practice_date": "2026-09-10", "practice_status_code": "LP",
             "first_observed_at": "2026-09-10T18:00:00Z", "historical_backfill": False},
            {"season_year": 2026, "week": 1, "team_abbr": "BUF", "player_id": 1,
             "practice_date": "2026-09-11", "practice_status_code": "FP",
             "first_observed_at": "2026-09-11T18:00:00Z", "historical_backfill": False},
            {"season_year": 2026, "week": 1, "team_abbr": "BUF", "player_id": 2,
             "practice_date": "2026-09-11", "practice_status_code": "DNP",
             "first_observed_at": "2026-09-11T18:00:00Z", "historical_backfill": True},
        ])

    def test_team_week_counts_players_not_player_days(self):
        result = build_team_week_features(self.injuries, self.practice)
        buf = result[result.team == "BUF"].iloc[0]
        self.assertEqual(buf["practice_dnp_players_any_day"], 2)
        self.assertEqual(buf["practice_dnp_player_days"], 2)
        self.assertEqual(buf["practice_limited_players_any_day"], 1)
        self.assertEqual(buf["practice_full_players_any_day"], 1)
        self.assertEqual(buf["qb_dnp_players_any_day"], 1)
        self.assertEqual(buf["ol_out_designations"], 1)
        self.assertEqual(buf["report_questionable_players"], 1)
        self.assertEqual(buf["game_inactive_players_postgame"], 2)

    def test_game_features_join_teams_and_mark_timing_unverified_if_missing(self):
        team_week = build_team_week_features(self.injuries, self.practice)
        schedule = pd.DataFrame([{
            "game_id": "G1", "season": 2026, "week": 1, "gameday": "2026-09-14",
            "gametime": "13:00", "home_team": "BUF", "away_team": "MIA",
        }])
        result = build_game_injury_features(schedule, team_week).iloc[0]
        self.assertEqual(result["home_injury_data_available"], 1)
        self.assertEqual(result["away_injury_data_available"], 1)
        self.assertEqual(result["home_report_out_players"], 1)
        self.assertFalse(result["injury_features_point_in_time_verified"])

    def test_report_observation_after_kickoff_blocks_pregame_verification(self):
        injuries = self.injuries.copy()
        injuries.loc[injuries.team_abbr.eq('BUF'), 'source_observed_at'] = '2026-09-14T18:00:00Z'
        practice = pd.concat([self.practice, pd.DataFrame([{
            'season_year': 2026, 'week': 1, 'team_abbr': 'MIA', 'player_id': 3,
            'practice_date': '2026-09-11', 'practice_status_code': 'FP',
            'first_observed_at': '2026-09-11T18:00:00Z', 'historical_backfill': False,
        }])], ignore_index=True)
        team_week = build_team_week_features(injuries, practice)
        schedule = pd.DataFrame([{
            'game_id': 'G3', 'season': 2026, 'week': 1, 'gameday': '2026-09-14',
            'gametime': '13:00', 'home_team': 'BUF', 'away_team': 'MIA',
        }])
        result = build_game_injury_features(schedule, team_week).iloc[0]
        self.assertFalse(result['injury_features_point_in_time_verified'])
        self.assertIn('post-kickoff', result['injury_feature_timing_status'])

    def test_game_features_filter_each_record_at_exact_kickoff(self):
        injuries = self.injuries.copy()
        # 13:00 Eastern on Sep 14 is 17:00 UTC. Keep one pregame BUF report
        # and exclude the later report; the MIA report is pregame.
        injuries.loc[injuries.team_abbr.eq("BUF") & injuries.player_id.eq(2),
                     "source_observed_at"] = "2026-09-14T18:00:00Z"
        practice = self.practice.copy()
        practice.loc[practice.player_id.eq(1) & practice.practice_date.eq("2026-09-11"),
                     "first_observed_at"] = "2026-09-14T18:00:00Z"
        practice.loc[practice.player_id.eq(2), "historical_backfill"] = False
        practice = pd.concat([practice, pd.DataFrame([{
            "season_year": 2026, "week": 1, "team_abbr": "MIA", "player_id": 3,
            "practice_date": "2026-09-11", "practice_status_code": "FP",
            "first_observed_at": "2026-09-11T18:00:00Z", "historical_backfill": False,
        }])], ignore_index=True)
        schedule = pd.DataFrame([{
            "game_id": "G-PIT", "season": 2026, "week": 1, "gameday": "2026-09-14",
            "gametime": "13:00", "home_team": "BUF", "away_team": "MIA",
        }])
        result = build_game_point_in_time_features(schedule, injuries, practice).iloc[0]
        self.assertEqual(result["home_injury_report_players_pregame"], 1)
        self.assertEqual(result["home_report_out_players_pregame"], 0)
        self.assertEqual(result["away_injury_report_players_pregame"], 1)
        self.assertEqual(result["home_practice_records_pregame"], 2)
        self.assertEqual(result["away_practice_records_pregame"], 1)
        self.assertTrue(result["injury_report_timing_verified"])
        self.assertTrue(result["practice_timing_verified"])
        self.assertTrue(result["injury_features_point_in_time_verified"])

    def test_game_features_exclude_backfill_and_missing_timestamps(self):
        injuries = self.injuries.copy()
        injuries["source_observed_at"] = None
        practice = self.practice.copy()
        practice["historical_backfill"] = True
        schedule = pd.DataFrame([{
            "game_id": "G-UNKNOWN", "season": 2026, "week": 1, "gameday": "2026-09-14",
            "gametime": "13:00", "home_team": "BUF", "away_team": "MIA",
        }])
        result = build_game_point_in_time_features(schedule, injuries, practice).iloc[0]
        self.assertEqual(result["home_injury_report_players_pregame"], 0)
        self.assertEqual(result["home_practice_records_pregame"], 0)
        self.assertFalse(result["injury_features_point_in_time_verified"])
        self.assertEqual(result["home_practice_observation_coverage"], "Only backfilled records")

    def test_team_aliases_are_normalized(self):
        injuries = self.injuries.copy()
        injuries.loc[injuries.team_abbr.eq("BUF"), "team_abbr"] = "LAR"
        practice = self.practice.copy()
        practice.loc[practice.team_abbr.eq("BUF"), "team_abbr"] = "LAR"
        team_week = build_team_week_features(injuries, practice)
        schedule = pd.DataFrame([{
            "game_id": "G2", "season": 2026, "week": 1, "gameday": "2026-09-14",
            "gametime": "13:00", "home_team": "LAR", "away_team": "MIA",
        }])
        result = build_game_injury_features(schedule, team_week).iloc[0]
        self.assertEqual(result["home_injury_data_available"], 1)


if __name__ == "__main__":
    unittest.main()
