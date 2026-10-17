"""Allowlisted child processes with bounded runtime and stripped environments."""
import os
from pathlib import Path
import subprocess
import sys
from .contracts import encoded,strict_json


def worker_environment(root,provider=False):
    allowed=('SystemRoot','WINDIR','TEMP','TMP')
    env={k:os.environ[k] for k in allowed if k in os.environ}
    env['PYTHONPATH']=str(Path(root).resolve()/'python')
    env['PYTHONIOENCODING']='utf-8';env['PYTHONDONTWRITEBYTECODE']='1'
    if provider:
        key=os.environ.get('OPENAI_API_KEY')
        if not key:raise ValueError('OPENAI_API_KEY_REQUIRED')
        env['OPENAI_API_KEY']=key
    return env


def run_worker(root,kind,payload,timeout):
    if kind not in ('provider','simulation') or not 0<timeout<=120:raise ValueError('CONTROLLED_TOOL_REQUIRED')
    raw=encoded(payload)
    if len(raw)>12_000_000:raise ValueError('WORKER_PAYLOAD_TOO_LARGE')
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    try:
        r=subprocess.run([sys.executable,'-m','trading_agent.ai_strategy_researcher.worker',kind],
            cwd=Path(root).resolve(),env=worker_environment(root,kind=='provider'),input=raw,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout,creationflags=flags)
    except subprocess.TimeoutExpired:raise TimeoutError('CONTROLLED_WORKER_TIMEOUT') from None
    if r.returncode!=0 or len(r.stdout)>4_000_000:raise ValueError('CONTROLLED_WORKER_FAILED')
    result=strict_json(r.stdout)
    if result.get('worker_error'):raise ValueError('CONTROLLED_WORKER_FAILED')
    return result
