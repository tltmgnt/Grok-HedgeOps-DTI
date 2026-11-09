"""Read-only evidence completeness checks; never authorize orders or certify claims."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

REQUIRED = {
    'trading_evidence': ('protocol', 'data_integrity', 'experiment_registry',
        'execution_costs', 'independent_evaluation', 'attribution', 'degradation_policy'),
    'investor_fit': ('investor_profile', 'loss_capacity', 'portfolio_context',
        'alternatives', 'conflicts_authority', 'ongoing_review'),
    'operational_assurance': ('assessment_scope', 'execution_ownership',
        'service_objectives', 'recovery', 'security', 'change_governance', 'independent_assessment'),
}
CLAIMS = {
    'trading_evidence': 'Evidence is complete for the scoped historical evaluation; future profitability is not established.',
    'investor_fit': 'Evidence is complete for this investor and strategy scope; suitability is not automatically determined.',
    'operational_assurance': 'Evidence is complete for the named deployment and criteria; certification is not automatically issued.',
}


def stamp(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timezone required')
    return value.astimezone(timezone.utc)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def template():
    return {'schema_version': 1, 'strategy_version': '', 'gates': {
        name: {'owner': '', 'scope': '', 'subject_id': '', 'criteria_version': '',
               'blockers': [], 'evidence': []}
        for name in REQUIRED}}


def assess(register, root, now):
    """Verify private local artifacts and evidence completeness. Return no sensitive paths/content."""
    now = stamp(now.isoformat())
    root = Path(root).resolve()
    if not isinstance(register, dict) or type(register.get('schema_version')) is not int or register['schema_version'] != 1:
        raise ValueError('unsupported register schema')
    if not nonempty(register.get('strategy_version')):
        raise ValueError('strategy version required')
    gates = register.get('gates')
    if not isinstance(gates, dict) or set(gates) != set(REQUIRED):
        raise ValueError('exactly three named gates required')
    results = {}
    for name, requirements in REQUIRED.items():
        gate = gates[name]
        if not isinstance(gate, dict):
            raise ValueError('invalid gate')
        gaps = []
        for field in ('owner', 'scope', 'subject_id', 'criteria_version'):
            if not nonempty(gate.get(field)):
                gaps.append('missing_' + field)
        blockers = gate.get('blockers')
        if not isinstance(blockers, list) or any(not nonempty(b) for b in blockers):
            gaps.append('invalid_blockers')
        elif blockers:
            gaps.append('unresolved_blockers')
        evidence = gate.get('evidence')
        if not isinstance(evidence, list):
            evidence = []
            gaps.append('invalid_evidence')
        valid, seen = set(), set()
        for record in evidence:
            try:
                key = record['requirement']
                if key not in requirements or key in seen:
                    raise ValueError('duplicate or unknown requirement')
                seen.add(key)
                if record['strategy_version'] != register['strategy_version']:
                    raise ValueError('version mismatch')
                if record['subject_id'] != gate.get('subject_id'):
                    raise ValueError('subject mismatch')
                if not stamp(record['observed_at']) <= now < stamp(record['expires_at']):
                    raise ValueError('stale or future evidence')
                relative = Path(record['path'])
                if relative.is_absolute():
                    raise ValueError('relative artifact path required')
                path = (root / relative).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise ValueError('artifact outside evidence root or missing')
                if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                    raise ValueError('artifact digest mismatch')
                valid.add(key)
            except (KeyError, TypeError, ValueError, OSError, AttributeError):
                gaps.append('invalid_evidence_record')
        missing = sorted(set(requirements) - valid)
        packet = {'strategy_version': register['strategy_version'],
                  **{k: v for k, v in gate.items() if k != 'review'}}
        packet_hash = digest(packet)
        eligible = not gaps and not missing
        results[name] = {'evidence_complete': eligible,
                         'missing_requirements': missing, 'gaps': sorted(set(gaps)),
                         'packet_sha256': packet_hash,
                         'permitted_claim': CLAIMS[name] if eligible else 'Evidence incomplete; no affirmative readiness claim.'}
    return {'assessed_at': now.isoformat(), 'gates': results,
            'all_evidence_complete': all(g['evidence_complete'] for g in results.values()),
            'execution_authorized': False, 'certification_issued': False,
            'limitations': 'Local hashes establish artifact consistency, not truth. No financial or legal conclusion is automated.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('register', nargs='?', type=Path)
    parser.add_argument('--evidence-root', type=Path)
    parser.add_argument('--template', action='store_true')
    args = parser.parse_args()
    if args.template:
        print(json.dumps(template(), indent=2))
        return 0
    if not args.register or not args.evidence_root:
        parser.error('register and --evidence-root required')
    try:
        report = assess(json.loads(args.register.read_text()), args.evidence_root,
                        datetime.now(timezone.utc))
    except (ValueError, OSError, TypeError):
        print(json.dumps({'status': 'INVALID_REGISTER', 'execution_authorized': False}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['all_evidence_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
