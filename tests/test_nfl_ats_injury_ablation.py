import unittest

import numpy as np
import pandas as pd

from injury_model import _feature_names
from model import chronological_backtest
from research.nfl_ats_injury_ablation import ARMS, CALIBRATIONS, FULL, calibrate_forward, ridge_arms


class NFLATSInjuryAblationTests(unittest.TestCase):
    def test_fixed_fit_reproduces_chronological_scores_and_preserves_missing(self):
        days = pd.date_range("2024-09-01", periods=12, freq="7D")
        counts = np.array([0, 1] * 6, dtype=float)
        dataset = pd.DataFrame(dict(
            game_id=[str(i) for i in range(len(days))], gameday=days, season=2024,
            week=range(len(days)), home_team="A", away_team="B",
            home_score=20 + counts * 10, away_score=20,
            home_injury_report_available=1.0, away_injury_report_available=1.0,
        ))
        for side in ("home", "away"):
            for name in _feature_names():
                dataset[f"{side}_{name}"] = 0.0
        dataset["home_inj_out"] = counts
        dataset.loc[9, "home_inj_out"] = np.nan
        dataset.loc[9, "home_injury_report_available"] = 0.0

        arms = ridge_arms(dataset, min_train_games=5)
        official = chronological_backtest(dataset, min_train_games=5)["predictions"]
        np.testing.assert_allclose(
            arms[ARMS[1]], official.pred_home_score - official.pred_away_score
        )
        self.assertTrue(arms.train_through.lt(arms.gameday).all())
        by_id = arms.set_index("game_id")
        self.assertEqual(by_id.loc["9", ARMS[0]], by_id.loc["9", ARMS[1]])
        self.assertLess(by_id.loc["11", ARMS[0]], by_id.loc["11", ARMS[1]])

    def test_calibration_freezes_before_each_season(self):
        rng = np.random.default_rng(3)
        games = pd.DataFrame(dict(
            season=np.repeat(range(2023, 2027), 15), spread_line=rng.normal(size=60),
            actual_margin=rng.normal(size=60), **{FULL: rng.normal(size=60)},
        ))
        initial, coefficients = calibrate_forward(games)
        games.loc[games.season.ge(2025), "actual_margin"] += 20
        revised, _ = calibrate_forward(games)
        pd.testing.assert_frame_equal(
            initial.loc[games.season.eq(2025), list(CALIBRATIONS)],
            revised.loc[games.season.eq(2025), list(CALIBRATIONS)],
        )
        self.assertEqual(coefficients.groupby("season").training_games.first().tolist(), [15, 30, 45])
