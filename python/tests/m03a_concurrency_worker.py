"""Closed synthetic subprocess protocol, used only by concurrency-check.py."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO/'python'),str(REPO/'python/tests')]

import json
import os
from dataclasses import replace
from unittest.mock import patch
from core_v38_offline_check import guard, VIOLATIONS
from trading_agent.core_v3.market_observation.contracts import Origin, SessionKind, Kind
from trading_agent.core_v3.market_observation.journal import Journal
from trading_agent.core_v3.contracts import ContractError
from trading_agent.market_data.archive import Archive
from trading_agent.market_data.consumer import Consumer
from trading_agent.market_data.reader import TranscriptReader
from trading_agent.market_data.publication import Publisher
from test_m03a_contracts import AT
from test_m03a_reader import config, permission, packets


def emit(value):
    print(json.dumps(value),flush=True)


def main():
    root = Path(sys.argv[2]).resolve()
    role = sys.argv[1]
    assert role in ('writer','reader') and root.is_dir() and root.name == 'capture'
    assert root.parent.name.startswith('m03a1-fixture-') and root.parent.parent == Path(__import__('tempfile').gettempdir()).resolve()
    def fixture_guard(event,args):
        guard(event,args)
        if event == 'sqlite3.connect':
            assert role == 'writer' and Path(args[0]).resolve().parent == root,'FIXTURE_SQLITE_ONLY'
        if event == 'open' and len(args) > 2 and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            assert role == 'writer' and Path(args[0]).resolve().parent == root,'FIXTURE_WRITES_ONLY'
    sys.addaudithook(fixture_guard)
    cfg = config(enabled=True)
    archive = None
    try:
        if role == 'writer':
            try:
                archive = Archive(root,cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER,create=not (root/'identity.json').exists())
            except ContractError:
                emit({'phase':'WRITER_REJECTED','barrier_violations':len(VIOLATIONS)})
                return
        reader = Consumer(root,cfg,'session-1',Origin.FIXTURE,SessionKind.PAPER)
        emit({'phase':'READY','role':role,'pid':os.getpid()})
        for command in sys.stdin:
            command = command.strip()
            assert command in ('capture','poll','rotate','rotate-pause','pause','stop','disconnect','refresh')
            if command == 'stop': break
            if command == 'poll':
                result = reader.poll(AT)
                view = result.observation
                emit({'phase':'READ','code':result.code,'cursor':result.cursor.to_dict() if result.cursor else None,
                      'quote':view.quote is not None if view else False,'ask':str(view.quote.ask) if view and view.quote else None,
                      'freshness':view.freshness if view else 'UNAVAILABLE','origin':view.origin.value if view else None})
                continue
            assert archive is not None
            if command == 'capture':
                source = TranscriptReader(packets(),cfg,permission(cfg),now=lambda:AT,mono=lambda:0)
                iterator = source.events()
                try:
                    for raw in iterator:
                        archive.append(raw,as_of=AT)
                        if raw.kind is Kind.ASK: break
                finally: iterator.close()
            elif command == 'rotate': archive.rotate(AT)
            elif command == 'rotate-pause':
                write = Publisher._write
                def during_rotation(publisher,name,data):
                    if name == 'consumer.json':
                        emit({'phase':'ROTATING'})
                        assert sys.stdin.readline().strip() == 'release'
                    return write(publisher,name,data)
                with patch.object(Publisher,'_write',during_rotation): archive.rotate(AT)
            elif command in ('pause','refresh','disconnect'):
                last = archive.history()[-1].value.event
                event = replace(last,sequence=last.sequence+1)
                if command == 'disconnect': event = replace(event,kind=Kind.DISCONNECTED,price_text=None)
                if command == 'pause':
                    event = replace(event,price_text='1.1003')
                    def paused(_):
                        emit({'phase':'PAUSED'})
                        assert sys.stdin.readline().strip() == 'release'
                    with patch.object(Journal,'_before_commit',paused): archive.append(event,as_of=AT)
                else: archive.append(event,as_of=AT)
            emit({'phase':'COMMITTED','segments':len(archive.segments),'folded':archive._projection.folded})
    finally:
        if archive: archive.close()
        emit({'phase':'CLOSED','barrier_violations':len(VIOLATIONS)})


if __name__ == '__main__': main()
