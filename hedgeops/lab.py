"""Five-agent laboratory with evidence-based arbitration and human approval gate."""
import json
from typing import Callable

ROLES = {
    "temporal": "Analyze timing, sequencing, deadlines, slack, latency, and option value.",
    "strategy": "Generate competing strategies, opportunity costs, reversibility and dependencies.",
    "risk": "Assess downside scenarios, uncertainty, bottlenecks and resource constraints.",
    "contrarian": "Challenge the leading thesis with alternative hypotheses and falsifiers.",
    "red_team": "Stress-test the proposal under adversarial and cascading failure scenarios.",
}
FIELDS = {
    "hypothesis": str,
    "evidence": list,
    "assumptions": list,
    "risks": list,
    "falsification_tests": list,
    "confidence": str,
}
ALLOWED_CONFIDENCE = {"low", "medium", "high", "unknown"}


def validate_report(report: dict) -> dict:
    if not isinstance(report, dict):
        raise ValueError("Agent report must be a JSON object")
    for key, expected in FIELDS.items():
        if key not in report or type(report[key]) is not expected:
            raise ValueError(f"Invalid or missing field: {key}")
    if report["confidence"] not in ALLOWED_CONFIDENCE:
        raise ValueError("confidence must be low, medium, high or unknown")
    for key in ("evidence", "assumptions", "risks", "falsification_tests"):
        if not all(isinstance(x, str) for x in report[key]):
            raise ValueError(f"{key} must contain strings")
    return report


def run_lab(problem: str, ask: Callable[[str, str], dict]) -> dict:
    """ask(system_prompt, user_prompt) is injected for testing or API use."""
    if not problem.strip():
        raise ValueError("Problem cannot be empty")
    reports = {}
    for role, mission in ROLES.items():
        system = (
            f"You are the HEDGE 302 {role} agent. {mission} "
            "Return ONLY JSON with keys hypothesis (string), evidence (array of "
            "strings), assumptions (array of strings), risks (array of strings), "
            "falsification_tests (array of strings), confidence "
            "(low/medium/high/unknown). Do not invent evidence. "
            "Unverified claims must be labeled as assumptions."
        )
        reports[role] = validate_report(ask(system, problem))
    return {"problem": problem, "agents": reports, "arbitration": arbitrate(reports)}


def arbitrate(reports: dict) -> dict:
    """Conservative deterministic gate; does not treat consensus as proof."""
    if set(reports) != set(ROLES):
        raise ValueError("All five specialized agents are required")
    for report in reports.values():
        validate_report(report)
    missing_evidence = [name for name, report in reports.items() if not report["evidence"]]
    low_confidence = [name for name, report in reports.items()
                      if report["confidence"] in {"low", "unknown"}]
    hypotheses = {name: report["hypothesis"] for name, report in reports.items()}
    tests = sorted({test for report in reports.values()
                    for test in report["falsification_tests"]})
    return {
        "status": "investigate" if missing_evidence or low_confidence else "human_review",
        "hypotheses": hypotheses,
        "missing_evidence_agents": missing_evidence,
        "low_confidence_agents": low_confidence,
        "falsification_tests": tests,
        "conflicts_resolved": False,
        "human_approval_required": True,
        "reason": "Evidence and confidence are screening signals, not proof of agreement.",
    }


def render(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
