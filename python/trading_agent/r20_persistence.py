"""R20 V2 accounting persistence prototype. Restricted to a named TEST cluster.

No cohorts, market readers, order transport or operational database configuration.
psql is the existing local PostgreSQL dependency; each mutation is one transaction.
"""
import base64
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import subprocess

from .r20_profiles import EconomicProfile, decimal_text, encoded, strict_json
from .r20_economics import Cost, DailyState, equity, identity, signed, unique

TEST_SYSTEM_ID = '7692346685552779632'
PSQL = Path(r'C:\Program Files\PostgreSQL\17\bin\psql.exe')


@dataclass(frozen=True)
class Snapshot:
    profile: EconomicProfile
    daily: DailyState
    realized_gross: Decimal
    open_gross: tuple[tuple[str, Decimal], ...]
    costs: tuple[Cost, ...]
    evidence: str

    def __post_init__(self):
        if not isinstance(self.profile,EconomicProfile) or not isinstance(self.daily,DailyState):
            raise ValueError('TYPED_SNAPSHOT_REQUIRED')
        if (self.daily.profile_hash!=self.profile.configuration_hash or
            self.daily.profile_version!=self.profile.configuration_version or
            self.daily.scope_id!=self.profile.scope_id): raise ValueError('PROFILE_MISMATCH')
        if not self.profile.scope_id.startswith('r20-v2-test-ledger-'):
            raise ValueError('TEST_LEDGER_REQUIRED')
        signed(self.realized_gross)
        if not isinstance(self.open_gross,tuple) or not isinstance(self.costs,tuple):
            raise ValueError('IMMUTABLE_SNAPSHOT_REQUIRED')
        for item in self.open_gross:
            if not isinstance(item,tuple) or len(item)!=2: raise ValueError('OPEN_PNL_REQUIRED')
            identity(item[0]); signed(item[1])
        unique([i for i,_ in self.open_gross])
        if any(not isinstance(c,Cost) for c in self.costs): raise ValueError('COST_REQUIRED')
        if self.daily.inventory_verified and {i for i,_ in self.open_gross}!={x.position_id for x in self.daily.open_terms}:
            raise ValueError('OPEN_INVENTORY_MISMATCH')
        value=equity(self.profile.capital_base_usd,self.realized_gross,
                     tuple(v for _,v in self.open_gross),self.costs)
        if value.economic!=self.daily.current_equity: raise ValueError('EQUITY_MISMATCH')
        if self.daily.entry_profile_valid!=self.profile.valid_at(self.daily.at):
            raise ValueError('PROFILE_VALIDITY_MISMATCH')
        if not isinstance(self.evidence,str) or not 0<len(self.evidence.strip())<=2000:
            raise ValueError('SNAPSHOT_EVIDENCE_REQUIRED')

    def to_json(self):
        return encoded(dict(format='R20_V2_TEST_ACCOUNTING_V1',
            profile=strict_json(self.profile.to_json()),daily=strict_json(self.daily.to_json()),
            realized_gross=self.realized_gross,open_gross=self.open_gross,
            costs=[asdict(c) for c in self.costs],evidence=self.evidence))

    @classmethod
    def from_json(cls,text):
        obj=strict_json(text)
        if not isinstance(obj,dict) or set(obj)!=set(f.name for f in fields(cls))|{'format'}:
            raise ValueError('SNAPSHOT_FIELDS_INVALID')
        if obj.pop('format')!='R20_V2_TEST_ACCOUNTING_V1': raise ValueError('SNAPSHOT_FORMAT')
        costs=[]
        for row in obj['costs']:
            if not isinstance(row,dict) or set(row)!={f.name for f in fields(Cost)}:
                raise ValueError('COST_FIELDS_INVALID')
            costs.append(Cost(**dict(row,amount=decimal_text(row['amount']))))
        return cls(EconomicProfile.from_json(encoded(obj['profile'])),
                   DailyState.from_json(encoded(obj['daily'])),decimal_text(obj['realized_gross']),
                   tuple((i,decimal_text(v)) for i,v in obj['open_gross']),tuple(costs),obj['evidence'])


