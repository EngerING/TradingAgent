"""Explicit public artifact download only; never imports or executes Hub code."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from .config import load

def install_models(root):
    from huggingface_hub import snapshot_download
    root=Path(root);c=load(root);lock_path=root/'config/kronos/upstream-lock.json';lock=json.loads(lock_path.read_bytes())
    vendor=root/'.local/kronos/upstream'
    commit=subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()
    if commit!=c['upstream_commit']:raise ValueError('PINNED_UPSTREAM_REQUIRED')
    for file,h in lock['files'].items():
        if hashlib.sha256((vendor/file).read_bytes()).hexdigest()!=h:raise ValueError('AUDITED_UPSTREAM_CHANGED')
    for kind,key in [('Kronos-base','model_version'),('Kronos-Tokenizer-base','tokenizer_version')]:
        version=c[key];directory=root/'.local/kronos/models'/kind/version
        snapshot_download('NeoQuasar/'+kind,revision=version,allow_patterns=['config.json','model.safetensors','README.md'],
            local_dir=str(directory),cache_dir=str(root/'.local/kronos/hf-cache'),token=False)
        files={f:hashlib.sha256((directory/f).read_bytes()).hexdigest() for f in ('config.json','model.safetensors','README.md')}
        prior=lock['weights'].get(kind)
        pin=dict(revision=version,files=files)
        if prior and prior!=pin:raise ValueError('PUBLIC_MODEL_ARTIFACT_CONFLICT')
        lock['weights'][kind]=pin
    lock_path.write_text(json.dumps(lock,indent=2),encoding='utf-8')
    print(json.dumps(dict(downloaded=True,commit=commit,weights=lock['weights'],remote_code_executed=False)))

if __name__=='__main__':install_models(Path(sys.argv[1]) if len(sys.argv)>1 else Path('.'))
