"""Phase 90 advisory final release assessment; no deployment side effects."""
from hedgeops.reconciliation_cli import EXIT_READY, readiness_exit_code
from hedgeops.release_gate import REQUIRED, assess_release

OPERATIONAL_EVIDENCE = (
    "production_https_custody_validation",
    "checkpoint_key_rotation_tested",
    "backup_restore_drill",
    "monitoring_and_incident_runbooks",
    "rollback_plan_approved",
)


def final_release_assessment(readiness_report, evidence):
    """Fail closed on incomplete runtime, human, or operational evidence.

    This is a recommendation only. It never grants authorization or deploys.
    """
    if not isinstance(evidence, dict):
        evidence = {}
    prior = assess_release(evidence)
    missing = list(prior.missing)
    missing.extend(name for name in OPERATIONAL_EVIDENCE
                   if evidence.get(name) is not True)
    ready = readiness_exit_code(readiness_report) == EXIT_READY
    return {
        "recommendation": "REVIEW_FOR_GO" if ready and not missing else "NO_GO",
        "runtime_ready": ready,
        "missing_evidence": missing,
        "explicit_human_release_authorization_required": True,
    }
