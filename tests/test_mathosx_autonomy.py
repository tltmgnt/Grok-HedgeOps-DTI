"""Tests for a bounded autonomous theorem prover, reviewer gate, and code generator."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mathosx.autonomy import (
    PROGRAMS, KNOWN, _rows, check_certificate, derive, load_registry,
    novelty_audit, prove, recheck_records, render_generated, run,
    validate_problem,
)


class TestBoundedAutonomousProver(unittest.TestCase):
    def setUp(self):
        self.programs = load_registry(PROGRAMS, type_name="programs")
        self.known = load_registry(KNOWN, type_name="known claims")

    def test_xor_transitivity_has_replayable_proof(self):
        problem = self.programs[0]
        result = prove(problem)
        self.assertEqual(result["status"], "PROVED_FINITE_XOR_ENTAILMENT")
        rows, _ = _rows(problem, negate=True)
        self.assertTrue(check_certificate(
            rows, result["certificate_indices"], required_index=len(rows) - 1
        ))
        self.assertFalse(result["novelty_established"])

    def test_inconsistent_axioms_not_misreported_as_theorem(self):
        result = prove(self.programs[1])
        self.assertEqual(result["status"], "INCONSISTENT_AXIOMS")
        rows, _ = _rows(self.programs[1])
        self.assertTrue(check_certificate(rows, result["certificate_indices"]))

    def test_false_claim_yields_real_countermodel(self):
        result = prove(self.programs[2])
        self.assertEqual(result["status"], "COUNTERMODEL_FOUND")
        x = result["countermodel"]
        self.assertEqual(x["a"] ^ x["b"], 0)
        self.assertEqual(x["b"] ^ x["c"], 0)
        self.assertNotEqual(x["a"] ^ x["c"], 1)

    def test_longer_chain_proved(self):
        result = prove(self.programs[3])
        self.assertEqual(result["status"], "PROVED_FINITE_XOR_ENTAILMENT")

    def test_forged_and_incomplete_certificates_fail(self):
        problem = self.programs[0]
        rows, _ = _rows(problem, negate=True)
        self.assertFalse(check_certificate(rows, []))
        self.assertFalse(check_certificate(rows, [0, 0]))
        self.assertFalse(check_certificate(rows, [999]))
        self.assertFalse(check_certificate(rows, [0, 1], required_index=2))
        self.assertTrue(check_certificate(rows, [0, 1, 2], required_index=2))

    def test_rejects_invalid_and_unbounded_problems(self):
        for bad in (
            {"id": "x", "axioms": [], "conclusion": {"variables": [], "rhs": 0}},
            {"id": "x", "axioms": [{"variables": ["x"], "rhs": 2}],
             "conclusion": {"variables": ["x"], "rhs": 0}},
            {"id": "x", "axioms": [{"variables": ["x"], "rhs": True}],
             "conclusion": {"variables": ["x"], "rhs": 0}},
            {"id": "x", "axioms": [{"variables": ["x"], "rhs": 0}],
             "conclusion": {"variables": ["x"], "rhs": 0}, "certified": True},
            {"id": "x", "axioms": [{"variables": [str(i) for i in range(11)], "rhs": 0}],
             "conclusion": {"variables": [], "rhs": 0}},
        ):
            with self.subTest(case=bad):
                with self.assertRaises(ValueError):
                    validate_problem(bad)

    def test_duplicate_variables_cancel_exactly(self):
        problem = validate_problem({
            "id": "cancel", "axioms": [{"variables": ["x", "x"], "rhs": 0}],
            "conclusion": {"variables": [], "rhs": 0},
        })
        self.assertEqual(problem["axioms"][0]["variables"], [])
        self.assertEqual(prove(problem)["status"], "PROVED_FINITE_XOR_ENTAILMENT")

    def test_known_claim_is_not_novel(self):
        result = novelty_audit(self.programs[0], self.known)
        self.assertTrue(result["local_exact_match"])
        self.assertEqual(result["matching_known_ids"], ["known-xor-transitivity"])
        self.assertEqual(result["global_mathematical_novelty"], "NOT_ESTABLISHED")
        self.assertEqual(result["literature_review"], "NOT_PERFORMED")

    def test_absence_from_local_corpus_is_not_global_novelty(self):
        result = novelty_audit(self.programs[2], self.known)
        self.assertFalse(result["local_exact_match"])
        self.assertEqual(result["global_mathematical_novelty"], "NOT_ESTABLISHED")

    def test_bounded_autonomous_derivation_replays(self):
        report = run()
        derived = report["verified_finite_consequences"]
        self.assertGreater(len(derived), 0)
        self.assertTrue(recheck_records(derived))
        self.assertEqual(report["global_theorem_certification"], "NOT_CERTIFIED")
        self.assertFalse(report["automatic_merge"])
        self.assertTrue(all(
            entry["proof"]["status"] == "PROVED_FINITE_XOR_ENTAILMENT"
            for entry in derived
        ))

    def test_forged_proof_promotion_rejected(self):
        report = run()
        bad = json.loads(json.dumps(report["verified_finite_consequences"]))
        bad[0]["proof"]["certificate_indices"] = [0]
        self.assertFalse(recheck_records(bad))
        bad = json.loads(json.dumps(report["verified_finite_consequences"]))
        bad[0]["novelty"]["global_mathematical_novelty"] = "PROVED_NOVEL"
        self.assertFalse(recheck_records(bad))

    def test_generated_python_is_fixed_template_and_replayable(self):
        records = run()["verified_finite_consequences"]
        source = render_generated(records)
        self.assertEqual(source, render_generated(records))
        self.assertIn("FINITE_XOR_PROOF_RECORDS", source)
        self.assertNotIn("eval(", source)
        compile(source, "<generated-mathosx>", "exec")
        scope = {"__name__": "test_generated"}
        exec(compile(source, "<generated-mathosx>", "exec"), scope)
        self.assertTrue(scope["recheck"]())

    def test_invalid_registry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text(json.dumps({
                "schema_version": "1.0", "entries": self.programs,
                "certification": "PROVED",
            }))
            with self.assertRaises(ValueError):
                load_registry(p, type_name="programs")

    def test_cli_produces_report_and_no_global_novelty_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [sys.executable, "-m", "mathosx.autonomy",
                 "--output-dir", tmp],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "BOUNDED_FINITE_PROOFS_ONLY")
            self.assertEqual(
                summary["global_mathematical_novelty"], "NOT_ESTABLISHED"
            )
            report = json.loads(
                (Path(tmp) / "autonomous_proof_report.json").read_text()
            )
            self.assertEqual(report["global_theorem_certification"], "NOT_CERTIFIED")

    def test_new_axiom_system_creates_new_checked_code_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "programs.json"
            extra = {
                "id": "new-parity-chain",
                "axioms": [
                    {"variables": ["p", "q"], "rhs": 1},
                    {"variables": ["q", "r"], "rhs": 1},
                ],
                "conclusion": {"variables": ["p", "r"], "rhs": 0},
            }
            custom.write_text(json.dumps({
                "schema_version": "1.0",
                "entries": self.programs + [extra],
            }))
            augmented = derive(
                load_registry(custom, type_name="programs"), self.known
            )
            self.assertTrue(recheck_records(
                augmented["verified_finite_consequences"]
            ))
            self.assertNotEqual(
                render_generated(augmented["verified_finite_consequences"]),
                render_generated(run()["verified_finite_consequences"]),
            )


if __name__ == "__main__":
    unittest.main()
