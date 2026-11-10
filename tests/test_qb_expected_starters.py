"""Game-specific coach EXPECTATION is not the same as confirmed starting QB."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from qb_epa_model import _starter_for
from scripts import capture_qb_aware_injury as capture


class CoachExpectedStarterTests(unittest.TestCase):
    def setUp(self):
        self.schedule=pd.DataFrame([{
            "game_id":"2026_10_LAC_BAL","gameday":"2026-11-16",
            "gametime":"20:15","home_team":"BAL","away_team":"LAC",
        }])
        self.item={
            "game_id":"2026_10_LAC_BAL","team":"BAL","qb_id":"00-0033119",
            "qb_name":"Jacoby Brissett","source_url":"https://www.baltimoreravens.com/news/coaches-starter",
            "source_report_date":"2026-11-09",
            "expectation_status":"COACH_EXPECTED_NOT_FINAL",
            "review_note":"Head coach expects Jacoby Brissett to start this Monday night."
        }

    def with_file(self,change=None):
        temp=tempfile.TemporaryDirectory()
        root=Path(temp.name)
        target=root/"data"/"qb_starters"
        target.mkdir(parents=True)
        r=self.item.copy()
        if change:
            r.update(change)
        pd.DataFrame([r]).to_csv(target/"2026_week10_expected.csv",index=False)
        return temp,root

    def test_real_source_expectation_loaded_but_not_marked_confirmed(self):
        temp,root=self.with_file()
        try:
            with patch.object(capture,"ROOT",root):
                eligible=capture.load_coach_expected_starters(self.schedule,2026,10)
            self.assertEqual(len(eligible),1)
            history=pd.DataFrame([
                {"team":"BAL","gameday":pd.Timestamp("2026-11-08"),
                 "qb_id":"00-0000001","qb_name":"Tyler Huntley","dropbacks":35}
            ])
            id_,name,status,_=_starter_for(
                "BAL","2026_10_LAC_BAL",history,None,
                observed=None,expected=eligible
            )
            self.assertEqual(id_,"00-0033119")
            self.assertEqual(name,"Jacoby Brissett")
            self.assertEqual(status,"coach_expected_pregame_unverified")
        finally:
            temp.cleanup()

    def test_missing_source_rejected(self):
        temp,root=self.with_file({"source_url":""})
        try:
            with patch.object(capture,"ROOT",root):
                with self.assertRaises(ValueError):
                    capture.load_coach_expected_starters(self.schedule,2026,10)
        finally:
            temp.cleanup()

    def test_stale_expected_source_rejected(self):
        temp,root=self.with_file({"source_report_date":"2026-09-21"})
        try:
            with patch.object(capture,"ROOT",root):
                with self.assertRaisesRegex(ValueError,"stale"):
                    capture.load_coach_expected_starters(self.schedule,2026,10)
        finally:
            temp.cleanup()

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as dirname:
            with patch.object(capture,"ROOT",Path(dirname)):
                self.assertIsNone(capture.load_coach_expected_starters(self.schedule,2026,10))

    def test_wrong_team_rejected(self):
        temp,root=self.with_file({"team":"ARI"})
        try:
            with patch.object(capture,"ROOT",root):
                with self.assertRaisesRegex(ValueError,"not in game"):
                    capture.load_coach_expected_starters(self.schedule,2026,10)
        finally:
            temp.cleanup()

    def test_confirmed_override_takes_precedence_over_coach_expectation(self):
        temp,root=self.with_file()
        try:
            with patch.object(capture,"ROOT",root):
                expected=capture.load_coach_expected_starters(self.schedule,2026,10)
            history=pd.DataFrame([
                {"team":"BAL","gameday":pd.Timestamp("2026-11-08"),
                 "qb_id":"00-0000001","qb_name":"Tyler Huntley","dropbacks":35}
            ])
            confirmed=pd.DataFrame([{
                "game_id":"2026_10_LAC_BAL","team":"BAL",
                "qb_id":"00-0000002","qb_name":"Confirmed QB",
                "source_url":"https://www.baltimoreravens.com/news/game-day-starter",
            }])
            id_,name,status,_=_starter_for(
                "BAL","2026_10_LAC_BAL",history,confirmed,
                observed=None,expected=expected
            )
            self.assertEqual(id_,"00-0000002")
            self.assertEqual(status,"verified_pregame")
        finally:
            temp.cleanup()

    def test_ir_starter_from_old_depth_chart_is_blocked(self):
        board=pd.DataFrame([
            {"game_id":"2026_10_LAC_BAL","team":"BAL","qb_name":"Tyler Huntley"}
        ])
        watch=pd.DataFrame([
            {"game_id":"2026_10_LAC_BAL","team":"BAL","player_name":"Tyler Huntley",
             "starter_confirmation_status":"IR_REPORTED"}
        ])
        with self.assertRaisesRegex(ValueError,"Known unavailable QB"):
            capture.reject_known_inactive_qb(board,watch)
        replacement=board.copy()
        replacement["qb_name"]="Jacoby Brissett"
        capture.reject_known_inactive_qb(replacement,watch)

    def test_questionable_injury_not_equivalent_to_confirmed_out(self):
        board=pd.DataFrame([
            {"game_id":"2026_10_LA_ARI","team":"ARI","qb_name":"Gardner Minshew"}
        ])
        watch=pd.DataFrame([
            {"game_id":"2026_10_LA_ARI","team":"ARI","player_name":"Gardner Minshew",
             "starter_confirmation_status":"STARTER_STATUS_UNRESOLVED"}
        ])
        capture.reject_known_inactive_qb(board,watch)


if __name__=="__main__":
    unittest.main()
