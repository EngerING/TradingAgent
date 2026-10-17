"""Paper-only observation. No permission, authorization, what-if or order writes."""
from datetime import datetime, timezone
from pathlib import Path
from .broker import PaperOptions
from .ibkr_session import AccountBinding, SessionConfiguration
from .paper_lab import unseal
from .equity_research_data import stock_wire, UNIVERSE
from .equity_evidence_extension import save, fact, SOURCES
from .tws import finite

TAGS = ('AccountType','SettledCash','AvailableFunds','BuyingPower','DayTradesRemaining',
    'DayTradesRemainingT+1','DayTradesRemainingT+2','DayTradesRemainingT+3','DayTradesRemainingT+4',
    'InitMarginReq','MaintMarginReq','RegTEquity','RegTMargin','SMA','ExcessLiquidity',
    'LookAheadAvailableFunds','LookAheadInitMarginReq','LookAheadMaintMarginReq','Cushion',
    'TotalCashValue','CashBalance','TotalCashBalance','NetLiquidation','TradingType-S',
    'AccountReady','Leverage-S')
TEXT = {'AccountType','TradingType-S','AccountReady'}
SUMMARY_TAGS=tuple(t for t in TAGS if t not in TEXT-{'AccountType'} and
    t not in ('CashBalance','TotalCashBalance','Leverage-S') and not t.startswith('DayTradesRemainingT+'))


def capabilities_wire(options, sdk_types=None):
    base = stock_wire(options, sdk_types)

    class Capabilities(type(base)):
        def values(self, mode):
            if mode not in ('summary','ledger','updates','multi'):
                raise ValueError('CAPABILITIES_QUERY_NOT_ALLOWED')
            with self.lock:
                req = self._begin('cap_'+mode)
                try:
                    if mode in ('summary','ledger'):
                        self._client.reqAccountSummary(req,'All',','.join(SUMMARY_TAGS) if mode=='summary' else '$LEDGER:USD')
                    elif mode=='updates':self._client.reqAccountUpdates(True,options.account)
                    else:self._client.reqAccountUpdatesMulti(req,options.account,'',False)
                    return self._wait()
                finally:
                    self.active = None
                    if mode in ('summary','ledger'):self._client.cancelAccountSummary(req)
                    elif mode=='updates':self._client.reqAccountUpdates(False,options.account)
                    else:self._client.cancelAccountUpdatesMulti(req)

        def accept_value(self, tag, value, currency):
            original = tag
            if tag.startswith('$LEDGER-'):tag=tag[len('$LEDGER-'):]
            if tag=='AccountOrGroup':
                self._check_account(value)  # identity-bearing metadata never enters archive
                return
            if tag not in TAGS:return
            try:
                if tag not in TEXT:value=str(finite(value))
                elif (tag=='AccountType' and value not in ('INDIVIDUAL','JOINT','IRA','TRUST','CORPORATE')) or (
                    tag=='TradingType-S' and value not in ('CASH','STKNOPT','PM')) or (
                    tag=='AccountReady' and value.lower() not in ('true','false')):
                    return  # unknown text/PII is not persisted
                self.data.append(dict(tag=tag,original_tag=original,value=value,currency=currency,
                    received_at=datetime.now(timezone.utc).isoformat()))
            except (ValueError,ArithmeticError):self._invalid('INVALID_CAPABILITY_VALUE')

        def accountSummary(self, reqId, account, tag, value, currency):
            if self.active in ('cap_summary','cap_ledger'):
                if reqId==self.request_id and self._check_account(account):self.accept_value(tag,value,currency)
            else:super().accountSummary(reqId,account,tag,value,currency)

        def accountSummaryEnd(self, reqId):
            if self.active in ('cap_summary','cap_ledger'):
                if reqId==self.request_id:self.done.set()
            else:super().accountSummaryEnd(reqId)

        def updateAccountValue(self, key, value, currency, account):
            if self.active=='cap_updates' and self._check_account(account):self.accept_value(key,value,currency)
            else:super().updateAccountValue(key,value,currency,account)

        def accountDownloadEnd(self, account):
            if self.active=='cap_updates' and self._check_account(account):self.done.set()
            else:super().accountDownloadEnd(account)

        def accountUpdateMulti(self, reqId, account, modelCode, key, value, currency):
            if self.active=='cap_multi' and reqId==self.request_id and self._check_account(account):
                if modelCode:self._invalid('ACCOUNT_MODEL_UNCERTAIN')
                else:self.accept_value(key,value,currency)

        def accountUpdateMultiEnd(self, reqId):
            if self.active=='cap_multi' and reqId==self.request_id:self.done.set()

        def error(self, reqId, *args):
            super().error(reqId,*args)
            if self.events:self.events[-1].update(request_id=reqId,request_kind=self.active)
    return Capabilities()


