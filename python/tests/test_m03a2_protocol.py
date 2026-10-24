"""Independent SDK oracle, fail-closed defaults and rejected durable-event regressions."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
from trading_agent.core_v3.market_observation.ibkr_protocol import Command
from trading_agent.market_data.backfill.__main__ import main
from trading_agent.market_data.backfill.reader import FixtureHistoricalReader, collect
from trading_agent.market_data.backfill.store import HistoricalStore, HistoricalConsumer
from trading_agent.market_data.backfill.wire import plan, request, cancel
from test_m03a2_backfill import START, spec, permit, Clock, stream
from test_core_v39_protocol import frame


class ProtocolTests(unittest.TestCase):
    def test_connection_unavailable_publishes_no_data_without_inventing_connected_event(self):
        s=replace(spec(),end=START+timedelta(days=1),timeframes=(15,));c=Clock()
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
            r=FixtureHistoricalReader(stream(s),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
            with patch.object(r,'_open',side_effect=OSError('synthetic connection unavailable')):
                result=collect(r,store)
            self.assertEqual('HISTORICAL_UNAVAILABLE',result.status)
            self.assertIn('BACKFILL_CONNECTION_OR_VALIDATION',result.quality)
            self.assertFalse(result.pages)
            self.assertEqual(0,result.committed_events)
            self.assertTrue(r.closed)

    def test_sdk_10502_history_oracle_all_segment_sizes_without_connection(self):
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
        c=EClient(EWrapper());c.serverVersion_=157;c.connState=c.CONNECTED;c.isConnected=lambda:True
        sent=[];c.sendMsg=lambda opcode,body:sent.append(frame(opcode)[4:]+body.encode())
        instrument=Contract();instrument.conId=12087792;instrument.symbol='EUR';instrument.secType='CASH'
        instrument.currency='USD';instrument.exchange='IDEALPRO';instrument.strike=0.0
        for w in plan(spec()):
            c.reqHistoricalData(w.request_id,instrument,w.end.strftime('%Y%m%d-%H:%M:%S'),
                str((w.end-w.start).days)+' D',{15:'15 mins',60:'1 hour',240:'4 hours'}[w.minutes],
                'MIDPOINT',0,2,False,[])
            self.assertEqual(request(w,12087792)[4:],sent[-1])
        c.cancelHistoricalData(3000);self.assertEqual(cancel(3000)[4:],sent[-1])

    def test_default_entrypoint_has_no_socket_or_filesystem_inputs(self):
        with patch('socket.socket',side_effect=AssertionError('NO_SOCKET')):
            self.assertEqual(0,main([]))
            self.assertEqual(1,main(['--approved-history-only']))

    def test_quote_and_trading_commands_have_no_transport_path(self):
        s=replace(spec(),end=START+timedelta(days=1),timeframes=(15,));c=Clock()
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
            r=FixtureHistoricalReader(stream(s),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
            for command in (Command.SUBSCRIBE,Command.CANCEL,Command.DATA_TYPE,'placeOrder','cancelOrder','reqGlobalCancel'):
                with self.assertRaises(ContractError): r._send(command)
            self.assertFalse(r.sent_opcodes)

    def rejected_plan(self, *, clock_error=False):
        s=replace(spec(),end=START+timedelta(days=1),timeframes=(15,));c=Clock()
        with tempfile.TemporaryDirectory() as d, HistoricalStore(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
            r=FixtureHistoricalReader(stream(s),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
            iterator=r.events();store.archive.rotate(c.now());changed=False;rejected=None
            try:
                for e in iterator:
                    if e.diagnostic=='BACKFILL_PLANNED': changed=True
                    if changed:
                        e=replace(e,monotonic_ns=e.monotonic_ns+10**9) if clock_error else replace(e,sequence=e.sequence+1)
                    row=store.append(e,as_of=c.now())
                    if e.diagnostic=='BACKFILL_PLANNED': rejected=row
                self.assertFalse(rejected.value.accepted)
                result=store.publish(c.now())
                self.assertFalse(result.pages);self.assertIn('HISTORY_EVENT_REJECTED',result.quality)
                self.assertEqual('HISTORICAL_REJECTED',result.status)
                consumer=HistoricalConsumer(Path(d),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
                self.assertFalse(consumer.read(15,START,s.end,as_of=c.now()).bars)
            finally: iterator.close();r.close()

    def test_rejected_sequence_plan_cannot_authorize_later_batch(self): self.rejected_plan()
    def test_rejected_clock_plan_cannot_authorize_later_batch(self): self.rejected_plan(clock_error=True)


if __name__=='__main__': unittest.main()
