"""Durable local outbox -> isolated PostgreSQL -> offline research evidence.

Database failure blocks BUY admission. Owned protection/reduction and durable
local reconciliation do not depend on database or OpenAI availability.
"""
import json
from pathlib import Path
import subprocess
from . import stock_paper_forward as stock

def probe(root,trial,binding,scope):
    """Read the isolated PG table; never creates an intent/reservation/event."""
    sink=PostgresMirror(root,None)
    sink._invoke(dict(trial=trial,binding=binding,scope=scope,events=[]))
    return 'VERIFIED_READABLE_NOT_AUTHORIZED'


class PostgresMirror:
    def __init__(self,root,journal,invoke=None):
        self.root=Path(root);self.journal=journal;self.revision=0;self.hash='';self.pending=True
        self.invoke=invoke or self._invoke
    def _invoke(self,value):
        try:
            r=subprocess.run(['dotnet',str(self.root/'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'),
                '--ford-diagnostic-evidence'],input=stock.encoded(value).decode(),capture_output=True,text=True,timeout=8,cwd=self.root)
            if r.returncode:raise ValueError()
            return json.loads(r.stdout)
        except (ValueError,OSError,subprocess.TimeoutExpired):
            raise PermissionError('FORD_DIAGNOSTIC_POSTGRES_UNAVAILABLE_OR_CONFLICT') from None
    def sync(self,required=False):
        try:
            local_revision,state=self.journal.load()
            while self.revision<local_revision:
                rows=self.journal.db.execute('SELECT * FROM events WHERE revision>? ORDER BY revision LIMIT 50',(self.revision,)).fetchall()
                events=[dict(revision=r,at=t,kind=k,payload=p,previous=prev,hash=h,
                    material=stock.encoded([r,t,k,json.loads(p),prev]).decode()) for r,t,k,p,prev,h in rows]
                result=self.invoke(dict(trial=state['trial_id'],binding=state['binding_id'],scope=state['scope'],events=events))
                end=rows[-1]
                # A replay may find a longer PG chain: never silently adopt it.
                if result.get('revision',-1)<end[0] or (result['revision']==end[0] and result.get('hash')!=end[5]):
                    raise PermissionError('FORD_DIAGNOSTIC_POSTGRES_HEAD_MISMATCH')
                self.revision=end[0];self.hash=end[5]
            proof=self.invoke(dict(trial=state['trial_id'],binding=state['binding_id'],scope=state['scope'],events=[]))
            if proof.get('revision')!=local_revision or proof.get('hash')!=self.hash:
                raise PermissionError('FORD_DIAGNOSTIC_POSTGRES_HEAD_MISMATCH')
            self.pending=False;return True
        except Exception:
            self.pending=True
            if required:raise PermissionError('FORD_DIAGNOSTIC_POSTGRES_UNAVAILABLE_OR_CONFLICT') from None
            return False


def completed_receipt(root,journal,mirror):
    """Export only a definitive flat cycle, after the complete chain is mirrored."""
    revision,state=journal.load()
    if state['intent'] or stock.number(state['reservation']) or mirror.pending or mirror.revision!=revision:return None
    row=journal.db.execute("SELECT * FROM events WHERE kind='DIAGNOSTIC_CYCLE_SETTLED' ORDER BY revision DESC LIMIT 1").fetchone()
    if not row:return None
    r,t,kind,payload,previous,h=row;report=json.loads(payload)['details']
    fills=report['executions'];fees=report['fees']
    if not fills or set(f['exec_id'] for f in fills)!=set(fees) or any(f['currency']!='USD' for f in fees.values()):return None
    snapshots=[json.loads(p)['details'] for (p,) in journal.db.execute("SELECT payload FROM events WHERE kind IN ('DIAGNOSTIC_PRE_ENTRY_SNAPSHOT','BROKER_RECONCILIATION_EVIDENCE') ORDER BY revision")]
    expected=dict(entry=report['entry'],stop=report['stop'],target=report['target'],friction=report['estimated_friction'])
    exit_row=journal.db.execute("SELECT payload FROM events WHERE kind='DIAGNOSTIC_EXIT_EXPECTATION' AND revision<=? ORDER BY revision DESC LIMIT 1",(r,)).fetchone()
    expected['exit_limit']=json.loads(exit_row[0])['details']['limit'] if exit_row else None
    expected['fees']=json.loads(payload)['state']['diagnostic_estimated_fees']
    sides={}
    for side in ('BUY','SELL'):
        part=[f for f in fills if f['side']==side];q=sum(stock.number(f['quantity']) for f in part)
        sides[side]=dict(quantity=str(q),price=str(sum(stock.number(f['price'])*stock.number(f['quantity']) for f in part)/q),
            commissions=str(sum(stock.number(fees[f['exec_id']]['commission']) for f in part)))
    value=dict(schema_version=1,classification='EXECUTION_DIAGNOSTICS',environment='PAPER_TRADING',
        scope=state['scope'],trial_id=state['trial_id'],binding_id=state['binding_id'],strategy_version=None,
        strategy_success=False,profitability_evidence=False,execution_authorized=False,openai_requests=0,
        evidence_status='OBSERVED_SIMULATED_PAPER_EXECUTION_NOT_LIVE',at=t,
        source=dict(journal_path=str(journal.path.relative_to(root)).replace('\\','/'),revision=r,event_hash=h,
            reconciled_revision=revision,reconciled_hash=mirror.hash,postgres_mirrored=True),
        report=report,expected=expected,observed=sides,
        discrepancies=dict(buy_price_minus_expected=str(stock.number(sides['BUY']['price'])-stock.number(report['entry'])),
            sell_price_minus_expected=str(stock.number(sides['SELL']['price'])-stock.number(expected['exit_limit'])) if expected['exit_limit'] else None,
            commissions_minus_estimated=str(sum(stock.number(v['commission']) for v in fees.values())-stock.number(json.loads(payload)['state']['diagnostic_estimated_fees']))),
        snapshots=snapshots,quote_observations=[dict(at=s.get('at'),quote=s.get('quote')) for s in snapshots],
        limitations=['ONE_INFRASTRUCTURE_CYCLE_NOT_A_STRATEGY_SAMPLE',
            'PAPER_FILL_AND_PROTECTION_SIMULATION_NOT_REAL_EXECUTION','NO_SLIPPAGE_CAUSAL_ESTIMATE_WITHOUT_FILL_TIME_QUOTE',
            'EFFECTIVE_FEES_OBSERVED_FOR_THIS_CYCLE_ONLY','NO_AUTOMATIC_RESEARCH_OR_PROMOTION'])
    from .ai_strategy_researcher.execution_memory import save
    return save(root,value)
