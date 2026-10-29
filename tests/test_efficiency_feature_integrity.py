"""Synthetic integrity tests for play-by-play feature calculations.

These tests isolate feature definitions from live NFL data and API availability.
Run with: python -m unittest discover -s tests
"""
import unittest

import pandas as pd

from model import build_efficiency_table


class EfficiencyFeatureIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.pbp = pd.DataFrame(
            [
                {
                    "game_id": "TEST_1", "season": 2026, "week": 8,
                    "posteam": "KC", "defteam": "BUF", "play_type": "run",
                    "epa": 4.0, "success": 1, "yardline_100": 10,
                    "touchdown": 1, "interception": 0, "fumble_lost": 0,
                },
                {
                    "game_id": "TEST_1", "season": 2026, "week": 8,
                    "posteam": "KC", "defteam": "BUF", "play_type": "pass",
                    "epa": -4.0, "success": 0, "yardline_100": 5,
                    "touchdown": 0, "interception": 1, "fumble_lost": 0,
                },
                {
                    "game_id": "TEST_1", "season": 2026, "week": 8,
                    "posteam": "BUF", "defteam": "KC", "play_type": "run",
                    "epa": -2.0, "success": 0, "yardline_100": 60,
                    "touchdown": 0, "interception": 0, "fumble_lost": 1,
                },
            ]
        )

    def test_red_zone_rate_is_touchdowns_per_red_zone_scrimmage_play(self):
        table = build_efficiency_table(self.pbp).set_index("team")
        self.assertAlmostEqual(table.loc["KC", "red_zone_td_rate"], 0.5)
        # No Buffalo red-zone plays means the rate is undefined, not zero.
        self.assertTrue(pd.isna(table.loc["BUF", "red_zone_td_rate"]))

    def test_turnovers_are_attributed_to_the_offense_that_lost_them(self):
        table = build_efficiency_table(self.pbp).set_index("team")
        self.assertAlmostEqual(table.loc["KC", "turnovers_per_play"], 0.5)
        self.assertAlmostEqual(table.loc["BUF", "turnovers_per_play"], 1.0)

    def test_takeaways_are_attributed_to_the_defense_on_the_play(self):
        table = build_efficiency_table(self.pbp).set_index("team")
        self.assertAlmostEqual(table.loc["BUF", "def_takeaways_per_play"], 0.5)
        self.assertAlmostEqual(table.loc["KC", "def_takeaways_per_play"], 1.0)

    def test_missing_red_zone_location_stays_unavailable(self):
        pbp = self.pbp.drop(columns=["yardline_100"])
        table = build_efficiency_table(pbp).set_index("team")
        self.assertTrue(pd.isna(table.loc["KC", "red_zone_td_rate"]))
        self.assertTrue(pd.isna(table.loc["BUF", "red_zone_td_rate"]))


if __name__ == "__main__":
    unittest.main()
