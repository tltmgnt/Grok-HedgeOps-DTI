"""Durable, hash-chained custody alert journal (local integrity only).

The chain is not externally anchored and cannot detect whole-database rollback.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

from hedgeops.store import canonical

SCHEME = "hedgeops-custody-alert-journal-v1"
ALLOWED = frozenset(("authentication_failures", "rate_limited",
                     "service_unavailable", "connection_rejections"))
GENESIS = "GENESIS"


def _digest(body):
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def _validated_alerts(alerts):
    if not isinstance(alerts, list):
        raise ValueError("Alerts must be a list")
    result = []
    for alert in alerts:
        if (not isinstance(alert, dict) or
                set(alert) != {"event", "count", "threshold"} or
                alert["event"] not in ALLOWED or
                type(alert["count"]) is not int or alert["count"] < 1 or
                type(alert["threshold"]) is not int or alert["threshold"] < 1 or
                alert["count"] < alert["threshold"]):
            raise ValueError("Invalid custody alert")
        result.append(dict(alert))
    if len(result) != len(set(item["event"] for item in result)):
        raise ValueError("Duplicate alert event")
    return result


def _validated_evaluation(evaluation):
    if (not isinstance(evaluation, dict) or
            set(evaluation) != {"baseline", "counter_reset", "alerts"} or
            type(evaluation["baseline"]) is not bool or
            type(evaluation["counter_reset"]) is not bool):
        raise ValueError("Invalid alert evaluation")
    alerts = _validated_alerts(evaluation["alerts"])
    if evaluation["baseline"] and alerts:
        raise ValueError("Baseline cannot include alerts")
    if evaluation["counter_reset"] and not evaluation["baseline"]:
        raise ValueError("Reset must establish a baseline")
    return {"baseline": evaluation["baseline"],
            "counter_reset": evaluation["counter_reset"], "alerts": alerts}


class CustodyAlertJournal:
    def __init__(self, path):
        self.path = str(Path(path))
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS custody_alert_events (
                sequence INTEGER PRIMARY KEY,
                previous_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                event_hash TEXT NOT NULL)""")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _body(sequence, previous_hash, payload):
        return {"scheme": SCHEME, "sequence": sequence,
                "previous_hash": previous_hash, "payload": payload}

    @classmethod
    def _verify_rows(cls, rows):
        previous = GENESIS
        for sequence, prev, raw, digest in rows:
            if type(sequence) is not int or sequence < 1:
                return False
            if sequence != cls._next_sequence or prev != previous:
                return False
            try:
                payload = json.loads(raw)
                if _validated_evaluation(payload) != payload:
                    return False
                if canonical(payload) != raw:
                    return False
            except (ValueError, TypeError, KeyError):
                return False
            if digest != _digest(cls._body(sequence, prev, payload)):
                return False
            previous = digest
            cls._next_sequence += 1
        return True

    def verify(self):
        with self._connect() as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            rows = db.execute(
                "SELECT sequence,previous_hash,payload,event_hash "
                "FROM custody_alert_events ORDER BY sequence").fetchall()
        return self._verify_chain(rows)

    @classmethod
    def _verify_chain(cls, rows):
        previous = GENESIS
        for expected, (sequence, prev, raw, digest) in enumerate(rows, 1):
            if sequence != expected or prev != previous:
                return False
            try:
                payload = json.loads(raw)
                if _validated_evaluation(payload) != payload or canonical(payload) != raw:
                    return False
            except (ValueError, TypeError, KeyError):
                return False
            if digest != _digest(cls._body(sequence, prev, payload)):
                return False
            previous = digest
        return True

    def append(self, evaluation):
        payload = _validated_evaluation(evaluation)
        raw = canonical(payload)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT sequence,previous_hash,payload,event_hash "
                "FROM custody_alert_events ORDER BY sequence").fetchall()
            if not self._verify_chain(rows):
                raise ValueError("Alert journal chain invalid")
            sequence = len(rows) + 1
            previous = rows[-1][3] if rows else GENESIS
            digest = _digest(self._body(sequence, previous, payload))
            db.execute(
                "INSERT INTO custody_alert_events VALUES (?,?,?,?)",
                (sequence, previous, raw, digest))
            db.commit()
        return {"sequence": sequence, "event_hash": digest}

    def head(self):
        with self._connect() as db:
            row = db.execute(
                "SELECT sequence,event_hash FROM custody_alert_events "
                "ORDER BY sequence DESC LIMIT 1").fetchone()
        return {"sequence": row[0], "event_hash": row[1]} if row else {
            "sequence": 0, "event_hash": GENESIS}
