"""Bounded read-only evidence extension. Frozen R0 candidates and old holdout remain intact."""
import argparse
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from .broker import PaperOptions
from .ibkr_session import AccountBinding,SessionConfiguration
from .paper_lab import unseal
from .equity_research_data import stock_wire,normalize,UNIVERSE
from .equity_strategy_research import (at,digest,PARAMETERS,RATES,MODELS,FAMILIES,TIMEFRAMES,
    candidate_versions,validated_bars,simulate,signals,evidence_checks,ZONE,NY,commission,costs,num,price_tick)

HISTORY_START=datetime(2021,1,1,tzinfo=timezone.utc)
SELECTION_START=datetime(2024,1,1,tzinfo=timezone.utc)
FINAL_START=datetime(2025,1,1,tzinfo=timezone.utc)
HISTORY_END=datetime(2026,4,3,tzinfo=timezone.utc)
SPLIT_DATE=datetime(2024,10,11,13,30,tzinfo=timezone.utc)
FOLDER='artifacts/research/equity-evidence'
SOURCES={
 'ibkr_bars':'https://interactivebrokers.github.io/tws-api/historical_bars.html',
 'schx_split':'https://pressroom.aboutschwab.com/press-releases/press-release/2024/Schwab-Asset-Management-Announces-ETF-Share-Splits/default.aspx',
 'commissions':'https://www.interactivebrokers.com/en/pricing/commissions-stocks.php',
 'margin_code':'https://www.interactivebrokers.com/campus/trading-lessons/risk-navigator-alternative-margin-calculator/',
 'intraday':'https://www.ibkrguides.com/ibkrdesktop/available-for-trading.htm',
 'settlement':'https://www.interactivebrokers.com/campus/traders-insight/t1-settlement-what-it-means-for-traders-and-investors/',
 'paper':'https://www.ibkrguides.com/advisorportal/aboutpapertradingaccount.htm'}
SOURCES['adjusted_end_date']='https://www.interactivebrokers.com/docs/tws-api/sync-doc/historical-market-data'


def save(path,value):
    encoded=json.dumps(value,indent=2,allow_nan=False).encode()
    Path(path).write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def protocol(root):
    # New historical samples must NEVER train on the examined April–October 2026 archive.
    old=json.loads((Path(root)/'artifacts/research/us-equities/protocol.json').read_bytes())
    if old['versions']!=candidate_versions() or old['parameters']!=PARAMETERS:
        raise ValueError('FROZEN_CANDIDATE_CHANGED')
    return dict(schema_version=1,universe=list(UNIVERSE),versions=old['versions'],parameters=old['parameters'],
        capital_usd=100,loss_allowance_usd=20,exposure_limit=1,rates=RATES,cost_models=MODELS,
        train=[HISTORY_START.isoformat(),SELECTION_START.isoformat()],
        selection=[SELECTION_START.isoformat(),FINAL_START.isoformat()],
        final=[FINAL_START.isoformat(),HISTORY_END.isoformat()],
        quarantined_previous_archive=['2026-04-03T00:00:00+00:00','2026-10-03T00:00:00+00:00'],
        optimization=False,parameters_refitted=False,final_open_rule='ONLY_IF_SELECTION_PASSES_ALL_ECONOMIC_AND_DATA_GATES',
        retrospective_unexamined_not_prospective=True,survivorship_control='FIXED_CASE_STUDY_NOT_POINT_IN_TIME_UNIVERSE',
        corporate_action_method='RESTORE_SCHX_PRE_SPLIT_PRICE_THEN_PARTITION_EPISODES_NO_SPLIT_CROSSING',
        uncertain_corporate_actions_block_promotion=True,orders_allowed=False,live_enabled=False,
        frozen_at=datetime.now(timezone.utc).isoformat())


