"""Small, dependency-free diagnostics with explicit undefined-value semantics."""
import math
from collections import Counter


def _probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("probabilities must be finite numbers in [0, 1]")
    return float(value)


def calibration(probabilities, outcomes, bins=10):
    """Binary Brier score and equal-width ECE against external adjudication.

    No automatic calibration fitting, missing-label imputation, independence
    inference, or empirical validity claim is made by these diagnostics.
    """
    if type(bins) is not int or not 1 <= bins <= 1000:
        raise ValueError("bins must be an integer in [1, 1000]")
    p, y = list(probabilities), list(outcomes)
    if len(p) != len(y):
        raise ValueError("probabilities and outcomes must have equal length")
    p = [_probability(v) for v in p]
    if any(type(v) is not int or v not in (0, 1) for v in y):
        raise ValueError("outcomes must be adjudicated integers 0 or 1; omit unresolved cases explicitly")
    n = len(p)
    cells = [[] for _ in range(bins)]
    for confidence, outcome in zip(p, y):
        cells[min(int(confidence * bins), bins - 1)].append((confidence, outcome))
    table = []
    for i, cell in enumerate(cells):
        count = len(cell)
        table.append({"lower": i / bins, "upper": (i + 1) / bins, "n": count,
                      "mean_probability": sum(v[0] for v in cell) / count if count else None,
                      "observed_frequency": sum(v[1] for v in cell) / count if count else None})
    return {"n": n, "brier": sum((a-b)**2 for a, b in zip(p, y)) / n if n else None,
            "ece": sum(c["n"] * abs(c["mean_probability"] - c["observed_frequency"])
                       for c in table if c["n"]) / n if n else None,
            "bins": table, "status": "descriptive_only" if n else "insufficient_data"}


def agreement(first, second):
    """Paired categorical agreement and Cohen kappa; undefined kappa is None.

    Call separately for evaluator pairs and repeat trials on aligned item IDs.
    Agreement does not establish correctness or authenticate evaluator identity.
    """
    a, b = list(first), list(second)
    if len(a) != len(b):
        raise ValueError("ratings must be aligned and have equal length")
    if any(not isinstance(x, str) or not x.strip() for x in a+b):
        raise ValueError("ratings must be nonempty category strings")
    n = len(a)
    if not n:
        return {"n": 0, "observed_agreement": None, "kappa": None, "status": "insufficient_data"}
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[x] * cb[x] for x in ca.keys() | cb.keys()) / (n*n)
    return {"n": n, "observed_agreement": observed,
            "kappa": (observed - expected) / (1 - expected) if expected < 1 else None,
            "status": "descriptive_only" if expected < 1 else "degenerate_marginals"}


def scoped_decision(*, claim_id, scope, policy_version, evidence_refs, checks):
    """Advisory gate aggregation, never a production TECT state transition.

    Required externally evaluated checks: validity, calibration, provenance,
    reproduction, adversarial, governance. No numerical score can override them.
    FAIL rejects a promotion under this policy, rather than proving a claim false.
    """
    for name, value in (("claim_id", claim_id), ("scope", scope), ("policy_version", policy_version)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " must be a nonempty string")
    if not isinstance(evidence_refs, list) or any(not isinstance(x, str) or not x.strip() for x in evidence_refs):
        raise ValueError("evidence_refs must be a list of nonempty references")
    required = ("validity", "calibration", "provenance", "reproduction", "adversarial", "governance")
    if not isinstance(checks, dict) or set(checks) - set(required):
        raise ValueError("unknown check names")
    allowed = ("PASS", "FAIL", "UNCERTAIN", "ERROR", "SKIPPED")
    if any(v not in allowed for v in checks.values()):
        raise ValueError("invalid check status")
    normalized = {key: checks.get(key, "UNCERTAIN") for key in required}
    failed = [key for key, value in normalized.items() if value == "FAIL"]
    unresolved = [key for key, value in normalized.items() if value not in ("PASS", "FAIL")]
    decision = "rejected" if failed else "uncertain" if unresolved or not evidence_refs else "accepted"
    return {"schema_version": 1, "claim_id": claim_id, "scope": scope,
            "policy_version": policy_version, "evidence_refs": list(evidence_refs),
            "checks": normalized, "decision": decision, "failed": failed,
            "unresolved": unresolved, "missing_evidence": not bool(evidence_refs),
            "advisory_only": True, "empirically_validated": False}
