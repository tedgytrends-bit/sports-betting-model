"""Unit checks for source-vintage QA on purported confirmed QB starters."""
import unittest
import pandas as pd

from research.audit_qb_starter_source_metadata import audit, kickoff_utc


class QBSourceMetadataAuditTest(unittest.TestCase):
    def setUp(self):
        self.schedule = pd.DataFrame([
            {"game_id":"2026_09_A_B","gameday":"2026-11-08","gametime":"13:00","home_team":"B","away_team":"A"},
            {"game_id":"2026_01_C_D","gameday":"2026-09-06","gametime":"13:00","home_team":"D","away_team":"C"},
        ])

    def row(self, **changes):
        item={"game_id":"2026_09_A_B","team":"B","qb_id":"q1","qb_name":"QB 1",
              "source_url":"https://example.org/team/starting-qb",
              "source_published_at_utc":"2026-11-08T16:00:00Z"}
        item.update(changes)
        return pd.DataFrame([item])

    def test_day_of_game_source_before_actual_kickoff_is_eligible_metadata(self):
        # 13:00 Eastern in November is 18:00Z, so 16:00Z precedes kickoff.
        r=audit(self.schedule,self.row()).iloc[0]
        self.assertEqual(r.metadata_status,"recent_metadata_only_content_unverified")
        self.assertEqual(r.kickoff_utc,"2026-11-08T18:00:00+00:00")
        self.assertFalse(r.confirmed_matchup_starter)

    def test_kickoff_uses_dst_and_standard_time(self):
        self.assertEqual(kickoff_utc("2026-09-06","13:00").isoformat(),"2026-09-06T17:00:00+00:00")
        self.assertEqual(kickoff_utc("2026-11-08","13:00").isoformat(),"2026-11-08T18:00:00+00:00")

    def test_stale_article_flagged_not_confirmed(self):
        r=audit(self.schedule,self.row(source_published_at_utc="2026-09-21T20:29:00Z")).iloc[0]
        self.assertEqual(r.metadata_status,"stale_requires_manual_reconfirmation")
        self.assertIn("stale_older_than_one_week",r.flags)
        self.assertFalse(r.confirmed_matchup_starter)

    def test_after_kickoff_article_rejected(self):
        r=audit(self.schedule,self.row(source_published_at_utc="2026-11-08T18:01:00Z")).iloc[0]
        self.assertEqual(r.metadata_status,"invalid_metadata")
        self.assertIn("source_published_at_or_after_kickoff",r.flags)

    def test_wrong_team_and_game_rejected(self):
        for changes,expected in [
            ({"team":"C"},"team_not_in_matchup"),
            ({"game_id":"no_such_game"},"game_not_in_schedule"),
            ({"source_url":"http://example.org/qb"},"source_url_missing_or_non_https"),
            ({"qb_id":""},"qb_id_missing"),
        ]:
            with self.subTest(changes=changes):
                r=audit(self.schedule,self.row(**changes)).iloc[0]
                self.assertEqual(r.metadata_status,"invalid_metadata")
                self.assertIn(expected,r.flags)

    def test_duplicate_entry_rejected(self):
        frame=pd.concat([self.row(),self.row()],ignore_index=True)
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            audit(self.schedule,frame)


if __name__=="__main__":
    unittest.main()
