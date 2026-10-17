"""Read-only broker port and Paper gate. The domain never sees an IB order object."""
from dataclasses import dataclass
import hashlib
import logging
import re
import time

log=logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperOptions:
    account: str
    host: str = '127.0.0.1'
    port: int = 7497
    verified_tws_port: int = 7497
    paper_mode_attested: bool = False
    environment: str = 'PAPER_TRADING'
    live_enabled: bool = False
    client_id: int = 73
    timeout: float = 10
    read_only: bool = True
    configured_endpoint: bool = False

    def validate(self):
        if self.live_enabled or self.environment != 'PAPER_TRADING' or not self.read_only:
            raise PermissionError('LIVE_DISABLED')
        if self.host not in ('127.0.0.1','::1') or self.port != self.verified_tws_port or not 1<=self.port<=65535 or (not self.configured_endpoint and self.port!=7497):
            raise PermissionError('UNVERIFIED_TWS_PORT')
        # Syntax is not evidence of Paper mode; attestation and exact managed-account matching remain mandatory.
        if not self.paper_mode_attested or not re.fullmatch(r'DU(?:R)?[0-9]+',self.account) or self.client_id < 1 or not 0 < self.timeout <= 30:
            raise PermissionError('PAPER_IDENTITY_NOT_ATTESTED')

    @property
    def internal_id(self):
        return 'PAPER-' + hashlib.sha256(self.account.encode()).hexdigest()[:16]


class PaperDataBroker:
    def __init__(self, options, wire_factory, sleeper=time.sleep):
        self.options, self.factory, self.sleeper = options, wire_factory, sleeper
        self.wire = None
        self.verified = False

    @property
    def connected(self):
        return self.verified and self.wire is not None and self.wire.connected

    def connect(self, attempts=3):
        self.options.validate()
        self.disconnect()
        for attempt in range(min(max(attempts,1),3)):
            try:
                self.wire = self.factory(self.options)
                accounts = self.wire.connect()
                # The trusted local TWS session must expose exactly the authorized paper account.
                if set(accounts) != {self.options.account}:
                    raise PermissionError('UNAUTHORIZED_ACCOUNT')
                self.verified = True
                log.info('broker_connected',extra={'mode':'PAPER_TRADING','port':self.options.port})
                return
            except PermissionError:
                self.disconnect()
                raise
            except (ConnectionError,TimeoutError,OSError):
                self.disconnect()
                log.warning('broker_connection_failed',extra={'attempt':attempt+1})
                if attempt+1 == min(max(attempts,1),3):
                    raise
                self.sleeper(0.25 * 2**attempt)

    def disconnect(self):
        self.verified=False
        if self.wire:
            self.wire.disconnect()
            self.wire=None

    def _read(self, method, *args):
        if not self.connected:
            self.verified=False
            raise ConnectionError('BROKER_DISCONNECTED')
        try:
            return getattr(self.wire,method)(*args)
        except (ConnectionError,TimeoutError,OSError):
            self.disconnect()
            raise

    def balance(self): return self._read('balance')
    def positions(self): return self._read('positions')
    def contract_details(self, instrument='EUR/USD'): return self._read('contract_details',instrument)
    def quote(self, instrument='EUR/USD'): return self._read('quote',instrument)
    def history(self, instrument='EUR/USD', minutes=15, days=7):
        if minutes not in (15,60,240) or not 1<=days<=30:raise ValueError('Unsupported timeframe/range')
        # Keep the existing two-argument transport contract for the default window.
        return self._read('history',instrument,minutes) if days==7 else self._read('history',instrument,minutes,days)
