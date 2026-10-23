"""Foreground, default-disabled entrypoint. Never provisions operational approvals."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json

from trading_agent.core_v3.contracts import require, ContractError
from trading_agent.core_v3.economic_contracts import _hash
from trading_agent.core_v3.historical_ingestion.contracts import Record
from trading_agent.core_v3.historical_ingestion.files import safe_path, read_local
from trading_agent.core_v3.market_observation.authorization import Grant, Approval
from trading_agent.core_v3.market_observation.contracts import Origin
from .contracts import BackfillSpec, HistoricalPermit, HistoricalApproval
from .store import HistoricalStore
from .reader import HistoricalReader, collect


@dataclass(frozen=True, slots=True)
class Signatures(Record):
    SCHEMA='trading.m03a2.host_signatures'
    capture_signature: str
    historical_signature: str

    def __post_init__(self):
        self.check_types();_hash(self.capture_signature);_hash(self.historical_signature)


def main(argv=None):
    parser=argparse.ArgumentParser(description='M03-A.2 historical DATA_ONLY; disabled by default')
    parser.add_argument('--approved-history-only',action='store_true')
    parser.add_argument('--approval-directory');parser.add_argument('--dataset-directory')
    args=parser.parse_args(argv)
    if not args.approved_history_only:
        print(json.dumps({'status':'DISABLED','mode':'OFFLINE','decision':'NO_TRADE','executionAuthorized':False}));return 0
    try:
        require(bool(args.approval_directory) and bool(args.dataset_directory),'M032_LOCAL_INPUTS')
        root=safe_path(args.approval_directory)
        spec=BackfillSpec.from_json(read_local(root,'spec.json',max_bytes=4096))
        grant=Grant.from_json(read_local(root,'capture-grant.json',max_bytes=4096))
        permit=HistoricalPermit.from_json(read_local(root,'historical-permit.json',max_bytes=4096))
        signatures=Signatures.from_json(read_local(root,'signatures.json',max_bytes=4096))
        key=read_local(root,'verification.key',max_bytes=128)
        approval=HistoricalApproval(Approval(grant,signatures.capture_signature,key,enabled=spec.enabled),
                                    permit,signatures.historical_signature,key)
        approval.verify(spec,datetime.now(timezone.utc))
        target=safe_path(args.dataset_directory)
        if not target.exists(): target.mkdir(mode=0o700)
        create=not tuple(target.iterdir())
        with HistoricalStore(target,spec,grant.session_id,Origin.SOCKET,grant.session_kind,create=create) as store:
            result=collect(HistoricalReader(spec,approval,store),store)
        print(json.dumps({'status':result.status,'market_state':result.market_state,'quality':result.quality,
                          'decision':'NO_TRADE','executionAuthorized':False}))
        return 0 if result.status=='HISTORICAL_COMPLETE' else 1
    except (ContractError,OSError,UnicodeError):
        print(json.dumps({'status':'LOCAL_APPROVAL_OR_STORAGE_REJECTED','decision':'NO_TRADE','executionAuthorized':False}))
        return 1


if __name__=='__main__': raise SystemExit(main())
