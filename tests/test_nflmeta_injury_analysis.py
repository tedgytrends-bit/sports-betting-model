import unittest
import pandas as pd

from nflmeta_injury_analysis import build_team_week_features, build_game_injury_features


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
            "home_team": "BUF", "away_team": "MIA",
        }])
        result = build_game_injury_features(schedule, team_week).iloc[0]
        self.assertEqual(result["home_injury_data_available"], 1)
        self.assertEqual(result["away_injury_data_available"], 1)
        self.assertEqual(result["home_report_out_players"], 1)
        self.assertFalse(result["injury_features_point_in_time_verified"])

    def test_team_aliases_are_normalized(self):
        injuries = self.injuries.copy()
        injuries.loc[injuries.team_abbr.eq("BUF"), "team_abbr"] = "LAR"
        practice = self.practice.copy()
        practice.loc[practice.team_abbr.eq("BUF"), "team_abbr"] = "LAR"
        team_week = build_team_week_features(injuries, practice)
        schedule = pd.DataFrame([{
            "game_id": "G2", "season": 2026, "week": 1, "gameday": "2026-09-14",
            "home_team": "LAR", "away_team": "MIA",
        }])
        result = build_game_injury_features(schedule, team_week).iloc[0]
        self.assertEqual(result["home_injury_data_available"], 1)


if __name__ == "__main__":
    unittest.main()
