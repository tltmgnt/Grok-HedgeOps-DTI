"""Optional fail-closed PAPER entry gate. Never authorizes a broker order.

Activation is explicit for staged testing; once active, missing/unreviewed,
stale, bear, neutral and unknown evidence block NEW buys. This module cannot
override the broker's own risk, approval or durable-ledger requirements.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import json
import os
from pathlib import Path

from market_regime_validation import classify, timestamp

MAX_ENTRY_OBSERVATION_AGE = timedelta(hours=36)
MAX_APPROVAL_WINDOW = timedelta(hours=24)

# Domain separation and version pinning prevent reusing approvals for another
# operation or a future policy revision. The signing key is never in git.
APPROVAL_CONTEXT = b"HEDGEOPS:PAPER:REGIME_ENTRY:v1\n"
APPROVAL_POLICY = "regime-prototype-v1"


def _approval_message(digest, expires_at):
    # ASCII-only digest and an exact timestamp string. The latter is checked
    # for a timezone below; changes to it invalidate the authenticator.
    return (APPROVAL_CONTEXT +
            (APPROVAL_POLICY + "\n" + digest + "\n" + expires_at).encode("ascii"))


def _verify_approval(env, digest, expires_at):
    """Verify an out-of-band Ed25519 signature using only a public key.

    The signing private key MUST NOT exist in the trading runtime. Missing
    cryptography support or malformed keys/signatures fail closed.
    """
    key_hex = env.get("PAPER_REGIME_APPROVAL_PUBLIC_KEY", "")
    signature_hex = env.get("PAPER_REGIME_APPROVAL_SIGNATURE", "")
    pinned_key_id = env.get("PAPER_REGIME_APPROVAL_PUBLIC_KEY_SHA256", "")
    if (not isinstance(key_hex, str)
            or not re.fullmatch(r"[0-9a-f]{64}", key_hex)
            or not isinstance(signature_hex, str)
            or not re.fullmatch(r"[0-9a-f]{128}", signature_hex)
            or not isinstance(pinned_key_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", pinned_key_id)):
        return False
    public_key_bytes = bytes.fromhex(key_hex)
    if not hmac.compare_digest(hashlib.sha256(public_key_bytes).hexdigest(),
                               pinned_key_id):
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            bytes.fromhex(signature_hex),
            _approval_message(digest, expires_at),
        )
    except (ValueError, InvalidSignature, UnicodeEncodeError):
        return False
    return True


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
    expected_digest = env.get("PAPER_REGIME_APPROVED_SHA256", "")
    approval_expires = env.get("PAPER_REGIME_APPROVAL_EXPIRES_AT", "")
    if not path:
        return "Regime gate: evidence unavailable"
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        return "Regime gate: approved evidence digest missing"
    if not approval_expires:
        return "Regime gate: review expiry missing"
    if not _verify_approval(env, expected_digest, approval_expires):
        return "Regime gate: authenticated approval missing or invalid"
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None or now.utcoffset() is None:
        return "Regime gate: invalid clock"
    try:
        expiry = timestamp(approval_expires)
        if not now < expiry <= now + MAX_APPROVAL_WINDOW:
            return "Regime gate: approval expired or outside allowed window"
        # Pin the EXACT bytes reviewed via protected configuration. This
        # detects changed files but is not a digital signature or a source
        # authentication mechanism; reviewers must manage the digest separately.
        raw = Path(path).read_bytes()
        if len(raw) > 16384:
            return "Regime gate: evidence file too large"
        actual_digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            return "Regime gate: evidence does not match approved digest"
        evidence = json.loads(raw.decode("utf-8"))
        if not isinstance(evidence, dict):
            return "Regime gate: invalid evidence"
        decision_time = timestamp(evidence["decision_at"])
        observed = timestamp(evidence["observed_at"])
        if (decision_time > now or observed > decision_time
                or now - observed > MAX_ENTRY_OBSERVATION_AGE):
            return "Regime gate: stale or future evidence"
        # Reviewed evidence and claimed source IDs are assertions, not
        # verification of independent data rights or methodology.
        if evidence.get("evidence_verified") is not True:
            return "Regime gate: evidence not verified"
        if classify(evidence) != "BULL":
            return "Regime gate: market is not verified BULL"
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return "Regime gate: evidence unavailable or invalid"
    return None
