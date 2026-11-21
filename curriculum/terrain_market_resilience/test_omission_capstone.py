import unittest
from omission_capstone import run


class OmissionCapstoneTests(unittest.TestCase):
    def test_exhaustive_coverage_and_controls(self):
        report = run()
        self.assertEqual(report["enumerated_masks"], 64)
        counts = report["one_removal_comparisons"]
        self.assertEqual(sum(counts.values()), 6 * 2**5)
        self.assertTrue(all(value > 0 for value in counts.values()))
        self.assertEqual(report["missing_data_control"],
                         {"observed": 9, "excluded": None, "zero_filled": 3})
        self.assertEqual(report["count_of_90_cell_masks"], 1 << 90)
