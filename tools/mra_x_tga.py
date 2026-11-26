"""MRA-X 2.0 | TGA Research Intelligence Engine (MRA-X-TGA-2.0).
Offline, dependency-free reference policy; Python 3.9+. Run --self-test.
Architecture target 10/10, certification pending independent validation.
Evaluate a JSON research record with --record PATH; no external actions or
proof promotion. Evidence hashes establish consistency, not truth or origin.
Host adapters, independent review and formal verification remain separate.
"""
import argparse
import hashlib
import json
import unittest
from pathlib import Path

SYSTEM_ID = "MRA-X-TGA-2.0"
REQUIRED = ("claim", "hypothesis", "counterexample", "mechanism", "success_criterion",
            "falsifier", "baseline", "stopping_rule")
RESOURCES = ("calls", "tokens", "cost_microunits")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evaluate(record):
    """Advisory decision only. Invalid or incomplete inputs fail closed."""
    def result(status, reasons):
        return {"system_id": SYSTEM_ID, "status": status, "reasons": reasons,
                "authorizes_execution": False, "theorem_promoted": False}
    if not isinstance(record, dict):
        return result("STOP", ["record must be an object"])
    missing = [k for k in REQUIRED if not isinstance(record.get(k), str) or not record[k].strip()]
    if missing:
        return result("DECOMPOSE", ["missing: " + ", ".join(missing)])
    if type(record.get("mission_stopped")) is not bool or type(record.get("refuted")) is not bool:
        return result("STOP", ["explicit Boolean mission_stopped and refuted required"])
    if record["refuted"]:
        return result("RETIRE", ["refutation reported; independent review required"])
    history = record.get("prior_claim_hashes")
    if not isinstance(history, list) or any(not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h) for h in history):
        return result("STOP", ["invalid or missing exact-claim history"])
    claim_hash = digest(record["claim"])
    if claim_hash in history:
        return result("STOP", ["exact claim already recorded"])
    if record["mission_stopped"] and record.get("new_hypothesis") is not True:
        return result("STOP", ["new falsifiable hypothesis required after planned stop"])
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return result("DECOMPOSE", ["evidence snapshots required"])
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str) or not item["content"].strip() or digest(item["content"]) != item.get("sha256"):
            return result("STOP", ["invalid evidence snapshot or hash mismatch"])
    budget = record.get("budget")
    used = record.get("used")
    reserve = record.get("reserve")
    if any(not isinstance(x, dict) for x in (budget, used, reserve)):
        return result("STOP", ["budget, used and reserve required"])
    for key in RESOURCES:
        values = [x.get(key) for x in (budget, used, reserve)]
        if any(type(v) is not int or v < 0 for v in values):
            return result("STOP", ["invalid resource: " + key])
        if values[1] + values[2] > values[0]:
            return result("STOP", ["budget exceeded: " + key])
    obligations = record.get("obligations")
    if not isinstance(obligations, list) or not obligations or any(not isinstance(o, str) or not o.strip() for o in obligations):
        return result("DECOMPOSE", ["explicit proof or review obligations required"])
    return result("REVIEW_CANDIDATE", ["structural checks passed; human review required; novelty and soundness not established"])


def example():
    record = {k: "synthetic example: " + k for k in REQUIRED}
    record.update(mission_stopped=True, new_hypothesis=True, refuted=False,
                  prior_claim_hashes=[], evidence=[{"content": "synthetic evidence", "sha256": digest("synthetic evidence")}],
                  budget=dict(zip(RESOURCES, (5, 100, 100))),
                  used=dict(zip(RESOURCES, (1, 10, 10))),
                  reserve=dict(zip(RESOURCES, (1, 10, 10))),
                  obligations=["independently verify claim"])
    return record


class PolicyTests(unittest.TestCase):
    def test_valid(self):
        r = evaluate(example())
        self.assertEqual(r["status"], "REVIEW_CANDIDATE")
        self.assertFalse(r["authorizes_execution"])
        self.assertFalse(r["theorem_promoted"])
    def test_missing(self):
        self.assertEqual(evaluate({})["status"], "DECOMPOSE")
    def test_tamper(self):
        r = example(); r["evidence"][0]["content"] = "changed"
        self.assertEqual(evaluate(r)["status"], "STOP")
    def test_duplicate(self):
        r = example(); r["prior_claim_hashes"] = [digest(r["claim"])]
        self.assertEqual(evaluate(r)["status"], "STOP")
    def test_reopen(self):
        r = example(); r["new_hypothesis"] = False
        self.assertEqual(evaluate(r)["status"], "STOP")
    def test_budget(self):
        r = example(); r["reserve"]["calls"] = 5
        self.assertEqual(evaluate(r)["status"], "STOP")
    def test_boolean_budget(self):
        r = example(); r["used"]["calls"] = False
        self.assertEqual(evaluate(r)["status"], "STOP")
    def test_refutation(self):
        r = example(); r["refuted"] = True
        self.assertEqual(evaluate(r)["status"], "RETIRE")
    def test_obligations(self):
        r = example(); r["obligations"] = []
        self.assertEqual(evaluate(r)["status"], "DECOMPOSE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--example", action="store_true")
    group.add_argument("--record", type=Path)
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PolicyTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.example:
        print(json.dumps(example(), indent=2)); return 0
    try:
        record = json.loads(args.record.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    result = evaluate(record)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "REVIEW_CANDIDATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
