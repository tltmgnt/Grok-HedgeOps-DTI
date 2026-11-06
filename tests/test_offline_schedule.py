import unittest
from datetime import datetime, timezone
from scripts.offline_schedule import decide

class OfflineScheduleTests(unittest.TestCase):
    def check(self, cron, date):
        return decide("schedule", cron, datetime.fromisoformat(date).replace(tzinfo=timezone.utc))
    def test_winter_9am(self):
        self.assertEqual(self.check("0 17 * * *", "2026-11-06T17:00:00")[0], True)
        self.assertEqual(self.check("0 16 * * *", "2026-11-06T16:00:00")[1], "DST_ALTERNATE_CRON")
    def test_summer_9am(self):
        self.assertEqual(self.check("0 16 * * *", "2026-07-06T16:00:00")[0], True)
        self.assertEqual(self.check("0 17 * * *", "2026-07-06T17:00:00")[0], False)
    def test_manual_always_runs(self):
        self.assertEqual(decide("workflow_dispatch", "", datetime.now(timezone.utc))[0], True)
    def test_unknown_cron_fails_closed(self):
        self.assertEqual(self.check("0 18 * * *", "2026-11-06T18:00:00")[0], False)

if __name__ == "__main__":
    unittest.main()
