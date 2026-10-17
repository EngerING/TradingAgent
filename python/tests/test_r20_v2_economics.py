"""Synthetic, isolated arithmetic. No runner, DB or execution calls."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, localcontext
import json
import unittest

from test_r20_v2_profiles import AT, profile
from trading_agent.r20_economics import Cost, equity, OpenRisk, PendingRisk, DailyState


class AccountingTests(unittest.TestCase):
    def test_compounding_and_optional_explicit_cap(self):
        result=equity(D('100'),D('30'),(D('0'),),
                      (Cost('fee',D('5'),'SETTLED','BROKER_CONFIRMED','test-only'),))
        self.assertEqual(D('125'),result.economic)
        self.assertEqual(D('125'),result.eligible())
        self.assertEqual(D('110'),result.eligible(cap=D('110')))
        self.assertEqual(D('122'),result.eligible(pending=D('3')))

    def test_cost_migration_not_double_discount(self):
        for status,source in [('RESERVED','ESTIMATED'),('ACCRUED','BROKER_CONFIRMED'),
                              ('SETTLED','BROKER_CONFIRMED')]:
            value=equity(D('100'),D('0'),(D('2'),D('-1')),
                         (Cost('one-fee',D('4'),status,source,'test-only'),))
            self.assertEqual(D('97'),value.economic)
        actual=equity(D('100'),D('0'),(D('1'),),
                      (Cost('one-fee',D('5'),'SETTLED','BROKER_CONFIRMED','test-only'),))
        self.assertEqual(D('96'),actual.economic)

    def test_mixed_costs_and_closure(self):
        costs=(Cost('open',D('2'),'SETTLED','MODELED','test-only'),
               Cost('funding',D('.5'),'ACCRUED','MODELED','test-only'),
               Cost('exit',D('2'),'RESERVED','ESTIMATED','test-only'))
        before=equity(D('100'),D('3'),(D('5'),D('-2')),costs)
        self.assertEqual(D('101.5'),before.economic)
        closed=equity(D('100'),D('6'),(),tuple(replace(c,status='SETTLED',provenance='MODELED') for c in costs))
        self.assertEqual(before.economic,closed.economic)

    def test_duplicate_cost_and_invalid_inputs_rejected(self):
        c=Cost('fee',D('2'),'RESERVED','ESTIMATED','test-only')
        with self.assertRaises(ValueError): equity(D('100'),D('0'),(),(c,c))
        for amount in (D('-1'),D('NaN'),1.0):
            with self.assertRaises(ValueError): Cost('fee',amount,'RESERVED','ESTIMATED','test-only')
        with self.assertRaises(ValueError): Cost('fee',D('1'),'SETTLED','ESTIMATED','test-only')

    def test_decimal_context_does_not_change_money(self):
        with localcontext() as c:
            c.prec=4
            x=equity(D('100'),D('1.123456789'),(),())
        self.assertEqual(D('101.123456789'),x.economic)


class DailyTests(unittest.TestCase):
    def begin(self, **changes):
        return DailyState.begin(profile(**changes),D('100'),AT,boundary_verified=True,
                                operational_blocks=('EMERGENCY_STOP','RECONCILIATION_REQUIRED'))

    def test_disjoint_open_pending_and_paid_terms(self):
        # E=94 already includes 2 settled, 1 accrued and 3 reserved costs.
        # OpenRisk values exclude settled costs, already present in cash.
        day=self.begin().observe(profile(),AT,D('94'),
            (OpenRisk('long',D('-2'),D('-5')),OpenRisk('short',D('-2'),D('-4'))),
            (PendingRisk('pending',D('3')),))
        self.assertEqual(D('6'),day.used_loss)
        self.assertEqual(D('5'),day.open_risk)
        self.assertEqual(D('3'),day.pending_risk)
        self.assertEqual(D('6'),day.remaining)
        self.assertFalse(day.can_enter(D('1')))  # emergency/reconciliation persist

    def test_profile_and_restart_cannot_unlock_daily_loss(self):
        day=DailyState.begin(profile(),D('100'),AT,boundary_verified=True)
        day=day.observe(profile(),AT,D('79'),(),())
        self.assertTrue(day.loss_blocked)
        p=profile(configuration_version=2,daily_loss_limit_pct=D('50'))
        restored=DailyState.from_json(day.to_json()).observe(p,AT+timedelta(seconds=1),D('110'),(),())
        self.assertEqual(D('20'),restored.budget)
        self.assertTrue(restored.loss_blocked)
        self.assertFalse(restored.can_enter(D('0')))

    def test_lower_profile_latches_and_cap_cannot_raise_day_budget(self):
        day=DailyState.begin(profile(),D('150'),AT,boundary_verified=True)
        self.assertEqual(D('30'),day.budget)
        small=profile(configuration_version=2,daily_loss_limit_pct=D('5'),equity_cap_usd=D('80'))
        day=day.observe(small,AT,D('140'),(),())
        self.assertEqual(D('7.5'),day.budget)
        self.assertTrue(day.loss_blocked)

    def test_new_day_preserves_global_blocks(self):
        old=self.begin().observe(profile(),AT,D('70'),(),())
        tomorrow=AT+timedelta(days=1)
        p=profile(configuration_version=2,effective_from=tomorrow,created_at=tomorrow,
                  effective_until=tomorrow.replace(day=14,hour=4))
        with self.assertRaises(ValueError): old.next_day(p,D('70'),tomorrow,boundary_verified=False)
        new=old.next_day(p,D('70'),tomorrow,boundary_verified=True)
        self.assertFalse(new.loss_blocked)
        self.assertEqual(old.operational_blocks,new.operational_blocks)
        self.assertTrue(old.loss_blocked)
        self.assertFalse(new.can_enter(D('1')))

    def test_expiry_clock_scope_and_tamper(self):
        day=self.begin()
        with self.assertRaises(ValueError): day.observe(profile(),AT-timedelta(seconds=1),D('100'),(),())
        with self.assertRaises(ValueError): day.observe(profile(scope_id='r20-v2-other'),AT,D('100'),(),())
        with self.assertRaises(ValueError): day.observe(profile(),profile().effective_until,D('100'),(),())
        obj=json.loads(day.to_json()); obj['loss_blocked']=False; obj['budget']='1000'
        with self.assertRaises(ValueError): DailyState.from_json(json.dumps(obj))

    def test_duplicate_inventory_ids_are_rejected(self):
        with self.assertRaises(ValueError): self.begin().observe(profile(),AT,D('90'),
            (OpenRisk('same',D('0'),D('-1')),),(PendingRisk('same',D('1')),))

    def test_expired_intraday_profile_does_not_stop_loss_accounting(self):
        p=profile(effective_until=AT+timedelta(minutes=1))
        day=DailyState.begin(p,D('100'),AT,boundary_verified=True)
        day=day.observe(p,AT+timedelta(minutes=2),D('70'),(),())
        self.assertTrue(day.loss_blocked)
        self.assertFalse(day.can_enter(D('0')))
        self.assertEqual(day,DailyState.from_json(day.to_json()))

    def test_new_day_cannot_reuse_old_version_or_drop_known_inventory(self):
        old=self.begin().observe(profile(),AT,D('90'),(OpenRisk('old',D('-1'),D('-3')),),())
        tomorrow=AT+timedelta(days=1)
        p=profile(effective_from=tomorrow,created_at=tomorrow,effective_until=tomorrow.replace(day=14,hour=4))
        with self.assertRaises(ValueError): old.next_day(p,D('90'),tomorrow,boundary_verified=True)
        new=old.next_day(replace(p,configuration_version=2),D('90'),tomorrow,boundary_verified=True)
        self.assertEqual(old.open_terms,new.open_terms)
        self.assertFalse(new.inventory_verified)

    def test_pending_to_open_to_closed_daily_loss_identity(self):
        p=profile(); day=DailyState.begin(p,D('100'),AT,boundary_verified=True)
        pending=day.observe(p,AT,D('100'),(),(PendingRisk('p',D('8')),))
        opened=pending.observe(p,AT,D('96'),(OpenRisk('p',D('-4'),D('-8')),),())
        closed=opened.observe(p,AT,D('92'),(),())
        self.assertEqual([D('12')]*3,[x.remaining for x in (pending,opened,closed)])

    def test_nested_unknown_fields_and_corrupt_state_rejected(self):
        from trading_agent.r20_profiles import digest
        day=self.begin().observe(profile(),AT,D('90'),(OpenRisk('p',D('-1'),D('-3')),),())
        obj=json.loads(day.to_json());obj['open_terms'][0]['extra']='not allowed'
        obj.pop('state_hash'); obj['state_hash']=digest(obj)
        with self.assertRaises(ValueError): DailyState.from_json(json.dumps(obj))

    def test_overreserved_day_has_no_capacity_even_for_zero(self):
        day=DailyState.begin(profile(),D('100'),AT,boundary_verified=True).observe(
            profile(),AT,D('100'),(),(PendingRisk('p',D('21')),))
        self.assertFalse(day.can_enter(D('0')))


if __name__=='__main__': unittest.main()
