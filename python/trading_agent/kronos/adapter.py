"""Audited upstream code + safetensors only. No Hub code or pickle execution."""
import hashlib
import json
import sys
import time
from pathlib import Path

def choose_device(torch, c):
    available = bool(torch.cuda.is_available())
    free = total = 0
    if available: free, total = torch.cuda.mem_get_info()
    use = c['device'] != 'cpu' and available and free >= c['minimum_free_vram_mb']*1024**2
    return dict(device='cuda:0' if use else 'cpu', dtype='float32', cuda_available=available,
                vram_free_mb=free/1024**2, vram_total_mb=total/1024**2)

class LocalKronosAdapter:
    def __init__(self, root, config):
        self.root, self.config = Path(root), config
        self.predictor = None; self.telemetry = {}; self.degraded = False; self.warmed = False

    def with_oom_fallback(self, torch, operation):
        try:return operation()
        except torch.cuda.OutOfMemoryError:
            self.predictor.model=self.predictor.model.cpu();self.predictor.tokenizer=self.predictor.tokenizer.cpu()
            self.predictor.device='cpu';self.telemetry['device']='cpu';self.telemetry['cpu_oom_fallback']=True;self.degraded=True;torch.cuda.empty_cache()
            return operation() # One CPU fallback; further failures propagate.

    def load(self):
        import torch
        from safetensors.torch import load_file
        started = time.perf_counter(); c = self.config
        vendor = self.root/'.local/kronos/upstream'
        manifest = json.loads((self.root/'config/kronos/upstream-lock.json').read_bytes())
        if manifest['commit'] != c['upstream_commit']: raise ValueError('UPSTREAM_COMMIT_MISMATCH')
        for file, sha in manifest['files'].items():
            if hashlib.sha256((vendor/file).read_bytes()).hexdigest() != sha: raise ValueError('UPSTREAM_CODE_HASH_MISMATCH')
        sys.path.insert(0, str(vendor))
        from model import Kronos, KronosTokenizer, KronosPredictor
        models = self.root/'.local/kronos/models'
        def weights(kind, version, cls):
            directory = models/kind/version
            pins = manifest['weights'][kind]
            if pins['revision'] != version: raise ValueError('MODEL_REVISION_MISMATCH')
            for filename, sha in pins['files'].items():
                if hashlib.sha256((directory/filename).read_bytes()).hexdigest() != sha: raise ValueError('MODEL_HASH_MISMATCH')
            args = json.loads((directory/'config.json').read_bytes())
            model = cls(**args)
            model.load_state_dict(load_file(str(directory/'model.safetensors'), device='cpu'), strict=True)
            return model.eval()
        model = weights('Kronos-base', c['model_version'], Kronos)
        tokenizer = weights('Kronos-Tokenizer-base', c['tokenizer_version'], KronosTokenizer)
        self.telemetry = choose_device(torch, c)
        try: self.predictor = KronosPredictor(model, tokenizer, device=self.telemetry['device'], max_context=512)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache(); self.degraded = True
            self.telemetry['device'] = 'cpu';self.telemetry['cpu_oom_fallback'] = True
            self.predictor = KronosPredictor(model.cpu(), tokenizer.cpu(), device='cpu', max_context=512)
        torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
        self.telemetry['load_seconds'] = time.perf_counter() - started

    def samples(self, request):
        import numpy as np
        import pandas as pd
        import torch
        from .features import future_timestamps
        if self.predictor is None: self.load()
        c = self.config; started = time.perf_counter(); paths = []
        frame = pd.DataFrame(request['bars'])[['open', 'high', 'low', 'close']].astype(float)
        if all(b.get('volume_evidence') == 'VERIFIED' for b in request['bars']):
            frame['volume'] = [b['volume'] for b in request['bars']]; frame['amount'] = [b['amount'] for b in request['bars']]
        x_ts = pd.Series(pd.to_datetime([b['opened_at'] for b in request['bars']], utc=True))
        y_ts = pd.Series(pd.to_datetime(future_timestamps(request, c), utc=True))
        if not self.warmed:
            warm=time.perf_counter()
            try:
                with torch.inference_mode():self.predictor.predict_batch([frame],[x_ts],[y_ts.iloc[:1]],1,T=c['temperature'],top_p=c['top_p'],sample_count=1,verbose=False)
            except torch.cuda.OutOfMemoryError:
                self.predictor.model=self.predictor.model.cpu();self.predictor.tokenizer=self.predictor.tokenizer.cpu();self.predictor.device='cpu'
                self.telemetry['device']='cpu';self.telemetry['cpu_oom_fallback']=True;self.degraded=True;torch.cuda.empty_cache()
            self.warmed=True;self.telemetry['warmup_seconds']=time.perf_counter()-warm
        torch.manual_seed(c['seed']); np.random.seed(c['seed'])
        def batch(n):
            # Official predict_batch with sample_count=1 retains every independent path.
            # Upstream sample_count>1 averages paths, which would destroy TP/SL evidence.
            with torch.inference_mode():
                result = self.predictor.predict_batch([frame]*n, [x_ts]*n, [y_ts]*n, c['pred_len'],
                        T=c['temperature'], top_p=c['top_p'], sample_count=1, verbose=False)
            return [[{k: float(row[k]) for k in ('open', 'high', 'low', 'close')} for _, row in df.iterrows()] for df in result]
        for i in range(0, c['sample_count'], c['batch_size']):
            n = min(c['batch_size'], c['sample_count']-i)
            paths.extend(self.with_oom_fallback(torch,lambda:batch(n)))
        self.telemetry['inference_seconds'] = time.perf_counter()-started
        self.telemetry['gpu_peak_memory_mb'] = torch.cuda.max_memory_allocated()/1024**2 if self.telemetry['device'].startswith('cuda') else 0
        return paths
