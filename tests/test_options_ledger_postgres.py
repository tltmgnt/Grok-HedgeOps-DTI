"""PostgreSQL-backed options ledger invariants; no broker calls.

Run against a disposable PostgreSQL database with OPTIONS_TEST_DATABASE_URL set.
The test schema is isolated and dropped after the test suite.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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

    def test_public_has_no_ledger_or_audit_privileges(self):
        # PUBLIC is a pseudo-role (grantee OID 0), not a login role.
        for relation in ('options_order_intents', 'options_order_events'):
            with self.subTest(relation=relation):
                public_grants = self.db.execute(
                    """SELECT count(*) FROM pg_class c,
                       LATERAL aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) acl
                       WHERE c.oid = %s::regclass AND acl.grantee = 0""",
                    (relation,)).fetchone()[0]
                self.assertEqual(public_grants, 0)
        public_sequence_grants = self.db.execute(
            """SELECT count(*) FROM pg_class c,
               LATERAL aclexplode(coalesce(c.relacl, acldefault('S', c.relowner))) acl
               WHERE c.oid = 'options_order_events_event_id_seq'::regclass
                 AND acl.grantee = 0""").fetchone()[0]
        self.assertEqual(public_sequence_grants, 0)

    def test_public_cannot_execute_ledger_trigger_functions(self):
        # PostgreSQL grants EXECUTE on new functions to PUBLIC by default;
        # migration must explicitly revoke it.
        for function in ('options_order_events_no_mutation()',
                         'options_intent_guard()', 'options_intent_audit()'):
            with self.subTest(function=function):
                public_grants = self.db.execute(
                    """SELECT count(*) FROM pg_proc p,
                       LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
                       WHERE p.oid = %s::regprocedure AND acl.grantee = 0""",
                    (function,)).fetchone()[0]
                self.assertEqual(public_grants, 0)

    def test_duplicate_client_order_id_rejected(self):
        client_id = str(uuid.uuid4())
        self.reserve(client_id)
        with self.assertRaises(errors.UniqueViolation):
            self.reserve(client_id)

    def test_concurrent_reservations_only_one_wins(self):
        """Independent connections race to reserve the same client order ID."""
        client_id = str(uuid.uuid4())
        barrier = Barrier(2, timeout=10)

        def attempt(_):
            with psycopg.connect(os.environ['OPTIONS_TEST_DATABASE_URL'],
                                 autocommit=True) as db:
                db.execute('SET search_path TO ' + self.schema + ', public')
                barrier.wait()
                try:
                    db.execute(
                        """INSERT INTO options_order_intents
                           (intent_id, client_order_id, account_id, environment,
                            contract_symbol, side, quantity, limit_price, payload_sha256)
                           VALUES (%s, %s, 'acct', 'paper',
                                   'SPY   271119C00500000', 'buy', 1, 2.50, %s)""",
                        (str(uuid.uuid4()), client_id, 'a' * 64))
                    return 'reserved'
                except errors.UniqueViolation:
                    return 'duplicate'

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertCountEqual(outcomes, ['reserved', 'duplicate'])
        count = self.db.execute(
            'SELECT count(*) FROM options_order_intents WHERE client_order_id = %s',
            (client_id,)).fetchone()[0]
        self.assertEqual(count, 1)

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

    def test_ambiguous_order_cannot_be_declared_cancelled_or_rejected(self):
        intent = self.reserve()
        self.db.execute(
            "UPDATE options_order_intents SET status = 'submission_unknown' WHERE intent_id = %s",
            (intent,))
        for terminal in ('cancelled', 'rejected'):
            with self.subTest(terminal=terminal):
                with self.assertRaisesRegex(errors.RaiseException,
                                            'invalid options order status transition'):
                    self.db.execute(
                        'UPDATE options_order_intents SET status = %s WHERE intent_id = %s',
                        (terminal, intent))
        status = self.db.execute(
            'SELECT status FROM options_order_intents WHERE intent_id = %s',
            (intent,)).fetchone()[0]
        self.assertEqual(status, 'submission_unknown')
        events = self.db.execute(
            'SELECT event_type FROM options_order_events WHERE intent_id = %s ORDER BY event_id',
            (intent,)).fetchall()
        self.assertEqual([event[0] for event in events],
                         ['reserved', 'submission_unknown'])

    def test_broker_order_id_cannot_be_reassigned_or_cleared(self):
        intent = self.reserve()
        broker_id = str(uuid.uuid4())
        self.db.execute(
            "UPDATE options_order_intents SET status = 'submission_unknown' WHERE intent_id = %s",
            (intent,))
        self.db.execute(
            """UPDATE options_order_intents
               SET status = 'acknowledged', broker_order_id = %s
               WHERE intent_id = %s""",
            (broker_id, intent))
        for replacement in (str(uuid.uuid4()), None):
            with self.subTest(replacement=replacement):
                with self.assertRaisesRegex(errors.RaiseException, 'immutable once assigned'):
                    self.db.execute(
                        "UPDATE options_order_intents SET broker_order_id = %s WHERE intent_id = %s",
                        (replacement, intent))
        actual = self.db.execute(
            'SELECT broker_order_id FROM options_order_intents WHERE intent_id = %s',
            (intent,)).fetchone()[0]
        self.assertEqual(actual, broker_id)

    def test_reservation_and_transitions_are_audited_atomically(self):
        intent = self.reserve()
        broker_id = str(uuid.uuid4())
        self.db.execute(
            "UPDATE options_order_intents SET status = 'submission_unknown' WHERE intent_id = %s",
            (intent,))
        self.db.execute(
            """UPDATE options_order_intents
               SET status = 'acknowledged', broker_order_id = %s
               WHERE intent_id = %s""",
            (broker_id, intent))
        self.db.execute(
            "UPDATE options_order_intents SET status = 'filled' WHERE intent_id = %s",
            (intent,))
        rows = self.db.execute(
            """SELECT event_type, details FROM options_order_events
               WHERE intent_id = %s ORDER BY event_id""", (intent,)).fetchall()
        self.assertEqual([row[0] for row in rows],
                         ['reserved', 'submission_unknown', 'acknowledged', 'filled'])
        self.assertEqual(rows[1][1]['previous_status'], 'reserved')
        self.assertEqual(rows[2][1]['broker_order_id'], broker_id)
        with self.assertRaises(errors.RaiseException):
            self.db.execute(
                "UPDATE options_order_intents SET status = 'reserved' WHERE intent_id = %s",
                (intent,))
        count = self.db.execute(
            'SELECT count(*) FROM options_order_events WHERE intent_id = %s',
            (intent,)).fetchone()[0]
        self.assertEqual(count, 4)

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
