"""PowerShell/DPAPI registration in an isolated fixture root; no real TWS, grants or orders."""
import copy
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from trading_agent.paper_lab import unseal
from test_paper_lab import grant


class ProtectedExceptionRegistrationTests(unittest.TestCase):
    def run_registration(self,minutes=15,*,strategy=False):
        base=Path(__file__).resolve().parents[2];temporary=tempfile.TemporaryDirectory(dir=base/'artifacts')
        self.addCleanup(temporary.cleanup);root=Path(temporary.name);(root/'scripts').mkdir();(root/'.local').mkdir()
        (root/'scripts/paper-lab.ps1').write_bytes((base/'scripts/paper-lab.ps1').read_bytes())
        # Mock only the new identity/config collaborator. The real registration,
        # owner consent, DPAPI and immutable grant/emergency assertions remain.
        (root/'scripts/ibkr-session.ps1').write_text(r'''
$transport=[pscustomobject]@{host='127.0.0.1';port=7497}
function Get-PaperAccountBinding {return (Get-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) '.local/fixture.json') -Raw | ConvertFrom-Json)}
''',encoding='utf-8')
        (root/'scripts/paper-identity.ps1').write_text(r'''
param($Action)
$root=Split-Path -Parent $PSScriptRoot
$record=Get-Content -LiteralPath (Join-Path $root '.local/fixture.json') -Raw | ConvertFrom-Json
$plain=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 10))
[IO.File]::WriteAllBytes((Join-Path $root '.local/ibkr-paper-candidate.dpapi'),[Security.Cryptography.ProtectedData]::Protect($plain,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser))
''',encoding='utf-8')
        a=copy.deepcopy(grant());a['tws_pid']=1;a['tws_start_filetime']='1'
        (root/'.local/fixture.json').write_text(json.dumps(a),encoding='utf-8')
        if strategy:
            from test_strategy_continuous import plan
            from trading_agent.paper_lab import utc
            evidence=plan(utc());evidence['strategy_version']='d'*64
            (root/'.local/strategy-plan.json').write_text(json.dumps(evidence),encoding='utf-8')
            (root/'.venv/Scripts').mkdir(parents=True)
            shutil.copy2(base/'.venv/Scripts/python.exe',root/'.venv/Scripts/python.exe')
            shutil.copy2(base/'.venv/pyvenv.cfg',root/'.venv/pyvenv.cfg')
            shutil.copytree(base/'python/trading_agent',root/'python/trading_agent',ignore=shutil.ignore_patterns('__pycache__'))
            import tzdata
            shutil.copytree(Path(tzdata.__file__).parent,root/'python/tzdata',ignore=shutil.ignore_patterns('__pycache__'))
        script=r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Security
$root=$env:TEST_LAB_ROOT
$record=Get-Content -LiteralPath (Join-Path $root '.local/fixture.json') -Raw | ConvertFrom-Json
$plain=[Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 10))
$path=Join-Path $root '.local/paper-lab-authorization.dpapi'
[IO.File]::WriteAllBytes($path,[Security.Cryptography.ProtectedData]::Protect($plain,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser))
$before=(Get-FileHash -LiteralPath $path).Hash
$marker=Join-Path $root '.local/paper-lab.emergency'
[IO.File]::WriteAllText($marker,'synthetic emergency remains latched')
function global:Get-Process {param($Id,[Parameter(ValueFromRemainingArguments=$true)]$rest) return [pscustomobject]@{Id=1;StartTime=[DateTime]::FromFileTimeUtc(1)}}
function global:Get-NetTCPConnection {param([Parameter(ValueFromRemainingArguments=$true)]$rest) return [pscustomobject]@{OwningProcess=1}}
function global:Read-Host {param($Prompt,[switch]$AsSecureString)
 if($AsSecureString){return (ConvertTo-SecureString 'DUR12345678' -AsPlainText -Force)}
 if($Prompt -like '*Paper y cuenta*'){return 'PAPER_IDENTITY_CHECKED'}
 if($Prompt -like '*sin fila EUR*'){return 'EUR_ROW_ABSENT'}
 return 'ACCEPT_INITIAL_EUR_UNCERTAINTY'
}
$extra=@{}
if($env:TEST_STRATEGY -ceq 'true'){$extra=@{Mode='StrategyPaper';RiskProfile='PAPER_EXPERIMENTAL_10_PERCENT';StrategyVersion=('d'*64);StrategyEvidencePath=(Join-Path $root '.local/strategy-plan.json')}}
& (Join-Path $root 'scripts/paper-lab.ps1') -Action AuthorizeEurAbsence -ExceptionMinutes ([int]$env:TEST_EXCEPTION_MINUTES) @extra
if((Get-FileHash -LiteralPath $path).Hash -cne $before){throw 'FIXTURE_EXECUTION_GRANT_CHANGED'}
if([IO.File]::ReadAllText($marker) -cne 'synthetic emergency remains latched'){throw 'FIXTURE_EMERGENCY_CHANGED'}
'''
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',script],env={**os.environ,'TEST_LAB_ROOT':str(root),'TEST_EXCEPTION_MINUTES':str(minutes),'TEST_STRATEGY':str(strategy).lower()},capture_output=True,text=True,timeout=20)
        return root,result
    def test_manual_registration_is_separate_protected_and_never_renews_or_clears(self):
        root,result=self.run_registration()
        self.assertEqual(0,result.returncode,result.stderr)
        e=unseal(root/'.local/paper-lab-eur-exception.dpapi')
        self.assertTrue(e['manual_uncertainty_accepted']);self.assertEqual('EUR_ROW_ABSENT',e['observed_state'])
        self.assertNotIn('eur_balance',e);self.assertEqual(10,e['diagnostic_loss_budget'])
        self.assertNotIn('DUR12345678',result.stdout+result.stderr)
        a=unseal(root/'.local/paper-lab-authorization.dpapi');self.assertEqual(grant()['expires_at'],a['expires_at'])
    def test_longer_than_thirty_minutes_is_rejected_without_creating_exception(self):
        root,result=self.run_registration(31)
        self.assertNotEqual(0,result.returncode);self.assertFalse((root/'.local/paper-lab-eur-exception.dpapi').exists())
    def test_strategy_registration_seals_exact_plan_and_future_session_without_renewing_grant(self):
        from trading_agent.paper_eur_reconciliation import AbsentEurAuthorization
        from trading_agent.research_analysis import digest
        root,result=self.run_registration(strategy=True);self.assertEqual(0,result.returncode,result.stderr)
        e=unseal(root/'.local/paper-lab-eur-exception.dpapi');a=unseal(root/'.local/paper-lab-authorization.dpapi')
        self.assertEqual('INITIAL_STRATEGY_PAPER_EUR_ABSENCE',e['scope']);self.assertEqual('d'*64,e['strategy_version'])
        evidence=json.loads((root/'.local/strategy-plan.json').read_text());self.assertEqual(digest(evidence),e['plan_hash'])
        self.assertEqual(a['session_id'],e['review_session_id']);self.assertNotEqual(a['session_id'],e['execution_session_id'])
        self.assertEqual(e,AbsentEurAuthorization(lambda:e).read(a,for_review=True))
        with self.assertRaises(PermissionError):AbsentEurAuthorization(lambda:e).read(a)
