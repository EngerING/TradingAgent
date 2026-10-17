from pathlib import Path
import uuid
import unittest
from contextlib import contextmanager
from trading_agent.paper_identity import discover


class Wire:
    server_version=226
    def __init__(self,accounts):self.accounts=accounts;self.closed=False
    def connect(self):return self.accounts
    def disconnect(self):self.closed=True


class IdentityTests(unittest.TestCase):
    @contextmanager
    def directory(self):
        base=Path(__file__).resolve().parents[2]/'.local/identity-tests'
        base.mkdir(parents=True,exist_ok=True)
        target=(base/uuid.uuid4().hex).resolve()
        if not target.is_relative_to(base.resolve()):raise RuntimeError('UNSAFE_TEST_DIRECTORY')
        target.mkdir()
        try:yield target
        finally:
            for name in ('candidate.dpapi','candidate.tmp'):
                (target/name).unlink(missing_ok=True)
            target.rmdir()
    def test_discovery_masks_and_seals_without_authorizing(self):
        w=Wire(['DU12345678']);captured=[]
        def seal(data):captured.append(data);return b'ciphertext'
        with self.directory() as root:
            p=Path(root)/'candidate.dpapi';summary=discover(p,lambda *a,**k:w,seal)
            self.assertEqual(p.read_bytes(),b'ciphertext')
            self.assertNotIn('DU12345678',str(summary));self.assertEqual(summary['masked_account'],'***5678')
            self.assertFalse(summary['authorized']);self.assertIn(b'DU12345678',captured[0]);self.assertTrue(w.closed)
    def test_empty_malformed_and_additional_accounts_rejected(self):
        for accounts in ([],['masked***'],['DU123','DU456'],['DU123','U456']):
            with self.directory() as root:
                p=Path(root)/'candidate.dpapi';w=Wire(accounts)
                with self.assertRaises(PermissionError):discover(p,lambda *a,**k:w,lambda _:b'sealed')
                self.assertFalse(p.exists());self.assertTrue(w.closed)
    def test_encryption_failure_never_writes_plaintext(self):
        def failed(_):raise RuntimeError('encryption failed')
        with self.directory() as root:
            p=Path(root)/'candidate.dpapi';w=Wire(['DU12345678'])
            with self.assertRaises(RuntimeError):discover(p,lambda *a,**k:w,failed)
            self.assertFalse(p.exists());self.assertTrue(w.closed)
    def test_discovery_prefix_never_authorizes_paper_or_live(self):
        for account in ('U12345678','DF12345678','DU12345678','DUR12345678'):
            with self.directory() as root:
                summary=discover(root/'candidate.dpapi',lambda *a,**k:Wire([account]),lambda _:b'sealed')
                self.assertFalse(summary['authorized']);self.assertTrue(summary['manual_paper_check_required'])


if __name__=='__main__':unittest.main()
