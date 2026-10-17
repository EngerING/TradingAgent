from datetime import datetime,timedelta,timezone
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from trading_agent.broker import PaperOptions
from trading_agent.history_extension import Archive,pages,research_wire
from test_tws import Client
from types import SimpleNamespace

class HistoryExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp_root=Path(__file__).resolve().parents[2]/'.local'/'test-history-temp'
        self.temp_root.mkdir(parents=True,exist_ok=True)
    def wire(self):
        w=research_wire(PaperOptions('DU123',paper_mode_attested=True,timeout=.05),(Client,object,SimpleNamespace));w.connect();return w
    def test_six_month_pages_are_bounded_contiguous_and_unique(self):
        end=datetime(2026,10,3,tzinfo=timezone.utc);start=datetime(2026,4,3,tzinfo=timezone.utc)
        for minutes in (15,60,240):
            plan=list(pages(start,end,minutes));self.assertEqual(plan[0]['end'],end.isoformat());self.assertEqual(plan[-1]['start'],start.isoformat())
            self.assertEqual(len({json.dumps(p) for p in plan}),len(plan))
            for a,b in zip(plan,plan[1:]):self.assertEqual(a['start'],b['end'])
            self.assertTrue(all(p['days']<=(7 if minutes==15 else 28) for p in plan))
    def test_guarded_archive_caches_identical_requests_and_detects_tampering(self):
        w=self.wire();end=datetime.now(timezone.utc);spec={**next(pages(end-timedelta(days=7),end,15)),'kind':'MIDPOINT'}
        with tempfile.TemporaryDirectory(dir=self.temp_root) as root,patch.dict(os.environ,{'PAPER_MANUAL_EXPIRES_AT':(end+timedelta(hours=1)).isoformat()}):
            a=Archive(w,root,'PAPER-test',end);r=a.request(spec);self.assertEqual(r['availability'],'AVAILABLE')
            a.request(spec);self.assertEqual(len(w._client.calls),1)
            path=next(p for p in Path(root).glob('*.json') if p.name!='pacing.json');r['rows'][0]['close']='99';path.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'INTEGRITY'):a.request(spec)
        w.disconnect()
    def test_expiry_and_disconnection_cannot_authorize_reads(self):
        w=self.wire();end=datetime.now(timezone.utc);spec={**next(pages(end-timedelta(days=7),end,15)),'kind':'MIDPOINT'}
        with tempfile.TemporaryDirectory(dir=self.temp_root) as root,patch.dict(os.environ,{'PAPER_MANUAL_EXPIRES_AT':(end-timedelta(seconds=1)).isoformat()}):
            with self.assertRaises(PermissionError):Archive(w,root,'PAPER-test',end).request(spec)
            self.assertEqual(w._client.calls,[])
        w.disconnect()
        with self.assertRaises(ConnectionError):w._begin('research_history')
    def test_adapter_preserves_order_block(self):
        w=self.wire()
        for name in ('placeOrder','placeOrderProtoBuf','cancelOrder','reqGlobalCancel'):
            with self.assertRaises(PermissionError):getattr(w._client,name)(object())
        w.disconnect()
