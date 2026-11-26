"""Read-only MRA-X evidence attachment for an existing team report.

No strategy, risk limit, decision, approval or execution path is changed.
Use only synthetic or authorized redacted research reports.
"""
import json
from copy import deepcopy
from .core import DecisionReport
from tools.mra_x_tga import digest, evaluate


def review_research_record(report, record):
    """Append a report snapshot as an unverified input and evaluate structure.

    The returned disposition never changes the report and cannot authorize
    a trade or validate a market prediction. Caller keeps evidence private.
    """
    if not isinstance(report, DecisionReport):
        raise TypeError("expected native DecisionReport")
    if not isinstance(record, dict):
        return evaluate(record)
    item = deepcopy(record)
    evidence = item.get("evidence")
    if not isinstance(evidence, list):
        return evaluate(item)
    snapshot = json.dumps(report.to_dict(), sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False)
    item["evidence"] = evidence + [{"content": snapshot, "sha256": digest(snapshot)}]
    result = evaluate(item)
    return dict(result, report_sha256=digest(snapshot), report_changed=False,
                source_authentication=False, trade_authorized=False)
