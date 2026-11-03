"""Reference recovery fencing authority with atomic SQLite generations.

A generation only fences actions that call require_current() at their
commit boundary. SQLite is not an independently rollback-resistant authority.
"""
import sqlite3
import hashlib
import re
from hedgeops.operations import require_operator_token


class StaleRecoveryFence(ValueError):
    """Recovery operation no longer owns the current fencing generation."""


class RecoveryFenceAuthority:
    def __init__(self, path, *, strict=False):
        if type(strict) is not bool:
            raise ValueError("strict must be boolean")
        self.path = str(path)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS recovery_fence (
                id INTEGER PRIMARY KEY CHECK(id=1),
                generation INTEGER NOT NULL CHECK(generation >= 1))""")
            db.execute("""CREATE TABLE IF NOT EXISTS recovery_fence_issuance (
                generation INTEGER PRIMARY KEY,
                operator_digest TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS recovery_fence_policy (
                id INTEGER PRIMARY KEY CHECK(id=1),
                strict INTEGER NOT NULL CHECK(strict=1))""")
            if strict:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT OR IGNORE INTO recovery_fence_policy(id,strict) VALUES(1,1)")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def acquire(self):
        """Atomically issue a strictly increasing positive generation."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM recovery_fence_policy WHERE id=1").fetchone():
                raise PermissionError("Strict recovery fence requires authorized issuance")
            row = db.execute(
                "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
            if row is None:
                generation = 1
                db.execute(
                    "INSERT INTO recovery_fence(id,generation) VALUES(1,?)",
                    (generation,))
            else:
                generation = row[0] + 1
                db.execute(
                    "UPDATE recovery_fence SET generation=? WHERE id=1",
                    (generation,))
            db.commit()
            return generation

    def acquire_authorized(self, operator_id, token, *, configured_token=None):
        """Issue a generation with operator authentication and audit."""
        require_operator_token(token, configured_token)
        if not isinstance(operator_id, str) or re.fullmatch(
                r"[A-Za-z0-9_.@-]{1,80}", operator_id) is None:
            raise ValueError("Invalid operator identifier")
        operator_digest = hashlib.sha256(
            ("hedgeops-fence-operator-v1:" + operator_id).encode()).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
            generation = 1 if row is None else row[0] + 1
            if row is None:
                db.execute("INSERT INTO recovery_fence(id,generation) VALUES(1,?)",
                           (generation,))
            else:
                db.execute("UPDATE recovery_fence SET generation=? WHERE id=1",
                           (generation,))
            previous = db.execute(
                "SELECT event_hash FROM recovery_fence_issuance "
                "ORDER BY generation DESC LIMIT 1").fetchone()
            previous_hash = previous[0] if previous else "0" * 64
            event_hash = hashlib.sha256(
                ("hedgeops-fence-issuance-v1:" + str(generation) + ":" +
                 operator_digest + ":" + previous_hash).encode()).hexdigest()
            db.execute(
                "INSERT INTO recovery_fence_issuance "
                "(generation,operator_digest,previous_hash,event_hash) "
                "VALUES(?,?,?,?)",
                (generation, operator_digest, previous_hash, event_hash))
            db.commit()
            return generation

    def verify_issuance_audit(self):
        """Validate local hash continuity, not independent anchoring."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT generation,operator_digest,previous_hash,event_hash "
                "FROM recovery_fence_issuance ORDER BY generation").fetchall()
            previous_hash = "0" * 64
            last_generation = 0
            for generation, operator_digest, predecessor, event_hash in rows:
                if (generation <= last_generation or predecessor != previous_hash
                        or not isinstance(operator_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", operator_digest) is None):
                    return False
                expected = hashlib.sha256(
                    ("hedgeops-fence-issuance-v1:" + str(generation) + ":" +
                     operator_digest + ":" + predecessor).encode()).hexdigest()
                if expected != event_hash:
                    return False
                last_generation, previous_hash = generation, event_hash
            current = db.execute(
                "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
            return not rows or (current is not None and current[0] >= last_generation)

    def current(self):
        with self._connect() as db:
            row = db.execute(
                "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
            return row[0] if row else None

    def require_current(self, generation):
        """Read-only freshness check; not an atomic external commit guard."""
        if type(generation) is not int or generation < 1:
            raise StaleRecoveryFence("Invalid recovery fencing generation")
        if self.current() != generation:
            raise StaleRecoveryFence("Stale recovery fencing generation")
        return True

    def guarded_update(self, generation, callback):
        """Run a local SQLite mutation inside the fence transaction.

        callback(db) must use the provided connection and must not commit,
        rollback, or make remote side effects. All local fenced writers must
        share this same SQLite database and authority.
        """
        if type(generation) is not int or generation < 1:
            raise StaleRecoveryFence("Invalid recovery fencing generation")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT generation FROM recovery_fence WHERE id=1").fetchone()
            if row is None or row[0] != generation:
                raise StaleRecoveryFence("Stale recovery fencing generation")
            result = callback(db)
            db.commit()
            return result
