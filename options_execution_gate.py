"""Default-deny gate for future options broker execution.

No broker client, network calls, credentials, or order submission exists here.
The gate is deliberately insufficient to authorize live execution on its own:
an independently reviewed broker adapter and transactional ledger are required.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hmac
import os


@dataclass(frozen=True)
class ExecutionDecision:
    permitted: bool
    reason: str


def evaluate_execution_gate(*, environment: str, broker_authenticated: bool,
                            account_verified: bool, ledger_reserved: bool,
                            reconciliation_healthy: bool, kill_switch_clear: bool,
                            risk_limits_verified: bool, operator_approval: str,
                            expected_approval: str, order_notional_usd: str,
                            max_order_notional_usd: str) -> ExecutionDecision:
    """Fail closed; NEVER place orders or return an executable authorization.

    An enabled gate only says that preconditions appear satisfied. Broker-side
    authorization, account checks, and atomic ledger transitions remain mandatory.
    """
    if environment not in ('paper', 'live'):
        return ExecutionDecision(False, 'invalid environment')
    if environment == 'live' and os.environ.get('OPTIONS_LIVE_EXECUTION_ENABLED') != 'true':
        return ExecutionDecision(False, 'live execution disabled by default')
    checks = (broker_authenticated, account_verified, ledger_reserved,
              reconciliation_healthy, kill_switch_clear, risk_limits_verified)
    if any(type(flag) is not bool or not flag for flag in checks):
        return ExecutionDecision(False, 'required broker, ledger, or risk check failed')
    if (not isinstance(operator_approval, str) or
            not isinstance(expected_approval, str) or
            len(expected_approval) < 24 or
            not hmac.compare_digest(operator_approval, expected_approval)):
        return ExecutionDecision(False, 'independent operator approval missing')
    try:
        notional = Decimal(order_notional_usd)
        ceiling = Decimal(max_order_notional_usd)
    except (InvalidOperation, TypeError, ValueError):
        return ExecutionDecision(False, 'invalid order notional or limit')
    if (not notional.is_finite() or not ceiling.is_finite()
            or not 0 < notional <= ceiling):
        return ExecutionDecision(False, 'order notional exceeds approved limit')
    # This repository has no reviewed broker execution adapter. The gate
    # intentionally cannot issue permission based on caller-supplied booleans.
    return ExecutionDecision(False, 'broker execution adapter not independently verified')
