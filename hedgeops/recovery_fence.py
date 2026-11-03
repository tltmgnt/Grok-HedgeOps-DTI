"""Reference recovery fencing authority with atomic SQLite generations.

A generation only fences actions that call require_current() at their
commit boundary. SQLite is not an independently rollback-resistant authority.
"""
import sqlite3


class StaleRecoveryFence(ValueError):
    """Recovery operation no longer owns the current fencing generation."""


class RecoveryFenceAuthority:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS recovery_fence (
                id INTEGER PRIMARY KEY CHECK(id=1),
                generation INTEGER NOT NULL CHECK(generation >= 1))""")
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