def collect_capabilities(root):
    root=Path(root);folder=root/'artifacts/research/equity-operational'
    folder.mkdir(parents=True,exist_ok=True)
    observation=dict(environment='PAPER_TRADING',identity_verified=False,queries={},symbols={},errors=[],
        orders_sent=0,execution_authorized=False,live_enabled=False,started_at=datetime.now(timezone.utc).isoformat())
    wire=None
    try:
        binding=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'))
        endpoint=SessionConfiguration.load(root)
        wire=capabilities_wire(PaperOptions(binding.account,host=endpoint.host,port=endpoint.port,
            verified_tws_port=endpoint.port,paper_mode_attested=True,configured_endpoint=True,client_id=91,timeout=20))
        binding.select(wire.connect())
        observation.update(identity_verified=True,account=binding.masked_account,server_version=wire.server_version)
        for mode in ('summary','ledger','updates','multi'):
            receipt=dict(started_at=datetime.now(timezone.utc).isoformat(),complete=False)
            observation['queries'][mode]=receipt
            try:
                receipt.update(rows=wire.values(mode),complete=True,request_id=wire.request_id,
                    callback='accountSummaryEnd' if mode in ('summary','ledger') else
                        'accountDownloadEnd' if mode=='updates' else 'accountUpdateMultiEnd')
            except Exception as exc:
                receipt['error']=type(exc).__name__;receipt['request_id']=wire.request_id
            receipt['completed_at']=datetime.now(timezone.utc).isoformat()
            if not wire.connected:break
        for symbol in UNIVERSE:
            if not wire.connected:break
            item={};observation['symbols'][symbol]=item
            try:item.update(contract=wire.contract_details(symbol),quote=wire.quote(symbol))
            except Exception as exc:item['error']=type(exc).__name__
        observation['connected_before_disconnect']=wire.connected
    except Exception as exc:observation['errors'].append(dict(request='CONNECTION',error=type(exc).__name__))
    finally:
        if wire:
            observation['ibkr_events']=wire.events[:];wire.disconnect()
            observation['disconnected']=not wire.connected
        observation['completed_at']=datetime.now(timezone.utc).isoformat()
        sha=save(folder/'capabilities-readonly.json',observation)
        (folder/'capabilities-readonly.sha256').write_text(sha,encoding='utf-8')
    return observation


def observed(observation, tag, currency=None):
    """No incomplete callback, BASE-to-USD inference or AvailableFunds substitution."""
    if observation.get('identity_verified') is not True or observation.get('environment')!='PAPER_TRADING':return None
    matches=[(x,q) for q in observation.get('queries',{}).values() if q.get('complete') is True
        for x in q.get('rows',[]) if x['tag']==tag and (currency is None or x['currency']==currency)]
    values={x['value'] for x,q in matches}
    if len(values)!=1:return None
    return dict(value=next(iter(values)),received_at=max(x['received_at'] for x,q in matches),
        query_callbacks=sorted({q['callback'] for x,q in matches}))


def account_facts(observation):
    results=[];stamp=observation.get('completed_at')
    for tag in TAGS:
        currency='USD' if tag not in TEXT and not tag.startswith('DayTrades') and tag not in ('Cushion','Leverage-S') else None
        item=observed(observation,tag,currency)
        f=fact(tag+('_USD' if currency else ''),'VERIFIED' if item else 'UNKNOWN',
            item['value'] if item else None,'IBKR_TWS','EXACT_PAPER_OBSERVATION; NOT_VIRTUAL_CAPITAL')
        f['observed_at']=item['received_at'] if item else stamp;f['callbacks']=item['query_callbacks'] if item else []
        results.append(f)
    for name in ('stock_etf_permissions','fractional_permissions','effective_fee_plan','effective_per_order_fees',
        'account_entity','effective_intraday_restrictions','contract_specific_margin','effective_bracket_acceptance'):
        f=fact(name,'UNKNOWN',None,'IBKR_TWS_READ_ONLY','NOT_EXPOSED_BY_QUERIES; CONTRACT_IS_NOT_PERMISSION')
        f['observed_at']=stamp;results.append(f)
    return results