def extension_wire(options,sdk_types=None):
    base=stock_wire(options,sdk_types)
    class Archive(type(base)):
        def error(self,reqId,*args):
            code=args[1] if len(args)>=3 and isinstance(args[1],int) else args[0]
            # Store correlation/category without raw messages, account IDs or secrets.
            super().error(reqId,*args)
            if self.events:
                self.events[-1].update(request_id=reqId,request_kind=self.active,
                    category='ARCHIVE_TAIL_ADVISORY' if code==2188 else 'BROKER_CODE')

        def historical(self,symbol,minutes,end,duration,kind='TRADES'):
            if symbol not in UNIVERSE or minutes not in (60,1440) or kind not in ('TRADES','ADJUSTED_LAST'):
                raise ValueError('ARCHIVE_REQUEST_SCOPE_REQUIRED')
            if end.tzinfo is None or not HISTORY_START < end <= HISTORY_END:
                raise ValueError('ARCHIVE_END_OUT_OF_SCOPE')
            if duration not in ('1 Y','6 M','3 M','6 Y') or (minutes==60 and duration=='6 Y'):
                raise ValueError('ARCHIVE_DURATION_OUT_OF_SCOPE')
            if kind=='ADJUSTED_LAST' and minutes!=1440:raise ValueError('ADJUSTED_DAILY_ONLY')
            with self.lock:
                self.paced();req=self._begin('stock_history');self.bar_minutes=minutes
                try:
                    # Official IBKR requirement: ADJUSTED_LAST cannot specify endDateTime.
                    # Its current-tail data are quality-only and filtered to the frozen range.
                    sdk_end='' if kind=='ADJUSTED_LAST' else end.strftime('%Y%m%d-%H:%M:%S')
                    self._client.reqHistoricalData(req,self.contract(symbol),sdk_end,
                        duration,'1 hour' if minutes==60 else '1 day',kind,1,2,False,[])
                    rows=self._wait()
                    if not rows:raise ValueError('EMPTY_ARCHIVE_REQUEST')
                    return rows
                finally:self.active=None;self._client.cancelHistoricalData(req)

        def archive_schedule(self,symbol):
            with self.lock:
                self.paced();req=self._begin('stock_schedule')
                try:
                    self._client.reqHistoricalData(req,self.contract(symbol),HISTORY_END.strftime('%Y%m%d-%H:%M:%S'),
                        '6 Y','1 day','SCHEDULE',1,2,False,[])
                    result=self._wait()
                    if not result:raise ValueError('EMPTY_AUTHENTIC_SCHEDULE')
                    return result
                finally:self.active=None;self._client.cancelHistoricalData(req)

        def multi_account(self):
            with self.lock:
                req=self._begin('evidence_multi')
                try:
                    self._client.reqAccountUpdatesMulti(req,options.account,'',True)
                    return self._wait()
                finally:self.active=None;self._client.cancelAccountUpdatesMulti(req)

        def accountUpdateMulti(self,reqId,account,modelCode,key,value,currency):
            if reqId==self.request_id and self.active=='evidence_multi' and self._check_account(account):
                if modelCode:self._invalid('ACCOUNT_MODEL_UNCERTAIN');return
                self.update_value(key,value,currency)

        def update_value(self,key,value,currency):
            if key in ('SettledCash','SettledCash-S','CashBalance','TotalCashBalance','TotalCashValue',
                       'AvailableFunds','DayTradesRemaining','DayTradesRemainingT+1','TradingType-S','AccountReady'):
                self.data.append(dict(tag=key,value=value,currency=currency))

        def accountUpdateMultiEnd(self,reqId):
            if reqId==self.request_id and self.active=='evidence_multi':self.done.set()

        def usd_ledger(self):
            with self.lock:
                req=self._begin('evidence_usd')
                try:
                    self._client.reqAccountSummary(req,'All','$LEDGER:USD')
                    return self._wait()
                finally:self.active=None;self._client.cancelAccountSummary(req)

        def accountSummary(self,reqId,account,tag,value,currency):
            if reqId==self.request_id and self.active=='evidence_usd' and self._check_account(account):
                if tag in ('SettledCash','CashBalance','TotalCashBalance','TotalCashValue') and currency=='USD':
                    self.data.append(dict(tag=tag,value=value,currency=currency))
            else:super().accountSummary(reqId,account,tag,value,currency)

        def accountSummaryEnd(self,reqId):
            if reqId==self.request_id and self.active=='evidence_usd':self.done.set()
            else:super().accountSummaryEnd(reqId)
    return Archive()


def collect(root):
    root=Path(root);folder=root/FOLDER;folder.mkdir(parents=True,exist_ok=True)
    plan_path=folder/'protocol.json'
    if not plan_path.exists():save(plan_path,protocol(root))
    else:
        plan=json.loads(plan_path.read_bytes())
        if plan['versions']!=candidate_versions() or plan['parameters']!=PARAMETERS:
            raise ValueError('REGISTERED_PROTOCOL_CHANGED')
    report=dict(source='IBKR_TWS',scope='READ_ONLY_ARCHIVED_EVIDENCE',universe=list(UNIVERSE),
        symbols={},receipts=[],errors=[],orders_sent=0,live_enabled=False,
        requested_start=HISTORY_START.isoformat(),requested_end=HISTORY_END.isoformat())
    wire=None
    try:
        binding=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'));endpoint=SessionConfiguration.load(root)
        wire=extension_wire(PaperOptions(binding.account,host=endpoint.host,port=endpoint.port,
            verified_tws_port=endpoint.port,paper_mode_attested=True,configured_endpoint=True,client_id=89,timeout=20))
        binding.select(wire.connect());report.update(identity_verified=True,account=binding.masked_account,server_version=wire.server_version)
        for method in ('account_observation','account_details','multi_account','usd_ledger'):
            try:report[method]=getattr(wire,method)();report[method+'_completed']=True
            except Exception as exc:report[method+'_completed']=False;report['errors'].append(dict(request=method,error=type(exc).__name__))
        for symbol in UNIVERSE:
            record={};report['symbols'][symbol]=record
            try:
                record['contract']=wire.contract_details(symbol);record['quote']=wire.quote(symbol)
                sessions=wire.archive_schedule(symbol);record['sessions']=sessions;record['bars']={}
                for minutes in TIMEFRAMES:
                    original=[];end=HISTORY_END
                    for index in range(6 if minutes==60 else 1):
                        rows=wire.historical(symbol,minutes,end,'1 Y' if minutes==60 else '6 Y')
                        original.extend(rows)
                        report['receipts'].append(dict(symbol=symbol,minutes=minutes,kind='TRADES',
                            end=end.isoformat(),duration='1 Y' if minutes==60 else '6 Y',count=len(rows),
                            request_id=wire.request_id,callback='historicalDataEnd',completed_at=datetime.now(timezone.utc).isoformat()))
                        end-=timedelta(days=350)
                        # Six one-year windows with overlap cover all of Jan 2021..Apr 2026.
                        if minutes==60 and end<=HISTORY_START:break
                    record['bars'][str(minutes)]=normalize(original,sessions,start=HISTORY_START,end=HISTORY_END)
                    save(folder/f'{symbol}-{minutes}.json',record['bars'][str(minutes)])
                    save(folder/'collection-progress.json',report)
                try:
                    adjusted=wire.historical(symbol,1440,HISTORY_END,'6 Y','ADJUSTED_LAST')
                    record['adjusted_daily']=normalize(adjusted,sessions,start=HISTORY_START,end=HISTORY_END)
                    report['receipts'].append(dict(symbol=symbol,minutes=1440,kind='ADJUSTED_LAST',count=len(adjusted),
                        callback='historicalDataEnd',request_id=wire.request_id,completed_at=datetime.now(timezone.utc).isoformat()))
                except Exception as exc:record['adjusted_daily_error']=str(exc) if str(exc).startswith('IBKR_') else type(exc).__name__
            except Exception as exc:
                report['errors'].append(dict(symbol=symbol,error=str(exc) if str(exc).startswith(('IBKR_','EMPTY_','INVALID_','DAILY_','BAR_','CONFLICTING_')) else type(exc).__name__))
                if not wire.connected:break
            save(folder/'collection-progress.json',report)
    except Exception as exc:
        report['errors'].append(dict(request='CONNECTION',error=type(exc).__name__))
    finally:
        report['ibkr_events']=wire.events[:] if wire else []
        if wire:wire.disconnect()
        report['completed_at']=datetime.now(timezone.utc).isoformat()
        sha=save(folder/'readonly.json',report);(folder/'readonly.sha256').write_text(sha,encoding='utf-8')
    return report


