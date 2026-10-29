"""Regression tests for the prospective audit's apply-result normalization."""
import unittest

import numpy as np
import pandas as pd


def assign_grade_values(odds_index, selected_index, grades, source_col):
    """Normalize apply(axis=1) dict-Series before assigning values to odds rows."""
    grade_values = pd.DataFrame(grades.tolist(), index=selected_index)
    full_values = pd.Series(np.nan, index=odds_index, dtype="object")
    if source_col == "result":
        values = grade_values[source_col].fillna("Not gradable").astype(str).to_numpy()
    else:
        values = pd.to_numeric(
            grade_values[source_col], errors="coerce"
        ).astype("float64").to_numpy()
    full_values.loc[selected_index] = values
    return full_values


class GradeAssignmentTests(unittest.TestCase):
    def test_series_of_dicts_assigns_result_and_numeric_fields(self):
        index = pd.Index([2, 5])
        grades = pd.Series([
            {"result": "Win", "net_units": 0.9090909, "units_risked": 1.0},
            {"result": "Pending/Not eligible", "net_units": np.nan, "units_risked": np.nan},
        ], index=index)
        full_index = pd.Index([0, 2, 5, 8])
        results = assign_grade_values(full_index, index, grades, "result")
        net = assign_grade_values(full_index, index, grades, "net_units")
        risk = assign_grade_values(full_index, index, grades, "units_risked")
        self.assertEqual(results.loc[2], "Win")
        self.assertEqual(results.loc[5], "Pending/Not eligible")
        self.assertTrue(pd.isna(results.loc[0]))
        self.assertAlmostEqual(float(net.loc[2]), 0.9090909)
        self.assertAlmostEqual(float(risk.loc[2]), 1.0)
        self.assertTrue(pd.isna(net.loc[5]))
        self.assertTrue(pd.isna(risk.loc[5]))
        self.assertTrue(pd.isna(net.loc[8]))


if __name__ == "__main__":
    unittest.main()
