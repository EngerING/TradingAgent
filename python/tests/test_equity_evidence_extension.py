from datetime import datetime,timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from trading_agent.broker import PaperOptions
from trading_agent.equity_research_data import normalize
from trading_agent.equity_evidence_extension import (extension_wire,HISTORY_START,HISTORY_END,protocol,
    fact,reported_value,feasibility,episodes,partition_series,prepared_episodes,decision,final_gate,capital_requirement,quality)
from trading_agent.equity_strategy_research import FAMILIES
from test_equity_research_data import StockClient


class EvidenceClient(StockClient):
    def reqAccountUpdatesMulti(self,req,account,model,ledger):
        self.wrapper.accountUpdateMulti(req,account,model,'CashBalance','1000000','USD')
        self.wrapper.accountUpdateMulti(req,account,model,'DayTradesRemaining','-1','')
        self.wrapper.accountUpdateMultiEnd(req)
    def cancelAccountUpdatesMulti(self,*args):pass
    def reqHistoricalData(self,req,c,end,duration,size,kind,*args):
        self.calls.append((c.symbol,end,duration,size,kind))
        self.wrapper.historicalData(req,SimpleNamespace(date='20250702' if size=='1 day' else '1751463000',
            open=20,high=21,low=19,close=20,volume=100))
        self.wrapper.historicalDataEnd(req,'','')


