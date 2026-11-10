"""Paper submission contract tests using an in-memory broker; no network."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from investment_paper_execution import execute_one
from investment_research import main
from tests.test_investment_research import NOW, POLICY, policy, reviewed_policy, quote
from paper_opportunity_intelligence import PAPER, DATA

ENV = {'INVESTMENT_PAPER_ENABLED':'true', 'PAPER_AUTO_TRADING_ENABLED':'true',
       'PAPER_AUTO_KILL_SWITCH':'false', 'PAPER_ALLOCATION_MODE':'legacy'}


class Broker:
    def __init__(self):
        self.posts=[]; self.calls=[]; self.overrides={}
    def __call__(self, host, path, key, secret, *, params=None, payload=None):
        self.assert_host(host)
        self.calls.append((path, params, payload))
        if payload:
            self.posts.append(payload)
            return dict(payload, id='synthetic-order', status='accepted')
        if path in self.overrides:
            response = self.overrides[path]
            if path == '/v2/orders' and params and params.get('status') == 'open' and isinstance(response, list):
                response = [o for o in response if o.get('status') in ('new', 'accepted', 'partially_filled')]
            if isinstance(response, Exception):raise response
            return response
        if path.endswith('/quotes/latest'):
            return {'quote': {'t': NOW.isoformat(), 'bp':500, 'ap':500}}
        if path=='/v2/clock':return {'is_open':True}
        if path=='/v2/account':return {'status':'ACTIVE','trading_blocked':False,'account_blocked':False,
                                     'equity':'1000','last_equity':'1000','cash':'1000','buying_power':'1000'}
        if path in ('/v2/orders','/v2/positions'):return []
        if path=='/v2/orders:by_client_order_id':raise RuntimeError('Alpaca HTTP 404')
        if path.startswith('/v2/assets/'):return {'status':'active','tradable':True,'fractionable':True}
        raise AssertionError(path)
    def assert_host(self,host):
        if host not in (PAPER,DATA):raise AssertionError('live host')


class ExecutionTests(unittest.TestCase):
    def run_entry(self,p=None,broker=None,env=None,horizon='1-2y',audit=None):
        broker=broker or Broker()
        with patch.dict('os.environ', ENV if env is None else env, clear=True):
            result=execute_one(p or reviewed_policy(),horizon,key='fixture',secret='fixture',
                               get=broker,clock=lambda:NOW,audit=audit)
        return result,broker

    def test_default_and_kill_switch_no_network(self):
        for env in ({}, dict(ENV,PAPER_AUTO_KILL_SWITCH='true'),dict(ENV,INVESTMENT_PAPER_ENABLED='false')):
            r,b=self.run_entry(env=env)
            self.assertEqual(r['decision'],'SKIP'); self.assertEqual(b.calls,[])

    def test_only_fixed_ten_dollar_paper_day_limit_and_prepost_intent(self):
        events=[]
        def audit(e):
            self.assertEqual(b.posts,[]); events.append(e)
        b=Broker();r,b=self.run_entry(broker=b,audit=audit)
        self.assertEqual(r['decision'],'SUBMITTED'); self.assertFalse(r['order_filled'])
        self.assertEqual(len(b.posts),1)
        post=b.posts[0]
        self.assertEqual(post['notional'],'10.00');self.assertEqual(post['limit_price'],'520.00')
        self.assertEqual(post['type'],'limit'); self.assertEqual(post['time_in_force'],'day')
        self.assertTrue(post['client_order_id'].startswith('ho-invest-20261110-1-2y-'))
        self.assertEqual(events[0]['horizon'],'1-2y')

    def test_five_year_policy_and_identifier(self):
        b=Broker()
        def get(host,path,*a,**kw):
            if path.endswith('/quotes/latest'):return {'quote':{'t':NOW.isoformat(),'bp':470,'ap':470}}
            return b(host,path,*a,**kw)
        r,_=self.run_entry(broker=get,horizon='5y')
        self.assertEqual(r['decision'],'SUBMITTED')
        self.assertIn('-5y-',b.posts[0]['client_order_id'])
        self.assertEqual(b.posts[0]['limit_price'],'485.00')

    def test_example_policy_never_submits(self):
        r,b=self.run_entry(p=policy())
        self.assertEqual(r['decision'],'SKIP');self.assertEqual(b.posts,[])

    def test_existing_order_resolved_without_another_post(self):
        b=Broker();b.overrides['/v2/orders:by_client_order_id']={'id':'fixture','status':'partially_filled'}
        r,b=self.run_entry(broker=b)
        self.assertEqual(r['decision'],'ALREADY_EXISTS');self.assertEqual(b.posts,[])

    def test_risk_gate_and_holdings_prevent_submission(self):
        for path,response in [('/v2/positions',[{'symbol':'MSFT','market_value':'100'}]),
                              ('/v2/clock',{'is_open':False}),
                              ('/v2/account',{'status':'BLOCKED'}),
                              ('/v2/assets/MSFT',{'status':'inactive'}),
                              ('/v2/orders',[{'side':'buy','status':'new'}])]:
            b=Broker();b.overrides[path]=response
            r,b=self.run_entry(broker=b)
            self.assertEqual(r['decision'],'SKIP');self.assertEqual(b.posts,[])

    def test_previous_investment_attempt_blocks_both_horizons(self):
        b=Broker();b.overrides['/v2/orders']=[{'side':'buy','status':'rejected','notional':'10',
           'submitted_at':NOW.isoformat(),'client_order_id':'ho-invest-20261110-5y-googl'}]
        r,b=self.run_entry(broker=b)
        self.assertEqual(r['decision'],'SKIP');self.assertIn('One investment',r['reason'])

    def test_unsupported_lookup_failure_never_posts(self):
        b=Broker();b.overrides['/v2/orders:by_client_order_id']=RuntimeError('Alpaca HTTP 403')
        with self.assertRaises(RuntimeError):self.run_entry(broker=b)
        self.assertEqual(b.posts,[])

    def test_post_timeout_never_retries(self):
        b=Broker()
        def get(*a,**kw):
            if kw.get('payload'):
                b.posts.append(kw['payload']);raise TimeoutError('private-provider-message')
            return b(*a,**kw)
        r,_=self.run_entry(broker=get)
        self.assertEqual(r['decision'],'UNKNOWN_RECONCILE');self.assertEqual(len(b.posts),1)
        self.assertNotIn('private-provider',str(r))

    def test_final_quote_or_enable_change_blocks(self):
        b=Broker();count=0
        def get(*a,**kw):
            nonlocal count
            if a[1].endswith('/quotes/latest'):
                count+=1
                if count==2:return {'quote':{'t':NOW.isoformat(),'bp':530,'ap':530}}
            return b(*a,**kw)
        r,_=self.run_entry(broker=get)
        self.assertEqual(r['decision'],'SKIP');self.assertEqual(b.posts,[])

    def test_malformed_acknowledgment_is_uncertain_without_retry(self):
        for response in ({}, {'id':'bad'}, None):
            b=Broker()
            def get(*a,**kw):
                if kw.get('payload'):
                    b.posts.append(kw['payload']);return response
                return b(*a,**kw)
            r,_=self.run_entry(broker=get)
            self.assertEqual(r['decision'],'UNKNOWN_RECONCILE');self.assertEqual(len(b.posts),1)

    def test_enable_change_and_missing_credentials_block(self):
        import os
        b=Broker()
        def get(*a,**kw):
            if a[1].startswith('/v2/assets/'):
                os.environ['INVESTMENT_PAPER_ENABLED']='false'
            return b(*a,**kw)
        r,_=self.run_entry(broker=get)
        self.assertEqual(r['decision'],'SKIP');self.assertEqual(b.posts,[])
        with patch.dict('os.environ',ENV,clear=True):
            r=execute_one(reviewed_policy(),'1-2y',key='',secret='',get=b)
        self.assertEqual(r['decision'],'SKIP')

    def test_pre_submission_audit_failure_stops_post(self):
        b=Broker()
        def audit(event):raise OSError('synthetic disk full')
        with self.assertRaises(OSError):self.run_entry(broker=b,audit=audit)
        self.assertEqual(b.posts,[])

    def test_cli_uncertain_execution_is_failed_and_intent_saved(self):
        import json
        b=Broker()
        def get(*a,**kw):
            if kw.get('payload'):
                b.posts.append(kw['payload']);raise TimeoutError('synthetic timeout')
            return b(*a,**kw)
        def execution(p,h,**kw):
            return execute_one(p,h,**kw,get=get,clock=lambda:NOW)
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',dict(ENV,ALPACA_API_KEY='fixture',ALPACA_API_SECRET='fixture'),clear=True):
            path=Path(tmp)/'policy.json';path.write_text(json.dumps(reviewed_policy()))
            with patch('investment_research.collect_quotes',return_value=({'MSFT':quote()},[])), \
                 patch('investment_paper_execution.execute_one',side_effect=execution):
                self.assertEqual(main(['--policy',str(path),'--output',tmp,'--paper-entry']),1)
            report=json.loads((Path(tmp)/'research.json').read_text())
            self.assertEqual(report['execution']['decision'],'UNKNOWN_RECONCILE')
            self.assertIn('PAPER_ENTRY_INTENT',(Path(tmp)/'entry-intents.jsonl').read_text())

    def test_investment_lot_excluded_from_momentum_exits(self):
        from autonomous_paper_session import exit_plan
        stamp=(NOW-timedelta(days=10)).isoformat()
        pos={'symbol':'MSFT','side':'long','qty':'1','qty_available':'1','cost_basis':'500','market_value':'400'}
        buy={'id':'fixture','symbol':'MSFT','side':'buy','status':'filled','filled_qty':'1','filled_at':stamp,
             'submitted_at':stamp,'client_order_id':'ho-invest-20261031-5y-msft'}
        self.assertIsNone(exit_plan(pos,[buy],now=NOW))
