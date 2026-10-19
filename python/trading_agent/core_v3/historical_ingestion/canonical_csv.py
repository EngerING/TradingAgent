"""Canonical SYNTHETIC fixture grammar. This is not a Dukascopy CSV schema."""
import csv
from decimal import Context, localcontext
import io
import re

from ..contracts import ContractError, parse_decimal, require
from .contracts import MAX_BYTES, MAX_ROWS
from .records import HistoricalBar, HistoricalQuote, Issue
from .time_rules import parse_timestamp


BAR_HEADER = ('record_id', 'symbol', 'opened_at', 'closed_at', 'available_at',
              'open', 'high', 'low', 'close', 'volume')
QUOTE_HEADER = ('record_id', 'symbol', 'event_at', 'available_at', 'sequence',
                'bid', 'ask', 'bid_size', 'ask_size')


def _optional(text):
    return None if text == '' else parse_decimal(text)


def _record(row, number, spec, zone):
    header = BAR_HEADER if spec.kind == 'OHLC' else QUOTE_HEADER
    require(len(row) == len(header), 'H38_CSV_COLUMNS')
    values = dict(zip(header, row))
    require(values.pop('symbol') == spec.symbol, 'H38_SYMBOL_MISMATCH')
    for name in ('opened_at', 'closed_at', 'event_at', 'available_at'):
        if name in values:
            values[name] = parse_timestamp(values[name], zone)
    if spec.kind == 'OHLC':
        for name in ('open', 'high', 'low', 'close'):
            values[name] = parse_decimal(values[name])
        values['volume'] = _optional(values['volume'])
        record = HistoricalBar(number, **values)
        prices = record.open, record.high, record.low, record.close
    else:
        text = values['sequence']
        require(re.fullmatch(r'(?:0|[1-9][0-9]{0,18})', text) is not None, 'H38_QUOTE_SEQUENCE')
        values['sequence'] = int(text)
        for name in ('bid', 'ask'):
            values[name] = parse_decimal(values[name])
        for name in ('bid_size', 'ask_size'):
            values[name] = _optional(values[name])
        record = HistoricalQuote(number, **values)
        prices = record.bid, record.ask
    with localcontext(Context(prec=80)):
        require(all(price % spec.tick == 0 for price in prices), 'H38_OFF_TICK')
    require(record.available_at <= spec.exported_at, 'H38_AVAILABILITY_AFTER_EXPORT')
    if spec.available_basis == 'EXPORT_OBSERVED':
        require(record.available_at == spec.exported_at, 'H38_EXPORT_AVAILABILITY')
    return record


def parse(raw, spec, zone):
    """Return candidates, fixed issue codes, rows seen and whether the full scan completed."""
    require(type(raw) is bytes and len(raw) <= MAX_BYTES, 'H38_CSV_SIZE')
    records, issues, count, complete = [], [], 0, True
    try:
        text = raw.decode('utf-8')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = next(reader, None)
        require(header == list(BAR_HEADER if spec.kind == 'OHLC' else QUOTE_HEADER), 'H38_CSV_HEADER')
        for count, row in enumerate(reader, 1):
            if count > MAX_ROWS:
                issues.append(Issue(count+1, 'H38_ROW_LIMIT'))
                complete = False
                break
            try:
                records.append(_record(row, count+1, spec, zone))
            except ContractError as error:
                issues.append(Issue(count+1, str(error)))
            if len(issues) >= 128:
                issues.append(Issue(0, 'H38_ISSUE_LIMIT'))
                complete = False
                break
    except (UnicodeError, csv.Error):
        issues.append(Issue(0, 'H38_CSV_INVALID'))
        complete = False
    except ContractError as error:
        issues.append(Issue(1, str(error)))
        complete = False
    if count == 0:
        issues.append(Issue(0, 'H38_EMPTY_DATA'))
    return tuple(records), issues, count, complete
