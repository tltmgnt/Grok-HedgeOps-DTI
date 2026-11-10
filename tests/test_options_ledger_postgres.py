"""PostgreSQL-backed options ledger invariants; no broker calls.

Run against a disposable PostgreSQL database with OPTIONS_TEST_DATABASE_URL set.
The test schema is isolated and dropped after the test suite.
"""
import os
from pathlib import Path
import unittest
import uuid

try:
    import psycopg
    from psycopg import errors
except ImportError:
    psycopg = None

MIGRATION = (Path(__file__).resolve().parents[1] /
             'migrations/20261110_options_intent_ledger.sql')


@unittest.skipUnless(psycopg is not None and os.getenv('OPTIONS_TEST_DATABASE_URL'),
                     'requires psycopg and OPTIONS_TEST_DATABASE_URL')
class OptionsLedgerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'options_test_' + uuid.uuid4().hex
        cls.db = psycopg.connect(os.environ['OPTIONS_TEST_DATABASE_URL'], autocommit=True)
        cls.db.execute('CREATE SCHEMA ' + cls.schema)
        cls.db.execute('SET search_path TO ' + cls.schema + ', public')
        cls.db.execute(MIGRATION.read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'db'):
            cls.db.execute('DROP SCHEMA IF EXISTS ' + cls.schema + ' CASCADE')
            cls.db.close()

    def reserve(self, client_id=None, *, broker_id=None):
        intent = str(uuid.uuid4())
        self.db.execute(
            """INSERT INTO options_order_intents
               (intent_id, client_order_id, account_id, environment,
                contract_symbol, side, quantity, limit_price, payload_sha256,
                broker_order_id)
               VALUES (%s, %s, 'acct', 'paper', 'SPY   271119C00500000',
                       'buy', 1, 2.50, %s, %s)""",
            (intent, client_id or intent, 'a' * 64, broker_id))
        return intent

    def test_duplicate_client_order_id_rejected(self):
        client_id = str(uuid.uuid4())
        self.reserve(client_id)
        with self.assertRaises(errors.UniqueViolation):
            self.reserve(client_id)

    def test_delete_and_identity_mutation_rejected(self):
        intent = self.reserve()
        with self.assertRaises(errors.RaiseException):
            self.db.execute('DELETE FROM options_order_intents WHERE intent_id = %s',
                            (intent,))
        with self.assertRaises(errors.RaiseException):
            self.db.execute(
                "UPDATE options_order_intents SET quantity = 2 WHERE intent_id = %s",
                (intent,))

    def test_ambiguous_submission_and_terminal_transition(self):
        intent = self.reserve()
        self.db.execute(
            "UPDATE options_order_intents SET status = 'submission_unknown' WHERE intent_id = %s",
            (intent,))
        with self.assertRaises(errors.RaiseException):
            self.db.execute(
                "UPDATE options_order_intents SET status = 'reserved' WHERE intent_id = %s",
                (intent,))
        self.db.execute(
            """UPDATE options_order_intents
               SET status = 'acknowledged', broker_order_id = %s
               WHERE intent_id = %s""",
            (str(uuid.uuid4()), intent))
        self.db.execute(
            "UPDATE options_order_intents SET status = 'filled' WHERE intent_id = %s",
            (intent,))
        with self.assertRaises(errors.RaiseException):
            self.db.execute(
                "UPDATE options_order_intents SET status = 'cancelled' WHERE intent_id = %s",
                (intent,))

    def test_append_only_events(self):
        intent = self.reserve()
        event_id = self.db.execute(
            """INSERT INTO options_order_events (intent_id, event_type)
               VALUES (%s, 'reserved') RETURNING event_id""", (intent,)).fetchone()[0]
        with self.assertRaises(errors.RaiseException):
            self.db.execute('DELETE FROM options_order_events WHERE event_id = %s',
                            (event_id,))
        with self.assertRaises(errors.RaiseException):
            self.db.execute(
                "UPDATE options_order_events SET event_type = 'filled' WHERE event_id = %s",
                (event_id,))

    def test_broker_id_uniqueness_and_ack_requires_id(self):
        broker_id = str(uuid.uuid4())
        self.reserve(broker_id=broker_id)
        with self.assertRaises(errors.UniqueViolation):
            self.reserve(broker_id=broker_id)
        intent = self.reserve()
        self.db.execute(
            "UPDATE options_order_intents SET status = 'submission_unknown' WHERE intent_id = %s",
            (intent,))
        with self.assertRaises(errors.CheckViolation):
            self.db.execute(
                "UPDATE options_order_intents SET status = 'acknowledged' WHERE intent_id = %s",
                (intent,))


if __name__ == '__main__':
    unittest.main()
