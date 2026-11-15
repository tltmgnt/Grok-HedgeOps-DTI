"""Verify local PEA release consistency; hashes do not authenticate research evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path


REQUIRED_FILES = frozenset({
    "pea_assurance/__init__.py", "pea_assurance/__main__.py",
    "pea_assurance/measurement.py", "pea_assurance/test_measurement.py",
    "pea_assurance/synthetic_example.json", "pea_assurance/pilot_protocol.json",
    "pea_assurance/README.md", "docs/researchos/PEA_RESEARCH.md",
    "pea_assurance/verify_release.py", "pea_assurance/test_release.py",
    ".github/workflows/pea-assurance.yml",
})
VERSION = "0.1.1"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read_json(root, relative):
    path = (root / relative).resolve()
    _require(root in path.parents, "file escapes repository: " + relative)
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def verify_release(root, expected_repository):
    """Require an exact file inventory, digests and matching scope metadata.

    This checks consistency against the local manifest, not a trusted signature.
    The manifest itself is deliberately excluded from its own digest inventory.
    """
    root = Path(root).resolve()
    _require(isinstance(expected_repository, str) and
             re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", expected_repository),
             "expected repository must be owner/name")
    release = _read_json(root, "pea_assurance/release.json")
    _require(isinstance(release, dict), "release must be an object")
    _require(release.get("schema_version") == 1, "unsupported release schema")
    _require(release.get("version") == VERSION, "release version mismatch")
    _require(release.get("repository") == expected_repository, "repository mismatch")
    _require(release.get("canonical_repository") == "tltmgnt/ResearchOs", "canonical source mismatch")
    _require(release.get("empirically_validated") is False, "empirical validation is not established")
    _require(release.get("domain_adapter_integrated") is False, "live adapter is not established")
    files = release.get("files_sha256")
    _require(isinstance(files, dict) and set(files) == REQUIRED_FILES, "release inventory mismatch")
    for relative, digest in files.items():
        _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                 "invalid digest: " + relative)
        path = (root / relative).resolve()
        _require(root in path.parents and path.is_file(), "missing or escaping file: " + relative)
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "digest mismatch: " + relative)
    integration = _read_json(root, "docs/researchos/integration.json")
    _require(isinstance(integration, dict), "integration must be an object")
    _require(integration.get("repository") == expected_repository, "integration repository mismatch")
    pea = integration.get("pea")
    _require(isinstance(pea, dict) and pea.get("version") == VERSION, "integration PEA version mismatch")
    _require(pea.get("live_controller_adapter_implemented") is False and
             pea.get("independent_empirical_evaluation_completed") is False,
             "integration scope mismatch")
    _require(integration.get("domain") == release.get("domain"), "domain metadata mismatch")
    paper = (root / "docs/researchos/TECT_WHITE_PAPER.md").resolve()
    _require(root in paper.parents and paper.is_file(), "paper missing or escaping repository")
    _require(hashlib.sha256(paper.read_bytes()).hexdigest() == integration.get("paper_sha256"),
             "white paper digest mismatch")
    return {"result": "LOCAL_RELEASE_CONSISTENT", "repository": expected_repository,
            "version": VERSION, "verified_files": len(files),
            "scientific_validity_established": False, "source_authenticated": False,
            "deployment_authorized": False}


def main():
    parser = argparse.ArgumentParser(description="Check PEA local release integrity and scope")
    parser.add_argument("--repository", required=True, help="expected owner/name from trusted checkout context")
    args = parser.parse_args()
    try:
        result = verify_release(Path(__file__).resolve().parent.parent, args.repository)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"PEA release verification failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
