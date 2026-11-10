"""Offline checks for options ledger migration guardrails.

These do not replace PostgreSQL integration tests or prove runtime privileges.
"""
from pathlib import Path
import unittest

MIGRATION = (Path(__file__).resolve().parents[1] /
             'migrations/20261110_options_intent_ledger.sql')


class OptionsLedgerMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding='utf-8').lower()

    def test_unique_client_order_id_and_broker_reference(self):
        self.assertIn('client_order_id text not null unique', self.sql)
        self.assertIn('options_order_broker_id_unique', self.sql)
        self.assertIn('where broker_order_id is not null', self.sql)

    def test_immutable_identity_and_append_only_audit(self):
        self.assertIn('options_intent_guard()', self.sql)
        self.assertIn("if tg_op = 'delete' then", self.sql)
        self.assertIn('options_order_events_no_mutation()', self.sql)
        self.assertIn('before update or delete on options_order_events', self.sql)
        self.assertIn('before update or delete on options_order_intents', self.sql)

    def test_ambiguous_submission_is_a_first_class_state(self):
        self.assertIn("'submission_unknown'", self.sql)
        self.assertIn("old.status = 'reserved'", self.sql)
        self.assertIn("old.status = 'submission_unknown'", self.sql)
        self.assertIn('invalid options order status transition', self.sql)

    def test_no_grants_or_broker_calls_in_migration(self):
        # Migration is a storage foundation, not execution authorization.
        self.assertNotIn('grant insert', self.sql)
        self.assertNotIn('grant update', self.sql)
        self.assertNotIn('http_post', self.sql)


if __name__ == '__main__':
    unittest.main()
