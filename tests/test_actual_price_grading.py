"""Unit tests for hypothetical actual-price grading."""
import unittest

from research.actual_price_grading import grade_actual_price, american_profit_per_unit


def base_row(**overrides):
    row = {
        "final_available": True,
        "timing_eligible": True,
        "endzone_ats_edge": 4.0,
        "spread_home": 7.0,
        "spread_home_odds": -110,
        "spread_away_odds": -110,
        "actual_home_margin": -2.0,
        "endzone_total_edge": -4.0,
        "total": 54.5,
        "total_over_odds": -110,
        "total_under_odds": -112,
        "actual_total": 48,
    }
    row.update(overrides)
    return row


class ActualPriceGradingTests(unittest.TestCase):
    def test_american_odds_profit(self):
        self.assertAlmostEqual(american_profit_per_unit(-110), 100 / 110)
        self.assertAlmostEqual(american_profit_per_unit(150), 1.5)
        self.assertTrue(american_profit_per_unit(0) != american_profit_per_unit(0))

    def test_home_underdog_cover_uses_signed_handicap(self):
        result = grade_actual_price(base_row(), "ATS")
        self.assertEqual(result["result"], "Win")
        self.assertAlmostEqual(result["net_units"], 100 / 110)

    def test_away_side_is_selected_for_negative_edge(self):
        row = base_row(endzone_ats_edge=-4.0, spread_away_odds=125, actual_home_margin=10)
        result = grade_actual_price(row, "ATS")
        self.assertEqual(result["result"], "Win")
        self.assertAlmostEqual(result["net_units"], 1.25)

    def test_totals_under_win_and_push(self):
        under = grade_actual_price(base_row(), "Totals")
        self.assertEqual(under["result"], "Win")
        self.assertAlmostEqual(under["net_units"], 100 / 112)
        push = grade_actual_price(base_row(actual_total=54.5), "Totals")
        self.assertEqual(push["result"], "Push")
        self.assertEqual(push["net_units"], 0.0)

    def test_below_threshold_and_missing_price_are_not_graded(self):
        below = grade_actual_price(base_row(endzone_ats_edge=2.0), "ATS")
        self.assertTrue(below["result"].startswith("Below"))
        missing = grade_actual_price(base_row(spread_home_odds=float("nan")), "ATS")
        self.assertEqual(missing["result"], "Not gradable")

    def test_pending_or_ineligible_rows_are_not_graded(self):
        pending = grade_actual_price(base_row(final_available=False), "ATS")
        self.assertEqual(pending["result"], "Pending/Not eligible")
        ineligible = grade_actual_price(base_row(timing_eligible=False), "Totals")
        self.assertEqual(ineligible["result"], "Pending/Not eligible")

    def test_invalid_market_is_rejected(self):
        with self.assertRaises(ValueError):
            grade_actual_price(base_row(), "ML")


if __name__ == "__main__":
    unittest.main()
