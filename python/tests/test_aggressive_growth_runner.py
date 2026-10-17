from copy import deepcopy
from datetime import timedelta
import json
import unittest
from unittest.mock import patch, Mock
from test_aggressive_growth import ROOT,AT,observation
from trading_agent.aggressive_growth import configuration,sha,encoded
from trading_agent.aggressive_growth_runner import Experiment,Journal,engine_hashes,wait_for_poll


class MemoryJournal:
    experiment='aggressive-r20-'+'a'*32
    def __init__(self):self.head=dict(revision=0,hash='',payload=None);self.fail=False
    def load(self):return deepcopy(self.head)
    def commit(self,revision,previous,payload):
        if previous!=self.head['hash'] or revision!=self.head['revision']+1:raise RuntimeError('CAS')
        self.head=dict(revision=revision,hash=sha([revision,payload,previous]),payload=encoded(payload).decode())
        if self.fail:raise RuntimeError('ACK_LOST')
        return deepcopy(self.head)


class RunnerTests(unittest.TestCase):
    def test_durable_stop_waits_between_failed_market_reads(self):
        elapsed=[0.0]; marker=Mock(); marker.exists.return_value=True
        def sleep(seconds): elapsed[0]+=seconds
        with patch('trading_agent.aggressive_growth_runner.time.monotonic',side_effect=lambda:elapsed[0]), patch('trading_agent.aggressive_growth_runner.time.sleep',side_effect=sleep):
            wait_for_poll(15,marker,stop_requested=True)
        self.assertEqual(15,elapsed[0])

    def test_new_stop_interrupts_poll_wait_before_it_is_acknowledged(self):
        marker=Mock();marker.exists.return_value=True
        with patch('trading_agent.aggressive_growth_runner.time.sleep') as sleep:
            wait_for_poll(15,marker,stop_requested=False)
        sleep.assert_not_called()

    def test_prepare_recovery_and_repeat_observation_are_idempotent(self):
        journal=MemoryJournal();e=Experiment(journal,lambda:AT+timedelta(seconds=1))
        e.prepare(configuration(ROOT),engine_hashes(ROOT));e.observe(observation())
        restored=Experiment(journal,lambda:AT+timedelta(seconds=1));restored.observe(observation())
        self.assertEqual(2,len(restored.state['seen']))
        self.assertEqual(e.state['portfolios']['R20']['active']['id'],restored.state['portfolios']['R20']['active']['id'])

    def test_uncertain_commit_invalidates_memory_then_reload(self):
        j=MemoryJournal();e=Experiment(j,lambda:AT);e.prepare(configuration(ROOT),engine_hashes(ROOT));j.fail=True
        with self.assertRaises(RuntimeError):e.observe(observation())
        self.assertIsNone(e.state)
        loaded=Experiment(j,lambda:AT)
        self.assertEqual(j.head['revision'],loaded.revision)

    def test_scope_blocks_traversal_and_live_env(self):
        with self.assertRaises(ValueError):Journal(ROOT,'../../bad')
        with patch.dict('os.environ',{'LIVE_TRADING':'true'}):
            with self.assertRaises(PermissionError):Journal(ROOT,MemoryJournal.experiment).load()

    def test_stop_durable_and_cannot_resume(self):
        j=MemoryJournal();e=Experiment(j,lambda:AT);e.prepare(configuration(ROOT),engine_hashes(ROOT));e.stop()
        loaded=Experiment(j,lambda:AT+timedelta(seconds=1));loaded.observe(observation())
        self.assertEqual('STOPPED',loaded.state['status'])
        self.assertIsNone(loaded.state['portfolios']['R20']['active'])


if __name__=='__main__':unittest.main()
