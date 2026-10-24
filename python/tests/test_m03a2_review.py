"""Adversarial M03-A.2 calendar/grid fixtures; no provider connection or data."""
from dataclasses import replace
from datetime import timedelta, timezone
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import json

from test_m03a2_backfill import START, spec, run, response
from test_m03a_reader import packets
from trading_agent.market_data.backfill.wire import plan
from trading_agent.market_data.backfill.store import HistoricalConsumer
from trading_agent.core_v3.contracts import ContractError, canonical_bytes
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind


class BackfillReviewTests(unittest.TestCase):
    def test_mutated_manifest_pointer_requires_original_immutable_generation(self):
        s=replace(spec(),end=START+timedelta(days=1),timeframes=(15,))
        with tempfile.TemporaryDirectory() as directory:
            _,_,clock=run(directory,s)
            path=Path(directory)/'dataset.json'
            document=json.loads(path.read_bytes());document['journal_head']='0'*64
            path.write_bytes(canonical_bytes(document))
            consumer=HistoricalConsumer(Path(directory),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            with self.assertRaises(ContractError): consumer.read(15,START,s.end,as_of=clock.now())

    def test_previous_local_closed_day_cannot_verify_entire_utc_day(self):
        s = replace(spec(), end=START+timedelta(days=1), timeframes=(15,))
        preflight = list(packets(hours='20261018:CLOSED')[:3])
        fields = preflight[1][:-1].decode().split('\0')
        fields[27] = 'America/New_York'
        preflight[1] = ('\0'.join(fields)+'\0').encode()
        payloads = tuple(preflight)+tuple(response(w) for w in plan(s))
        # Explicit synthetic UTC-4 zone: this fixture needs no system tzdata.
        with tempfile.TemporaryDirectory() as directory, patch(
                'trading_agent.market_data.calendar.ZoneInfo',
                return_value=timezone(timedelta(hours=-4))):
            result, _, _ = run(directory, s, payloads=payloads)
        self.assertNotEqual('HISTORICAL_COMPLETE', result.status)
        self.assertIn('CALENDAR_UNKNOWN', result.quality)
        self.assertIn('HISTORY_GAP', result.quality)

    def test_extra_off_grid_bar_rejects_frame_even_with_all_expected_slots(self):
        s = replace(spec(), end=START+timedelta(days=1), timeframes=(15,))
        window = plan(s)[0]
        fields = response(window)[:-1].decode().split('\0')
        extra = fields[5:13].copy()
        extra[0] = str(int(START.timestamp())+60)
        fields[4] = '97'
        fields[13:13] = extra
        batch = ('\0'.join(fields)+'\0').encode()
        payloads = packets(hours='20261019:0000-20261020:0000')[:3]+(batch,)
        with tempfile.TemporaryDirectory() as directory:
            result, _, _ = run(directory, s, payloads=payloads)
        self.assertEqual('HISTORICAL_REJECTED', result.status)
        self.assertFalse(result.pages)
        self.assertIn('HISTORY_REJECTED', result.quality)


class PartialTimeWindowTests(unittest.TestCase):
    """Finite intraday historical cutoffs; every broker frame is synthetic."""

    @staticmethod
    def _friday_hours():
        return ';'.join(
            (START+timedelta(days=i)).strftime('%Y%m%d')+':0000-'+
            ((START+timedelta(days=i+1)).strftime('%Y%m%d')+':0000'
             if i<4 else '20261023:2100')
            for i in range(5)
        )+';20261024:CLOSED;20261025:2100-20261026:0000'

    @staticmethod
    def _padded(window):
        """IBKR duration rounds up to days, delivering a bounded older overlap."""
        from test_core_v39_protocol import frame
        original=response(window)[:-1].decode('ascii').split('\0')
        count=int(original[4])
        blocks=[original[5+8*i:13+8*i] for i in range(count)]
        seconds=(window.end-window.start).total_seconds()
        days=int((seconds+86399)//86400)
        at=window.end-timedelta(days=days)
        prefix=[]
        while at<window.start:
            prefix.append([str(int(at.timestamp())),'1.1','1.2','1.0','1.15','-1','-1',-1])
            at+=timedelta(minutes=window.minutes)
        all_blocks=prefix+blocks
        return frame(17,window.request_id,'start','end',len(all_blocks),
                     *(part for block in all_blocks for part in block))[4:]

    def test_intraday_end_produces_exact_rounded_requests(self):
        from trading_agent.market_data.backfill.wire import request
        friday=START+timedelta(days=4,hours=21)
        s=replace(spec(),end=friday)
        self.assertEqual(friday,s.end)
        windows=plan(s)
        self.assertEqual([5,2,1],[sum(w.minutes==m for w in windows) for m in (15,60,240)])
        last=windows[-1]
        fields=request(last,12087792)[4:].decode('ascii').split('\0')
        self.assertEqual('5 D',fields[17])
        self.assertEqual('20261023-21:00:00',fields[15])
        self.assertEqual('MIDPOINT',fields[19])
        with self.assertRaises(Exception):
            replace(s,end=friday+timedelta(minutes=1))
        with self.assertRaises(Exception):
            replace(s,end=START+timedelta(days=7,minutes=15))

    def test_closed_friday_backfill_rejects_padding_from_dataset_but_is_complete(self):
        from test_m03a2_backfill import Clock
        from test_m03a_reader import packets
        friday=START+timedelta(days=4,hours=21)
        s=replace(spec(),end=friday)
        c=Clock();c.at=friday+timedelta(minutes=1)
        payloads=packets(hours=self._friday_hours())[:3]+tuple(self._padded(w) for w in plan(s))
        with tempfile.TemporaryDirectory() as directory:
            result,reader,_=run(directory,s,clock=c,payloads=payloads)
            self.assertEqual('HISTORICAL_COMPLETE',result.status)
            self.assertEqual('MARKET_CLOSED',result.market_state)
            self.assertEqual([468,117,30],
                [sum(p.count for p in result.pages if p.minutes==m) for m in (15,60,240)])
            self.assertEqual(8,reader.sent_opcodes.count(20))
            self.assertNotIn(1,reader.sent_opcodes)
            self.assertFalse(result.execution_authorized)
            from trading_agent.market_data.backfill.store import HistoricalConsumer
            from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
            consumer=HistoricalConsumer(Path(directory),s,'session-1',Origin.FIXTURE,SessionKind.PAPER)
            view=consumer.read(240,START,friday,as_of=c.now())
            self.assertTrue(view.sufficient)
            self.assertEqual(30,view.available_count)

    def test_future_cutoff_cannot_open_socket(self):
        from test_m03a2_backfill import Clock, permit
        from trading_agent.market_data.backfill.store import HistoricalStore
        from trading_agent.market_data.backfill.reader import FixtureHistoricalReader, collect
        from trading_agent.core_v3.contracts import ContractError
        from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
        friday=START+timedelta(days=4,hours=21)
        s=replace(spec(),end=friday)
        c=Clock();c.at=friday-timedelta(minutes=15)
        with tempfile.TemporaryDirectory() as directory:
            with HistoricalStore(Path(directory),s,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=True) as store:
                reader=FixtureHistoricalReader((),s,permit(s,c),store,now=c.now,mono=c.mono,wait=c.wait)
                with self.assertRaises(ContractError): collect(reader,store)
                self.assertEqual((),reader.sent_opcodes)

    def test_incomplete_last_hour_or_four_hours_is_not_complete(self):
        from trading_agent.market_data.calendar import TradingCalendar
        from trading_agent.market_data.backfill.store import expected, cutoff_has_incomplete_bar
        from trading_agent.market_data.backfill.contracts import Window
        friday=START+timedelta(days=4,hours=21)
        calendar=TradingCalendar('UTC',self._friday_hours(),friday)
        complete=replace(spec(),end=friday)
        incomplete=replace(complete,end=friday-timedelta(minutes=15))
        self.assertFalse(cutoff_has_incomplete_bar(calendar,complete))
        self.assertTrue(cutoff_has_incomplete_bar(calendar,incomplete))
        day=START+timedelta(days=4)
        slots=expected(calendar,Window(3000,240,day,incomplete.end))
        self.assertNotIn(day+timedelta(hours=20),slots)
        self.assertIn(day+timedelta(hours=16),slots)

    def test_sunday_reopening_backfills_only_finished_bars(self):
        from datetime import datetime
        from test_core_v39_protocol import frame
        from test_m03a2_backfill import Clock
        from test_m03a_reader import packets
        saturday=START+timedelta(days=5)
        sunday=saturday+timedelta(days=1)
        end=sunday+timedelta(hours=22)
        s=replace(spec(),start=saturday,end=end,timeframes=(15,))
        c=Clock();c.at=end+timedelta(minutes=1)
        windows=plan(s)
        self.assertEqual(2,len(windows))
        fields=[]
        for k in range(4):
            at=sunday+timedelta(hours=21,minutes=15*k)
            fields.extend([str(int(at.timestamp())),'1.1','1.2','1.0','1.15','-1','-1',-1])
        payloads=packets(hours='20261024:CLOSED;20261025:2100-20261025:2200')[:3]+(
            response(windows[0]),frame(17,windows[1].request_id,'start','end',4,*fields)[4:])
        with tempfile.TemporaryDirectory() as directory:
            result,reader,_=run(directory,s,clock=c,payloads=payloads)
            self.assertEqual('HISTORICAL_COMPLETE',result.status)
            self.assertEqual(4,sum(p.count for p in result.pages))
            self.assertEqual(2,reader.sent_opcodes.count(20))

    def test_dst_sunday_market_open_is_not_a_fixed_utc_hour(self):
        from datetime import datetime, timezone
        from trading_agent.market_data.calendar import TradingCalendar
        for day,open_hour in (('20261025',21),('20261101',22)):
            opening=datetime.strptime(day,'%Y%m%d').replace(tzinfo=timezone.utc)+timedelta(hours=open_hour)
            calendar=TradingCalendar('America/New_York',
                day+':1700-'+day+':1800',opening-timedelta(minutes=2))
            self.assertEqual('CLOSED',calendar.state(opening-timedelta(minutes=1)))
            self.assertEqual('OPEN',calendar.state(opening+timedelta(minutes=1)))


if __name__ == '__main__':
    unittest.main()
