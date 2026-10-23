"""Literal historical vectors plus the installed SDK as an offline oracle."""
import struct
import unittest
from datetime import timedelta
from decimal import Decimal

from trading_agent.core_v3.contracts import ContractError
from trading_agent.market_data.wire import history_request, cancel_history, historical
from trading_agent.market_data.calendar import TradingCalendar
from test_m03a_contracts import AT
from test_core_v39_protocol import frame


def batch(minutes=15, timestamp=None, count=1):
    timestamp = timestamp or str(int((AT-timedelta(hours=1)).timestamp()))
    return frame(17, 200+{15:1,60:2,240:3}[minutes], 'start', 'end', count,
                 *sum(([timestamp, '1.1', '1.2', '1.0', '1.15', '-1', '-1', -1]
                       for _ in range(count)), []))[4:]


class WireTests(unittest.TestCase):
    def test_history_grammar_and_cancel_are_data_only(self):
        blob = history_request(201, 12087792, 15, AT)
        self.assertEqual(frame(20,201,12087792,'EUR','CASH','','0.0','','','IDEALPRO','','USD','','',
                               0,'20261023-12:00:00','15 mins','1 D',0,'MIDPOINT',2,0,''), blob)
        self.assertEqual(frame(25,1,201), cancel_history(201))
        for req, con, minutes in ((3,1,15),(201,0,15),(201,1,5),(201,1,60),(True,1,15)):
            with self.assertRaises(ContractError): history_request(req, con, minutes, AT)

    def test_history_closed_incomplete_and_gap(self):
        cal = TradingCalendar('UTC', '20261023:0000-20261024:0000', AT)
        bars, quality = historical(batch(), 15, AT, cal)
        self.assertEqual(1, len(bars))
        self.assertTrue(bars[0].complete)
        future, reasons = historical(batch(timestamp=str(int(AT.timestamp()))), 15, AT, cal)
        self.assertFalse(future[0].complete)
        self.assertIn('BAR_INCOMPLETE', future[0].quality)
        self.assertIsNone(getattr(bars[0], 'volume', None))

    def test_history_duplicates_malformed_ohlc_and_oversize(self):
        cal = TradingCalendar('UTC', '20261023:0000-20261024:0000', AT)
        for blob in (batch(count=2), batch().replace(b'1.2\0', b'0.2\0'), b'17\0'+b'x'*20000):
            with self.assertRaises(ContractError): historical(blob, 15, AT, cal)

    def test_native_off_utc_grid_and_incomplete_at_request_cutoff(self):
        cal = TradingCalendar('UTC','20261023:0000-20261024:0000',AT)
        shifted = batch(timestamp=str(int((AT-timedelta(minutes=47)).timestamp())))
        bars,_ = historical(shifted,15,AT,cal,request_end=AT)
        self.assertTrue(bars[0].complete)
        partial = batch(timestamp=str(int((AT-timedelta(minutes=5)).timestamp())))
        bars,_ = historical(partial,15,AT+timedelta(minutes=20),cal,request_end=AT)
        self.assertFalse(bars[0].complete)

    def test_history_sdk_oracle_offline(self):
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
        c = EClient(EWrapper())
        c.serverVersion_ = 157
        c.connState = c.CONNECTED
        c.isConnected = lambda: True
        sent = []
        c.sendMsg = lambda opcode, body: sent.append(frame(opcode)[4:]+body.encode())
        instrument = Contract()
        instrument.conId, instrument.symbol, instrument.secType = 12087792, 'EUR', 'CASH'
        instrument.currency, instrument.exchange, instrument.strike = 'USD', 'IDEALPRO', 0.0
        for minutes, size in ((15,'15 mins'),(60,'1 hour'),(240,'4 hours')):
            req = {15:201,60:202,240:203}[minutes]
            c.reqHistoricalData(req,instrument,'20261023-12:00:00','1 D',size,'MIDPOINT',0,2,False,[])
            self.assertEqual(history_request(req,12087792,minutes,AT)[4:],sent[-1])
        c.cancelHistoricalData(201)
        self.assertEqual(cancel_history(201)[4:],sent[-1])


if __name__ == '__main__': unittest.main()
