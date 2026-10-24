"""Windows processes: JSON readers, exclusive fixture writer, crash after COMMIT."""
from pathlib import Path
import hashlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO/'python/tests/m03a2_concurrency_worker.py'
ROOTS, VIOLATIONS, CHILD_COUNTERS = set(), [], []
MARKER = 'M03A2_SYNTHETIC_PROCESS_FIXTURE_V1'


def guard(event, args):
    blocked = event.startswith('socket.') or event in ('sqlite3.connect', 'os.system', 'os.startfile')
    if event == 'subprocess.Popen':
        expected = [[sys.executable, '-B', str(WORKER), role, root] for role in ('writer','reader','probe') for root in ROOTS]
        blocked |= not (args[0] and Path(args[0]).resolve() == Path(sys.executable).resolve() and
            Path(args[2]).resolve() == REPO and args[3] is None and
            (args[1] in expected if type(args[1]) is list else args[1] in [subprocess.list2cmdline(c) for c in expected]))
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0], (str,bytes,os.PathLike)):
        blocked |= any(p.casefold().rstrip(' .') == '.local' for p in Path(os.fsdecode(args[0])).parts)
    if blocked:
        VIOLATIONS.append(event)
        raise AssertionError('M032_PARENT_PROCESS_BARRIER')


class Worker:
    def __init__(self, role, root):
        self.lines, self.errors = queue.Queue(), []
        self.process = subprocess.Popen([sys.executable,'-B',str(WORKER),role,str(root)], executable=sys.executable,
            cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        def output():
            while True:
                line = self.process.stdout.readline(4097)
                if not line: break
                self.lines.put(line if len(line) <= 4096 and line.endswith('\n') else '{}')
        self.threads = [threading.Thread(target=output, daemon=True),
                        threading.Thread(target=lambda:self.errors.append(self.process.stderr.read(4097)), daemon=True)]
        for thread in self.threads: thread.start()
        try: self.initial = self.receive()
        except BaseException: self.close(crash=True); raise

    def receive(self):
        try:
            result = json.loads(self.lines.get(timeout=15))
            if 'barrier_violations' in result:
                assert result['barrier_violations'] == 0, result
            return result
        except queue.Empty: raise AssertionError('M032_WORKER_TIMEOUT '+''.join(self.errors)[-1200:]) from None

    def send(self, command):
        self.process.stdin.write(json.dumps({'cmd':command})+'\n'); self.process.stdin.flush()

    def call(self, command):
        self.send(command)
        return self.receive()

    def close(self, crash=False):
        if self.process.stdout.closed: return
        try:
            if crash:
                if self.process.poll() is None: self.process.terminate()
            elif self.initial['phase'] == 'WRITER_REJECTED': self.closed(self.receive())
            else: self.closed(self.call('stop'))
            self.process.wait(timeout=15)
        finally:
            if self.process.poll() is None: self.process.kill(); self.process.wait(timeout=15)
            for thread in self.threads: thread.join(timeout=2)
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr): stream.close()
        if not crash: assert self.process.returncode == 0 and not ''.join(self.errors), ''.join(self.errors)

    @staticmethod
    def closed(result):
        assert result == {'phase':'CLOSED','barrier_violations':0}, result
        CHILD_COUNTERS.append(result['barrier_violations'])


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='m03a2-fixture-')
        self.root = Path(self.temporary.name)/'dataset'; self.root.mkdir()
        (self.root.parent/'owner.json').write_text(MARKER)
        ROOTS.add(str(self.root)); self.workers = []

    def worker(self, role):
        child = Worker(role, self.root); self.workers.append(child); return child

    def tearDown(self):
        try:
            for child in reversed(self.workers): child.close()
        finally:
            ROOTS.discard(str(self.root)); self.temporary.cleanup()

    def test_two_json_readers_during_atomic_publication_and_writer_exclusion(self):
        writer = self.worker('writer'); probe = self.worker('probe')
        self.assertEqual('WRITER_REJECTED', probe.initial['phase']); probe.close()
        readers = [self.worker('reader'), self.worker('reader')]
        for reader in readers: self.assertEqual('UNAVAILABLE', reader.call('poll')['status'])
        self.assertEqual('COMMITTED', writer.call('capture')['phase'])
        before = [reader.call('poll') for reader in readers]
        self.assertEqual('PAUSED', writer.call('publish-pause')['phase'])
        for reader, previous in zip(readers, before): self.assertEqual(previous, reader.call('poll'))
        writer.send('release'); self.assertEqual('COMMITTED', writer.receive()['phase'])
        for reader, previous in zip(readers, before):
            after = reader.call('poll'); self.assertEqual(96, after['count'])
            self.assertEqual('HISTORICAL_COMPLETE', after['status']); self.assertNotEqual(previous['snapshot'], after['snapshot'])

    def test_terminated_writer_after_commit_replays_without_repeating_capture(self):
        writer = self.worker('writer'); reader = self.worker('reader')
        paused = writer.call('capture-pause'); self.assertEqual('PAUSED', paused['phase']); self.assertEqual(96, paused['samples'])
        self.assertEqual('UNAVAILABLE', reader.call('poll')['status'])
        writer.close(crash=True)
        recovered = self.worker('writer')
        self.assertEqual(96, recovered.initial['samples']); self.assertEqual(0, recovered.initial['pending'])
        self.assertEqual({'phase':'COMMITTED','samples':96,'requests':0}, recovered.call('publish'))
        self.assertEqual(96, reader.call('poll')['count'])


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.addaudithook(guard)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProcessTests)
    names = [test.id() for test in suite]
    result = unittest.TextTestRunner().run(suite)
    report = {'schema':'trading.m03a2.windows_process_tests','schema_version':1,'platform':sys.platform,
        'total':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failed':len(result.failures)+len(result.errors),'skipped':len(result.skipped),'test_ids':names,
        'barrier_violations':len(VIOLATIONS),'child_barrier_violations':sum(CHILD_COUNTERS),
        'worker_sha256':hashlib.sha256(WORKER.read_bytes()).hexdigest()}
    output = REPO/'tmp/m03a2'; output.mkdir(parents=True,exist_ok=True)
    (output/'concurrency.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if result.wasSuccessful() and sys.platform == 'win32' and result.testsRun == len(set(names)) == 2 and
                     not result.skipped and not VIOLATIONS and not any(CHILD_COUNTERS) else 1)