def transition(previous,current):
    """Conservative persistence boundary; clearing global blocks has no API here."""
    a,b=previous.daily,current.daily
    if previous.profile.capital_base_usd!=current.profile.capital_base_usd:
        raise ValueError('CAPITAL_BASE_IMMUTABLE')
    if not set(a.operational_blocks)<=set(b.operational_blocks):
        raise ValueError('OPERATIONAL_BLOCK_REMOVED')
    if b.day_id==a.day_id:
        expected=a.observe(current.profile,b.at,b.current_equity,b.open_terms,b.pending_terms)
        # An unverified new day may be saved unchanged before its first observation.
        if b==a and current.profile==previous.profile: expected=a
        # Configuration-only commits can tighten a day's budget before the next
        # accounting observation. Additional tightening cannot restore capacity.
        if ((expected.reference,expected.eligible_base,expected.inventory_verified,expected.entry_profile_valid)!=(
            b.reference,b.eligible_base,b.inventory_verified,b.entry_profile_valid) or b.budget>expected.budget
        or (expected.loss_blocked and not b.loss_blocked)): raise ValueError('DAILY_TRANSITION')
    else:
        verified=not ('ECONOMIC_BOUNDARY_UNVERIFIED' in b.operational_blocks and b.reference==a.reference
                      and b.budget==a.budget)
        expected=(a.management_day(current.profile,b.reference,b.at,boundary_verified=verified)
                  if current.profile==previous.profile and not b.entry_profile_valid
                  else a.next_day(current.profile,b.reference,b.at,boundary_verified=True))
        if (expected.reference,expected.eligible_base,expected.budget,expected.loss_blocked,
            expected.open_terms,expected.pending_terms,expected.inventory_verified)!=(b.reference,b.eligible_base,
            b.budget,b.loss_blocked,b.open_terms,b.pending_terms,b.inventory_verified): raise ValueError('DAILY_TRANSITION')
    old={c.cost_id:c for c in previous.costs}; new={c.cost_id:c for c in current.costs}
    rank={'RESERVED':0,'ACCRUED':1,'SETTLED':2}
    for key,cost in old.items():
        replacement=new.get(key)
        # Pending estimates can be released. Recognized expenses cannot disappear.
        if cost.status=='RESERVED' and replacement is None: continue
        if (replacement is None or rank[replacement.status]<rank[cost.status]
            or (cost.status=='SETTLED' and replacement!=cost)
            or (cost.status=='ACCRUED' and replacement.amount!=cost.amount)):
            raise ValueError('COST_HISTORY')


