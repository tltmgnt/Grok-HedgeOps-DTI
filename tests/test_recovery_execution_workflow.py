"""Phase 63 integrated execution and reconciliation status tests."""
import unittest
from unittest.mock import patch

from hedgeops.recovery_execution_workflow import (
    CommittedRecoveryUnconfirmed, execute_and_reconcile_recovery)
from hedgeops.recovery_execution_reconciliation import ExecutionReconciliationError


class IntegratedWorkflowTests(unittest.TestCase):
    def run_workflow(self):
        return execute_and_reconcile_recovery(
            None, None, None, None, None, None, None, None,
            1, "test-token", lambda db: "mutated",
            custody_key=b"k" * 32, custody_custodian=object())

    def test_success_returns_result_and_checkpoint(self):
        with patch("hedgeops.recovery_execution_workflow.execute_fenced_recovery",
                   return_value="done") as execute, patch(
                       "hedgeops.recovery_execution_workflow.reconcile_execution_custody",
                       return_value={"sequence": 2}) as reconcile:
            self.assertEqual(self.run_workflow(), ("done", {"sequence": 2}))
            execute.assert_called_once()
            reconcile.assert_called_once()

    def test_publication_failure_marks_local_commit(self):
        with patch("hedgeops.recovery_execution_workflow.execute_fenced_recovery",
                   return_value="done") as execute, patch(
                       "hedgeops.recovery_execution_workflow.reconcile_execution_custody",
                       side_effect=ExecutionReconciliationError("offline")):
            with self.assertRaises(CommittedRecoveryUnconfirmed) as caught:
                self.run_workflow()
            self.assertTrue(caught.exception.local_committed)
            self.assertIsInstance(caught.exception.cause, ExecutionReconciliationError)
            execute.assert_called_once()

    def test_mutation_failure_never_attempts_publication(self):
        with patch("hedgeops.recovery_execution_workflow.execute_fenced_recovery",
                   side_effect=PermissionError("admission denied")), patch(
                       "hedgeops.recovery_execution_workflow.reconcile_execution_custody"
                   ) as reconcile:
            with self.assertRaises(PermissionError):
                self.run_workflow()
            reconcile.assert_not_called()

    def test_unexpected_post_commit_error_is_marked_unconfirmed(self):
        with patch("hedgeops.recovery_execution_workflow.execute_fenced_recovery",
                   return_value="done"), patch(
                       "hedgeops.recovery_execution_workflow.reconcile_execution_custody",
                       side_effect=ValueError("invalid checkpoint")):
            with self.assertRaises(CommittedRecoveryUnconfirmed) as caught:
                self.run_workflow()
            self.assertIsInstance(caught.exception.cause, ValueError)


if __name__ == "__main__":
    unittest.main()
