"""Read-only source inventory for the manual. Never connects to services."""
from pathlib import Path
import hashlib, json, re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXCLUDED = {'bin','obj','node_modules','__pycache__','dist','.venv','.git','ui-dist','test-results','playwright-report'}
EXTENSIONS = {'.py','.cs','.csproj','.sql','.ps1','.ts','.vue','.json','.html','.css','.props','.sln'}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def collect():
    files=[]
    for folder in ['src','python','scripts','config','contracts','frontend']:
        for p in sorted((ROOT/folder).rglob('*')):
            if not p.is_file() or any(x in EXCLUDED for x in p.relative_to(ROOT).parts) or p.suffix not in EXTENSIONS: continue
            # Inventory source and manifests, never secret directories or generated bundles.
            if p.name=='package-lock.json':
                files.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'inspection':'dependency-lock-inventory'});continue
            text=p.read_text(encoding='utf-8-sig')
            files.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'lines':len(text.splitlines()),
                          'inspection':'static-symbol-inventory',
                          'symbols':[{'line':n,'text':s.strip()[:180]} for n,s in enumerate(text.splitlines(),1)
                              if re.match(r'^(?:class |def |    def |public (?:sealed |static |partial )*(?:class|record|interface)|CREATE (?:TABLE|SCHEMA|VIEW)|app.Map(?:Get|Post|Delete|Hub))',s)]})
    for name in ['Directory.Build.props','TradingAgent.sln','README.md']:
        p=ROOT/name;files.append({'path':name,'sha256':sha(p),'inspection':'directed-read'})
    return files

def protected():
    base=ROOT/'artifacts/aggressive-growth-r20-20261010/r20-v2-phase3-20261014'
    result={}
    for name in ['protected-final.json','engine-final.json']:
        rows=json.loads((base/name).read_text(encoding='utf-8-sig'))
        checks=[]
        for r in rows:
            p=ROOT/r['path'];actual=sha(p) if p.is_file() else None
            checks.append({'path':r['path'].replace('\\','/'),'matches':actual==r['actual']})
        result[name]={'count':len(checks),'matches':sum(x['matches'] for x in checks),'files':checks}
    return result

if __name__=='__main__':
    import sys
    final='--final' in sys.argv
    data={'at_utc':datetime.now(timezone.utc).isoformat(),'method':'Static files; no service/DB/broker access',
          'files':collect(),'integrity':protected()}
    if final:
        before=json.loads((OUT/'source-audit.json').read_text(encoding='utf-8'))
        old={f['path']:f['sha256'] for f in before['files']};new={f['path']:f['sha256'] for f in data['files']}
        data['source_changes']=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    target=OUT/('integrity-final.json' if final else 'source-audit.json')
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(data['files']),'protected':{k:(v['matches'],v['count']) for k,v in data['integrity'].items()},'changes':data.get('source_changes')}))
