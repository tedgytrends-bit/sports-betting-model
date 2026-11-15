"""Current-season roster eligibility is distinct from a depth chart's QB guess."""
import unittest
import pandas as pd

from research.validate_live_qb_roster import enforce_active_roster_qbs


class LiveQBReserveRosterGateTests(unittest.TestCase):
    def setUp(self):
        self.board=pd.DataFrame([
            {"game_id":"2026_10_MIA_IND","team":"MIA","side":"away",
             "qb_id":"00-0040014","qb_name":"Kyle McCord"},
            {"game_id":"2026_10_MIA_IND","team":"IND","side":"home",
             "qb_id":"00-0033537","qb_name":"Daniel Jones"}
        ])
        self.roster=pd.DataFrame([
            {"season":2026,"week":10,"team":"MIA","position":"QB","full_name":"Kyle McCord",
             "gsis_id":"00-0040014","status":"ACT"},
            {"season":2026,"week":10,"team":"IND","position":"QB","full_name":"Daniel Jones",
             "gsis_id":"00-0033537","status":"ACT"},
            {"season":2026,"week":10,"team":"MIA","position":"QB","full_name":"Malik Willis",
             "gsis_id":"00-0038128","status":"RES"}
        ])

    def test_source_confirmed_replacement_is_on_active_roster(self):
        result=enforce_active_roster_qbs(self.board,self.roster,season=2026,week=10)
        self.assertEqual(len(result),2)
        self.assertEqual(set(result.roster_status),{"ACT"})
        self.assertEqual(set(result.roster_validation),{"ACTIVE_ROSTER_NOT_PROOF_OF_STARTER"})

    def test_older_injured_reserve_qb_rejected_even_if_previous_pbp_selected(self):
        b=self.board.copy()
        b.loc[0,["qb_id","qb_name"]]=["00-0038128","Malik Willis"]
        with self.assertRaisesRegex(ValueError,"not on active roster"):
            enforce_active_roster_qbs(b,self.roster,season=2026,week=10)

    def test_missing_qb_on_current_team_rejected(self):
        b=self.board.copy()
        b.loc[0,"qb_id"]="00-0049999"
        with self.assertRaisesRegex(ValueError,"not found"):
            enforce_active_roster_qbs(b,self.roster,season=2026,week=10)

    def test_wrong_name_with_real_id_fails(self):
        b=self.board.copy()
        b.loc[0,"qb_name"]="Malik Willis"
        with self.assertRaisesRegex(ValueError,"name and GSIS"):
            enforce_active_roster_qbs(b,self.roster,season=2026,week=10)

    def test_roster_from_previous_week_fails(self):
        old=self.roster.copy()
        old.loc[:,"week"]=9
        with self.assertRaisesRegex(ValueError,"has not reached"):
            enforce_active_roster_qbs(self.board,old,season=2026,week=10)

    def test_missing_current_week_player_row_fails(self):
        old=self.roster.copy()
        old.loc[old.full_name.eq("Kyle McCord"),"week"]=9
        with self.assertRaisesRegex(ValueError,"not current"):
            enforce_active_roster_qbs(self.board,old,season=2026,week=10)

    def test_both_sides_must_exist(self):
        with self.assertRaisesRegex(ValueError,"two team"):
            enforce_active_roster_qbs(self.board.iloc[:1],self.roster,season=2026,week=10)


if __name__=="__main__":
    unittest.main()
