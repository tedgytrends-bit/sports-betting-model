"""Policy test: derived directional grades must not masquerade as originally published picks."""
import unittest
from pathlib import Path
from scripts.build_full_directional_results import grade,read,ROOT

class FullDirectionalTests(unittest.TestCase):
    def test_grade_both_sides_without_using_result_to_select_direction(self):
        self.assertEqual(grade("Over",49,46),"Win")
        self.assertEqual(grade("Under",49,46),"Loss")
        self.assertEqual(grade("Under",39,46),"Win")
        self.assertEqual(grade("Over",46,46),"Push")
        self.assertEqual(grade("Over",None,46),"Pending")

    def test_original_week8_tie_is_immutable(self):
        original=read(ROOT/"data"/"public_results"/"nfl_2026_graded_games.csv")
        match=[r for r in original if r["game_id"]=="2026_08_IND_JAX" and r["model"]=="injury"]
        self.assertEqual(len(match),1)
        self.assertEqual(match[0]["total_pick"],"No lean")
        self.assertEqual(match[0]["total_result"],"No lean")
        self.assertEqual(match[0]["projected_total"],"46.0")
        self.assertEqual(match[0]["bovada_total"],"46.0")
        self.assertEqual(int(match[0]["actual_away"])+int(match[0]["actual_home"]),49)
        published_baseline=[r for r in original if r["game_id"]=="2026_08_IND_JAX"
                            and r["model"]=="baseline" and r["record_class"]=="PUBLIC_PUBLISHED"]
        self.assertEqual(len(published_baseline),1)
        self.assertEqual(published_baseline[0]["total_pick"],"Over")
        self.assertEqual(published_baseline[0]["projected_total"],"46.9")
        self.assertEqual(published_baseline[0]["total_result"],"Win")

if __name__=="__main__":
    unittest.main()
