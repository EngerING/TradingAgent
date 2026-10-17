"""Research-only US securities reader. Reuses the mutation-blocked TWS client.

No authorization, migration, order, what-if, or production executor changes.
"""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo
from .broker import PaperOptions
from .ibkr_session import AccountBinding, SessionConfiguration
from .paper_lab import unseal
from .tws import official_wire, finite

UNIVERSE = ('SCHX', 'SPY', 'F')
START = datetime(2026, 4, 3, tzinfo=timezone.utc)
END = datetime(2026, 10, 3, tzinfo=timezone.utc)


def stock_wire(options, sdk_types=None):
    base = official_wire(options, sdk_types)
    if sdk_types is None:
        from ibapi.contract import Contract
    else:
        Contract = sdk_types[2]

    class Stocks(type(base)):
        def error(self, reqId, *args):
            code = args[1] if len(args)>=3 and isinstance(args[1],int) else args[0]
            if code == 2188 and self.active == 'stock_history' and reqId == self.request_id:
                # Archived requests end days/months ago. Advisory about the real-time tail
                # cannot complete the request: still require historicalDataEnd and real bars.
                self.events.append(dict(code=2188, request_id=reqId, request='stock_history',
                    advisory=True, received_at=datetime.now(timezone.utc).isoformat()))
                return
            super().error(reqId, *args)

        @staticmethod
        def contract(symbol):
            if symbol not in UNIVERSE:
                raise ValueError('RESEARCH_UNIVERSE_REQUIRED')
            c = Contract(); c.symbol = symbol; c.secType = 'STK'
            c.currency = 'USD'; c.exchange = 'SMART'
            return c

        def contract_details(self, symbol):
            self.symbol = symbol
            return super().contract_details(symbol)

        def contractDetails(self, reqId, details):
            if reqId != self.request_id or self.active != 'contract':
                return
            c = details.contract
            try:
                if c.conId <= 0 or (c.symbol, c.currency, c.secType) != (self.symbol, 'USD', 'STK'):
                    raise ValueError()
                row = dict(con_id=c.conId, symbol=c.symbol, security_type=c.secType,
                    primary_exchange=getattr(c, 'primaryExchange', None), currency=c.currency,
                    valid_exchanges=details.validExchanges, order_types=details.orderTypes,
                    min_tick=str(finite(details.minTick, True)), market_rule_ids=details.marketRuleIds,
                    trading_hours=details.tradingHours, liquid_hours=details.liquidHours,
                    time_zone=details.timeZoneId, minimum_size=None, size_increment=None,
                    fractional_permission=None, trading_permission=None,
                    received_at=datetime.now(timezone.utc).isoformat())
                for field, attr in (('minimum_size', 'minSize'), ('size_increment', 'sizeIncrement')):
                    v = getattr(details, attr, None)
                    if v is not None and Decimal(str(v)).is_finite() and 0 < Decimal(str(v)) < Decimal('1e100'):
                        row[field] = str(v)
                self.data.append(row)
            except (ValueError, ArithmeticError):
                self._invalid('INVALID_STOCK_CONTRACT')

        def account_observation(self):
            with self.lock:
                req = self._begin('stock_account')
                try:
                    self._client.reqAccountSummary(req, 'All',
                        'AccountType,SettledCash,AvailableFunds,BuyingPower,DayTradesRemaining,InitMarginReq,MaintMarginReq')
                    return self._wait()
                finally:
                    self.active = None; self._client.cancelAccountSummary(req)

        def accountSummary(self, reqId, account, tag, value, currency):
            if reqId != self.request_id or self.active != 'stock_account' or not self._check_account(account):
                return
            if tag not in ('AccountType', 'SettledCash', 'AvailableFunds', 'BuyingPower',
                           'DayTradesRemaining', 'InitMarginReq', 'MaintMarginReq'):
                return
            self.data.append(dict(tag=tag, value=value, currency=currency))

        def accountSummaryEnd(self, reqId):
            if reqId == self.request_id and self.active == 'stock_account':
                self.done.set()

        def account_details(self):
            with self.lock:
                self._begin('stock_account_details'); self.portfolio_rows=[]
                try:
                    self._client.reqAccountUpdates(True, options.account)
                    values=self._wait()
                    return dict(values=values,portfolio=self.portfolio_rows,
                        completed_at=datetime.now(timezone.utc).isoformat())
                finally:
                    self.active=None;self._client.reqAccountUpdates(False,options.account)

        def updateAccountValue(self,key,value,currency,account):
            if self.active!='stock_account_details' or not self._check_account(account):
                return
            if key in ('AccountType','TradingType-S','TradingType','SettledCash','SettledCash-S',
                'CashBalance','CashBalance-S','DayTradesRemaining','DayTradesRemainingT+1',
                'AvailableFunds','AvailableFunds-S','EquityWithLoanValue-S'):
                self.data.append(dict(tag=key,value=value,currency=currency))

        def updatePortfolio(self,contract,position,marketPrice,marketValue,averageCost,unrealizedPNL,realizedPNL,account):
            if self.active=='stock_account_details' and self._check_account(account):
                self.portfolio_rows.append(dict(con_id=contract.conId,symbol=contract.symbol,
                    security_type=contract.secType,currency=contract.currency,quantity=str(finite(position))))

        def accountDownloadEnd(self,account):
            if self.active=='stock_account_details' and self._check_account(account):
                self.done.set()

        def quote(self, symbol):
            self.symbol = symbol
            return super().quote(symbol)

        def _quote_result(self, reason):
            result = super()._quote_result(reason); result['instrument'] = self.symbol
            # Type 4 is delayed AND frozen, never current executable data.
            if result['market_data_type'] == 4:
                result['data_type'] = 'DELAYED_FROZEN'
            return result

        def historicalSchedule(self, reqId, startDateTime, endDateTime, timeZone, sessions):
            if reqId != self.request_id or self.active != 'stock_schedule':
                return
            self.data = [dict(start=s.startDateTime, end=s.endDateTime, day=s.refDate,
                              time_zone=timeZone) for s in sessions]
            self.done.set()

        def paced(self):
            delay = 16 - (time.monotonic() - self.last_history)
            if delay > 0:
                time.sleep(delay)
            self.last_history = time.monotonic()

        def schedule(self, symbol):
            with self.lock:
                self.paced(); req = self._begin('stock_schedule')
                try:
                    self._client.reqHistoricalData(req, self.contract(symbol), END.strftime('%Y%m%d-%H:%M:%S'),
                        '6 M', '1 day', 'SCHEDULE', 1, 2, False, [])
                    rows = self._wait()
                    if not rows:
                        raise ValueError('AUTHENTIC_STOCK_SCHEDULE_REQUIRED')
                    return rows
                finally:
                    self.active = None; self._client.cancelHistoricalData(req)

        def chunk(self, symbol, minutes, end):
            if minutes not in (60, 1440):
                raise ValueError('STOCK_TIMEFRAME_NOT_ENABLED')
            if end.tzinfo is None or not START <= end <= END or end > datetime.now(timezone.utc)-timedelta(minutes=15):
                raise ValueError('ARCHIVED_HISTORY_ONLY')
            with self.lock:
                self.paced(); req = self._begin('stock_history'); self.bar_minutes = minutes
                try:
                    self._client.reqHistoricalData(req, self.contract(symbol), end.strftime('%Y%m%d-%H:%M:%S'),
                        '1 M' if minutes == 60 else '6 M', '1 hour' if minutes == 60 else '1 day',
                        'TRADES', 1, 2, False, [])
                    return self._wait()
                finally:
                    self.active = None; self._client.cancelHistoricalData(req)

        def historicalData(self, reqId, bar):
            if reqId != self.request_id or self.active != 'stock_history':
                return
            try:
                raw = str(bar.date)
                values = [finite(v, True) for v in (bar.open, bar.high, bar.low, bar.close)]
                o, h, l, c = values
                if h < max(o, l, c) or l > min(o, h, c):
                    raise ValueError()
                volume = finite(bar.volume)
                if volume < 0:
                    raise ValueError()
                self.data.append(dict(broker_date=raw, minutes=self.bar_minutes,
                    **{k: str(v) for k, v in zip(('open', 'high', 'low', 'close'), values)}, volume=str(volume)))
            except (ValueError, ArithmeticError, OverflowError):
                self._invalid('INVALID_STOCK_CANDLE')

        def historicalDataEnd(self, reqId, start, end):
            if reqId == self.request_id and self.active == 'stock_history':
                self.done.set()

    return Stocks()


