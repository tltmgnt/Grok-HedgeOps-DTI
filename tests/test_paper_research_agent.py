from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import MagicMock, patch
import pytest

import paper_research_agent as agent
from paper_opportunity_intelligence import main as entry_main


def candidate():
    return {'decision': 'READY', 'symbol': 'SPY', 'notional_usd': '10.00',
            'signal': {'return_5d_pct': 4, 'relative_volume_1d': 2},
            'quote': {'ask': '500', 'timestamp': datetime.now(timezone.utc).isoformat()},
            'catalyst_headlines': [{'headline': 'Results published'}]}


def test_review_rejects_invented_evidence():
    packet = agent.evidence_packet(candidate())
    review = agent.fallback_review(packet)
    review['evidence_ids'] = ['fake-source']
    with pytest.raises(ValueError, match='fabricated'):
        agent.validate_review(review, packet)


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(notional_usd='100000'),
    lambda r: r.update(verdict='BUY'),
    lambda r: r.update(evidence_ids=[]),
    lambda r: r.update(unknowns='nothing'),
    lambda r: r.update(counterargument=''),
])
def test_invalid_model_output_cannot_authorize_entry(mutate):
    packet = agent.evidence_packet(candidate())
    review = agent.fallback_review(packet)
    mutate(review)
    with pytest.raises(ValueError):
        agent.validate_review(review, packet)


def test_ai_timeout_defers_and_call_budget_prevents_retries(tmp_path):
    infer = MagicMock(side_effect=TimeoutError)
    review = agent.Reviewer(agent.Journal(tmp_path/'events.jsonl'), key='test', model='test-model', inference=infer)
    assert review(candidate())['verdict'] == 'DEFER'
    assert review(candidate())['verdict'] == 'DEFER'
    infer.assert_called_once()


def test_ai_required_missing_configuration_never_passes(tmp_path):
    reviewer = agent.Reviewer(agent.Journal(tmp_path/'events.jsonl'), mode='required')
    assert reviewer(candidate())['verdict'] == 'DEFER'
    assert reviewer.calls == 0


def test_auto_fallback_is_explicitly_not_ai(tmp_path):
    reviewer = agent.Reviewer(agent.Journal(tmp_path/'events.jsonl'))
    result = reviewer(candidate())
    assert result['verdict'] == 'PASS'
    assert result['provider'] == 'deterministic'
    assert reviewer.calls == 0


def test_review_cannot_mutate_executor_order(tmp_path):
    with patch('paper_opportunity_intelligence.assess', return_value=candidate()), \
         patch('paper_opportunity_intelligence.execute', return_value={'decision': 'SKIP'}) as execute:
        def mutate(decision):
            decision['symbol'] = 'NVDA'
            decision['notional_usd'] = '200'
            return {'verdict': 'PASS'}
        assert entry_main(['--output-dir', str(tmp_path)], reviewer=mutate) == 0
    assert execute.call_args.args[0]['symbol'] == 'SPY'
    assert execute.call_args.args[0]['notional_usd'] == '10.00'


def test_reject_stops_before_post_and_preserves_review(tmp_path):
    with patch('paper_opportunity_intelligence.assess', return_value=candidate()), \
         patch('paper_opportunity_intelligence.execute') as execute:
        assert entry_main(['--output-dir', str(tmp_path)], reviewer=lambda d: {'verdict': 'REJECT'}) == 0
    execute.assert_not_called()
    decision = json.loads((tmp_path/'decision.json').read_text())
    assert decision['decision'] == 'SKIP'
    assert decision['assessments'][0]['agent_review']['verdict'] == 'REJECT'


def test_monitor_reviews_without_execution(tmp_path):
    reviewer = MagicMock(return_value={'verdict': 'PASS'})
    with patch('paper_opportunity_intelligence.assess', return_value=candidate()), \
         patch('paper_opportunity_intelligence.execute') as execute:
        assert entry_main(['--monitor-only', '--output-dir', str(tmp_path)], reviewer=reviewer) == 0
    reviewer.assert_called_once()
    execute.assert_not_called()


def test_journal_detects_tampering(tmp_path):
    path = tmp_path/'events.jsonl'
    journal = agent.Journal(path)
    journal.record('PLAN', {'value': 1})
    journal.record('GATE', {'verdict': 'PASS'})
    assert agent.verify_journal(path) == journal.previous
    path.write_text(path.read_text().replace('"value":1', '"value":2'))
    with pytest.raises(ValueError, match='integrity'):
        agent.verify_journal(path)


