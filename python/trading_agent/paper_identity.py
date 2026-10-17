"""Discover a managed identity into Windows DPAPI storage, never authorize it.

Only a masked suffix is returned to the terminal. Operational authorization is
an independent manual step in scripts/paper-identity.ps1.
"""
import ctypes
from ctypes import wintypes
from datetime import datetime,timezone
import json
import logging
import os
from pathlib import Path
import re
from .broker import PaperOptions
from .tws import official_wire


def protect(data):
    if os.name!='nt':raise RuntimeError('WINDOWS_DPAPI_REQUIRED')
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    source=Blob(len(data),buffer);target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    crypt.CryptProtectData.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.POINTER(Blob),
        ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not crypt.CryptProtectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
        raise RuntimeError('DPAPI_PROTECTION_FAILED')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data,ctypes.c_void_p))


def discover(path,wire_factory=official_wire,sealer=protect,*,binding=None,configuration=None):
    if os.environ.get('LIVE_TRADING','false').lower()!='false':raise PermissionError('LIVE_DISABLED')
    logging.getLogger('ibapi').setLevel(logging.CRITICAL)
    from .ibkr_session import SessionConfiguration
    configuration=configuration or SessionConfiguration()
    wire=wire_factory(PaperOptions('',host=configuration.host,port=configuration.port,
        verified_tws_port=configuration.port,configured_endpoint=True),diagnostic=True)
    try:
        accounts=wire.connect()
        # No selection among linked accounts; even a second Paper identity fails closed.
        # Discovery records an opaque candidate; its prefix cannot prove Paper.
        if len(accounts)!=1 or not re.fullmatch(r'[A-Za-z0-9]{1,64}',accounts[0]):raise PermissionError('MANAGED_IDENTITY_REJECTED')
        if binding:binding.select(accounts)
        record={'schema_version':1,'account':accounts[0],'observed_at':datetime.now(timezone.utc).isoformat(),
            'server_version':wire.server_version,'host':configuration.host,'port':configuration.port,'authorized':False}
        sealed=sealer(json.dumps(record).encode('utf-8'))
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        # Replace atomically: failed discovery never leaves a partially written candidate.
        temporary=path.with_suffix('.tmp');temporary.write_bytes(sealed);temporary.replace(path)
        return {'masked_account':'***'+accounts[0][-4:],'handshake':True,'server_version':wire.server_version,
            'port':configuration.port,'authorized':False,'account_bound':binding is not None,
            'manual_paper_check_required':True,'manual_read_only_check_required':True}
    finally:wire.disconnect()


if __name__=='__main__':
    try:
        root=Path(__file__).resolve().parents[2]
        from .ibkr_session import AccountBinding,SessionConfiguration
        anchors=any((root/'.local'/n).exists() for n in ('ibkr-account-binding.dpapi','paper-lab-authorization.dpapi','ibkr-paper-authorized.dpapi'))
        binding=AccountBinding.load_or_migrate(root) if anchors else None
        print(json.dumps(discover(root/'.local/ibkr-paper-candidate.dpapi',binding=binding,configuration=SessionConfiguration.load(root))))
    except Exception:
        # Arbitrary exception text/tracebacks can contain identity data.
        print('PAPER_IDENTITY_DISCOVERY_FAILED',file=__import__('sys').stderr)
        raise SystemExit(1)
