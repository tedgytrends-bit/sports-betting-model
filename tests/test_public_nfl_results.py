"""Guardrails for scheduled official NFL model results; no network in unit tests."""
import unittest
from datetime import datetime,timezone
from pathlib import Path

from scripts.refresh_public_nfl_results import (
    grade,load_espn_finals,future_published_rows,market_quotes,
    eligible_published,week8_rows,week9_rows,with_scores,pending_row,immutable_grade,
)

def fixture(*,completed=True):
    return {"events":[{
        "id":"9999888","date":"2026-11-15T18:00:00Z",
        "status":{"type":{"name":"STATUS_FINAL" if completed else "STATUS_IN_PROGRESS","completed":completed}},
        "competitions":[{"competitors":[
            {"homeAway":"away","team":{"abbreviation":"MIA"},"score":"18"},
            {"homeAway":"home","team":{"abbreviation":"IND"},"score":"21"},
        ]}]
    }]}

class PublicResultsTests(unittest.TestCase):
    def test_simple_grading(self):
        self.assertEqual(grade(1,10),"Win")
        self.assertEqual(grade(-1,-8),"Win")
        self.assertEqual(grade(1,-4),"Loss")
        self.assertEqual(grade(1,0),"Push")
        self.assertEqual(grade(0,100),"No lean")

    def test_week8_published_14_plus_week9_official15(self):
        r8=week8_rows()
        r9=week9_rows()
        self.assertEqual(len(r8),28)
        self.assertEqual(len(r9),30)
        self.assertEqual({r["model"] for r in r8},{"injury","baseline"})
        self.assertEqual(len([r for r in r9 if r["record_class"]=="PUBLIC_PUBLISHED"]),15)
        self.assertEqual(len([r for r in r9 if r["record_class"]=="RESEARCH_COMPARATOR"]),15)
        official=[r for r in r9 if r["model"]=="injury"]
        self.assertEqual(sum(r["ats_result"]=="Win" for r in official),3)
        self.assertEqual(sum(r["ats_result"]=="Loss" for r in official),11)
        self.assertEqual(sum(r["ats_result"]=="Push" for r in official),1)
        self.assertEqual(sum(r["total_result"]=="Win" for r in official),9)

    def test_pregame_selection_requires_latest_corrected_qb_and_official_inactives(self):
        snapshots,kickoffs=future_published_rows()
        self.assertGreaterEqual(len(kickoffs),14)
        rows=eligible_published(snapshots,kickoffs,market_quotes(),datetime(2026,11,16,14,tzinfo=timezone.utc))
        self.assertEqual(len([k for k in rows if k[0].startswith("2026_10_")]),28)
        self.assertIn("nfl_week10_mia_ind_mccord_corrected",rows[("2026_10_MIA_IND","injury")]["forecast_file"])
        self.assertIn("nfl_week10_ne_det_inactives_adjusted",rows[("2026_10_NE_DET","injury")]["forecast_file"])
        self.assertIn("nfl_week10_initial_projections",rows[("2026_10_WAS_NYG","injury")]["forecast_file"])
        self.assertIn("nfl_week10_sunday_pregame",rows[("2026_10_MIA_IND","baseline")]["forecast_file"])
        for row in rows.values():
            self.assertLess(datetime.fromisoformat(row["published_at_utc"]),datetime.fromisoformat(row["kickoff_utc"]))
            self.assertLess(datetime.fromisoformat(row["quote_at_utc"]),datetime.fromisoformat(row["kickoff_utc"]))

    def test_official_score_must_have_complete_and_final(self):
        now=datetime(2026,11,16,15,tzinfo=timezone.utc)
        out=load_espn_finals(["20261115"],now,fetcher=lambda _:fixture(completed=False))
        self.assertFalse(out)
        out=load_espn_finals(["20261115"],now,fetcher=lambda _:fixture(completed=True))
        self.assertEqual(out[("MIA","IND","20261115")]["actual_home"],21)
        self.assertEqual(out[("MIA","IND","20261115")]["actual_away"],18)

    def test_pending_not_graded_and_final_grade_cannot_change(self):
        p={"game_id":"2026_10_MIA_IND","model":"injury","away_team":"MIA","home_team":"IND",
           "projected_away":"22.9","projected_home":"20.9","projected_total":"43.8",
           "home_favored_spread":"4.5","bovada_total":"37.5","published_at_utc":"2026-11-15T15:07:30Z",
           "quote_at_utc":"2026-11-15T12:56:00Z","forecast_file":"snapshot.csv"}
        wait=pending_row(p)
        self.assertEqual(wait["ats_result"],"Pending")
        self.assertEqual(wait["score_status"],"PENDING")
        g=with_scores(p,18,21,"scoreboard.example","2026-11-16T12:00:00Z")
        self.assertEqual(g["ats_result"],"Loss")  # model MIA, Colts win by 3 (< -4.5 spread)
        immutable_grade(g,g.copy())
        changed=g.copy();changed["actual_home"]="22"
        with self.assertRaisesRegex(ValueError,"retroactive"):
            immutable_grade(g,changed)
        with self.assertRaisesRegex(ValueError,"pending"):
            immutable_grade(g,wait)

if __name__=="__main__":
    unittest.main()
