"""Verify that a source URL cannot silently become a confirmed starter."""
import unittest
import pandas as pd

from research.validate_qb_starter_confirmations import validate_starter_confirmations


class QBConfirmationGateTests(unittest.TestCase):
    def setUp(self):
        self.schedule=pd.DataFrame([{
            "game_id":"2026_10_WAS_NYG","gameday":"2026-11-12",
            "gametime":"20:15","home_team":"NYG","away_team":"WAS"
        }])
        self.now="2026-11-10T19:00:00Z"

    def entry(self,**change):
        row={
            "game_id":"2026_10_WAS_NYG","team":"NYG",
            "qb_id":"00-test","qb_name":"Test Starter",
            "source_url":"https://www.giants.com/news/specific-game-starter",
            "source_published_at_utc":"2026-11-10T16:00:00Z",
            "source_checked_at_utc":"2026-11-10T18:00:00Z",
            "source_reviewed":"true",
            "confirmation_kind":"coach_explicitly_names_starting_qb_for_game",
            "review_note":"Head coach explicitly names QB for the November 12 opponent."
        }
        row.update(change)
        return pd.DataFrame([row])

    def evaluate(self,**change):
        return validate_starter_confirmations(
            self.schedule,self.entry(**change),checked_as_of_utc=self.now
        )

    def test_explicit_content_review_can_pass_metadata_gate(self):
        accepted,log=self.evaluate()
        self.assertEqual(len(accepted),1)
        self.assertTrue(log.loc[0,"override_eligible"])
        self.assertEqual(log.loc[0,"eligibility_reason"],"explicit_reviewed_game_starter_confirmation")

    def test_missing_manual_review_fails_closed(self):
        accepted,log=self.evaluate(source_reviewed="false")
        self.assertTrue(accepted.empty)
        self.assertIn("source_content_not_reviewed",log.loc[0,"eligibility_reason"])

    def test_generic_article_cannot_confirm_this_game(self):
        accepted,log=self.evaluate(confirmation_kind="historic_roster_profile")
        self.assertTrue(accepted.empty)
        self.assertIn("source_does_not_explicitly_confirm_starter",log.loc[0,"eligibility_reason"])

    def test_stale_source_from_september_rejected(self):
        accepted,log=self.evaluate(source_published_at_utc="2026-09-21T20:00:00Z")
        self.assertTrue(accepted.empty)
        self.assertIn("metadata_not_current_or_invalid",log.loc[0,"eligibility_reason"])

    def test_review_timestamp_cannot_be_in_future(self):
        accepted,log=self.evaluate(source_checked_at_utc="2026-11-11T18:00:00Z")
        self.assertTrue(accepted.empty)
        self.assertIn("content_review_timestamp_in_future",log.loc[0,"eligibility_reason"])

    def test_review_cannot_predate_source_publication(self):
        accepted,log=self.evaluate(source_checked_at_utc="2026-11-10T15:00:00Z")
        self.assertTrue(accepted.empty)
        self.assertIn("content_review_before_source_publication",log.loc[0,"eligibility_reason"])

    def test_review_cannot_happen_after_kickoff(self):
        accepted,log=self.evaluate(source_checked_at_utc="2026-11-13T02:00:00Z")
        self.assertTrue(accepted.empty)
        self.assertIn("content_review_at_or_after_kickoff",log.loc[0,"eligibility_reason"])

    def test_team_does_not_match_game(self):
        accepted,log=self.evaluate(team="BUF")
        self.assertTrue(accepted.empty)
        self.assertIn("metadata_not_current_or_invalid",log.loc[0,"eligibility_reason"])

    def test_same_day_article_before_kickoff_is_not_automatically_rejected(self):
        # Use a future evaluation time so a same-day Thursday source can be reviewed.
        entry=self.entry(
            source_published_at_utc="2026-11-12T23:00:00Z",
            source_checked_at_utc="2026-11-13T00:30:00Z",
        )
        accepted,log=validate_starter_confirmations(
            self.schedule,entry,checked_as_of_utc="2026-11-13T00:45:00Z"
        )
        # 20:15 Eastern = 01:15Z next day
        self.assertEqual(len(accepted),1)
        self.assertTrue(log.loc[0,"override_eligible"])

    def test_missing_attestation_schema_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"missing required evidence"):
            validate_starter_confirmations(
                self.schedule,self.entry().drop(columns=["source_reviewed"]),
                checked_as_of_utc=self.now
            )

    def test_duplicate_confirmations_rejected(self):
        row=self.entry()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            validate_starter_confirmations(self.schedule,pd.concat([row,row]),
                                          checked_as_of_utc=self.now)


if __name__=="__main__":
    unittest.main()
