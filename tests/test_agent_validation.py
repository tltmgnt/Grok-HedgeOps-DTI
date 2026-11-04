"""Offline validation tests for the advisory agent response schema."""
import json
import unittest

from agent import ARRAY_FIELDS, REQUIRED_FIELDS, validate_report


class AgentValidationTests(unittest.TestCase):
    def test_valid_report(self):
        report = {key: [] if key in ARRAY_FIELDS else "UNKNOWN" for key in REQUIRED_FIELDS}
        self.assertEqual(validate_report(json.dumps(report)), report)

    def test_rejects_non_object(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            validate_report("[]")

    def test_rejects_invalid_json(self):
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            validate_report("{not-json}")

    def test_rejects_missing_fields(self):
        with self.assertRaisesRegex(ValueError, "missing fields"):
            validate_report('{"observation": "UNKNOWN"}')

    def test_rejects_wrong_array_type(self):
        report = {key: [] if key in ARRAY_FIELDS else "UNKNOWN" for key in REQUIRED_FIELDS}
        report["evidence"] = "unverified"
        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_report(json.dumps(report))


if __name__ == "__main__":
    unittest.main()
