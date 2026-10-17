import json
from pathlib import Path
import unittest
from trading_agent.exposure_economic_research import (EXPOSURES,RATES,FAMILY_TESTS,
    alternative_costs,margin_sensitivity,minimum_summary,profiles,invoke)
from trading_agent.progressive_risk_research import uncertainty

ROOT=Path(__file__).resolve().parents[2]
COSTS=dict(spread='.0014',openingCommission='2',closingCommission='2',commissionPerUnitRoundTrip='0',
    slippage='.00045',adverseGap='.00005',minimumQuantity='.01',quantityStep='.01',marginRate='1',source='TEST_ONLY')


class ExposureEconomicResearchTests(unittest.TestCase):
    def test_sweep_covers_all_integer_risks_and_protected_fractional_cases(self):
        self.assertEqual((1,2,5,10,15,20),EXPOSURES)
        self.assertTrue(set(range(1,16)).issubset(RATES))
        self.assertEqual(17,len(RATES));self.assertEqual(1530,FAMILY_TESTS)

    def test_stress_profiles_do_not_alter_observed_fees_or_original_input(self):
        before=json.dumps(COSTS,sort_keys=True);p=profiles(COSTS)
        self.assertEqual(5,len(p));self.assertEqual(before,json.dumps(COSTS,sort_keys=True))
        self.assertEqual('.0014',p[1]['costs']['spread'])
        self.assertEqual('.00005',p[0]['costs']['spread'])
        for model in p:
            self.assertEqual('2',model['costs']['openingCommission'])
            self.assertEqual('2',model['costs']['closingCommission'])

    def test_5percent_margin_at_twenty_times_exhausts_collateral_before_costs(self):
        rates={r['rate']:r for r in margin_sensitivity(2000,8)}
        self.assertEqual(100,rates[.05]['initial_margin'])
        self.assertFalse(rates[.05]['collateral_fits_100'])
        self.assertFalse(rates[.025]['account_verified'])

    def test_margin_sensitivity_keeps_actual_rate_unknown(self):
        rows={r['rate']:r for r in margin_sensitivity(1500,10)}
        self.assertTrue(rows[.05]['collateral_fits_100'])
        self.assertFalse(rows[.10]['collateral_fits_100'])
        self.assertEqual(85,rows[.05]['total_with_reserved_loss'])
        with self.assertRaises(ValueError):margin_sensitivity(-1)

    def test_missing_minimum_is_not_zero_quantity_or_proof_of_viability(self):
        result=minimum_summary([dict(minimum=None)])
        self.assertIsNone(result['minimum_cost_covering'])
        self.assertFalse(result['actual_ibkr_executable'])
        self.assertIsNone(result['actual_margin_rate'])

    def test_cost_covering_threshold_can_fail_risk_or_margin(self):
        def row(exposure,risk,margin):
            return dict(minimum=dict(exposure=exposure,withinFifteenPercent=risk<=15,
                withinTwentyTimes=exposure<=20,maximumAffordableMarginRate=margin))
        result=minimum_summary([row(10,16,.06),row(15,10,.04),row(18,11,.055)])
        self.assertEqual(2,result['positive_thresholds_within_20x_15usd'])
        self.assertEqual(1,result['hypothetically_funded'])
        self.assertEqual(18,result['minimum_funded_risk_bounded']['minimum']['exposure'])
        favorable=minimum_summary([row(15,10,.04)],.025)
        self.assertEqual(1,favorable['hypothetically_funded'])
        self.assertEqual(.025,favorable['funding_margin_rate_assumption'])

    def test_alternative_tariffs_apply_fractional_and_crypto_caps(self):
        rows={x['instrument']:x for x in alternative_costs(90)}
        self.assertAlmostEqual(.7,rows['US_WHOLE_SHARES_TIERED']['round_trip_fee_usd'])
        self.assertAlmostEqual(1.8,rows['US_FRACTIONAL']['round_trip_fee_usd'])
        self.assertAlmostEqual(1.8,rows['SPOT_CRYPTO']['round_trip_fee_usd'])
        self.assertEqual(4,rows['EURUSD_CASH']['round_trip_fee_usd'])
        for row in rows.values():
            self.assertFalse(row['execution_verified']);self.assertFalse(row['strategy_backtested'])

    def test_alternative_tariff_screen_rejects_fictitious_capital(self):
        for notional in (0,-1,101,1000000):
            with self.subTest(notional=notional),self.assertRaises(ValueError):alternative_costs(notional)

    def test_multiple_testing_family_is_not_the_old_24_case_family(self):
        trades=[dict(netPnl=1,exitAt='2026-08-04T12:00:00Z') for _ in range(100)]
        ordinary=uncertainty(trades,'old')
        large=uncertainty(trades,'new',family_tests=FAMILY_TESTS)
        self.assertEqual(1530,large['comparisons'])
        self.assertLess(large['win_wilson_family_adjusted'][0],ordinary['win_wilson_family_adjusted'][0])
        with self.assertRaises(ValueError):uncertainty([], 'invalid', family_tests=0)

    def test_actual_executable_has_six_exposures_seventeen_rates_and_no_permission(self):
        rows=invoke(ROOT,'trend',[],[],[],profiles(COSTS)[0])
        self.assertEqual(102,len(rows))
        self.assertEqual(set(EXPOSURES),{r['exposureLimit'] for r in rows})
        self.assertEqual({r/100 for r in RATES},{x['riskFraction'] for x in rows})
        for r in rows:
            self.assertFalse(r['executionAuthorized']);self.assertFalse(r['liveEnabled'])
            self.assertEqual(100,r['metrics']['finalEquity'])

    def test_original_executable_boundary_still_rejects_operational_exposure(self):
        # Tested through the existing boundary test as well; this study never changes its exposure field.
        from test_progressive_risk_research import ProgressiveRiskEvidenceTests
        fixture=ProgressiveRiskEvidenceTests();p=fixture.payload();p['exposure']=20
        code,out=fixture.invoke(p)
        self.assertNotEqual(0,code);self.assertEqual(0,out['ordersSent'])
        self.assertEqual('ISOLATED_RESEARCH_SCOPE_REQUIRED',out['reason'])


if __name__=='__main__':unittest.main()
