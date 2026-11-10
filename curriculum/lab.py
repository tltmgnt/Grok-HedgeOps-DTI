"""Offline curriculum answer key. Synthetic checks, never operational approval."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for base in (ROOT, ROOT / "src", ROOT / "layer-b"):
    sys.path.insert(0, str(base))
CASES = []

def check(name, actual, expected):
    passed = actual == expected
    CASES.append({"case": name, "actual": actual, "expected": expected, "passed": passed})
    if not passed:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")

def rejects(name, call, error=ValueError):
    try:
        call()
    except error:
        check(name, error.__name__, error.__name__)
    else:
        raise AssertionError(f"{name}: expected {error.__name__}")



def definitions(path, names, namespace):
    # Execute selected original AST definitions, excluding provider imports/calls.
    tree = ast.parse((ROOT / path).read_text())
    chosen = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            chosen.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            chosen.append(node)
    found = {n.name for n in chosen if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    found |= {t.id for n in chosen if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    if found != set(names):
        raise ValueError("Reviewed source definitions changed")
    exec(compile(ast.Module(body=chosen, type_ignores=[]), str(ROOT / path), "exec"), namespace)
    return namespace

def run():
    # Evaluate the original pure validator without importing or calling model clients.
    ns = definitions("agent.py", {"REQUIRED_FIELDS","ARRAY_FIELDS","validate_report"}, {"json":json})
    validate = ns["validate_report"]
    r = {key: [] if key in ns["ARRAY_FIELDS"] else "UNKNOWN" for key in ns["REQUIRED_FIELDS"]}
    check("complete advisory schema", validate(json.dumps(r)), r)
    rejects("nonobject response", lambda: validate("[]"))
    rejects("missing report fields", lambda: validate("{}"))
    bad = copy.deepcopy(r); bad["evidence"] = "unsupported"
    rejects("evidence must be an array", lambda: validate(json.dumps(bad)))
    bad = copy.deepcopy(r); bad["recommendation"] = "An unverified assertion"
    check("schema accepts unverified prose: not factual validation", validate(json.dumps(bad))["recommendation"], "An unverified assertion")

if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--verify"]):
        raise SystemExit("Usage: python curriculum/lab.py [--verify]")
    run()
    report = {"schema_version": 1, "status": "PASS", "case_count": len(CASES),
              "cases": CASES, "scope": "Synthetic curriculum checks only"}
    if sys.argv[1:] == ["--verify"]:
        expected = json.loads((Path(__file__).parent / "expected.json").read_text())
        if report != expected:
            raise AssertionError("Observed answers differ from curriculum/expected.json")
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
