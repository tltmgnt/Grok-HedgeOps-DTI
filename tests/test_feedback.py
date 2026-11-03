import unittest
from hedgeops.feedback import FeedbackEngine


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.engine = FeedbackEngine()
        self.identifier = self.engine.propose(
            "Deployment reduces latency", "latency", 100, 10, "ms")

    def test_within_tolerance(self):
        status = self.engine.observe(self.identifier, 108, "metrics.csv", "analyst")
        self.assertEqual(status, "within_tolerance")
        self.assertFalse(self.engine.predictions[self.identifier]["measurement"]["source_verified"])
        self.assertEqual(len(self.engine.events), 2)

    def test_outside_tolerance(self):
        self.assertEqual(self.engine.observe(self.identifier, 130, "metrics.csv", "analyst"),
                         "outside_tolerance")

    def test_duplicate_observation_blocked(self):
        self.engine.observe(self.identifier, 100, "metrics.csv", "analyst")
        with self.assertRaises(ValueError):
            self.engine.observe(self.identifier, 100, "metrics.csv", "analyst")

    def test_missing_source_blocked(self):
        with self.assertRaises(ValueError):
            self.engine.observe(self.identifier, 100, "", "analyst")

    def test_invalid_tolerance_blocked(self):
        with self.assertRaises(ValueError):
            self.engine.propose("H", "m", 100, -1, "ms")


if __name__ == "__main__":
    unittest.main()
