"""Disposable PostgreSQL + simulated broker + real journal CLI, never IBKR orders."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import hashlib
import os
from unittest.mock import patch
import unittest
import uuid
from trading_agent.paper_lab import Authorization,DotnetJournal,PaperLab,stamp
from test_paper_lab import grant,Wire

@unittest.skipUnless(os.environ.get('TRADING_TEST_DB'),'Disposable PostgreSQL required')
class PaperLabPostgresTests(unittest.TestCase):
    def test_absence_exception_consumption_and_pending_reconciliation_survive_sql_restart(self):
        from test_paper_eur_reconciliation import ExceptionWire,exception
        from trading_agent.paper_eur_reconciliation import AbsentEurAuthorization
        now=datetime.now(timezone.utc);a=grant();a['account']='DUR'+str(uuid.uuid4().int)
        a.update(confirmed_at=stamp(now),expires_at=stamp(now+timedelta(minutes=30)))
        e=exception();e.update(account=a['account'],confirmed_at=stamp(now),expires_at=stamp(now+timedelta(minutes=15)))
        a['eur_absence_exception_id']=e['record_id'];auth=Authorization(lambda:a,lambda *args:True,lambda:now)
        exc=AbsentEurAuthorization(lambda:e,lambda:now);w=ExceptionWire(lambda:now);w.accounts=[a['account']]
        root=Path(__file__).resolve().parents[2];intent=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        with patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']}):
            j=DotnetJournal(root);lab=PaperLab(auth,j,w,clock=lambda:now,eur_exception=exc);lab.begin(intent,100,w.quote())
            saved=j.load(lab.scope)['state'];self.assertIsNone(saved['orders'][intent]['initial_eur_uncertainty']['eur_balance'])
            self.assertEqual(intent,saved['eur_absence_consumed'][e['record_id']]['intent'])
            self.assertEqual('10',saved['sessions'][a['session_id']]['reserved'])
            restarted=PaperLab(auth,j,w,clock=lambda:now,eur_exception=exc)
            restarted.connect_and_reconcile()
            self.assertEqual('OWNED_PREFILL_EUR_ABSENCE',restarted.reconciliation_kind)
            with self.assertRaises(PermissionError):restarted.check()
            self.assertEqual(1,len(w.calls));self.assertEqual('10',j.load(lab.scope)['state']['sessions'][a['session_id']]['reserved'])
    def test_simulated_roundtrip_survives_restart_and_sql_journal(self):
        now=datetime.now(timezone.utc);a=grant();a['account']='DUR'+str(uuid.uuid4().int)
        a['confirmed_at']=stamp(now);a['expires_at']=stamp(now+timedelta(minutes=30))
        auth=Authorization(lambda:a,lambda *args:True,lambda:now);w=Wire(lambda:now);w.accounts=[a['account']]
        root=Path(__file__).resolve().parents[2];intent=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        with patch.dict(os.environ,{'TRADING_LAB_DB':os.environ['TRADING_TEST_DB']}):
            j=DotnetJournal(root);lab=PaperLab(auth,j,w,clock=lambda:now);lab.connect_and_reconcile();o=lab.begin(intent,100,w.quote())
            def fill(index,side,id,price):return {'kind':'fill','exec_id':id,'order_id':o['order_ids'][index],'perm_id':index+1,'client_id':82,'contract_id':12087792,'side':side,'quantity':'100','price':price,'broker_time_raw':'SYNTHETIC','at':stamp(now)}
            lab.ingest([fill(0,'BUY','entry','1.1001'),{'kind':'status','order_id':o['order_ids'][0],'status':'Filled','at':stamp(now)},fill(1,'SELL','exit','1.1011')])
            self.assertEqual('AWAITING_COMMISSIONS',o['state'])
            lab.ingest([{'kind':'commission','exec_id':id,'amount':'2','currency':'USD','at':stamp(now)} for id in ('entry','exit')])
            w.orders=[];w.eur_cash='0';restarted=PaperLab(auth,j,w,clock=lambda:now);restarted.connect_and_reconcile()
            self.assertEqual('CLOSED',restarted.state['orders'][intent]['state']);self.assertEqual('-3.9000',restarted.state['experiences'][intent]['net_usd'])
            self.assertEqual('100',restarted.state['strategy_capital']['equity']);self.assertEqual(1,len(w.calls))
            restarted.begin(intent,100,w.quote());self.assertEqual(1,len(w.calls))
