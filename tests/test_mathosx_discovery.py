"""Regression and adversarial tests for the bounded MathOS × discovery loop."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mathosx.discovery import (
    DIRECTIONS, DEPTHS, abstraction_defects, build_report, catalog,
    load_feedback, parity_obstruction, record_feedback, run_benchmarks,
    search_abstractions,
)


class DiscoveryTests(unittest.TestCase):
    def test_all_directions_depths_and_frontiers_covered(self):
        questions = catalog()
        self.assertEqual(len(questions), 56)
        self.assertEqual(len({q.id for q in questions}), len(questions))
        self.assertEqual(
            {(q.direction, q.depth) for q in questions},
            {(a, b) for a in DIRECTIONS for b in DEPTHS},
        )
        self.assertTrue(all(q.falsification_case for q in questions))
        self.assertTrue(all(q.status == "OPEN_RESEARCH_QUESTION" for q in questions))

    def test_exact_and_inexact_abstractions(self):
        states = ("00", "01", "10", "11")
        macro = {s: s[0] for s in states}
        identity = {s: {s: 1} for s in states}
        xor = {s: {str(int(s[0]) ^ int(s[1])) + s[1]: 1} for s in states}
        output = abstraction_defects(states, macro, {"identity": identity, "xor": xor})
        self.assertFalse(output["exact"])
        self.assertEqual(output["defects"], {"identity": "0", "xor": "1"})
        self.assertEqual(output["optimal_error_lower_bound"], "1/2")
        self.assertEqual(output["optimal_error_upper_bound"], "1")
        self.assertEqual(output["witnesses"]["xor"]["states"], ["00", "01"])
        self.assertTrue(abstraction_defects(states, macro, {"id": identity})["exact"])

    def test_fractional_probability_bounds(self):
        states = ("a", "b", "c")
        macro = {"a": "0", "b": "0", "c": "1"}
        kernels = {"mixed": {
            "a": {"a": 1},
            "b": {"a": "1/2", "c": "1/2"},
            "c": {"c": 1},
        }}
        result = abstraction_defects(states, macro, kernels)
        self.assertEqual(result["worst_defect"], "1/2")
        self.assertEqual(result["optimal_error_lower_bound"], "1/4")
        self.assertEqual(result["optimal_error_upper_bound"], "1/2")

    def test_rejects_invalid_kernels(self):
        states = ("a", "b", "c")
        macro = {"a": "0", "b": "0", "c": "1"}
        for bad in (
            {"a": {"a": "1/2"}, "b": {"b": 1}, "c": {"c": 1}},
            {"a": {"a": -1, "b": 2}, "b": {"b": 1}, "c": {"c": 1}},
            {"a": {"z": 1}, "b": {"b": 1}, "c": {"c": 1}},
            {"a": {"a": True}, "b": {"b": 1}, "c": {"c": 1}},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    abstraction_defects(states, macro, {"bad": bad})

    def test_exhaustive_canonical_quotients(self):
        states = ("a", "b", "c", "d")
        identity = {s: {s: 1} for s in states}
        candidates = search_abstractions(states, {"id": identity}, limit=100)
        # 7 partitions into 2 blocks and 6 into 3 blocks.
        self.assertEqual(len(candidates), 13)
        self.assertTrue(all(candidate["exact"] for candidate in candidates))
        self.assertEqual(candidates[0]["macrostates"], 2)
        self.assertEqual(
            len({tuple(c["macro"][s] for s in states) for c in candidates}),
            13,
        )

    def test_abstraction_search_bounded(self):
        with self.assertRaises(ValueError):
            search_abstractions(tuple(str(i) for i in range(8)), {})

    def test_global_parity_obstruction(self):
        result = parity_obstruction([
            (("a", "b"), 1),
            (("b", "c"), 1),
            (("a", "c"), 1),
        ])
        self.assertFalse(result["satisfiable"])
        self.assertEqual(result["deletion_minimal_core"], [0, 1, 2])
        self.assertTrue(result["every_single_deletion_satisfiable"])

    def test_satisfiable_parity_and_repeated_variables(self):
        self.assertTrue(parity_obstruction([(("a", "b"), 1)])["satisfiable"])
        contradictory = parity_obstruction([(("a", "a"), 1)])
        self.assertFalse(contradictory["satisfiable"])
        self.assertEqual(contradictory["deletion_minimal_core"], [0])

    def test_benchmark_results_are_finite_and_scoped(self):
        results = run_benchmarks()
        self.assertTrue(results["abstraction"]["passed"])
        self.assertTrue(results["parity_gluing"]["passed"])
        self.assertEqual(
            results["parity_gluing"]["evidence"]["scope"],
            "finite parity contradiction; not a general gluing theorem",
        )

    def test_human_feedback_changes_ranking_without_claiming_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feedback.json"
            question_id = "causal-abstraction:invent:research"
            before = build_report(path, limit=56)
            score_before = next(
                x["priority_score"] for x in before["questions"]
                if x["id"] == question_id
            )
            record_feedback(
                path, question_id, "useful", "evaluation/experiment-001.json",
                "local-human-review",
            )
            after = build_report(path, limit=56)
            score_after = next(
                x["priority_score"] for x in after["questions"]
                if x["id"] == question_id
            )
            self.assertGreater(score_after, score_before)
            self.assertEqual(after["questions"][0]["id"], question_id)
            self.assertEqual(after["feedback_samples"], 1)
            self.assertEqual(after["certification"], "NOT_CERTIFIED")
            self.assertFalse(after["automatic_code_modification"])
            self.assertFalse(after["questions"][0]["proof_verified"])
            self.assertFalse(after["questions"][0]["novelty_verified"])

    def test_negative_feedback_lowers_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rating.json"
            question = "emergence:foundations:radical"
            record_feedback(path, question, "not_useful", "exp-3", "reviewer-x")
            report = build_report(path, limit=56)
            observed = next(q for q in report["questions"] if q["id"] == question)
            self.assertLess(observed["priority_score"], 0.65)

    def test_duplicate_evidence_cannot_be_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rating.json"
            question = "emergence:invent:research"
            record_feedback(path, question, "useful", "exp-1", "reviewer")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                record_feedback(path, question, "useful", "exp-1", "reviewer")
            self.assertEqual(original, path.read_bytes())
            self.assertEqual(len(load_feedback(path)["ratings"]), 1)

    def test_reject_forged_verification_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rating.json"
            path.write_text(json.dumps({
                "schema_version": "1.0", "ratings": [],
                "certification": "PROVED",
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_report(path)

    def test_filter_and_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_report(
                Path(tmp) / "empty.json", direction="unify", depth="radical",
                limit=7,
            )
            self.assertEqual(len(result["questions"]), 7)
            self.assertTrue(all(
                q["direction"] == "unify" and q["depth"] == "radical"
                for q in result["questions"]
            ))
            self.assertEqual(json.loads(json.dumps(result)), result)

    def test_module_cli_offline_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "-m", "mathosx.discovery",
                 "--limit", "2", "--output-dir", tmp],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(len(output["questions"]), 2)
            report_file = Path(tmp) / "discovery_report.json"
            self.assertEqual(json.loads(report_file.read_text()), output)


if __name__ == "__main__":
    unittest.main()
