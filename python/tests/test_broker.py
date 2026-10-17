from dataclasses import replace
import unittest
from trading_agent.broker import PaperDataBroker,PaperOptions

class Wire:
    def __init__(self,accounts=('DU123',),fail=False):self.accounts=accounts;self.connected=False;self.fail=fail
    def connect(self):
        if self.fail:raise ConnectionError('offline')
        self.connected=True;return self.accounts
    def disconnect(self):self.connected=False
    def balance(self):return {'equity':100}
    def positions(self):return []
    def quote(self,instrument):return {'bid':1.1,'ask':1.1002}
    def history(self,instrument,minutes):return [{'minutes':minutes,'volume':None}]

class PaperBrokerTests(unittest.TestCase):
    def options(self):return PaperOptions('DU123',paper_mode_attested=True)
    def test_du_and_dur_require_full_authorized_identity(self):
        for account in ('DU12345678','DUR12345678'):
            with self.subTest(account=account):
                wire=Wire([account]);broker=PaperDataBroker(replace(self.options(),account=account),lambda _:wire)
                broker.connect();self.assertTrue(broker.connected);broker.disconnect()
    def test_unknown_and_malformed_configured_identifiers_rejected_before_connect(self):
        for account in ('','U123','DF123','DU','DUR','DURR123','dur123','DU123X','DUR123\n',' DU123','DU１２３'):
            with self.subTest(account=account):
                wire=Wire([account])
                with self.assertRaises(PermissionError):
                    PaperDataBroker(replace(self.options(),account=account),lambda _:wire).connect()
                self.assertFalse(wire.connected)
    def test_suffix_match_does_not_authorize_either_format(self):
        for configured,received in (('DU12345678','DU99995678'),('DUR12345678','DUR99995678'),
                                    ('DU12345678','DUR12345678'),('DUR12345678','DU12345678')):
            with self.subTest(configured=configured,received=received):
                wire=Wire([received]);broker=PaperDataBroker(replace(self.options(),account=configured),lambda _:wire)
                with self.assertRaisesRegex(PermissionError,'UNAUTHORIZED_ACCOUNT'):broker.connect()
                self.assertFalse(broker.connected);self.assertFalse(wire.connected)
                with self.assertRaises(ConnectionError):broker.balance()
    def test_both_formats_preserve_all_safety_gates(self):
        for account in ('DU123','DUR123'):
            for overrides in ({'paper_mode_attested':False},{'read_only':False},{'live_enabled':True},
                              {'environment':'LIVE_TRADING'},{'host':'192.0.2.1'},{'port':7496},
                              {'verified_tws_port':7496}):
                with self.subTest(account=account,overrides=overrides):
                    wire=Wire([account])
                    with self.assertRaises(PermissionError):
                        PaperDataBroker(replace(self.options(),account=account,**overrides),lambda _:wire).connect()
                    self.assertFalse(wire.connected)
    def test_success_reads_disconnect(self):
        b=PaperDataBroker(self.options(),lambda _:Wire());b.connect()
        self.assertEqual(b.balance()['equity'],100);self.assertEqual(b.positions(),[])
        self.assertLess(b.quote()['bid'],b.quote()['ask'])
        for tf in (15,60,240):self.assertIsNone(b.history(minutes=tf)[0]['volume'])
        b.disconnect();self.assertFalse(b.connected)
    def test_live_mismatch_unknown_and_unattested_rejected(self):
        for options in (replace(self.options(),environment='LIVE_TRADING'),replace(self.options(),live_enabled=True),
                        replace(self.options(),port=7496),replace(self.options(),paper_mode_attested=False)):
            with self.assertRaises(PermissionError):PaperDataBroker(options,lambda _:Wire()).connect()
        for accounts in (['U123'],[],['DU456'],['DU123','U123']):
            b=PaperDataBroker(self.options(),lambda _:Wire(accounts))
            with self.assertRaises(PermissionError):b.connect()
            self.assertFalse(b.connected)
    def test_bounded_reconnection(self):
        attempts=[]
        def factory(_):attempts.append(1);return Wire(fail=len(attempts)<3)
        b=PaperDataBroker(self.options(),factory,sleeper=lambda _:None);b.connect();self.assertEqual(len(attempts),3)
    def test_persistent_connection_failure(self):
        attempts=[]
        def factory(_):attempts.append(1);return Wire(fail=True)
        with self.assertRaises(ConnectionError):PaperDataBroker(self.options(),factory,lambda _:None).connect()
        self.assertEqual(len(attempts),3)
    def test_drop_blocks_reads(self):
        wire=Wire();b=PaperDataBroker(self.options(),lambda _:wire);b.connect();wire.connected=False
        with self.assertRaises(ConnectionError):b.balance()
    def test_no_order_capability(self):
        self.assertFalse(hasattr(PaperDataBroker,'placeOrder'));self.assertFalse(hasattr(PaperDataBroker,'submit_order'))

if __name__=='__main__':unittest.main()