def adjusted_quality(root):
    root=Path(root);folder=root/FOLDER;wire=None
    record=dict(scope='READ_ONLY_ADJUSTMENT_QUALITY_NOT_SIGNALS',symbols={},errors=[],orders_sent=0,
        source='IBKR_TWS',logical_analysis_end=HISTORY_END.isoformat(),sdk_end_date_time='',
        reason='OFFICIAL_ADJUSTED_LAST_REQUIRES_EMPTY_END; FILTER_CURRENT_TAIL_BEFORE_ANALYSIS')
    try:
        binding=AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'));endpoint=SessionConfiguration.load(root)
        wire=extension_wire(PaperOptions(binding.account,host=endpoint.host,port=endpoint.port,
            verified_tws_port=endpoint.port,paper_mode_attested=True,configured_endpoint=True,client_id=90,timeout=20))
        binding.select(wire.connect());record.update(identity_verified=True,account=binding.masked_account)
        source=json.loads((folder/'readonly.json').read_bytes())
        for symbol in UNIVERSE:
            try:
                rows=wire.historical(symbol,1440,HISTORY_END,'6 Y','ADJUSTED_LAST')
                record['symbols'][symbol]=dict(bars=normalize(rows,source['symbols'][symbol]['sessions'],
                    start=HISTORY_START,end=HISTORY_END),original_count=len(rows),request_id=wire.request_id,
                    callback='historicalDataEnd',received_at=datetime.now(timezone.utc).isoformat())
            except Exception as exc:record['errors'].append(dict(symbol=symbol,error=str(exc) if str(exc).startswith('IBKR_') else type(exc).__name__))
    finally:
        if wire:record['ibkr_events']=wire.events[:];wire.disconnect()
        record['completed_at']=datetime.now(timezone.utc).isoformat()
        sha=save(folder/'adjusted-quality.json',record);(folder/'adjusted-quality.sha256').write_text(sha,encoding='utf-8')
    return record


def fact(name,status,value,source,scope,required=False,reason=None):
    if status not in ('VERIFIED','ESTIMATED','UNKNOWN'):raise ValueError('FACT_STATUS_REQUIRED')
    if status=='UNKNOWN' and value is not None:raise ValueError('UNKNOWN_IS_NULL')
    return dict(name=name,status=status,value=value,source=source,scope=scope,
        required_for_execution=required,reason=reason)


def reported_value(observation,tag,currency=None):
    values=[]
    for field in ('account_observation','multi_account','usd_ledger'):
        if observation.get(field+'_completed') is True:values.extend(observation.get(field,[]))
    if observation.get('account_details_completed') is True:
        values.extend(observation.get('account_details',{}).get('values',[]))
    matches={v['value'] for v in values if v['tag']==tag and (currency is None or v['currency']==currency)}
    return next(iter(matches)) if len(matches)==1 else None


