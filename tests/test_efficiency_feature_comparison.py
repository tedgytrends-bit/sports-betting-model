import unittest
import pandas as pd

from research.efficiency_feature_experiments import (
    _exact_binomial_two_sided,
    _matched_directional_comparison,
)


class TestMatchedEfficiencyComparison(unittest.TestCase):
    def _frame(self):
        rows = []
        # Results intentionally span each paired correctness cell for ATS/totals.
        # Use prediction edges and actual margins to encode outcomes.
        samples = [
            # game, actual ATS, baseline ATS edge, passing ATS edge,
            # actual total, baseline total edge, passing total edge
            ("g1", 7, 1, 1, 5, 1, 1),      # both correct
            ("g2", -7, 1, 1, -5, 1, 1),    # both wrong
            ("g3", 7, 1, -1, 5, 1, -1),    # baseline only
            ("g4", 7, -1, 1, 5, -1, 1),   # passing only
            ("g5", 0, 1, 1, 0, 1, 1),      # push excluded
            ("g6", -7, 0, 1, -5, 0, 1),    # baseline no-lean excluded
            ("g7", -7, 1, 0, -5, 1, 0),    # passing no-lean excluded
        ]
        for gid, aa, be, pe, at, bte, pte in samples:
            base = dict(game_id=gid, season=2024, week=1, gameday="2024-09-01",
                        spread_line=0, total_line=0, actual_ats_margin=aa,
                        actual_total_margin=at, variant="baseline_frozen_features",
                        ats_edge=be, total_edge=bte)
            passing = dict(base, variant="baseline_plus_all_passing",
                           ats_edge=pe, total_edge=pte)
            rows.extend([base, passing])
        return pd.DataFrame(rows)

    def test_exact_two_sided_binomial(self):
        self.assertAlmostEqual(_exact_binomial_two_sided(1, 4), 0.625)
        self.assertAlmostEqual(_exact_binomial_two_sided(0, 4), 0.125)
        self.assertEqual(_exact_binomial_two_sided(0, 0), 1.0)

    def test_four_cells_and_exclusions(self):
        result = _matched_directional_comparison(self._frame())["markets"]
        for market in ("ats", "totals"):
            item = result[market]
            self.assertEqual(item["both_correct"], 1)
            self.assertEqual(item["both_wrong"], 1)
            self.assertEqual(item["baseline_only_correct"], 1)
            self.assertEqual(item["passing_only_correct"], 1)
            self.assertEqual(item["actual_market_pushes_excluded"], 1)
            self.assertEqual(item["either_model_no_lean_excluded"], 2)
            self.assertEqual(item["evaluated_paired_games"], 4)
            self.assertEqual(item["baseline_accuracy_pct"], 50.0)
            self.assertEqual(item["passing_accuracy_pct"], 50.0)
            self.assertEqual(item["mcnemar_exact"]["discordant_pairs"], 2)
            self.assertEqual(item["mcnemar_exact"]["exact_two_sided_p_value"], 1.0)


if __name__ == "__main__":
    unittest.main()
