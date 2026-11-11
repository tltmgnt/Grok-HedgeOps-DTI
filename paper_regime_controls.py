"""Optional fail-closed PAPER entry gate. Never authorizes a broker order.

Activation is explicit for staged testing; once active, missing/unreviewed,
stale, bear, neutral and unknown evidence block NEW buys. This module cannot
override the broker's own risk, approval or durable-ledger requirements.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from market_regime_validation import classify, timestamp, MAX_AGE


def entry_block_reason(*, now=None, environ=None):
    """Return None only for approved, independently reviewed bull evidence.

    Disabled mode preserves existing behavior for staged rollout; it is NOT
    evidence of market suitability. An activated control fails closed.
    """
    env = os.environ if environ is None else environ
    if env.get("PAPER_REGIME_CONTROL_ENABLED") != "true":
        return None
    if env.get("PAPER_REGIME_REVIEW_APPROVED") != "true":
        return "Regime gate: independent review approval missing"
    path = env.get("PAPER_REGIME_EVIDENCE_FILE", "")
    if not path:
        return "Regime gate: evidence unavailable"
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None or now.utcoffset() is None:
        return "Regime gate: invalid clock"
    try:
        evidence = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(evidence, dict):
            return "Regime gate: invalid evidence"
        decision_time = timestamp(evidence["decision_at"])
        observed = timestamp(evidence["observed_at"])
        if decision_time > now or not 0 <= (now - observed).total_seconds() <= MAX_AGE.total_seconds():
            return "Regime gate: stale or future evidence"
        # Do not accept a previously reviewed decision from a different session
        # or an evidence file that is newer than its own decision timestamp.
        if evidence.get("evidence_verified") is not True:
            return "Regime gate: evidence not verified"
        if classify(evidence) != "BULL":
            return "Regime gate: market is not verified BULL"
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return "Regime gate: evidence unavailable or invalid"
    return None