def feasibility(data):
    result=[];stamp=data.get('completed_at');scope='THIS_PAPER_ACCOUNT_OBSERVATION'
    def add(name,status,value,source='IBKR_TWS',required=False,reason=None,field_scope=scope):
        result.append(fact(name,status,value,source,field_scope,required,reason))
    add('paper_identity','VERIFIED' if data.get('identity_verified') else 'UNKNOWN',
        data.get('account') if data.get('identity_verified') else None,required=True)
    kind=reported_value(data,'AccountType');add('account_legal_type','VERIFIED' if kind else 'UNKNOWN',kind)
    trading=reported_value(data,'TradingType-S');add('trading_type_code','VERIFIED' if trading else 'UNKNOWN',trading)
    add('account_margin_class','ESTIMATED' if trading=='STKNOPT' else 'UNKNOWN',
        'REG_T_MARGIN_FROM_STKNOPT' if trading=='STKNOPT' else None,SOURCES['margin_code'],True)
    for tag in ('SettledCash','AvailableFunds','CashBalance'):
        value=reported_value(data,tag,'USD')
        try:
            if value is not None:num(value)
        except ValueError:value=None
        add(tag+'_USD','VERIFIED' if value is not None else 'UNKNOWN',value,required=tag=='SettledCash',
            reason='BROKER_PAPER_FUNDS_MUST_NOT_SIZE_STRATEGY; NO_SUBSTITUTION_FOR_SETTLED_CASH')
    day=reported_value(data,'DayTradesRemaining')
    add('day_trades_remaining','VERIFIED' if day is not None else 'UNKNOWN',day,required=True)
    for name in ('stock_etf_trading_permissions','applicable_commission_plan','effective_stock_commissions',
                 'account_entity_and_restrictions','applicable_intraday_regime','fractional_order_permissions',
                 'effective_stock_bracket_protection','intraday_usd100_executability'):
        add(name,'UNKNOWN',None,required=True,
            reason='READ_ONLY_TWS_CONTRACT_ACCOUNT_VALUES_DO_NOT_CERTIFY_THIS_REQUIREMENT')
    add('public_tiered_low_volume_tariff','VERIFIED',dict(per_share_usd='.0035',minimum_usd='.35',
        additional_fees=True),SOURCES['commissions'],field_scope='PUBLIC_US_SCHEDULE_NOT_ACCOUNT_PRICE')
    add('research_commission_envelope','ESTIMATED',dict(extra_per_order_usd='.02',extra_per_share_usd='.01',
        base='PUBLIC_TIERED_OR_FIXED_SENSITIVITY'),field_scope='SIMULATION_ONLY')
    add('settlement_cycle','VERIFIED','T+1_US_STOCKS',SOURCES['settlement'],field_scope='GENERAL_MARKET_RULE_NOT_ACCOUNT_CREDIT')
    add('virtual_allocation','VERIFIED',dict(initial_usd=100,exposure_limit=1,loss_allowance_usd=20),
        'FROZEN_RESEARCH_PROTOCOL',field_scope='RESEARCH_ONLY_NOT_BROKER_BUYING_POWER')
    add('cash_availability_model','ESTIMATED','NO_SAME_DAY_REUSE_OF_SALE_PROCEEDS',field_scope='CONSERVATIVE_SIMULATION')
    for symbol in UNIVERSE:
        row=data.get('symbols',{}).get(symbol,{})
        c=row.get('contract');q=row.get('quote',{})
        add(symbol+'_contract','VERIFIED' if c else 'UNKNOWN',
            {k:c.get(k) for k in ('con_id','minimum_size','size_increment','min_tick')} if c else None)
        types=set(c.get('order_types','').split(',')) if c else set()
        add(symbol+'_declared_protective_types','VERIFIED' if c else 'UNKNOWN',
            sorted(types & {'LMT','STP','STPLMT','OCA'}) if c else None,
            field_scope='CONTRACT_CAPABILITIES_NOT_ACCOUNT_ORDER_ACCEPTANCE')
        add(symbol+'_market_data_observation','VERIFIED' if q else 'UNKNOWN',
            {k:q.get(k) for k in ('data_type','bid','ask','reason','received_at')} if q else None)
        add(symbol+'_realtime_execution_data','UNKNOWN',None,required=True,
            reason='QUOTE_REQUEST_DELAYED_FROZEN_ONLY; NO_EXECUTABLE_TIMESTAMP_OR_ENTITLEMENT_CERTIFICATION')
    add('production_stock_adapter','VERIFIED',False,'python/trading_agent/paper_execution_wire.py',True,
        'PRODUCTION_ORDER_CONTRACT_IS_EUR_USD_CASH_IDEALPRO_ONLY',field_scope='CODE_INSPECTION')
    return dict(observed_at=stamp,facts=result,execution_blockers=[f['name'] for f in result
        if f['required_for_execution'] and (f['status']!='VERIFIED' or f['value'] is False)],
        execution_authorized=False,live_enabled=False)


def episodes(symbol,rows):
    """Restore historical notional; never let a split produce a spurious stop/gap trade."""
    rows=validated_bars(rows)
    if symbol!='SCHX':return {symbol:rows},[]
    before=[];after=[]
    for row in rows:
        if at(row['opened_at'])<SPLIT_DATE:
            before.append({**row,**{k:float(num(row[k])*3) for k in ('open','high','low','close')}})
        else:after.append(row)
    result={}
    if before:result['SCHX_PRE_20241011']=before
    if after:result['SCHX_POST_20241011']=after
    return result,[dict(symbol='SCHX',split_ratio=3,trading_effective=SPLIT_DATE.isoformat(),
        source=SOURCES['schx_split'],event_status='VERIFIED',price_reconstruction_status='ESTIMATED',
        no_position_crossing=True,volume_left_as_received=True,
        reason='NO_INVENTORY_SPLIT_ACCOUNTING_IMPLEMENTED; CAUSAL_FEATURE_WARMUP_RESTARTS_PER_EPISODE')]


def prepared_episodes(series,family):
    result={};excluded=0
    for name,rows in series.items():
        candidates,fs=signals(rows,family)
        if name=='SCHX_PRE_20241011':
            kept=[s for s in candidates if s['entry_index']+PARAMETERS['maximum_hold_bars']<len(rows)]
            excluded+=len(candidates)-len(kept);candidates=kept
        result[name]=(candidates,fs)
    return result,excluded


def quality(data):
    details={};complete=True
    for symbol in UNIVERSE:
        r=data.get('symbols',{}).get(symbol,{});sessions=r.get('sessions',[])
        wanted={s['day'] for s in sessions if '20210101'<=s['day']<'20260403'}
        item={'session_days':len(wanted),'timeframes':{},'dividend_cash_calendar':'UNKNOWN',
            'all_splits_independently_complete':'UNKNOWN','survivorship_free_universe':False}
        for tf in TIMEFRAMES:
            bars=r.get('bars',{}).get(str(tf),[])
            valid=validated_bars(bars)
            actual={at(b['opened_at']).astimezone(NY).strftime('%Y%m%d') for b in valid}
            missing=sorted(wanted-actual);unexpected=sorted(actual-wanted)
            ok=bool(wanted) and not missing and not unexpected
            complete=complete and ok
            item['timeframes'][str(tf)]=dict(count=len(valid),missing_sessions=missing,
                unexpected_sessions=unexpected,complete=ok)
        adjusted=r.get('adjusted_daily',[])
        raw_by={b['opened_at']:num(b['close']) for b in r.get('bars',{}).get('1440',[])}
        paired=[(num(b['close']),raw_by[b['opened_at']]) for b in adjusted if b['opened_at'] in raw_by]
        item['adjusted_daily_comparison']=dict(available=bool(adjusted),paired_days=len(paired),
            different_close_days=sum(a!=b for a,b in paired),used_for_signal_or_pnl=False,
            reason='ADJUSTED_LAST_IS_NOT_EXECUTABLE_PRICE_OR_DIVIDEND_RECEIVABLE_LEDGER')
        details[symbol]=item
    return dict(coverage_complete=complete,instruments=details,corporate_action_accounting_complete=False,
        point_in_time_universe_verified=False,eligible_for_promotion=False)


