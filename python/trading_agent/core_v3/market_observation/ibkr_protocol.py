"""Independent, fail-closed legacy 157 market wire grammar, without a general SDK."""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import struct

from ..contracts import require, ContractError, parse_decimal
from .contracts import ContractIdentity, Kind, DataType


class Command(Enum):
    SUBSCRIBE = 1
    CANCEL = 2
    CONTRACT = 9
    ACCOUNTS = 17
    TIME = 49
    DATA_TYPE = 59
    START = 71


def handshake():
    version = b'v157..157'
    return b'API\0'+struct.pack('!I', len(version))+version


def encode(command, *, request_id=101, con_id=0, client_id=39):
    require(type(command) is Command, 'OBS_COMMAND_DENIED')
    require(all(type(v) is int and 0 <= v < 2**31 for v in (request_id, con_id, client_id)), 'OBS_COMMAND_ARGUMENT')
    instrument = [con_id, 'EUR', 'CASH', '', '0.0', '', '', 'IDEALPRO', '', 'USD', '', '']
    values = {
        Command.START: [71, 2, client_id, ''], Command.TIME: [49, 1],
        Command.ACCOUNTS: [17, 1], Command.DATA_TYPE: [59, 1, 1], Command.CANCEL: [2, 2, request_id],
        Command.CONTRACT: [9, 8, request_id]+instrument+[0, '', ''],
        Command.SUBSCRIBE: [1, 11, request_id]+instrument+[0, '', 0, 0, ''],
    }[command]
    require(command is not Command.SUBSCRIBE or con_id > 0, 'OBS_CONTRACT_UNVERIFIED')
    payload = ('\0'.join(map(str, values))+'\0').encode('ascii')
    return struct.pack('!I', len(payload))+payload


def fields(payload, max_bytes=16384):
    require(type(payload) is bytes and 0 < len(payload) <= max_bytes and payload.endswith(b'\0'), 'OBS_FRAME')
    try:
        values = payload[:-1].decode('ascii').split('\0')
    except UnicodeError:
        raise ContractError('OBS_FRAME_ENCODING') from None
    require(1 <= len(values) <= 256 and values[0].isdigit(), 'OBS_FRAME_FIELDS')
    return values


@dataclass(frozen=True, slots=True)
class Decoded:
    kind: Kind = Kind.NOTICE
    request_id: int = -1
    price_text: str | None = None
    tick_type: int | None = None
    data_type: DataType | None = None
    contract: ContractIdentity | None = None
    diagnostic: str = ''
    redacted: bool = False
    accounts: str | None = None
    details_end: bool = False


def decode(payload, max_bytes=16384):
    f = fields(payload, max_bytes)
    try:
        code = int(f[0])
        if code == 1:
            require(len(f) == 7 and int(f[1]) in (6,), 'OBS_TICK_LAYOUT')
            tick, request_id = int(f[3]), int(f[2])
            kind = Kind.BID if tick in (1,66) else Kind.ASK if tick in (2,67) else Kind.NOTICE
            require(len(f[4]) <= 128, 'OBS_PRICE_LENGTH')
            return Decoded(kind, request_id, f[4] if kind is not Kind.NOTICE else None,
                           tick, diagnostic='' if kind is not Kind.NOTICE else 'UNUSED_TICK')
        if code == 58:
            require(len(f) == 4 and f[1] == '1', 'OBS_TYPE_LAYOUT')
            types = {1:DataType.LIVE,2:DataType.FROZEN,3:DataType.DELAYED,4:DataType.DELAYED_FROZEN}
            require(int(f[3]) in types, 'OBS_TYPE_UNKNOWN')
            return Decoded(Kind.DATA_TYPE, int(f[2]), data_type=types[int(f[3])])
        if code == 15:
            require(len(f) == 3 and f[1] == '1', 'OBS_ACCOUNT_LAYOUT')
            return Decoded(accounts=f[2], diagnostic='ACCOUNT_IDENTITY_REDACTED', redacted=True)
        if code == 52:
            require(len(f) == 3 and f[1] == '1', 'OBS_DETAILS_END_LAYOUT')
            return Decoded(request_id=int(f[2]), details_end=True, diagnostic='CONTRACT_DETAILS_END')
        if code == 10:
            require(len(f) >= 39 and f[1] == '8' and int(f[32]) >= 0 and len(f) == 39+2*int(f[32]), 'OBS_DETAILS_LAYOUT')
            require('IDEALPRO' in f[18].split(','), 'OBS_CONTRACT_VENUE')
            contract = ContractIdentity(int(f[13]), f[3], f[4], f[9], f[8], parse_decimal(f[14]), hashlib.sha256(payload).hexdigest())
            return Decoded(Kind.CONTRACT, int(f[2]), contract=contract)
        if code == 4:
            require(len(f) == 5 and f[1] == '2', 'OBS_ERROR_LAYOUT')
            error = int(f[3])
            # Connectivity, farms and entitlements invalidate even while TCP stays open.
            gap = error in (1100,1101,1102,1300,2103,2108,354,10167,10168,10186)
            return Decoded(Kind.GAP if gap else Kind.NOTICE, int(f[2]),
                           diagnostic='IBKR_ERROR_'+str(abs(error)), redacted=True)
        if code in (2,45,46,47,57):
            return Decoded(diagnostic='UNUSED_MARKET_CALLBACK')
        if code in (9,49):
            require(len(f) == 3 and f[1] == '1', 'OBS_HANDSHAKE_CALLBACK')
            return Decoded(diagnostic='HANDSHAKE_CALLBACK', redacted=True)
        return Decoded(Kind.GAP, diagnostic='UNSUPPORTED_CALLBACK', redacted=True)
    except (ValueError, IndexError, OverflowError):
        raise ContractError('OBS_PROTOCOL_INVALID') from None
