"""Bounded synthetic process roles for the historical-backfill harness only."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO/'python'), str(REPO/'python/tests')]
import hashlib
import json
import os
import tempfile
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from core_v38_offline_check import guard, VIOLATIONS
from trading_agent.core_v3.contracts import ContractError
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind
from trading_agent.market_data.backfill.store import HistoricalStore, HistoricalConsumer
from trading_agent.market_data.backfill.reader import FixtureHistoricalReader
from test_m03a2_backfill import START, Clock, spec, permit, stream

MARKER = 'M03A2_SYNTHETIC_PROCESS_FIXTURE_V1'


def emit(value):
    raw = json.dumps(value)
    assert len(raw) < 4096
    print(raw, flush=True)


def command():
    raw = sys.stdin.readline(1025)
    assert raw.endswith('\n') and len(raw) <= 1024, 'M032_PROTOCOL_BOUND'
    value = json.loads(raw)
    assert type(value) is dict and set(value) == {'cmd'}
    return value['cmd']


def main():
    role, root = sys.argv[1], Path(sys.argv[2]).resolve()
    assert role in ('writer', 'reader', 'probe') and root.name == 'dataset' and root.is_dir()
    assert root.parent.name.startswith('m03a2-fixture-')
    assert root.parent.parent == Path(tempfile.gettempdir()).resolve()
    assert (root.parent/'owner.json').read_text() == MARKER
    def fixture_guard(event, args):
        guard(event, args)
        blocked = event == 'sqlite3.connect' and (role == 'reader' or Path(args[0]).resolve().parent != root/'capture')
        paths = []
        if event == 'open' and len(args) > 2 and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC): paths = args[:1]
        if event in ('os.remove', 'os.mkdir', 'os.rmdir'): paths = args[:1]
        if event in ('os.rename', 'os.link', 'os.symlink'): paths = args[:2]
        blocked |= bool(paths) and (role == 'reader' or any(root not in Path(p).resolve().parents for p in paths))
        if blocked:
            VIOLATIONS.append(event)
            raise AssertionError('M032_PROCESS_ROLE_BARRIER')
    sys.addaudithook(fixture_guard)
    s = replace(spec(), end=START+timedelta(days=1), timeframes=(15,))
    clock, store, requests = Clock(), None, 0
    try:
        if role != 'reader':
            try: store = HistoricalStore(root, s, 'session-1', Origin.FIXTURE, SessionKind.PAPER, create=not (root/'identity.json').exists())
            except ContractError:
                assert role == 'probe'
                emit({'phase':'WRITER_REJECTED'})
                return
            assert role == 'writer', 'SECOND_WRITER_ACQUIRED_LOCK'
        consumer = HistoricalConsumer(root, s, 'session-1', Origin.FIXTURE, SessionKind.PAPER)
        emit({'phase':'READY', 'role':role, 'barrier_violations':len(VIOLATIONS), 'samples':len(store.samples) if store else 0,
              'pending':len(store.pending()) if store else 0})
        while True:
            cmd = command()
            if cmd == 'stop': break
            if cmd == 'poll':
                assert role == 'reader'
                if not (root/'dataset.json').exists(): emit({'phase':'READ', 'status':'UNAVAILABLE', 'count':0}); continue
                first = consumer.read(15, START, s.end, as_of=clock.now()+timedelta(hours=1))
                digest = hashlib.sha256(first.dataset.to_json().encode()).hexdigest()
                values, cursor = list(first.bars), first.next_cursor
                while cursor:
                    page = consumer.read(15, START, s.end, as_of=clock.now()+timedelta(hours=1), cursor=cursor, snapshot=digest)
                    values.extend(page.bars); cursor = page.next_cursor
                assert len(values) == first.available_count == len({b.bar.opened_at for b in values}) == 96
                assert all(b.origin is Origin.FIXTURE for b in values)
                emit({'phase':'READ', 'status':first.dataset.status, 'count':len(values), 'snapshot':digest})
                continue
            assert role == 'writer' and cmd in ('capture', 'capture-pause', 'publish', 'publish-pause')
            original = os.replace
            def paused(source, target):
                if Path(target) == root/'dataset.json':
                    emit({'phase':'PAUSED', 'barrier_violations':len(VIOLATIONS), 'samples':len(store.samples), 'events':store.archive.checkpoint().sequence})
                    assert command() == 'release'
                return original(source, target)
            with patch('trading_agent.market_data.backfill.store.os.replace', paused if cmd.endswith('pause') else original):
                if cmd.startswith('capture'):
                    reader = FixtureHistoricalReader(stream(s), s, permit(s, clock), store,
                        now=clock.now, mono=clock.mono, wait=clock.wait)
                    iterator = reader.events()
                    try:
                        store.archive.rotate(clock.now())
                        for event in iterator: assert store.append(event, as_of=clock.now()).value.accepted
                    finally: iterator.close(); reader.close()
                    requests += reader.sent_opcodes.count(20)
                else:
                    clock.wait(1)
                    store.publish(clock.now())
            emit({'phase':'COMMITTED', 'samples':len(store.samples), 'requests':requests})
    finally:
        if store: store.close()
        emit({'phase':'CLOSED', 'barrier_violations':len(VIOLATIONS)})


if __name__ == '__main__': main()