def test_existing_output_directory_cannot_overwrite_journal(tmp_path):
    journal = agent.Journal(tmp_path/'events.jsonl')
    journal.record('PLAN', {})
    with pytest.raises(ValueError):
        agent.Journal(tmp_path/'events.jsonl')


def test_model_selection_checks_account_entitlement():
    def open_model(req, timeout):
        assert req.full_url == 'https://api.x.ai/v1/models'
        return BytesIO(json.dumps({'data': [{'id': 'grok-4.3'}]}).encode())
    assert agent.available_model('fake', opener=open_model) == 'grok-4.3'
    with pytest.raises(ValueError):
        agent.available_model('fake', requested='unavailable', opener=open_model)


def test_inference_has_no_tools_no_retries_and_bounded_output():
    packet = agent.evidence_packet(candidate())
    review = agent.fallback_review(packet)
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason='stop', message=SimpleNamespace(content=json.dumps(review)))])
    with patch('openai.OpenAI', return_value=client) as factory:
        assert agent.grok_review(packet, key='fake', model='test-model') == review
    assert factory.call_args.kwargs['max_retries'] == 0
    args = client.chat.completions.create.call_args.kwargs
    assert args['max_tokens'] == 1200
    assert 'tools' not in args
    assert args['response_format']['json_schema']['strict'] is True


def orders():
    return [dict(id='a', symbol='SPY', side='buy', client_order_id='hedgeopsauto-20261102-spy',
                 status='filled', filled_qty='1', filled_avg_price='100'),
            dict(id='b', symbol='SPY', side='sell', client_order_id='ho-exit-test',
                 status='filled', filled_qty='1', filled_avg_price='97')]


def test_losing_outcomes_are_counted_and_policy_not_changed():
    result = agent.reconcile_outcomes(orders())
    assert result['completed_round_trips'] == 1
    assert result['losing_or_flat_round_trips'] == 1
    assert result['realized_paper_pnl_usd'] == '-3'
    assert result['automatic_policy_changes'] is False


def test_manual_or_mixed_holdings_are_not_claimed_as_strategy_profit():
    broker = orders()+[dict(symbol='SPY', side='buy', client_order_id='manual',
                           status='filled', filled_qty='1', filled_avg_price='1')]
    result = agent.reconcile_outcomes(broker)
    assert result['completed_round_trips'] == 0
    assert result['mixed_symbols_excluded'] == 1


def test_pending_exit_is_never_claimed_as_realized_profit():
    broker = orders()
    broker[1]['status'] = 'accepted'
    result = agent.reconcile_outcomes(broker)
    assert result['completed_round_trips'] == 0
    assert result['pending_orders'] == 1


def test_process_runs_closed_market_and_records_learning(tmp_path):
    def run(command, *, entry_reviewer, event_sink):
        event_sink('OBSERVE', {'market_open': False})
        (tmp_path/'summary.md').write_text('Market closed\n')
        return 0
    with patch.dict(os.environ, {'ALPACA_API_KEY': 'fake', 'ALPACA_API_SECRET': 'fake'}, clear=True), \
         patch.object(agent, 'session_main', side_effect=run), \
         patch.object(agent, 'order_history', return_value=orders()):
        assert agent.main(['--output-dir', str(tmp_path), '--monitor-only']) == 0
    report = json.loads((tmp_path/'agent-report.json').read_text())
    assert report['ai']['status'] == 'NOT_CONFIGURED'
    assert report['outcomes']['completed_round_trips'] == 1
    stages = [json.loads(line)['stage'] for line in (tmp_path/'agent-events.jsonl').read_text().splitlines()]
    assert stages == ['PLAN', 'AI_CONFIGURATION', 'OBSERVE', 'RECONCILE_AND_LEARN', 'REPORT']


def test_unavailable_history_is_reported_not_optimized(tmp_path):
    with patch.dict(os.environ, {}, clear=True), patch.object(agent, 'session_main', return_value=1):
        assert agent.main(['--output-dir', str(tmp_path)]) == 1
    report = json.loads((tmp_path/'agent-report.json').read_text())
    assert report['status'] == 'ERROR'
    assert report['outcomes']['status'] == 'UNKNOWN'
