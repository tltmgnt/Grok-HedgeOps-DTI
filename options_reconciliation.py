"""Fail-closed, offline broker reconciliation checks.

This module only evaluates a snapshot. It never authenticates a broker, updates
the ledger, sends requests, or authorizes an order. The calling integration
must authenticate its broker session and bind the snapshot to that session.
"""
from __future__ import annotations

import re

FINAL = frozenset({'filled', 'cancelled', 'rejected'})
KNOWN = frozenset({'new', 'accepted', 'partially_filled', 'filled',
                   'cancelled', 'rejected', 'pending_cancel'})


def assess_snapshot(intent: dict, snapshot: dict) -> dict:
    """Return a proposed reconciliation, never an executable state change.

    Unknown/ambiguous broker responses remain unresolved. A missing order is
    NOT proof of rejection, cancellation, or non-submission.
    """
    if not isinstance(intent, dict) or not isinstance(snapshot, dict):
        raise ValueError('Intent and broker snapshot must be objects')
    required = ('client_order_id', 'account_id', 'environment',
                'contract_symbol', 'side', 'quantity')
    if any(not isinstance(intent.get(k), str) or not intent[k] for k in
           ('client_order_id', 'account_id', 'environment', 'contract_symbol', 'side')):
        raise ValueError('Invalid intent identity')
    if type(intent.get('quantity')) is not int or not 1 <= intent['quantity'] <= 100:
        raise ValueError('Invalid intent quantity')
    if intent.get('environment') not in ('paper', 'live'):
        raise ValueError('Invalid environment')
    if intent.get('status') != 'submission_unknown':
        raise ValueError('Only ambiguous submissions can be assessed')
    if not snapshot:
        return {'status': 'UNRESOLVED', 'reason': 'broker order not found',
                'database_write_authorized': False}
    for key in required:
        if snapshot.get(key) != intent[key] or type(snapshot.get(key)) is not type(intent[key]):
            raise ValueError('Broker snapshot identity mismatch: ' + key)
    order_id = snapshot.get('broker_order_id')
    if not isinstance(order_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', order_id):
        raise ValueError('Missing or invalid broker order ID')
    if intent.get('broker_order_id') not in (None, order_id):
        raise ValueError('Broker order ID conflicts with ledger')
    state = snapshot.get('status')
    if not isinstance(state, str) or state not in KNOWN:
        return {'status': 'UNRESOLVED', 'reason': 'unrecognized broker status',
                'database_write_authorized': False}
    # Even a terminal-looking snapshot cannot be written to the ledger here:
    # verified provenance, account ownership, freshness, and database role
    # authorization must be enforced by a separately reviewed integration.
    return {'status': 'REVIEW_REQUIRED', 'broker_status': state,
            'broker_order_id': order_id, 'terminal': state in FINAL,
            'database_write_authorized': False}
