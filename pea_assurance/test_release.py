"""Synthetic failure controls for the release consistency checker."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pea_assurance.verify_release import REQUIRED_FILES, VERSION, verify_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in REQUIRED_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic integrity fixture\n", encoding="utf-8")
        paper = self.root / "docs/researchos/TECT_WHITE_PAPER.md"
        paper.write_text("synthetic paper\n", encoding="utf-8")
        self.release = {"schema_version": 1, "version": VERSION,
                        "repository": "tltmgnt/synthetic", "canonical_repository": "tltmgnt/ResearchOs",
                        "domain": "synthetic", "domain_adapter_integrated": False,
                        "empirically_validated": False,
                        "files_sha256": {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                                         for name in REQUIRED_FILES}}
        self.integration = {"repository": "tltmgnt/synthetic", "domain": "synthetic",
                            "paper_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                            "pea": {"version": VERSION, "live_controller_adapter_implemented": False,
                                    "independent_empirical_evaluation_completed": False}}
        self.save()

    def save(self):
        (self.root / "pea_assurance/release.json").write_text(json.dumps(self.release), encoding="utf-8")
        (self.root / "docs/researchos/integration.json").write_text(json.dumps(self.integration), encoding="utf-8")

    def verify(self):
        return verify_release(self.root, "tltmgnt/synthetic")

    def test_valid(self):
        result = self.verify()
        self.assertEqual(result["verified_files"], len(REQUIRED_FILES))
        self.assertFalse(result["scientific_validity_established"])
        self.assertFalse(result["source_authenticated"])

    def test_tamper_and_missing(self):
        path = self.root / "pea_assurance/measurement.py"
        path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.verify()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing or escaping"):
            self.verify()

    def test_inventory_cannot_omit_or_escape(self):
        del self.release["files_sha256"]["pea_assurance/measurement.py"]
        self.save()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            self.verify()
        self.release["files_sha256"]["../outside"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            self.verify()

    def test_symlink_escape(self):
        path = self.root / "pea_assurance/measurement.py"
        path.unlink()
        path.symlink_to(self.root.parent / "outside")
        with self.assertRaisesRegex(ValueError, "missing or escaping"):
            self.verify()

    def test_repository_and_version(self):
        with self.assertRaisesRegex(ValueError, "repository mismatch"):
            verify_release(self.root, "tltmgnt/other")
        self.release["version"] = "9.0.0"
        self.save()
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            self.verify()

    def test_false_validation_claim(self):
        self.release["empirically_validated"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "not established"):
            self.verify()

    def test_digest_format(self):
        self.release["files_sha256"]["pea_assurance/measurement.py"] = "invalid"
        self.save()
        with self.assertRaisesRegex(ValueError, "invalid digest"):
            self.verify()

    def test_integration_scope(self):
        self.integration["pea"]["live_controller_adapter_implemented"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            self.verify()

    def test_paper_drift(self):
        (self.root / "docs/researchos/TECT_WHITE_PAPER.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "white paper digest mismatch"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