def chain_hash(previous,revision,request,payload):
    return hashlib.sha256(f'{previous}\n{revision}\n{request}\n{payload}'.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class Head:
    revision: int
    hash: str
    snapshot: Snapshot


def sql_text(text):
    # Base64 alphabet cannot terminate this SQL literal; no shell interpolation.
    value=base64.b64encode(text.encode('utf-8')).decode('ascii')
    return f"convert_from(decode('{value}','base64'),'UTF8')"


class TestStore:
    def __init__(self,database,system_id):
        if (not isinstance(database,str) or not re.fullmatch('r20_v2_test_[a-f0-9]{32}',database)
            or system_id!=TEST_SYSTEM_ID): raise ValueError('ISOLATED_TEST_TARGET_REQUIRED')
        self.database,self.system_id=database,system_id

    def execute(self,sql):
        # Checks run in the SAME connection as the request, before any DDL/DML.
        guard=f"""DO $$ BEGIN
          IF current_database()<>'{self.database}' OR current_user<>'trading_test'
             OR inet_server_port()<>55432 OR inet_server_addr()<>'127.0.0.1'::inet
             OR (SELECT system_identifier::text FROM pg_control_system())<>'{self.system_id}'
          THEN RAISE EXCEPTION 'ISOLATED_TEST_TARGET_REQUIRED'; END IF;
        END $$;
        SET statement_timeout='15s'; SET lock_timeout='5s';
        """
        env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','TEMP','TMP')}
        result=subprocess.run([str(PSQL),'-X','-qAt','-v','ON_ERROR_STOP=1','-h','127.0.0.1',
            '-p','55432','-U','trading_test','-d',self.database],input=(guard+sql).encode('utf-8'),
            capture_output=True,env=env,timeout=25)
        # psql's localized diagnostic stream may use Windows' ANSI codepage.
        # Replacement is diagnostic-only; JSON/data stdout remains strict UTF-8.
        diagnostic=result.stderr.decode('utf-8',errors='replace')
        if result.returncode:
            for reason in ('CONFIG_CAS_CONFLICT','CAS_CONFLICT','IDEMPOTENCY_CONFLICT','PROFILE_VERSION_REUSED','SIGNAL_ALREADY_RESERVED'):
                if reason in diagnostic: raise ValueError(reason)
            raise RuntimeError('TEST_POSTGRES_REJECTED: '+diagnostic[:500])
        try:return result.stdout.decode('utf-8').strip()
        except UnicodeDecodeError as exc:raise RuntimeError('TEST_POSTGRES_INVALID_ENCODING') from exc

    def install(self):
        self.execute(Path(__file__).with_name('r20_test_schema.sql').read_text(encoding='utf-8'))

    def _rows(self,scope):
        identity(scope)
        rows=self.execute(f"""BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
          SELECT json_build_object('revision',e.revision,'previous',e.previous_hash,
          'hash',e.event_hash,'request',e.request_id,'payload',e.payload,'profile',p.payload)::text
          FROM r20_v2_test.events e LEFT JOIN r20_v2_test.profiles p
          ON p.scope_id=e.scope_id AND p.version=e.profile_version
          WHERE e.scope_id={sql_text(scope)} ORDER BY e.revision; COMMIT;""")
        return self.decode_rows(scope,[strict_json(line) for line in rows.splitlines()])

    @staticmethod
    def decode_rows(scope,rows):
        """Verify rows read by one transaction, including combined lab views."""
        previous=''; history=[]; prior=None
        for row in rows:
            revision=row['revision']; payload=row['payload']
            if (revision!=len(history)+1 or row['previous']!=previous or
                chain_hash(previous,revision,row['request'],payload)!=row['hash']):
                raise ValueError('CHAIN_INTEGRITY')
            s=Snapshot.from_json(payload)
            if s.profile.scope_id!=scope or s.profile.to_json()!=row['profile']:
                raise ValueError('PROFILE_INTEGRITY')
            if prior: transition(prior,s)
            history.append((row,Head(revision,row['hash'],s)))
            previous=row['hash']; prior=s
        return history

    def load(self,scope):
        history=self._rows(scope)
        return history[-1][1] if history else None

    def append(self,snapshot,request_id,expected_revision,previous_hash):
        if not isinstance(snapshot,Snapshot): raise ValueError('TYPED_SNAPSHOT_REQUIRED')
        identity(request_id)
        if type(expected_revision) is not int or expected_revision<0: raise ValueError('REVISION_REQUIRED')
        if not isinstance(previous_hash,str) or not re.fullmatch('(?:[a-f0-9]{64})?',previous_hash):
            raise ValueError('HASH_REQUIRED')
        payload=snapshot.to_json(); p=snapshot.profile; history=self._rows(p.scope_id)
        for row,head in history:
            if row['request']==request_id:
                if row['payload']!=payload: raise ValueError('IDEMPOTENCY_CONFLICT')
                return head
        head=history[-1][1] if history else None
        if (expected_revision,previous_hash)!=((head.revision,head.hash) if head else (0,'')):
            raise ValueError('CAS_CONFLICT')
        if head: transition(head.snapshot,snapshot)
        value=self.execute('SELECT r20_v2_test.append_state('+','.join((
            sql_text(p.scope_id),sql_text(request_id),str(expected_revision),sql_text(previous_hash),
            str(p.configuration_version),sql_text(p.configuration_hash),sql_text(p.to_json()),sql_text(payload)))+');')
        row=strict_json(value)
        return Head(row['revision'],row['hash'],snapshot)
