"""Phase 37 alert thresholds, deltas, resets and privacy tests."""
import unittest

from hedgeops.custody_alerts import AlertThresholds, CustodyAlertMonitor
from hedgeops.custody_metrics import CustodyMetrics


class FakeServer:
    rejected_connections = 0


class CustodyAlertTests(unittest.TestCase):
    def setUp(self):
        self.metrics = CustodyMetrics()
        self.server = FakeServer()
        self.monitor = CustodyAlertMonitor(AlertThresholds(
            authentication_failures=2, rate_limited=2,
            service_unavailable=1, connection_rejections=1))

    def test_first_sample_is_baseline(self):
        self.metrics.record("GET", "health", 401)
        result = self.monitor.sample(self.metrics, self.server)
        self.assertTrue(result["baseline"])
        self.assertEqual(result["alerts"], [])

    def test_authentication_threshold(self):
        self.monitor.sample(self.metrics, self.server)
        self.metrics.record("GET", "health", 401)
        self.metrics.record("PUT", "receipt", 401)
        result = self.monitor.sample(self.metrics, self.server)
        self.assertEqual(result["alerts"][0]["event"], "authentication_failures")
        self.assertEqual(result["alerts"][0]["count"], 2)

    def test_rate_limit_threshold(self):
        self.monitor.sample(self.metrics, self.server)
        for _ in range(2):
            self.metrics.record("GET", "health", 429)
        result = self.monitor.sample(self.metrics, self.server)
        self.assertEqual(result["alerts"][0]["event"], "rate_limited")
        self.assertEqual(result["alerts"][0]["count"], 2)

    def test_database_failure_alert(self):
        self.monitor.sample(self.metrics, self.server)
        self.metrics.record("PUT", "receipt", 503)
        self.assertEqual(self.monitor.sample(self.metrics, self.server)["alerts"][0]["event"],
                         "service_unavailable")

    def test_connection_rejection_alert(self):
        self.monitor.sample(self.metrics, self.server)
        self.server.rejected_connections += 1
        self.assertEqual(self.monitor.sample(self.metrics, self.server)["alerts"][0]["event"],
                         "connection_rejections")

    def test_no_repeat_alert_without_new_events(self):
        self.monitor.sample(self.metrics, self.server)
        self.metrics.record("PUT", "receipt", 503)
        self.assertEqual(len(self.monitor.sample(self.metrics, self.server)["alerts"]), 1)
        self.assertEqual(self.monitor.sample(self.metrics, self.server)["alerts"], [])

    def test_counter_reset_requires_new_baseline(self):
        self.monitor.sample(self.metrics, self.server)
        self.metrics.record("GET", "health", 401)
        self.monitor.sample(self.metrics, self.server)
        self.metrics = CustodyMetrics()
        result = self.monitor.sample(self.metrics, self.server)
        self.assertTrue(result["counter_reset"])
        self.assertEqual(result["alerts"], [])

    def test_invalid_thresholds(self):
        for bad in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                AlertThresholds(authentication_failures=bad)

    def test_alert_payload_has_no_secret_dimensions(self):
        self.monitor.sample(self.metrics, self.server)
        self.metrics.record("GET", "health", 503)
        result = self.monitor.sample(self.metrics, self.server)
        self.assertEqual(set(result["alerts"][0]), {"event", "count", "threshold"})

    def test_all_event_types_sorted_deterministically(self):
        self.monitor.sample(self.metrics, self.server)
        for _ in range(2):
            self.metrics.record("GET", "health", 401)
            self.metrics.record("PUT", "receipt", 429)
        self.metrics.record("PUT", "receipt", 503)
        self.server.rejected_connections = 1
        events = [row["event"] for row in self.monitor.sample(
            self.metrics, self.server)["alerts"]]
        self.assertEqual(events, ["authentication_failures", "rate_limited",
                                  "service_unavailable", "connection_rejections"])


if __name__ == "__main__":
    unittest.main()