def normalize(rows, sessions, *, start=START, end=END):
    """RTH durations and early closes come from IBKR SCHEDULE, never a template."""
    if start.tzinfo is None or end.tzinfo is None or not start < end <= END:
        raise ValueError('ARCHIVED_NORMALIZATION_SCOPE_REQUIRED')
    intervals = {}
    for s in sessions:
        zone = ZoneInfo(s['time_zone'])
        def at(v):
            local = datetime.strptime(v, '%Y%m%d-%H:%M:%S').replace(tzinfo=zone)
            if local.utcoffset() != local.replace(fold=1).utcoffset():
                raise ValueError('AMBIGUOUS_SESSION_TIME')
            return local.astimezone(timezone.utc)
        session_start, session_end = at(s['start']), at(s['end'])
        if not session_start < session_end:
            raise ValueError('INVALID_SESSION')
        intervals[s['day']] = (session_start, session_end)
    output = {}
    for row in rows:
        if row['minutes'] == 1440:
            # Requests overlap window boundaries; discard out-of-scope dates first.
            day=datetime.strptime(row['broker_date'], '%Y%m%d').date()
            if day < start.date() or day > end.date():
                continue
            interval = intervals.get(row['broker_date'])
            if not interval:
                raise ValueError('DAILY_SESSION_NOT_FOUND')
            opened, closed = interval
        else:
            opened = datetime.fromtimestamp(int(row['broker_date']), timezone.utc)
            if opened < start or opened >= end:
                continue
            matches = [(a, b) for a, b in intervals.values() if a <= opened < b]
            if len(matches) != 1:
                raise ValueError('BAR_OUTSIDE_AUTHENTIC_SESSION')
            closed = min(opened + timedelta(minutes=row['minutes']), matches[0][1])
        if not start <= opened < closed <= end:
            continue
        result = {k: row[k] for k in ('open', 'high', 'low', 'close', 'volume', 'minutes')}
        result.update(opened_at=opened.isoformat(), closed_at=closed.isoformat())
        if result['opened_at'] in output and output[result['opened_at']] != result:
            raise ValueError('CONFLICTING_STOCK_BAR')
        output[result['opened_at']] = result
    ordered = [output[k] for k in sorted(output)]
    for i, row in enumerate(ordered[:-1]):
        # IBKR can return a short first/last RTH bar in a nominal hourly series.
        if row['minutes'] == 60 and row['closed_at'] > ordered[i+1]['opened_at']:
            row['closed_at'] = ordered[i+1]['opened_at']
    return ordered


