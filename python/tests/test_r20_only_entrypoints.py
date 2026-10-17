"""Launch isolated wrapper copies; never execute a broker-capable project runner."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BLOCKED = {
    'eurusd-shadow-research': ['Prepare', 'Run', 'Once'],
    'eurusd-paper-exploratory': ['Prepare', 'Authorize', 'Run', 'Once', 'ReviewEmergency'],
    'r10-price-risk': ['Prepare'],
    'eurusd-cost-aware-research': ['Search', 'Prepare', 'Run', 'Once'],
    'eurusd-paper-research': ['ForwardStep'],
}
ALLOWED = {
    'eurusd-shadow-research': ['Status', 'Stop', 'Comparison'],
    'eurusd-paper-exploratory': ['Inspect', 'Assess', 'RecoveryInspect', 'Status', 'AuthorizeRecovery', 'Recovery', 'Stop', 'Revoke'],
    'r10-price-risk': ['Assess', 'Status', 'Stop', 'PaperPlan', 'Run', 'Once'],
    'eurusd-cost-aware-research': ['Status', 'Stop'],
    'eurusd-paper-research': ['Backtest', 'Observe'],
}


class RetirementEntrypoints(unittest.TestCase):
    def test_missing_policy_stops_before_existing_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in BLOCKED:
                source = (ROOT / 'scripts' / (name + '.ps1')).read_text(encoding='utf-8-sig')
                prefix = source.split('Assert-R20OnlyLegacyAction', 1)[0]
                # Replace everything after loading the policy with a harmless
                # sentinel, so a failed load cannot reach real operational code.
                script = Path(folder) / (name + '.ps1')
                script.write_text(prefix + "'EXISTING_HANDLER_REACHED'\n", encoding='utf-8')
                result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-File', str(script),
                                         '-Action', BLOCKED[name][0]],
                                        capture_output=True, text=True, timeout=20)
                self.assertNotIn('EXISTING_HANDLER_REACHED', result.stdout, name)
                self.assertNotEqual(0, result.returncode, name)

    def test_real_wrappers_deny_before_secrets_prompts_or_connections(self):
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder) / 'scripts'
            scripts.mkdir()
            for name in BLOCKED:
                shutil.copyfile(ROOT / 'scripts' / (name + '.ps1'), scripts / (name + '.ps1'))
            helper = ROOT / 'scripts/r20-only-policy.ps1'
            if helper.exists():
                shutil.copyfile(helper, scripts / helper.name)
            # No .local, venv, config or DB helper is copied. A regression must
            # fail locally, never fall through to an operational command.
            lines = ["$ErrorActionPreference='Stop'"]
            for name, actions in BLOCKED.items():
                for action in actions:
                    lines.append(
                        f"try {{ & './scripts/{name}.ps1' -Action '{action}'; throw 'NOT_DENIED' }} "
                        f"catch {{ if ($_.Exception.Message -notlike 'LEGACY_OPERATION_RETIRED_R20_ONLY*') "
                        f"{{ throw '{name}/{action}: wrong rejection' }} }}")
            lines.append('exit 0')  # Caught expected throws leave PowerShell $? false.
            result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', '\n'.join(lines)],
                                    cwd=folder, capture_output=True, text=True, timeout=40)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(['scripts'], sorted(p.name for p in Path(folder).iterdir()))

    def test_read_and_recovery_policy_preserves_existing_authorization_boundary(self):
        helper = ROOT / 'scripts/r20-only-policy.ps1'
        self.assertTrue(helper.exists())
        lines = ["$ErrorActionPreference='Stop'", f". '{helper}'"]
        for name, actions in ALLOWED.items():
            for action in actions:
                lines.append(f"Assert-R20OnlyLegacyAction -Entry '{name}' -Action '{action}'")
        lines.append("'POLICY_ALLOWED_NO_OPERATION_EXECUTED'")
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', '\n'.join(lines)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('POLICY_ALLOWED_NO_OPERATION_EXECUTED', result.stdout)

    def test_unknown_entry_or_action_fails_closed(self):
        helper = ROOT / 'scripts/r20-only-policy.ps1'
        self.assertTrue(helper.exists())
        command = f"$ErrorActionPreference='Stop'; . '{helper}'\n"
        for entry, action in [('unknown', 'Run'), ('eurusd-shadow-research', 'FutureAction'), ('eurusd-shadow-research', 'run')]:
            command += (f"try {{ Assert-R20OnlyLegacyAction '{entry}' '{action}'; throw 'NOT_DENIED' }} "
                        "catch { if ($_.Exception.Message -notlike 'LEGACY_OPERATION_RETIRED_R20_ONLY*') { throw } }\n")
        command += 'exit 0\n'  # Only reached after all rejection assertions pass.
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':
    unittest.main()
