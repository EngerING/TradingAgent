"""Offline risk-profile CLI; no protected configuration or broker access."""
import json
import os
from pathlib import Path
import subprocess
import unittest


class PaperRiskProfileCommandTests(unittest.TestCase):
    def run_cli(self, arguments, payload):
        root = Path(__file__).resolve().parents[2]
        dll = root / 'src/TradingAgent.Api/bin/Debug/net9.0/TradingAgent.Api.dll'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('TRADING_', 'LIVE_TRADING'))}
        env['LIVE_TRADING'] = 'false'
        return subprocess.run(['dotnet', str(dll), *arguments], input=json.dumps(payload),
                              text=True, capture_output=True, cwd=root, env=env, timeout=30)

    def test_study_reports_inactive_and_never_requires_database(self):
        initial = self.run_cli(['--paper-lab-journal'], {'operation': 'strategy-initial'})
        self.assertEqual(0, initial.returncode, initial.stdout)
        account = json.loads(initial.stdout)
        at = account['at']
        request = dict(instrument='EUR/USD', side='BUY', bid=1.0999, ask=1.1001, stop=1.099,
                       quoteToAccountFx=1, multiplier=1, minQuantity=1, quantityStep=1,
                       marginRate=1, availableMargin=100, commissionFixedRoundTrip=4,
                       commissionPerUnitRoundTrip=0, slippagePerUnit=.0001, adverseGapPerUnit=.0002,
                       marketAt=at, execution=dict(source='synthetic-test', environment='PAPER_TRADING',
                       mode='ODD_LOT', at=at, openingCommission=2, closingCommission=2,
                       costsReliable=True, marginReliable=True, contractReliable=True, brokerPermitsEntry=True,
                       quoteStatus='LIVE', equivalentRealAccount=dict(minimumQuantity=1, quantityStep=1,
                       marginRate=1, maximumLeverage=1, instrumentPermitted=True,
                       executionModePermitted=True, accountEligible=True)))
        payload = dict(profile='PAPER_EXPERIMENTAL_10_PERCENT', account=account, request=request,
                       asOf=at, broker='IBKR', mode='StrategyPaper', liveEnabled=False)
        result = self.run_cli(['--paper-risk-profile-study'], payload)
        self.assertEqual(0, result.returncode, result.stdout)
        study = json.loads(result.stdout)
        self.assertFalse(study['active']); self.assertFalse(study['executionAuthorized'])
        self.assertFalse(study['liveEnabled']); self.assertEqual(10, study['operationCeiling'])
        self.assertEqual('WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY',study['continuationPolicy'])
        self.assertEqual(10, study['evaluation']['budget'])
        self.assertTrue(study['evaluation']['allowed'])
        payload['mode'] = 'ExecutionDiagnostics'
        blocked = self.run_cli(['--paper-risk-profile-study'], payload)
        self.assertNotEqual(0, blocked.returncode)
        self.assertEqual('PAPER_PROFILE_STUDY_FAILED', json.loads(blocked.stdout)['error'])

    def test_runtime_commands_reject_experimental_ledger_without_activation(self):
        result=self.run_cli(['--paper-lab-journal'],{'operation':'strategy-initial'})
        account=json.loads(result.stdout)
        account['policyVersion']='PAPER_EXPERIMENTAL_10_PERCENT'
        for operation in ('strategy-mark','strategy-settle','strategy-risk'):
            result=self.run_cli(['--paper-lab-journal'],dict(operation=operation,account=account,net=4,fees=4))
            self.assertNotEqual(0,result.returncode)
            self.assertEqual('LAB_COMMAND_FAILED',json.loads(result.stdout)['error'])

    def test_incomplete_and_extra_fields_cannot_activate_profile(self):
        for payload in ({}, {'activate': True}, {'account': None, 'request': None}):
            result = self.run_cli(['--paper-risk-profile-study'], payload)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(json.loads(result.stdout)['executionAuthorized'])
