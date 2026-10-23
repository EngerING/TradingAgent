"""Explicit foreground entrypoint. Does not issue grants or infer broker permissions."""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json

from trading_agent.core_v3.contracts import require, ContractError
from trading_agent.core_v3.economic_contracts import _hash
from trading_agent.core_v3.historical_ingestion.contracts import Record
from trading_agent.core_v3.historical_ingestion.files import safe_path, read_local
from trading_agent.core_v3.market_observation.authorization import Grant, Approval
from trading_agent.core_v3.market_observation.contracts import Origin
from .authorization import DataPermit, DataApproval
from .contracts import CollectorConfig
from .archive import Archive
from .supervisor import Supervisor, Health


@dataclass(frozen=True, slots=True)
class Signatures(Record):
    SCHEMA = 'trading.m03a.host_signatures'
    capture_signature: str
    data_signature: str

    def __post_init__(self):
        self.check_types()
        _hash(self.capture_signature)
        _hash(self.data_signature)


def main(argv=None):
    parser = argparse.ArgumentParser(description='M03-A foreground collector; OFFLINE by default, always NO_TRADE')
    parser.add_argument('--approved-data-only', action='store_true')
    parser.add_argument('--approval-directory')
    parser.add_argument('--archive-directory')
    args = parser.parse_args(argv)
    if not args.approved_data_only:
        print(json.dumps(asdict(Health('DISABLED',0,0))))
        return 0
    try:
        require(bool(args.approval_directory) and bool(args.archive_directory), 'M03_LOCAL_INPUTS_REQUIRED')
        root = safe_path(args.approval_directory)
        config = CollectorConfig.from_json(read_local(root,'config.json',max_bytes=4096).decode('utf-8'))
        grant = Grant.from_json(read_local(root,'capture-grant.json',max_bytes=4096).decode('utf-8'))
        permit = DataPermit.from_json(read_local(root,'data-permit.json',max_bytes=4096).decode('utf-8'))
        signatures = Signatures.from_json(read_local(root,'signatures.json',max_bytes=4096).decode('utf-8'))
        key = read_local(root,'verification.key',max_bytes=128)
        cap = Approval(grant,signatures.capture_signature,key,enabled=config.enabled)
        approval = DataApproval(cap,permit,signatures.data_signature,key)
        approval.verify(config,datetime.now(timezone.utc))
        directory = safe_path(args.archive_directory)
        if not directory.exists(): directory.mkdir(mode=0o700)
        create = not tuple(directory.iterdir())
        with Archive(directory,config,grant.session_id,Origin.SOCKET,grant.session_kind,create=create) as archive:
            result = Supervisor(archive,approval).run()
        print(json.dumps(asdict(result)))
        return 0 if result.code in ('STOPPED','RUN_DEADLINE','SEGMENT_BUDGET') else 1
    except (ContractError,OSError,UnicodeError):
        print(json.dumps(asdict(Health('LOCAL_APPROVAL_OR_STORAGE_REJECTED',0,0))))
        return 1


if __name__ == '__main__': raise SystemExit(main())