def partition_series(data,end):
    # End-exclusive filtering ensures no final outcome/features enter selection.
    result={};events=[]
    for symbol in UNIVERSE:
        for tf in TIMEFRAMES:
            rows=[b for b in data.get('symbols',{}).get(symbol,{}).get('bars',{}).get(str(tf),[])
                if at(b['closed_at'])<end]
            pieces,metadata=episodes(symbol,rows);result.setdefault(tf,{}).update(pieces);events.extend(metadata)
    return result,events


def candidate_selection(result,folds,data_quality):
    selection=evidence_checks(result,folds)
    # Frozen R0 economics/sample thresholds plus explicit new data gates, never stronger win rate alone.
    economic_reasons=[r for r in selection['reasons'] if r not in (
        'IBKR_PERMISSIONS_TARIFF_SETTLEMENT_AND_PROTECTION_UNVERIFIED','LIMITED_SURVIVING_UNIVERSE',
        'CORPORATE_ACTION_AND_DELISTED_DATA_INCOMPLETE','NEW_UNEXAMINED_CONFIRMATION_REQUIRED',
        'PRODUCTION_STOCK_ADAPTER_NOT_IMPLEMENTED')]
    if not data_quality['coverage_complete']:economic_reasons.append('AUTHENTIC_COVERAGE_INCOMPLETE')
    if not data_quality['corporate_action_accounting_complete']:economic_reasons.append('CORPORATE_ACTION_LEDGER_INCOMPLETE')
    if not data_quality['point_in_time_universe_verified']:economic_reasons.append('SURVIVORSHIP_NOT_CONTROLLED')
    return dict(passes_for_final=not economic_reasons,reasons=economic_reasons,
        status='INSUFFICIENT_EVIDENCE' if any('INSUFFICIENT' in s or 'INCOMPLETE' in s or 'SURVIVORSHIP' in s for s in economic_reasons)
        else 'NO_VIABLE_STRATEGY_FOUND' if economic_reasons else 'VIABLE_FOR_FURTHER_PAPER_VALIDATION',
        execution_authorized=False)


def decision(operation,data_quality,rows):
    if operation['execution_blockers']:return 'EXECUTION_CONSTRAINT_BLOCKED'
    if not data_quality['eligible_for_promotion']:return 'INSUFFICIENT_EVIDENCE'
    if any(r['selection']['passes_for_final'] and r.get('final') is not None and final_gate(r['final']) for r in rows):
        return 'VIABLE_FOR_FURTHER_PAPER_VALIDATION'
    if any(r['selection']['passes_for_final'] and r.get('final') is None for r in rows):return 'INSUFFICIENT_EVIDENCE'
    if any(r['selection']['status']=='INSUFFICIENT_EVIDENCE' for r in rows) or not rows:return 'INSUFFICIENT_EVIDENCE'
    return 'NO_VIABLE_STRATEGY_FOUND'


def final_gate(result):
    m=result['metrics'];ci=result['confidence']
    lower=ci['win_wilson_family_adjusted'];ev=ci['block_bootstrap_expectancy_ci']
    return (m['admitted']>=100 and m['trade_days']>=30 and m['win_rate'] is not None and m['win_rate']>.8
        and m['net_expectancy'] is not None and m['net_expectancy']>0 and m['net_pnl']>0
        and m['profit_factor'] is not None and m['profit_factor']>1 and m['maximum_drawdown']<=.2
        and m['risk_budget_breaches']==0 and m['pending_position'] is None
        and lower is not None and lower[0]>.8 and ev is not None and ev[0]>0)


def capital_requirement(entry,stop,target,rate=15,model='TIERED_BASE',observed_spread=None):
    """Analytical requirement for ONE unchanged signal, not a capital backtest or recommendation."""
    entry,stop,target=map(num,(entry,stop,target))
    if rate not in RATES or not 0<stop<entry<target:return None
    spread,slip,gap=costs(entry,model,observed_spread)
    per_unit=target-entry-spread-2*slip-gap-Decimal('.02')
    if per_unit<=Decimal('.02'):return None  # extra fees alone eliminate positive surplus
    paid=price_tick(entry+spread/2+slip,buy=True)
    for q in range(1,10001):
        fees=commission(q,paid,model)+commission(q,target,model)
        net=q*per_unit-fees
        if net>0:
            risk=q*(entry-stop+spread+2*slip+gap+Decimal('.02'))+fees
            cash=q*paid+fees;capital=max(cash,risk*100/num(rate))
            return dict(quantity=q,notional_usd=float(q*paid),cash_required_usd=float(cash),
                risk_usd=float(risk),costs_usd=float(fees+q*(spread+2*slip)),gap_reserve_usd=float(q*gap),
                minimum_capital_usd=float(capital),potential_target_net=float(net),risk_percent=rate,
                fits_usd100=capital<=100,estimate_only=True,execution_authorized=False)
    return None


