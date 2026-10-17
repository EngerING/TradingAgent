"""Conservative US whole-share research scenarios, never an account fee quote.

2026 published schedules applied to old prices are a forward cost stress, NOT a
reconstruction of 2021-23 invoices. Unknown routing/account charges remain
unknown; the legacy allowance is retained without claiming it is an IBKR fee.
"""
from decimal import Decimal, ROUND_CEILING
from .contracts import number, MODELS

D = Decimal
COST_VERSION = 'US_WHOLE_SHARE_CONSERVATIVE_20261006_V2'
SOURCE = 'https://www.interactivebrokers.com/en/pricing/commissions-stocks.php'
TAF_SOURCE = 'https://www.sec.gov/files/rules/sro/finra/2026/34-106409-ex5.pdf'


def commission_details(quantity, price, model, side):
    if model not in MODELS or side not in ('BUY', 'SELL'):
        raise ValueError('COST_MODEL_AND_SIDE_REQUIRED')
    q, p = number(quantity), number(price)
    if q <= 0 or q != q.to_integral_value() or p <= 0:
        raise ValueError('POSITIVE_WHOLE_QUANTITY_PRICE_REQUIRED')
    fixed = model == 'FIXED_FEE_STRESS'
    rate, minimum = (D('.005'), D('1')) if fixed else (D('.0035'), D('.35'))
    notional = q * p
    # Retain the higher 1% table cap conservatively: the published Tiered
    # disclosure also says 0.5%. Its effective application is not verified.
    base = min(max(q * rate, minimum), notional * D('.01'))
    parts = dict(base_commission=base,
                 sec_sell=notional * D('.0000206') if side == 'SELL' else D(0),
                 taf_sell_reserve=min(q * D('.000195'), D('9.79')) if side == 'SELL' else D(0),
                 cat=q * D('.000003'),
                 clearing=D(0) if fixed else min(q * D('.00020'), notional * D('.005')),
                 pass_through=D(0) if fixed else base * D('.000735'),
                 unallocated_fee_allowance=D('.02') + q * D('.01'))
    raw = sum(parts.values())
    total = raw.quantize(D('.01'), rounding=ROUND_CEILING)
    parts['rounding_reserve'] = total - raw
    # Fixed includes venue/clearing charges: they are not charged again here.
    # The unallocated allowance is a separate UNVERIFIED contingency in BOTH
    # scenarios, not a statement that Fixed incurs exchange fees twice.
    return dict(version=COST_VERSION, side=side, currency='USD', total=total,
                components=parts, base_rate=rate, minimum=minimum,
                base_cap=notional * D('.01'),
                effective_account_fees='UNKNOWN', routing='UNKNOWN',
                allowance_status='ESTIMATED_NOT_A_GUARANTEED_UPPER_BOUND',
                taf_policy='NON_HOLIDAY_RESERVE_NOT_CURRENT_INVOICE',
                rounding_policy='CEIL_TOTAL_PER_ORDER_TO_CENT_ESTIMATED',
                tariff_scope='2026_FORWARD_COST_SCENARIO_NOT_HISTORICAL_INVOICE',
                source=SOURCE, checked_on='2026-10-06')


def commission(quantity, price, model, side='BUY'):
    return commission_details(quantity, price, model, side)['total']


def fee_evidence(details):
    # Bounded per-fill evidence; common provenance is recorded once per result.
    return {k: ({name: float(v) for name, v in value.items()} if k == 'components'
                else float(value) if isinstance(value, D) else value)
            for k, value in details.items() if k in ('version','side','currency','total','components')}


def cost_assumptions():
    return dict(version=COST_VERSION,checked_on='2026-10-06',source=SOURCE,taf_source=TAF_SOURCE,
        effective_account_fees='UNKNOWN',routing='UNKNOWN',historical_fee_schedule='NOT_RECONSTRUCTED',
        purpose='2026_CONSERVATIVE_FORWARD_COST_SCENARIO_ON_OLD_PRICES',
        allowance='LEGACY_0.02_PER_ORDER_PLUS_0.01_PER_SHARE_UNALLOCATED_CONTINGENCY_BOTH_PLANS',
        allowance_verified=False,allowance_guaranteed_upper_bound=False,
        taf='NON_HOLIDAY_0.000195_RESERVE__PUBLISHED_Q4_2026_HOLIDAY_NOT_APPLIED',
        cap='1_PERCENT_TABLE_RETAINED_CONSERVATIVELY__TIERED_0.5_PERCENT_DISCLOSURE_UNRESOLVED',
        rounding='CEIL_TOTAL_PER_ORDER_TO_CENT_ESTIMATED',
        minimum_scope='ONE_UNMODIFIED_BUY_AND_ONE_UNMODIFIED_SELL_FULL_FILL',
        partial_fills_modifications_overnight_minima='UNKNOWN_NOT_SIMULATED',
        account_surcharges_taxes_rebates='UNKNOWN_NO_REBATE_CREDIT')
