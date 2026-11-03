# Phase 79 — Outbox confirmation race regression

Reconciliation validates the outbox before remote custody publication and validates it again after acquiring the SQLite immediate write transaction. Tests simulate intervening local changes at the remote publication boundary: missing first or middle rows, substituted event hash and invalid confirmation order. All four scenarios must fail before the final custody read and must not mark additional rows confirmed.

These tests exercise the existing transaction-time validation, not a distributed lock. Remote custody may already have advanced when local confirmation is denied. Recovery mutation must not be retried automatically.
