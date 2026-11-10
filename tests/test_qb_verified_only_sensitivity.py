"""Research-only QB verification sensitivity must preserve the non-QB margin."""
import unittest

import pandas as pd

from scripts.capture_qb_aware_injury import add_verified_only_sensitivity


class VerifiedOnlyQBPolicyTests(unittest.TestCase):
    def setUp(self):
        self.projections=pd.DataFrame([
            {"game_id":"both","original_non_qb_home":21.0,"original_non_qb_away":20.0,
             "projected_home_qb_injury":19.0,"projected_away_qb_injury":22.0,
             "projected_home":19.0,"projected_away":22.0},
            {"game_id":"one","original_non_qb_home":22.0,"original_non_qb_away":18.0,
             "projected_home_qb_injury":26.0,"projected_away_qb_injury":14.0,
             "projected_home":26.0,"projected_away":14.0},
        ])
        self.board=pd.DataFrame([
            {"game_id":"both","side":"home","starter_source":"verified_pregame"},
            {"game_id":"both","side":"away","starter_source":"verified_pregame"},
            {"game_id":"one","side":"home","starter_source":"verified_pregame"},
            {"game_id":"one","side":"away","starter_source":"schedule_provisional_qb_unverified"},
        ])

    def test_full_pair_uses_overlay_but_partial_pair_reverts_to_original_nonqb(self):
        got=add_verified_only_sensitivity(self.projections,self.board).set_index("game_id")
        self.assertTrue(got.loc["both","both_qbs_source_verified"])
        self.assertEqual(got.loc["both","verified_only_projected_home"],19.0)
        self.assertEqual(got.loc["both","verified_only_projected_away"],22.0)
        self.assertFalse(got.loc["one","both_qbs_source_verified"])
        self.assertEqual(got.loc["one","verified_only_projected_home"],22.0)
        self.assertEqual(got.loc["one","verified_only_projected_away"],18.0)
        self.assertEqual(got.loc["one","verified_only_projected_total"],40.0)
        self.assertEqual(got.loc["one","projected_home"],26.0)
        self.assertEqual(got.loc["one","projected_away"],14.0)

    def test_missing_other_qb_fails_loudly(self):
        board=self.board.loc[~((self.board.game_id=="one")&(self.board.side=="away"))]
        with self.assertRaises(ValueError):
            add_verified_only_sensitivity(self.projections,board)

    def test_duplicate_qb_fails_loudly(self):
        with self.assertRaises(ValueError):
            add_verified_only_sensitivity(
                self.projections,
                pd.concat([self.board,self.board.iloc[[0]]],ignore_index=True)
            )


if __name__=="__main__":
    unittest.main()