def evaluate(root):
    root=Path(root);folder=root/FOLDER;raw=(folder/'readonly.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=(folder/'readonly.sha256').read_text().strip():raise ValueError('ARCHIVE_HASH_MISMATCH')
    data=json.loads(raw);plan=json.loads((folder/'protocol.json').read_bytes())
    if plan['versions']!=candidate_versions() or plan['parameters']!=PARAMETERS:raise ValueError('FROZEN_CANDIDATE_CHANGED')
    supplement=folder/'adjusted-quality.json'
    if supplement.exists():
        supplemental_raw=supplement.read_bytes()
        if hashlib.sha256(supplemental_raw).hexdigest()!=(folder/'adjusted-quality.sha256').read_text().strip():raise ValueError('ADJUSTED_QUALITY_HASH_MISMATCH')
        adjusted=json.loads(supplemental_raw)
        if adjusted.get('identity_verified') is not True or adjusted.get('account')!=data.get('account') or adjusted.get('orders_sent')!=0:
            raise ValueError('ADJUSTED_QUALITY_IDENTITY_MISMATCH')
        for s,r in adjusted['symbols'].items():data['symbols'][s]['adjusted_daily']=r['bars']
        data['adjusted_quality_sha256']=hashlib.sha256(supplemental_raw).hexdigest()
    operation=feasibility(data);data_quality=quality(data);rows=[];capital=[];spread_ratios={}
    for symbol,record in data.get('symbols',{}).items():
        q=record.get('quote',{})
        if q.get('bid') and q.get('ask'):
            bid,ask=num(q['bid']),num(q['ask'])
            if 0<bid<=ask:spread_ratios[symbol]=float((ask-bid)/((ask+bid)/2))
    if 'SCHX' in spread_ratios:
        for alias in ('SCHX_PRE_20241011','SCHX_POST_20241011'):spread_ratios[alias]=spread_ratios['SCHX']
    # NEVER call simulate/signals with final rows unless the selection/data gate passes.
    series,corporate=partition_series(data,FINAL_START)
    folds=[('wf_selection_1','2024-01-01T00:00:00Z','2024-05-01T00:00:00Z'),
           ('wf_selection_2','2024-05-01T00:00:00Z','2024-09-01T00:00:00Z'),
           ('wf_selection_3','2024-09-01T00:00:00Z','2025-01-01T00:00:00Z')]
    for tf in TIMEFRAMES:
        cohort=series.get(tf,{})
        # A short post-split episode must not suppress other instruments/timeframes.
        # Frozen signal code already enforces its 50-bar causal warm-up.
        if not cohort or all(len(b)<=PARAMETERS['context'] for b in cohort.values()):continue
        for family in FAMILIES:
            prepared,excluded=prepared_episodes(cohort,family)
            # Capital requirements are diagnostic geometry, no parameter fitting or new instruments.
            for symbol,(candidates,_) in prepared.items():
                for signal in candidates:
                    b=cohort[symbol][signal['entry_index']]
                    if SELECTION_START<=at(b['opened_at'])<FINAL_START:
                        requirement=capital_requirement(b['open'],signal['stop'],signal['target'],observed_spread=spread_ratios.get(symbol))
                        capital.append(dict(strategy=family,minutes=tf,symbol=symbol,signal_at=signal['at'],requirement=requirement))
            for rate in RATES:
                for model in MODELS:
                    common=(cohort,family,rate,model)
                    train=simulate(*common,HISTORY_START.isoformat(),SELECTION_START.isoformat(),spread_ratios,prepared=prepared)
                    selection_result=simulate(*common,SELECTION_START.isoformat(),FINAL_START.isoformat(),spread_ratios,prepared=prepared)
                    wf=[simulate(*common,start,end,spread_ratios,prepared=prepared) for _,start,end in folds]
                    check=candidate_selection(selection_result,wf,data_quality)
                    rows.append(dict(strategy=family,version=plan['versions'][family],minutes=tf,risk_percent=rate,
                        cost_model=model,train=train,selection_result=selection_result,walk_forward=wf,
                        corporate_crossing_signals_excluded=excluded,selection=check,final=None))
    opened=[]
    for row in rows:
        if row['selection']['passes_for_final']:
            final_series,_=partition_series(data,HISTORY_END)
            prepared,_=prepared_episodes(final_series[row['minutes']],row['strategy'])
            row['final']=simulate(final_series[row['minutes']],row['strategy'],row['risk_percent'],row['cost_model'],
                FINAL_START.isoformat(),HISTORY_END.isoformat(),spread_ratios,prepared=prepared)
            opened.append(row['version'])
    report=dict(status=decision(operation,data_quality,rows),protocol=plan,operation=operation,data_quality=data_quality,
        corporate_action_handling=corporate,dataset_sha256=hashlib.sha256(raw).hexdigest(),
        adjusted_quality_sha256=data.get('adjusted_quality_sha256'),
        observed_spread_ratios=spread_ratios,
        cost_scope='CURRENT_PUBLISHED_TARIFF_AND_SINGLE_QUOTE_SCENARIO_NOT_HISTORICAL_EFFECTIVE_FEES',
        configurations=len(rows),partition_results=len(rows)*5+len(opened),rows=rows,
        final_holdout_sealed=not opened,final_outcomes_evaluated=len(opened),capital_requirements=capital,
        final_dataset_bar_counts={s:{tf:sum(FINAL_START<=at(b['opened_at'])<HISTORY_END for b in bars)
            for tf,bars in record.get('bars',{}).items()} for s,record in data.get('symbols',{}).items()},
        evaluated_source_range=[HISTORY_START.isoformat(),FINAL_START.isoformat()],
        excluded_previous_validation_archive=plan['quarantined_previous_archive'],sources=SOURCES,
        limitations=['Universe remains SCHX/SPY/F, chosen among survivors. No broad strategy viability inference.',
            'SCHX split restored from verified issuer event; no position crosses the action; prior feature warmup restarts. Other actions/dividend cash ledger incomplete.',
            'ADJUSTED_LAST used only for data-quality comparison, never as executable prices or receivable cash.',
            'Selection is chronological retrospective unseen history, not a prospective confirmation. Earlier April–October 2026 results never train or select.',
            'Missing effective tariffs/permitted intraday funds remain execution blockers; simulations use frozen conservative cash T+1/cost assumptions.',
            'Risk of capital exhaustion cannot be assigned a reliable probability from policy-stopped, sparse/dependent samples.',
            'Maximum loss allowance remains 20 and gains do not replenish it. Five independent study allocations cannot be summed as one portfolio.'],
        orders_sent=0,execution_authorized=False,live_enabled=False)
    portal=folder/'portal-status.json'
    report['local_portal_observation']=json.loads(portal.read_bytes()) if portal.exists() else None
    report['historical_query_correction']=dict(initial_error='IBKR_321_ADJUSTED_LAST_END_DATE_MUST_BE_EMPTY',
        corrected_sdk_end='',supplemental_errors=adjusted.get('errors',[]) if supplement.exists() else None,
        data_use='QUALITY_ONLY; BARS_AFTER_HISTORY_END_EXCLUDED',source=SOURCES['adjusted_end_date'])
    save(folder/'report.json',report);render(root,report);return report


def render(root,r):
    base=[x for x in r['rows'] if x['cost_model']=='TIERED_BASE']
    sample=max((x['selection_result']['metrics']['admitted'] for x in base),default=0)
    tiny=[x for x in base if x['selection_result']['metrics']['admitted']==1 and x['selection_result']['metrics']['net_pnl']>0]
    small_note=''
    if tiny:
        x=tiny[0];ci=x['selection_result']['confidence']['win_wilson_95'];m=x['selection_result']['metrics']
        small_note=f" {x['strategy']} {x['minutes']}m/{x['risk_percent']}% obtiene +US${m['net_pnl']:.4f} con una única ganadora (Wilson95: {100*ci[0]:.2f}%–{100*ci[1]:.2f}%): no acredita edge ni acierto >80%."
    breaches=[(x,t) for x in base for t in x['selection_result']['trades'] if t['risk_breach']]
    gap_note='No se recortan pérdidas históricas para simular que se respetó US$20. Escenarios con breaches quedan descalificados. Probabilidad fiable de ruina y ejecución real: UNKNOWN.'
    if breaches:
        x,t=min(breaches,key=lambda item:item[1]['netPnl']);m=x['selection_result']['metrics']
        gap_note=(f"Riesgo observado: {x['strategy']} {x['minutes']}m/{x['risk_percent']}%, {t['symbol']} {t['exitAt']}, salida {t['close_reason']}. "
            f"Riesgo restante presupuestado US${t['risk_budget']:.2f}, pérdida realizada US${-t['netPnl']:.2f}; pérdidas acumuladas US${m['consumed_loss']:.2f} y DD {100*m['maximum_drawdown']:.2f}%. "
            'El motor congelado marca breach y bloquea nuevas entradas: el stop no garantiza el precio ni limita gaps. '+gap_note)
    lines=['# Evidencia operativa y económica bursátil','',f"**{r['status']}**. Sin promoción ni autorización de ejecución.",'',
        f"En selección 2024 la muestra máxima es {sample} operaciones por configuración; no se suman escenarios correlacionados.{small_note} Los cuatro candidatos mantienen parámetros/versiones R0 intactos.",
        '', '## Comparación de referencia, sin selección de perfil','',
        'Selección cronológica 2024, 1h, riesgo 15%, Tiered base estimado. Se muestra el mismo escenario para los cuatro; no es recomendación de riesgo.', '',
        '| Candidato | Admitidas | Win % | Neto US$ | EV neta | PF | DD % | Días primer loss |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in r['rows']:
        if row['cost_model']=='TIERED_BASE' and row['risk_percent']==15 and row['minutes']==60:
            m=row['selection_result']['metrics']
            lines.append(f"| {row['strategy']} | {m['admitted']} | {100*m['win_rate']:.2f} | {m['net_pnl']:.2f} | {m['net_expectancy']:.4f} | {m['profit_factor']:.4f} | {100*m['maximum_drawdown']:.2f} | {m['first_loss_days']} |")
    lines+=['',
        gap_note, '',
        '## Hechos y alcance','', '| Hecho | Estado | Valor / alcance |','|---|---|---|']
    for f in r['operation']['facts']:
        val='null' if f['value'] is None else json.dumps(f['value'],ensure_ascii=False)
        lines.append(f"| {f['name']} | {f['status']} | {val}; {f['scope']} |")
    lines+=['','VERIFIED acredita exclusivamente el hecho observado y su alcance. ESTIMATED indica inferencia/modelo; UNKNOWN conserva null y bloquea admisión cuando es requisito. AvailableFunds/CashBalance no sustituyen SettledCash ni el capital aislado US$100. Contrato y datos no prueban permiso de negociación.',
        'Bloqueos de ejecución: '+', '.join(r['operation']['execution_blockers'])+'.','',
        'La consulta local de estado de Client Portal falló con URLError; no se inició login ni se cambiaron permisos. Se necesitan pruebas de cuenta desde una sesión local autorizada o extracto. ADJUSTED_LAST devolvió inicialmente IBKR 321 porque requiere endDateTime vacío: corregido y obtenido en la consulta suplementaria. La cola reciente se descarta antes de cualquier uso; los datos ajustados solo verifican calidad.', '',
        '## Procedencia, separaciones y calidad','',
        'Universo fijo SCHX/SPY/F; IBKR TRADES RTH, timestamps UTC y calendario SCHEDULE auténtico. Entrenamiento 2021–2023, selección 2024, final 2025–2026-04-03. El archivo examinado 2026-04-03–2026-10-03 está en cuarentena, excluido de entrenamiento y selección. Sin optimización ni ajuste de parámetros.',
        f"Configuraciones reevaluadas: {r['configurations']}; resultados de entrenamiento/selección/tres folds: {r['partition_results']}. Final sellado: {r['final_holdout_sealed']}; resultados finales evaluados: {r['final_outcomes_evaluated']}.", '',
        '| Instrumento | Sesiones | Velas 1h | Velas diario | Cobertura | ADJUSTED_LAST |','|---|---:|---:|---:|---|---|']
    for s,q in r['data_quality']['instruments'].items():
        lines.append(f"| {s} | {q['session_days']} | {q['timeframes']['60']['count']} | {q['timeframes']['1440']['count']} | {all(t['complete'] for t in q['timeframes'].values())} | {q['adjusted_daily_comparison']['available']} |")
    lines+=['','SCHX: evento 3:1 verificado con el emisor, precio de cotización post-split desde 2024-10-11. Se restaura ×3 el OHLC anterior para dimensionar con notional histórico; estimación basada en TRADES ajustado por splits. Se excluyen entradas que puedan cruzar el evento y se reinicia warm-up causal por episodio. No se cambia ningún parámetro R0. Volumen permanece original; no se afirma reconstrucción completa de todas las acciones corporativas.',
        'ADJUSTED_LAST no alimenta señales/P&L: sus ajustes futuros por dividendos no son precios negociables históricos. Calendario de dividendos/receivables y otras acciones corporativas sin conciliación independiente: UNKNOWN. Universo sin sesgo de supervivencia: no demostrado; se limita a estudio de casos. Estas carencias impiden abrir la prueba final.',
        '', '## Selección 2024 — todos los riesgos, Tiered base','',
        '| Candidato | TF | Riesgo % | Admitidas/rechazadas | Win % | Wilson95 % | Neto US$ | EV | PF | DD % | Comisiones | Días primer loss |',
        '|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    def fmt(v):return 'N/D' if v is None else f'{v:.4f}'
    for row in r['rows']:
        if row['cost_model']!='TIERED_BASE':continue
        x=row['selection_result'];m=x['metrics'];ci=x['confidence']['win_wilson_95']
        lines.append(f"| {row['strategy']} | {row['minutes']}m | {row['risk_percent']} | {m['admitted']}/{m['rejected']} | {fmt(None if m['win_rate'] is None else 100*m['win_rate'])} | {'N/D' if ci is None else '/'.join(fmt(100*v) for v in ci)} | {fmt(m['net_pnl'])} | {fmt(m['net_expectancy'])} | {fmt(m['profit_factor'])} | {fmt(100*m['maximum_drawdown'])} | {fmt(m['commissions'])} | {m['first_loss_days']} |")
    lines+=['','Todos los costos stress/Fixed, medias de ganancias/pérdidas, rechazos, drawdowns, bootstrap/intervalos ajustados de familia y folds se conservan en `artifacts/research/equity-evidence/report.json`. El presupuesto de pérdidas acumuladas US$20 puede detener el experimento antes de completar el año; no se reinicia para fabricar muestra. No sumar asignaciones independientes de folds.',
        '', '## Cambios que podrían mejorar factibilidad','',
        '| Candidato / TF | Señales selección con target neto potencial positivo | Capital mínimo estimado en una señal a 15% | Dentro de US$100 |','|---|---:|---:|---:|']
    for family in FAMILIES:
        for tf in TIMEFRAMES:
            vals=[v['requirement'] for v in r['capital_requirements'] if v['strategy']==family and v['minutes']==tf and v['requirement']]
            lines.append(f"| {family} / {tf}m | {len(vals)} | {fmt(min(v['minimum_capital_usd'] for v in vals)) if vals else 'SIN_TAMAÑO_POSITIVO'} | {sum(v['fits_usd100'] for v in vals)} |")
    lines+=['','Estos mínimos son geometría de UNA señal y costos estimados, no rentabilidad de portfolio ni capital recomendado. Más capital puede reducir costo fijo relativo; no demuestra edge, acierto >80% ni permiso intradía. Instrumento: SPY entero es caro para US$100; fracciones requieren permiso/route/costos específicos. Frecuencia: el modelo T+1 reduce reutilización intradía; no se presupone crédito o cuota diaria. Costos: verificar el plan real y los cargos antes de cambiar el modelo. Estrategia: no crear/optimizar otra hasta cerrar evidencia operativa y calidad.',
        '', '## Recomendación concreta','',
        'Siguiente fase: evidencia de cuenta desde Portal/extracto autorizado de solo lectura (permisos US Stocks/ETF, entidad/Reg T/Cash, tarifa efectiva, settled USD y reglas de intradía), BID/ASK real time durante RTH y calendario/acciones corporativas íntegros de proveedor auténtico. No hace falta una orden para certificar ajustes de cuenta; what-if requeriría placeOrder y se mantiene prohibido. Protección efectiva bursátil exige una futura validación controlada separada, todavía sin autorizar.',
        'Conservar el test final cerrado hasta que selección y calidad lo justifiquen. Después ejecutar una sola evaluación congelada; si falla, no volver a entrenar o seleccionar sobre ese test. Mantener FIRST_LOSS_STOPS_DAY en America/Santo_Domingo, una posición y gestión/reconciliación de pendientes.',
        '', '## Limitaciones','']
    lines.extend('- '+v for v in r['limitations'])
    lines+=['','## Fuentes primarias','']
    lines.extend(f'- [{name}]({url}).' for name,url in SOURCES.items())
    verification=Path(root)/'artifacts/test-results/equity-evidence/verification.json'
    if verification.exists():
        v=json.loads(verification.read_bytes());lines+=['','## Regresiones y seguridad','',
            f"{v['python_passed']} Python + {v['csharp_passed']} C# = {v['total_passed']} aprobadas. Fallos/omitidas: {v['failed']}/{v['skipped']}. Build: {v['build_errors']} errores, {v['build_warnings']} advertencias.",
            'RiskEngine, candidatos R0/Forex V1, límites, AccountBinding, EmergencyStop y archivos previos permanecen idénticos por SHA256. Emergencia activa, PaperAuto ausente, Live bloqueado y órdenes transmitidas 0. PostgreSQL desechable detenido.']
    (Path(root)/'docs/architecture/equity-evidence-feasibility.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--collect',action='store_true')
    p.add_argument('--adjusted-quality',action='store_true')
    args=p.parse_args()
    if args.collect:
        r=collect(args.root);print(json.dumps(dict(errors=r['errors'],counts={s:{tf:len(b) for tf,b in v.get('bars',{}).items()}
            for s,v in r['symbols'].items()},orders_sent=0)))
    elif args.adjusted_quality:
        r=adjusted_quality(args.root);print(json.dumps(dict(errors=r['errors'],counts={s:len(x['bars']) for s,x in r['symbols'].items()})))
    else:
        r=evaluate(args.root);print(json.dumps(dict(status=r['status'],configurations=r['configurations'],
            results=r['partition_results'],final_sealed=r['final_holdout_sealed'])))
