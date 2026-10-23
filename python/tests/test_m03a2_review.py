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


if __name__ == '__main__':
    unittest.main()