class EquityEvidenceExtensionTests(unittest.TestCase):
    def wire(self):
        return extension_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.05),
                              (EvidenceClient,object,SimpleNamespace))

    def test_extended_reader_still_blocks_every_order_path(self):
        w=self.wire();w.connect()
        for name in ('placeOrder','placeOrderProtoBuf','cancelOrder','reqGlobalCancel','exerciseOptions'):
            with self.assertRaises(PermissionError):getattr(w._client,name)(1)
        w.disconnect()

    def test_archived_native_request_records_exact_duration_kind_and_completion(self):
        w=self.wire();w.connect();w.last_history=-1000
        rows=w.historical('SCHX',60,HISTORY_END,'1 Y')
        self.assertEqual(1,len(rows));self.assertEqual('TRADES',w._client.calls[-1][-1]);w.disconnect()

    def test_scope_rejects_live_tail_old_universe_and_unbounded_sizes(self):
        w=self.wire()
        for args in [('SCHX',60,datetime.now(timezone.utc),'1 Y'),('UNKNOWN',60,HISTORY_END,'1 Y'),
                     ('SCHX',60,HISTORY_END,'6 Y'),('SCHX',60,HISTORY_END,'1 Y','ADJUSTED_LAST')]:
            with self.assertRaises(ValueError):w.historical(*args)

    def test_multi_account_missing_settled_cash_remains_missing(self):
        w=self.wire();w.connect();rows=w.multi_account()
        self.assertFalse(any(r['tag']=='SettledCash' for r in rows))
        self.assertEqual('-1',next(x['value'] for x in rows if x['tag']=='DayTradesRemaining'))
        self.assertNotIn('DU123',str(rows));w.disconnect()

    def test_multi_end_missing_or_foreign_account_fails_closed(self):
        w=self.wire();w.connect();w._client.reqAccountUpdatesMulti=lambda *a:None
        with self.assertRaises(TimeoutError):w.multi_account()
        req=w._begin('evidence_multi');w.accountUpdateMulti(req,'U999','','SettledCash','0','USD')
        self.assertFalse(w.connected);w.disconnect()

    def test_normalizer_extends_scope_without_changing_prior_default(self):
        session=dict(day='20210702',start='20210702-09:30:00',end='20210702-16:00:00',time_zone='US/Eastern')
        r=dict(broker_date='20210702',minutes=1440,open='20',high='21',low='19',close='20',volume='100')
        self.assertEqual([],normalize([r],[session]))
        rows=normalize([r],[session],start=HISTORY_START,end=HISTORY_END)
        self.assertEqual('2021-07-02T13:30:00+00:00',rows[0]['opened_at'])
        with self.assertRaises(ValueError):normalize([r],[session],start=HISTORY_END,end=HISTORY_START)

    def test_adjusted_last_uses_empty_sdk_end_required_by_ibkr(self):
        w=self.wire();w.connect();w.last_history=-1000
        rows=w.historical('SCHX',1440,HISTORY_END,'6 Y','ADJUSTED_LAST')
        self.assertEqual('',w._client.calls[-1][1]);self.assertEqual('ADJUSTED_LAST',w._client.calls[-1][-1])
        self.assertEqual(1,len(rows));w.disconnect()

    def test_fact_unknown_never_contains_invented_zero(self):
        self.assertIsNone(fact('EUR','UNKNOWN',None,'TEST','TEST')['value'])
        for status,value in [('UNKNOWN',0),('APPROVED',None)]:
            with self.assertRaises(ValueError):fact('EUR',status,value,'TEST','TEST')

    def test_reported_zero_is_verified_only_after_complete_query_and_no_conflict(self):
        r={'usd_ledger_completed':True,'usd_ledger':[dict(tag='SettledCash',value='0',currency='USD')]}
        self.assertEqual('0',reported_value(r,'SettledCash','USD'))
        r['usd_ledger_completed']=False;self.assertIsNone(reported_value(r,'SettledCash','USD'))
        r['usd_ledger_completed']=True;r['usd_ledger'].append(dict(tag='SettledCash',value='10',currency='USD'))
        self.assertIsNone(reported_value(r,'SettledCash','USD'))

    def test_available_paper_million_and_margin_code_do_not_verify_execution(self):
        r={'identity_verified':True,'account':'***0123','account_observation_completed':True,
            'account_observation':[dict(tag='AvailableFunds',value='1000000',currency='USD')],
            'account_details_completed':True,'account_details':{'values':[dict(tag='TradingType-S',value='STKNOPT',currency='')]}}
        f={x['name']:x for x in feasibility(r)['facts']}
        self.assertEqual('VERIFIED',f['AvailableFunds_USD']['status']);self.assertEqual('UNKNOWN',f['SettledCash_USD']['status'])
        self.assertEqual('ESTIMATED',f['account_margin_class']['status']);self.assertFalse(f['production_stock_adapter']['value'])
        self.assertFalse(feasibility(r)['execution_authorized'])

    def test_contract_order_types_do_not_prove_permissions_or_effective_protection(self):
        r={'symbols':{'SCHX':{'contract':{'con_id':123,'order_types':'LMT,STP,OCA'}}}}
        f={x['name']:x for x in feasibility(r)['facts']}
        self.assertEqual('VERIFIED',f['SCHX_declared_protective_types']['status'])
        for name in ('stock_etf_trading_permissions','effective_stock_bracket_protection'):
            self.assertEqual('UNKNOWN',f[name]['status']);self.assertIsNone(f[name]['value'])

    def test_schx_pre_split_prices_restore_historical_whole_share_notional(self):
        from test_equity_strategy_research import bars
        rows=bars(2);rows[0].update(opened_at='2024-10-10T13:30:00Z',closed_at='2024-10-10T14:00:00Z')
        rows[1].update(opened_at='2024-10-11T13:30:00Z',closed_at='2024-10-11T14:00:00Z')
        series,events=episodes('SCHX',rows)
        self.assertEqual(30.,series['SCHX_PRE_20241011'][0]['open'])
        self.assertEqual(10.,series['SCHX_POST_20241011'][0]['open'])
        self.assertEqual('ESTIMATED',events[0]['price_reconstruction_status']);self.assertEqual(1000,series['SCHX_PRE_20241011'][0]['volume'])
        self.assertEqual(rows,episodes('F',rows)[0]['F'])

    def test_final_and_old_validation_never_enter_selection_features(self):
        from test_equity_strategy_research import bars
        rows=bars(3)
        for row,year in zip(rows,(2023,2025,2026)):
            row.update(opened_at=f'{year}-08-03T13:30:00Z',closed_at=f'{year}-08-03T14:30:00Z')
        data={'symbols':{'F':{'bars':{'60':rows,'1440':[]}}}}
        result,_=partition_series(data,datetime(2025,1,1,tzinfo=timezone.utc))
        self.assertEqual(1,len(result[60]['F']));self.assertTrue(result[60]['F'][0]['opened_at'].startswith('2023'))

    def test_execution_blocker_has_priority_and_final_is_required_for_viability(self):
        row={'selection':{'passes_for_final':True,'status':'VIABLE_FOR_FURTHER_PAPER_VALIDATION'},'final':None}
        self.assertEqual('EXECUTION_CONSTRAINT_BLOCKED',decision({'execution_blockers':['permissions']},{'eligible_for_promotion':True},[row]))
        self.assertEqual('INSUFFICIENT_EVIDENCE',decision({'execution_blockers':[]},{'eligible_for_promotion':True},[row]))
        self.assertEqual('NO_VIABLE_STRATEGY_FOUND',decision({'execution_blockers':[]},{'eligible_for_promotion':True},
            [{'selection':{'passes_for_final':False,'status':'NO_VIABLE_STRATEGY_FOUND'}}]))

    def test_missing_quality_is_not_coverage_success_or_promotion(self):
        q=quality({'symbols':{}})
        self.assertFalse(q['coverage_complete']);self.assertFalse(q['eligible_for_promotion'])
        self.assertFalse(q['corporate_action_accounting_complete'])

    def test_capital_requirement_counts_cash_fees_gap_and_risk_without_authorization(self):
        r=capital_requirement(10,9,12)
        self.assertIsNotNone(r);self.assertGreater(r['potential_target_net'],0)
        self.assertGreaterEqual(r['minimum_capital_usd'],r['cash_required_usd'])
        self.assertLessEqual(r['risk_usd'],r['minimum_capital_usd']*.15+1e-9)
        self.assertGreater(r['gap_reserve_usd'],0);self.assertFalse(r['execution_authorized'])
        self.assertIsNone(capital_requirement(10,9,10.02));self.assertIsNone(capital_requirement(10,11,12))

    def test_more_spread_cannot_reduce_minimum_capital(self):
        base=capital_requirement(10,9,12);stress=capital_requirement(10,9,12,observed_spread=.01)
        self.assertGreaterEqual(stress['minimum_capital_usd'],base['minimum_capital_usd'])

    def test_split_boundary_excludes_unaccounted_inventory_without_altering_signals(self):
        candidates=[dict(entry_index=2),dict(entry_index=85)]
        with patch('trading_agent.equity_evidence_extension.signals',return_value=(candidates,[])):
            result,excluded=prepared_episodes({'SCHX_PRE_20241011':[{}]*100,'F':[{}]*100},FAMILIES[0])
        self.assertEqual(1,excluded)
        self.assertEqual([candidates[0]],result['SCHX_PRE_20241011'][0])
        self.assertEqual(candidates,result['F'][0])

    def test_high_win_rate_without_sample_confidence_profit_or_finality_cannot_pass(self):
        import copy
        result=dict(metrics=dict(admitted=120,trade_days=40,win_rate=.95,net_expectancy=.2,
            net_pnl=24,profit_factor=2,maximum_drawdown=.1,risk_budget_breaches=0,pending_position=None),
            confidence=dict(win_wilson_family_adjusted=[.85,.99],block_bootstrap_expectancy_ci=[.01,.4]))
        self.assertTrue(final_gate(result))
        for key,value in [('admitted',5),('net_expectancy',-.01),('pending_position',{'quantity':1}),
                          ('risk_budget_breaches',1)]:
            changed=copy.deepcopy(result);changed['metrics'][key]=value
            self.assertFalse(final_gate(changed))
        for key,value in [('win_wilson_family_adjusted',[.7,.99]),('block_bootstrap_expectancy_ci',[-.1,.4])]:
            changed=copy.deepcopy(result);changed['confidence'][key]=value
            self.assertFalse(final_gate(changed))
