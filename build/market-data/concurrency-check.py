"""Bounded Windows process tests, separate from the unchanged no-subprocess unit guard."""
from pathlib import Path
import hashlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO/'python/tests/m03a_concurrency_worker.py'
VIOLATIONS = []
ROOTS = set()
SAMPLES = []


def guard(event,args):
    blocked = event.startswith('socket.') or event in ('os.system','os.startfile')
    if event == 'subprocess.Popen':
        command = args[1]
        expected = [[sys.executable,'-B',str(WORKER),role,root] for role in ('writer','reader') for root in ROOTS]
        # CPython's Windows audit event contains the final quoted CreateProcess command.
        blocked |= not (args[0] is not None and Path(args[0]).resolve() == Path(sys.executable).resolve() and
            Path(args[2]).resolve() == REPO and args[3] is None and
            (command in expected if type(command) is list else command in [subprocess.list2cmdline(c) for c in expected]))
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
        blocked |= any(p.casefold().rstrip(' .') == '.local' for p in Path(os.fsdecode(args[0])).parts)
    if event == 'sqlite3.connect': blocked = True
    if blocked:
        VIOLATIONS.append(event)
        raise AssertionError('M03A1_PROCESS_BARRIER')


class Worker:
    def __init__(self, role, root):
        self.lines, self.errors = queue.Queue(), []
        self.process = subprocess.Popen([sys.executable,'-B',str(WORKER),role,str(root)],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1,cwd=REPO,executable=sys.executable)
        def collect():
            for line in self.process.stdout: self.lines.put(line)
        def errors(): self.errors.extend(self.process.stderr.readlines())
        self.thread = threading.Thread(target=collect,daemon=True)
        self.error_thread = threading.Thread(target=errors,daemon=True)
        self.thread.start()
        self.error_thread.start()
        try: self.initial = self.receive()
        except BaseException:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.thread.join(timeout=2)
            self.error_thread.join(timeout=2)
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr): stream.close()
            raise

    def receive(self):
        try: return json.loads(self.lines.get(timeout=20))
        except queue.Empty:
            raise AssertionError('FIXTURE_WORKER_TIMEOUT '+''.join(self.errors)[-1200:]) from None

    def send(self, command):
        self.process.stdin.write(command+'\n')
        self.process.stdin.flush()

    def call(self, command):
        started = time.perf_counter()
        self.send(command)
        result = self.receive()
        if command == 'poll': SAMPLES.append((time.perf_counter()-started)*1000)
        return result

    def close(self, crash=False):
        try:
            if self.initial['phase'] == 'WRITER_REJECTED':
                assert self.receive() == {'phase':'CLOSED','barrier_violations':0}
            elif self.process.poll() is None:
                if crash: self.process.terminate()
                else:
                    self.send('stop')
                    closed = self.receive()
                    assert closed == {'phase':'CLOSED','barrier_violations':0}
            self.process.wait(timeout=20)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=5)
            self.thread.join(timeout=2)
            self.error_thread.join(timeout=2)
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr): stream.close()
        if not crash: assert self.process.returncode == 0 and not self.errors, ''.join(self.errors)[-1500:]


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='m03a1-fixture-')
        self.root = Path(self.temporary.name)/'capture'
        self.root.mkdir()
        ROOTS.add(str(self.root))
        self.workers = []

    def worker(self, role):
        result = Worker(role,self.root)
        self.workers.append(result)
        return result

    def tearDown(self):
        try:
            for worker in reversed(self.workers):
                if not worker.process.stdout.closed: worker.close()
        finally:
            ROOTS.discard(str(self.root))
            self.temporary.cleanup()  # Fails on Windows if a worker retained a handle.

    def test_real_writer_exclusion_and_two_independent_readers(self):
        writer = self.worker('writer')
        second = self.worker('writer')
        self.assertEqual('WRITER_REJECTED',second.initial['phase'])
        second.close()
        readers = [self.worker('reader'),self.worker('reader')]
        self.assertEqual(4,len({w.process.pid for w in self.workers}))
        writer.call('capture')
        for reader in readers:
            result = reader.call('poll')
            self.assertTrue(result['quote'])
            self.assertEqual('SYNTHETIC_TEST_FIXTURE',result['origin'])
        for _ in range(10):
            for reader in readers: self.assertEqual('UNCHANGED',reader.call('poll')['code'])

    def test_read_during_commit_and_rotation_has_no_dirty_observation(self):
        writer = self.worker('writer')
        reader = self.worker('reader')
        writer.call('capture')
        before = reader.call('poll')
        self.assertEqual('PAUSED',writer.call('pause')['phase'])
        during = reader.call('poll')
        self.assertIn(during['ask'],(None,'1.1002'))
        if during['cursor']: self.assertEqual(before['cursor'],during['cursor'])
        writer.send('release')
        self.assertEqual('COMMITTED',writer.receive()['phase'])
        after = reader.call('poll')
        self.assertEqual('1.1003',after['ask'])
        self.assertNotEqual(before['cursor'],after['cursor'])
        self.assertEqual('ROTATING',writer.call('rotate-pause')['phase'])
        self.assertFalse(reader.call('poll')['quote'])
        writer.send('release')
        self.assertEqual('COMMITTED',writer.receive()['phase'])
        self.assertFalse(reader.call('poll')['quote'])
        writer.call('capture')
        self.assertTrue(reader.call('poll')['quote'])
        self.assertEqual(2,reader.call('poll')['cursor']['segment'])

    def test_writer_interruption_recovery_and_reader_restart(self):
        writer = self.worker('writer')
        reader = self.worker('reader')
        writer.call('capture')
        self.assertTrue(reader.call('poll')['quote'])
        writer.call('pause')
        writer.close(crash=True)
        self.assertFalse(reader.call('poll')['quote'])
        recovered = self.worker('writer')
        self.assertEqual('READY',recovered.initial['phase'])
        self.assertFalse(reader.call('poll')['quote'])
        recovered.call('rotate')
        recovered.call('capture')
        self.assertTrue(reader.call('poll')['quote'])
        replacement = self.worker('reader')
        self.assertTrue(replacement.call('poll')['quote'])
        recovered.call('disconnect')
        self.assertFalse(replacement.call('poll')['quote'])


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.addaudithook(guard)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProcessTests)
    names = [test.id() for test in suite]
    result = unittest.TextTestRunner().run(suite)
    report = {'schema':'trading.m03a1.windows_process_tests','schema_version':1,'platform':sys.platform,
        'total':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failed':len(result.failures)+len(result.errors),'skipped':len(result.skipped),'test_ids':names,
        'barrier_violations':len(VIOLATIONS),'worker_sha256':hashlib.sha256(WORKER.read_bytes()).hexdigest(),
        'poll_samples':len(SAMPLES),'poll_ms_max':max(SAMPLES,default=0),
        'poll_ms_mean':sum(SAMPLES)/len(SAMPLES) if SAMPLES else 0}
    output = REPO/'tmp/m03a'
    output.mkdir(parents=True,exist_ok=True)
    (output/'concurrency.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('M03A1_PROCESS_BARRIER_VIOLATIONS:',len(VIOLATIONS))
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == len(set(names)) == 3 and
                     not result.skipped and not VIOLATIONS else 1)