def collect(root):
    root = Path(root); out = root/'artifacts/research/us-equities'; out.mkdir(parents=True, exist_ok=True)
    report = dict(scope='RESEARCH_READ_ONLY', source='IBKR_TWS', requested_start=START.isoformat(),
        requested_end=END.isoformat(), universe=list(UNIVERSE), orders_sent=0, live_enabled=False,
        permissions=None, pricing_plan=None, account_margin_type=None, account_entity=None,
        intraday_regime=None, fractional_support=None, symbols={}, account_values=[], errors=[], receipts=[])
    wire = None
    try:
        # Read existing binding directly: missing binding MUST NOT migrate/create one.
        binding = AccountBinding(unseal(root/'.local/ibkr-account-binding.dpapi'))
        endpoint = SessionConfiguration.load(root)
        wire = stock_wire(PaperOptions(binding.account, host=endpoint.host, port=endpoint.port,
            verified_tws_port=endpoint.port, paper_mode_attested=True, configured_endpoint=True,
            client_id=87, timeout=20))
        binding.select(wire.connect()); report['identity_verified'] = True
        report['account'] = binding.masked_account; report['server_version'] = wire.server_version
        report['account_values'] = wire.account_observation(); report['account_query_completed'] = True
        try:
            report['account_details']=wire.account_details()
        except Exception as exc:
            report['account_details_error']=type(exc).__name__
        for symbol in UNIVERSE:
            record = {}; report['symbols'][symbol] = record
            try:
                record['contract'] = wire.contract_details(symbol)
                record['quote'] = wire.quote(symbol)
                sessions = wire.schedule(symbol); record['sessions'] = sessions
                record['bars'] = {}
                for minutes in (60, 1440):
                    rows = []; end = END
                    for index in range(7 if minutes == 60 else 1):
                        chunk = wire.chunk(symbol, minutes, end); rows.extend(chunk)
                        report['receipts'].append(dict(symbol=symbol, minutes=minutes, end=end.isoformat(),
                            count=len(chunk), completed_at=datetime.now(timezone.utc).isoformat(),
                            request_id=wire.request_id, what_to_show='TRADES', use_rth=1))
                        if minutes == 60:
                            # Calendar-month paging with overlap; deduplication checks content equality.
                            end -= timedelta(days=28)
                    record['bars'][str(minutes)] = normalize(rows, sessions)
            except Exception as exc:
                record['error'] = str(exc) if str(exc).startswith(('IBKR_', 'INVALID_', 'AUTHENTIC_', 'BAR_', 'DAILY_', 'CONFLICTING_')) else type(exc).__name__
                report['errors'].append(dict(symbol=symbol, error=record['error']))
                if not wire.connected:
                    break
    except Exception as exc:
        report['errors'].append(dict(stage='CONNECTION_OR_ACCOUNT', error=type(exc).__name__,
            reason=str(exc) if str(exc).startswith(('IBKR_', 'TWS_', 'ACCOUNT_', 'AUTHORIZATION_')) else None))
    finally:
        report['connected_at_finish'] = wire.connected if wire else False
        report['ibkr_events'] = wire.events[:] if wire else []
        if wire:
            wire.disconnect()
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(report, indent=2, allow_nan=False).encode()
        (out/'ibkr-readonly.json').write_bytes(encoded)
        (out/'ibkr-readonly.sha256').write_text(hashlib.sha256(encoded).hexdigest(), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', default='.')
    result = collect(parser.parse_args().root)
    print(json.dumps(dict(errors=result['errors'], symbols={s: {m: len(b) for m, b in r.get('bars', {}).items()}
        for s, r in result['symbols'].items()}, orders_sent=0)))
