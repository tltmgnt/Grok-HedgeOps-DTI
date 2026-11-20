"""MathOS ×: bounded, feedback-driven mathematical question discovery.

This is an offline research *scheduler*, not a theorem prover or an AI model.
Human-labeled usefulness updates future ranking; counterexample probes provide
finite evidence only. Nothing here promotes proof, novelty, or Clay status.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
from itertools import combinations
import json
import math
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEEDBACK = ROOT / "mathosx/feedback.v1.json"
DIRECTIONS = ("invent", "conjecture", "unify", "foundations")
DEPTHS = ("research", "radical")

# Each frontier records a particular mathematical target and a testable boundary.
FRONTIERS = (
    ("causal-abstraction", "Interventional geometry",
     "intervention-preserving quotients of finite stochastic systems",
     "two-bit XOR intervention versus a first-bit coarse-graining",
     "Markov lumpability, causal abstraction, and total variation",
     "Could causation be more fundamental than an observed state?"),
    ("emergence", "Emergence invariant theory",
     "invariants that survive specified changes of coarse-graining",
     "nonisomorphic microstates with identical summary statistics",
     "multiscale dynamics, information theory, and invariant theory",
     "Can emergence be defined without privileging an observer?"),
    ("theory-space", "Theory-space geometry",
     "distances between formal theories under conservative interpretations",
     "a pair of finite axiom systems with different consequence sets",
     "model theory, category theory, and interpretation logic",
     "What if whole theories were geometric points?"),
    ("proof-space", "Proof-space dynamics",
     "representation-robust measures of proof-search difficulty",
     "equivalent finite proof systems with unequal shortest derivations",
     "proof complexity, graph search, and formal logic",
     "What if invention changes the geometry of what is provable?"),
    ("information-time", "Informational temporality",
     "invariants of filtrations beyond one-time distributions",
     "two processes with equal marginals but different dependence",
     "stochastic filtrations, entropy, and temporal logic",
     "What if temporal order is fundamentally informational?"),
    ("endogenous-law", "Endogenous law dynamics",
     "invariants of systems whose transition rules depend on state",
     "a rule-changing model embedded as a fixed enlarged-state map",
     "adaptive dynamical systems, automata, and state augmentation",
     "When does a rule count as distinct from the state it governs?"),
    ("explanation-obstruction", "Explanation obstruction theory",
     "global compatibility of locally satisfiable causal constraints",
     "a triangle of pairwise odd binary parity equations",
     "sheaf-theoretic contextuality, graph cohomology, and SAT",
     "Can locally valid explanations be globally impossible?"),
)

DIRECTION_PROTOCOL = {
    "invent": "Define a candidate object or invariant for {target}; state its domain and one computable example.",
    "conjecture": "Formulate a quantified, falsifiable conjecture about {target}; seek the smallest counterexample.",
    "unify": "Construct or refute an explicit bridge from {background} to {target}, preserving a declared operation.",
    "foundations": "Identify a necessary assumption behind {target}; remove it and construct a countermodel.",
}


@dataclass(frozen=True)
class Question:
    id: str
    frontier: str
    direction: str
    depth: str
    title: str
    question: str
    falsification_case: str
    prior_art_neighborhood: str
    status: str = "OPEN_RESEARCH_QUESTION"


def catalog() -> tuple[Question, ...]:
    """Seven frontiers x four directions x two depths = 56 traceable prompts."""
    items = []
    for key, title, target, case, background, radical in FRONTIERS:
        for direction in DIRECTIONS:
            for depth in DEPTHS:
                statement = DIRECTION_PROTOCOL[direction].format(
                    target=target, background=background
                )
                if depth == "research":
                    statement += (
                        " Give exact definitions, scope, quantifiers, a proof plan, "
                        "and a falsifiable finite test."
                    )
                else:
                    statement = (
                        radical + " " + statement +
                        " Challenge the conventional primitives, then give a "
                        "specific finite model capable of refuting the proposal."
                    )
                items.append(Question(
                    id=f"{key}:{direction}:{depth}", frontier=key,
                    direction=direction, depth=depth, title=title,
                    question=statement, falsification_case=case,
                    prior_art_neighborhood=background,
                ))
    return tuple(items)


QUESTION_IDS = frozenset(q.id for q in catalog())


def _weight(value: object) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("probability weights must be numbers, not booleans")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise ValueError("invalid rational probability") from exc
    if result < 0 or result > 1:
        raise ValueError("probabilities must lie in [0, 1]")
    return result


def abstraction_defects(
    states: tuple[str, ...],
    macro: dict[str, str],
    kernels: dict[str, dict[str, dict[str, object]]],
) -> dict:
    """Exact finite interventional lumpability defects in total variation.

    All transition rows must be complete probability distributions.
    The reported [D/2, D] interval bounds optimal uniform macro error,
    but does not claim to compute that optimum.
    """
    if not 1 <= len(states) <= 12 or len(set(states)) != len(states):
        raise ValueError("states must be 1..12 distinct identifiers")
    if not all(isinstance(s, str) and s for s in states):
        raise ValueError("state identifiers must be nonempty strings")
    if set(macro) != set(states) or not all(
        isinstance(v, str) and v for v in macro.values()
    ):
        raise ValueError("macro must map every state to a nonempty label")
    if not kernels or not isinstance(kernels, dict):
        raise ValueError("at least one intervention kernel is required")
    fibers: dict[str, list[str]] = {}
    for state in states:
        fibers.setdefault(macro[state], []).append(state)

    defects: dict[str, str] = {}
    witness: dict[str, object] = {}
    for action, kernel in kernels.items():
        if not isinstance(action, str) or not action or set(kernel) != set(states):
            raise ValueError("each intervention must cover all source states")
        projections: dict[str, dict[str, Fraction]] = {}
        for state in states:
            row = kernel[state]
            if not isinstance(row, dict) or not row or not set(row).issubset(states):
                raise ValueError("transition destination outside the state space")
            weights = {dest: _weight(p) for dest, p in row.items()}
            if sum(weights.values(), Fraction(0)) != 1:
                raise ValueError("every transition row must sum exactly to one")
            projected: dict[str, Fraction] = {}
            for dest, probability in weights.items():
                label = macro[dest]
                projected[label] = projected.get(label, Fraction(0)) + probability
            projections[state] = projected

        largest = Fraction(0)
        pair = None
        for fiber in fibers.values():
            for left, right in combinations(fiber, 2):
                first, second = projections[left], projections[right]
                labels = set(first) | set(second)
                distance = sum(
                    (abs(first.get(y, 0) - second.get(y, 0)) for y in labels),
                    Fraction(0),
                ) / 2
                if distance > largest:
                    largest = distance
                    pair = [left, right]
        defects[action] = str(largest)
        if pair is not None:
            witness[action] = {
                "states": pair,
                "macrostate": macro[pair[0]],
                "projected_distributions": [
                    {k: str(v) for k, v in projections[s].items()} for s in pair
                ],
            }
    worst = max(Fraction(v) for v in defects.values())
    return {
        "exact": worst == 0,
        "defects": defects,
        "worst_defect": str(worst),
        "optimal_error_lower_bound": str(worst / 2),
        "optimal_error_upper_bound": str(worst),
        "witnesses": witness,
        "scope": "finite supplied interventions; no universal causal theorem",
    }


def _partitions(n: int, k: int):
    """Canonical surjective labelings (restricted growth strings)."""
    def grow(prefix: tuple[int, ...], used: int):
        if len(prefix) == n:
            if used == k:
                yield prefix
            return
        if n - len(prefix) < k - used:
            return
        for label in range(min(used + 1, k)):
            yield from grow(prefix + (label,), max(used, label + 1))
    yield from grow((0,), 1)


def search_abstractions(
    states: tuple[str, ...],
    kernels: dict[str, dict[str, dict[str, object]]],
    *,
    limit: int = 8,
) -> list[dict]:
    """Enumerate canonical nontrivial quotients; bounded at 7 states."""
    if not 3 <= len(states) <= 7 or not 1 <= limit <= 100:
        raise ValueError("search requires 3..7 states and limit 1..100")
    candidates = []
    for groups in range(2, len(states)):
        for labels in _partitions(len(states), groups):
            macro = dict(zip(states, (str(x) for x in labels)))
            outcome = abstraction_defects(states, macro, kernels)
            candidates.append({
                "macro": macro,
                "macrostates": groups,
                "worst_defect": outcome["worst_defect"],
                "exact": outcome["exact"],
            })
    candidates.sort(key=lambda x: (
        Fraction(x["worst_defect"]), x["macrostates"],
        tuple(x["macro"][s] for s in states),
    ))
    return candidates[:limit]


def parity_obstruction(equations: list[tuple[tuple[str, ...], int]]) -> dict:
    """Find a deletion-minimal inconsistent subsystem over GF(2).

    Each equation is (variables, bit), representing XOR(vars)=bit.
    Repeated variables cancel. A deletion-minimal core need not be the
    smallest-cardinality unsatisfiable core.
    """
    if not isinstance(equations, list) or not 1 <= len(equations) <= 32:
        raise ValueError("provide 1..32 finite parity equations")
    variables = sorted({v for terms, _ in equations for v in terms})
    if len(variables) > 12 or not all(
        isinstance(v, str) and v for v in variables
    ):
        raise ValueError("provide at most 12 named variables")
    lookup = {v: i for i, v in enumerate(variables)}
    rows = []
    for terms, rhs in equations:
        if not isinstance(terms, tuple) or type(rhs) is not int or rhs not in (0, 1):
            raise ValueError("equations must contain a tuple and a parity bit")
        mask = 0
        for variable in terms:
            mask ^= 1 << lookup[variable]
        rows.append((mask, rhs))

    def consistent(indices: list[int]) -> bool:
        basis: dict[int, tuple[int, int]] = {}
        for index in indices:
            mask, bit = rows[index]
            while mask:
                pivot = mask.bit_length() - 1
                if pivot not in basis:
                    basis[pivot] = (mask, bit)
                    break
                other_mask, other_bit = basis[pivot]
                mask ^= other_mask
                bit ^= other_bit
            if mask == 0 and bit:
                return False
        return True

    all_indices = list(range(len(rows)))
    if consistent(all_indices):
        return {"satisfiable": True, "deletion_minimal_core": [],
                "scope": "finite parity constraints only"}
    core = all_indices[:]
    for index in all_indices:
        if index in core:
            trial = [item for item in core if item != index]
            if not consistent(trial):
                core = trial
    return {
        "satisfiable": False,
        "deletion_minimal_core": core,
        "every_single_deletion_satisfiable": all(
            consistent([item for item in core if item != index]) for index in core
        ),
        "scope": "finite parity contradiction; not a general gluing theorem",
    }


def run_benchmarks() -> dict:
    """Small independently reproducible checks; no claim of mathematical novelty."""
    states = ("00", "01", "10", "11")
    macro = {s: s[0] for s in states}
    identity = {s: {s: 1} for s in states}
    xor = {
        s: {str(int(s[0]) ^ int(s[1])) + s[1]: 1} for s in states
    }
    abstraction = abstraction_defects(
        states, macro, {"identity": identity, "xor_intervention": xor}
    )
    options = search_abstractions(states, {"identity": identity, "xor": xor}, limit=5)
    parity = parity_obstruction([
        (("a", "b"), 1), (("b", "c"), 1), (("a", "c"), 1),
    ])
    return {
        "abstraction": {
            "passed": (
                abstraction["defects"] == {
                    "identity": "0", "xor_intervention": "1"
                } and not abstraction["exact"]
            ),
            "evidence": abstraction,
            "enumerated_nontrivial_quotients_top5": options,
        },
        "parity_gluing": {
            "passed": (not parity["satisfiable"] and
                       len(parity["deletion_minimal_core"]) == 3 and
                       parity["every_single_deletion_satisfiable"]),
            "evidence": parity,
        },
    }


def load_feedback(path: Path = DEFAULT_FEEDBACK) -> dict:
    """Read a human-supplied rating ledger; strictly reject promotion fields."""
    if not path.exists():
        return {"schema_version": "1.0", "ratings": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if type(data) is not dict or set(data) != {"schema_version", "ratings"} or (
        data["schema_version"] != "1.0" or type(data["ratings"]) is not list
    ):
        raise ValueError("invalid discovery feedback schema")
    seen = set()
    for item in data["ratings"]:
        if type(item) is not dict or set(item) != {
            "question_id", "outcome", "evidence_ref", "reviewer"
        }:
            raise ValueError("invalid feedback record fields")
        if item["question_id"] not in QUESTION_IDS or item["outcome"] not in (
            "useful", "not_useful"
        ):
            raise ValueError("unknown question or feedback outcome")
        if any(
            not isinstance(item[field], str) or
            not 1 <= len(item[field].strip()) <= 300
            for field in ("evidence_ref", "reviewer")
        ):
            raise ValueError("feedback needs a bounded evidence reference and reviewer")
        key = (item["question_id"], item["evidence_ref"])
        if key in seen:
            raise ValueError("duplicate evidence for the same question")
        seen.add(key)
    return data


def record_feedback(
    path: Path, question_id: str, outcome: str, evidence_ref: str, reviewer: str
) -> dict:
    """Append labeled feedback atomically; never execute candidate suggestions."""
    data = load_feedback(path)
    candidate = {
        "question_id": question_id, "outcome": outcome,
        "evidence_ref": evidence_ref, "reviewer": reviewer,
    }
    data["ratings"].append(candidate)
    # Validate the complete ledger before attempting an on-disk change.
    validation = json.loads(json.dumps(data))
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reuse one schema validator for existing and proposed records.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".discovery-",
        suffix=".json", delete=False
    ) as handle:
        tmp = Path(handle.name)
        json.dump(validation, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        load_feedback(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return data


def _score(question: Question, ratings: list[dict]) -> tuple[float, int]:
    seen = [r for r in ratings if r["question_id"] == question.id]
    wins = sum(r["outcome"] == "useful" for r in seen)
    count = len(seen)
    # Beta(1,1) smoothed empirical usefulness and a bounded exploration bonus.
    # This heuristic is NOT a calibrated probability of a theorem or novelty.
    return (wins + 1) / (count + 2) + 0.15 / (count + 1), count


def build_report(
    feedback_path: Path = DEFAULT_FEEDBACK, *,
    direction: str = "all", depth: str = "all", limit: int = 8,
) -> dict:
    if direction not in ("all",) + DIRECTIONS or depth not in ("all",) + DEPTHS:
        raise ValueError("unsupported direction or depth")
    if type(limit) is not int or not 1 <= limit <= 56:
        raise ValueError("limit must be in 1..56")
    feedback = load_feedback(feedback_path)
    questions = [
        q for q in catalog()
        if (direction == "all" or q.direction == direction)
        and (depth == "all" or q.depth == depth)
    ]
    ranked = sorted(questions, key=lambda q: (-_score(q, feedback["ratings"])[0], q.id))
    cases = run_benchmarks()
    question_list = []
    for q in ranked[:limit]:
        score, count = _score(q, feedback["ratings"])
        question_list.append({
            **asdict(q),
            "priority_score": round(score, 6),
            "human_feedback_samples": count,
            "novelty_verified": False,
            "proof_verified": False,
            "next_gate": "HUMAN_REVIEW_AND_INDEPENDENT_PRIOR_ART_SEARCH",
        })
    digest = hashlib.sha256(
        json.dumps([asdict(q) for q in catalog()], sort_keys=True).encode()
    ).hexdigest()
    return {
        "schema_version": "1.0",
        "engine": "MathOS_x_offline_discovery",
        "scope": "bounded question generation, finite probes, adaptive scheduling",
        "direction": direction,
        "depth": depth,
        "catalog_size": len(catalog()),
        "catalog_sha256": digest,
        "feedback_samples": len(feedback["ratings"]),
        "ranker": "Beta(1,1) smoothed usefulness plus fixed exploration bonus",
        "questions": question_list,
        "benchmarks": cases,
        "certification": "NOT_CERTIFIED",
        "mathematical_novelty": "NOT_INDEPENDENTLY_ASSESSED",
        "automatic_code_modification": False,
        "human_review_required": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MathOS × guarded discovery engine")
    parser.add_argument("--feedback-file", type=Path, default=DEFAULT_FEEDBACK)
    parser.add_argument("--direction", choices=("all",) + DIRECTIONS, default="all")
    parser.add_argument("--depth", choices=("all",) + DEPTHS, default="all")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--rate-question")
    parser.add_argument("--outcome", choices=("useful", "not_useful"))
    parser.add_argument("--evidence-ref")
    parser.add_argument("--reviewer")
    args = parser.parse_args(argv)
    if args.rate_question:
        if not all((args.outcome, args.evidence_ref, args.reviewer)):
            parser.error("rating needs --outcome, --evidence-ref and --reviewer")
        record_feedback(
            args.feedback_file, args.rate_question, args.outcome,
            args.evidence_ref, args.reviewer,
        )
        print(json.dumps({
            "feedback_recorded": True,
            "certification": "NOT_CERTIFIED",
        }))
        return 0
    if any((args.outcome, args.evidence_ref, args.reviewer)):
        parser.error("--outcome, --evidence-ref and --reviewer require --rate-question")
    report = build_report(
        args.feedback_file, direction=args.direction,
        depth=args.depth, limit=args.limit,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "discovery_report.json").write_text(
            payload, encoding="utf-8"
        )
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
