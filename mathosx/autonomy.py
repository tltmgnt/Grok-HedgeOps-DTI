"""MathOS X: independently replayable finite GF(2) proof search and novelty triage.

Proof search is complete ONLY for the explicitly bounded parity-equation fragment.
Global mathematical originality is not algorithmically certified. Generated code
is a deterministic, data-only proposal for review; no generated code is executed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent
PROGRAMS = PACKAGE / "proof_programs.v1.json"
KNOWN = PACKAGE / "known_claims.v1.json"
GENERATED = PACKAGE / "generated_theorems.py"
MAX_VARIABLES = 10
MAX_AXIOMS = 32
MAX_CANDIDATES = 48


def _equation(raw: object) -> dict:
    if type(raw) is not dict or set(raw) != {"variables", "rhs"}:
        raise ValueError("equation requires only variables and rhs")
    terms, bit = raw["variables"], raw["rhs"]
    if type(terms) is not list or len(terms) > MAX_VARIABLES * 2:
        raise ValueError("equation variables must be a bounded list")
    if type(bit) is not int or bit not in (0, 1):
        raise ValueError("equation rhs must be 0 or 1")
    toggled: set[str] = set()
    for term in terms:
        if not isinstance(term, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,19}", term):
            raise ValueError("invalid variable name")
        if term in toggled:
            toggled.remove(term)
        else:
            toggled.add(term)
    return {"variables": sorted(toggled), "rhs": bit}


def validate_problem(raw: object) -> dict:
    if type(raw) is not dict or set(raw) != {"id", "axioms", "conclusion"}:
        raise ValueError("problem needs exactly id, axioms, conclusion")
    identifier = raw["id"]
    if not isinstance(identifier, str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,63}", identifier
    ):
        raise ValueError("invalid theorem problem identifier")
    axioms = raw["axioms"]
    if type(axioms) is not list or not 1 <= len(axioms) <= MAX_AXIOMS:
        raise ValueError("axioms must have 1..32 parity equations")
    normalized = {
        "id": identifier,
        "axioms": [_equation(eq) for eq in axioms],
        "conclusion": _equation(raw["conclusion"]),
    }
    names = {
        name for eq in normalized["axioms"] + [normalized["conclusion"]]
        for name in eq["variables"]
    }
    if len(names) > MAX_VARIABLES:
        raise ValueError("at most ten Boolean variables are supported")
    return normalized


def _rows(problem: dict, *, negate: bool = False) -> tuple[list[tuple[int, int]], list[str]]:
    universe = sorted({
        name for eq in problem["axioms"] + [problem["conclusion"]]
        for name in eq["variables"]
    })
    index = {name: i for i, name in enumerate(universe)}
    equations = problem["axioms"] + ([{
        "variables": problem["conclusion"]["variables"],
        "rhs": problem["conclusion"]["rhs"] ^ 1,
    }] if negate else [])
    rows = []
    for eq in equations:
        mask = 0
        for name in eq["variables"]:
            mask ^= 1 << index[name]
        rows.append((mask, eq["rhs"]))
    return rows, universe


def _refutation(rows: list[tuple[int, int]]) -> list[int] | None:
    """Gaussian elimination with a provenance bitset for each row."""
    basis: dict[int, tuple[int, int, int]] = {}
    for i, (mask, bit) in enumerate(rows):
        support = 1 << i
        while mask:
            pivot = mask.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = (mask, bit, support)
                break
            old_mask, old_bit, old_support = basis[pivot]
            mask ^= old_mask
            bit ^= old_bit
            support ^= old_support
        if mask == 0 and bit:
            return [j for j in range(len(rows)) if support & (1 << j)]
    return None


def check_certificate(
    rows: list[tuple[int, int]], indices: list[int], *,
    required_index: int | None = None,
) -> bool:
    """Independent XOR replay: subset of equations sums to 0 = 1."""
    if type(indices) is not list or not indices or len(set(indices)) != len(indices):
        return False
    if any(type(i) is not int or not 0 <= i < len(rows) for i in indices):
        return False
    if required_index is not None and required_index not in indices:
        return False
    mask, rhs = 0, 0
    for i in indices:
        mask ^= rows[i][0]
        rhs ^= rows[i][1]
    return mask == 0 and rhs == 1


def _holds(row: tuple[int, int], assignment: int) -> bool:
    return (row[0] & assignment).bit_count() % 2 == row[1]


def prove(raw: dict) -> dict:
    """Prove entailment or provide a countermodel within the finite XOR fragment.

    If axioms are inconsistent, report that condition explicitly rather than
    presenting an arbitrary consequence as a mathematical discovery.
    """
    problem = validate_problem(raw)
    rows, names = _rows(problem)
    contradiction = _refutation(rows)
    if contradiction is not None:
        if not check_certificate(rows, contradiction):
            raise RuntimeError("axiom contradiction certificate failed independent replay")
        return {
            "id": problem["id"], "status": "INCONSISTENT_AXIOMS",
            "certificate_indices": contradiction,
            "proof_checked": True, "novelty_established": False,
        }
    expanded, _ = _rows(problem, negate=True)
    cert = _refutation(expanded)
    if cert is not None:
        if not check_certificate(expanded, cert, required_index=len(rows)):
            raise RuntimeError("entailment proof failed independent replay")
        if any(
            all(_holds(row, assignment) for row in rows) and
            not _holds((expanded[-1][0], expanded[-1][1] ^ 1), assignment)
            for assignment in range(1 << len(names))
        ):
            raise RuntimeError("independent exhaustive countermodel contradicts proof")
        return {
            "id": problem["id"], "status": "PROVED_FINITE_XOR_ENTAILMENT",
            "certificate_indices": cert,
            "proof_checked": True, "novelty_established": False,
            "variables_exhaustively_checked": len(names),
        }
    for assignment in range(1 << len(names)):
        if all(_holds(row, assignment) for row in expanded):
            witness = {name: (assignment >> i) & 1 for i, name in enumerate(names)}
            return {
                "id": problem["id"], "status": "COUNTERMODEL_FOUND",
                "countermodel": witness, "proof_checked": True,
                "novelty_established": False,
            }
    raise RuntimeError("Gaussian elimination and exhaustive enumeration disagree")


def _fingerprint(problem: dict) -> str:
    data = {
        "axioms": sorted(problem["axioms"], key=lambda eq: (
            eq["variables"], eq["rhs"]
        )),
        "conclusion": problem["conclusion"],
    }
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_registry(path: Path, *, type_name: str) -> list[dict]:
    raw = path.read_bytes()
    if len(raw) > 200_000:
        raise ValueError("research registry exceeds size limit")
    content = json.loads(raw)
    if type(content) is not dict or set(content) != {"schema_version", "entries"} or (
        content["schema_version"] != "1.0" or type(content["entries"]) is not list
        or not 1 <= len(content["entries"]) <= 32
    ):
        raise ValueError(f"invalid {type_name} registry")
    entries = [validate_problem(item) for item in content["entries"]]
    if len({x["id"] for x in entries}) != len(entries):
        raise ValueError(f"duplicate {type_name} identifiers")
    return entries


def novelty_audit(problem: dict, known: list[dict]) -> dict:
    """Prove only exact absence/presence in one explicitly pinned finite corpus.

    No external literature was searched and mathematical novelty remains open.
    """
    signature = _fingerprint(validate_problem(problem))
    matches = [q["id"] for q in known if _fingerprint(q) == signature]
    return {
        "local_exact_match": bool(matches),
        "matching_known_ids": matches,
        "statement_sha256": signature,
        "local_corpus_sha256": sha256(json.dumps(
            known, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest(),
        "local_corpus_entries": len(known),
        "scope": "exact normalized statement and axiom-set comparison only",
        "global_mathematical_novelty": "NOT_ESTABLISHED",
        "literature_review": "NOT_PERFORMED",
        "independent_review": "NOT_PERFORMED",
    }


def derive(programs: list[dict], known: list[dict]) -> dict:
    """Autonomously enumerate small consequences of registered XOR systems."""
    results = []
    candidate_theorems = []
    seen = set()
    for program in programs:
        original = prove(program)
        results.append({
            "problem_id": program["id"], **original,
            "novelty": novelty_audit(program, known),
        })
        if original["status"] == "INCONSISTENT_AXIOMS":
            continue
        variables = sorted({
            name for eq in program["axioms"] for name in eq["variables"]
        })
        if len(variables) > 6:
            raise ValueError("automatic candidate search allows at most six variables")
        existing_axioms = {
            (tuple(eq["variables"]), eq["rhs"]) for eq in program["axioms"]
        }
        for size in range(1, min(3, len(variables)) + 1):
            for subset in combinations(variables, size):
                for rhs in (0, 1):
                    if (subset, rhs) in existing_axioms:
                        continue
                    candidate = {
                        "id": program["id"] + "-derived",
                        "axioms": program["axioms"],
                        "conclusion": {"variables": list(subset), "rhs": rhs},
                    }
                    signature = _fingerprint(candidate)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    proof = prove(candidate)
                    if proof["status"] == "PROVED_FINITE_XOR_ENTAILMENT":
                        candidate_theorems.append({
                            "origin": program["id"],
                            "problem": candidate,
                            "proof": proof,
                            "novelty": novelty_audit(candidate, known),
                        })
                        if len(candidate_theorems) >= MAX_CANDIDATES:
                            break
                if len(candidate_theorems) >= MAX_CANDIDATES:
                    break
            if len(candidate_theorems) >= MAX_CANDIDATES:
                break
    return {
        "schema_version": "1.0",
        "engine": "bounded_finite_GF2_autonomous_prover",
        "registered_results": results,
        "verified_finite_consequences": candidate_theorems,
        "proof_fragment": "finite parity equations with at most 10 Boolean variables",
        "candidate_search_limit": MAX_CANDIDATES,
        "mathematical_novelty": "NOT_ESTABLISHED",
        "independent_literature_review": False,
        "automatic_merge": False,
        "global_theorem_certification": "NOT_CERTIFIED",
    }


def recheck_records(records: list[dict]) -> bool:
    """Revalidate all saved certificates rather than trust the saved status."""
    if type(records) is not list or len(records) > MAX_CANDIDATES:
        return False
    for item in records:
        try:
            if type(item) is not dict or set(item) != {
                "origin", "problem", "proof", "novelty"
            }:
                return False
            problem = validate_problem(item["problem"])
            if item["proof"]["status"] != "PROVED_FINITE_XOR_ENTAILMENT":
                return False
            rows, _ = _rows(problem, negate=True)
            cert = item["proof"]["certificate_indices"]
            if not check_certificate(
                rows, cert, required_index=len(rows) - 1
            ):
                return False
            if not prove(problem)["status"] == "PROVED_FINITE_XOR_ENTAILMENT":
                return False
            if item["novelty"]["global_mathematical_novelty"] != "NOT_ESTABLISHED":
                return False
        except (ValueError, KeyError, TypeError, RuntimeError):
            return False
    return True


def render_generated(records: list[dict]) -> str:
    """Only fixed Python template plus escaped JSON data; not AI-authored code."""
    if not recheck_records(records):
        raise ValueError("refusing to generate code without checked finite proofs")
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return (
        '"""GENERATED: independently checked finite XOR consequences only.\n'
        'Do not interpret these records as novel theorems or external validation.\n'
        'Regenerate via python -m mathosx.autonomy --generate-code.\n'
        '"""\n'
        "from __future__ import annotations\n"
        "import json\n\n"
        "FINITE_XOR_PROOF_RECORDS = json.loads(" + repr(payload) + ")\n\n"
        "def recheck() -> bool:\n"
        "    from mathosx.autonomy import recheck_records\n"
        "    return recheck_records(FINITE_XOR_PROOF_RECORDS)\n"
    )


def run(programs_path: Path = PROGRAMS, known_path: Path = KNOWN) -> dict:
    programs = load_registry(programs_path, type_name="programs")
    known = load_registry(known_path, type_name="known claims")
    return derive(programs, known)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MathOS X bounded autonomous XOR proof search")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--generate-code", action="store_true")
    parser.add_argument("--check-code", action="store_true")
    args = parser.parse_args(argv)
    if args.generate_code and args.check_code:
        parser.error("choose --generate-code or --check-code")
    result = run()
    source = render_generated(result["verified_finite_consequences"])
    if args.generate_code:
        # Fixed, allowlisted code destination. No arbitrary file/command execution.
        GENERATED.write_text(source, encoding="utf-8")
    if args.check_code:
        if not GENERATED.exists() or GENERATED.read_text(encoding="utf-8") != source:
            parser.error("generated theorem code is missing or out of date")
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "autonomous_proof_report.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "engine": result["engine"],
        "registered_problems": len(result["registered_results"]),
        "checked_finite_consequences": len(result["verified_finite_consequences"]),
        "status": "BOUNDED_FINITE_PROOFS_ONLY",
        "global_mathematical_novelty": "NOT_ESTABLISHED",
        "generated_code": str(GENERATED) if args.generate_code else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
