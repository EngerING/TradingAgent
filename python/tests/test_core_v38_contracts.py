"""Fabricated test data only: never evidence of a market provider's origin."""
from dataclasses import replace, FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
import unittest

from trading_agent.core_v3.contracts import ContractError, content_hash
from trading_agent.core_v3.historical_ingestion.contracts import DatasetSpec, ReviewReceipt


def instant(hour=0):
    return datetime(2026, 1, 5, hour, tzinfo=timezone.utc)


def spec(**changes):
    values = dict(provider_id='fixture-provider', export_id='export-1', instrument_id='EURUSD',
        symbol='EURUSD', venue='FIXTURE', quote_currency='USD', price_unit='EUR', tick=Decimal('0.0001'),
        data_origin='SYNTHETIC_TEST_FIXTURE', kind='OHLC', representation='MID', interval_seconds=3600,
        quote_max_gap_seconds=0, timezone_name='UTC', available_basis='PROVIDER_PUBLISHED',
        window_start=instant(0), window_end=instant(2), exported_at=instant(3), observed_at=instant(4),
        raw_sha256='a'*64, evidence_sha256='b'*64, calendar_sha256='c'*64, tzif_sha256='d'*64)
    return DatasetSpec(**(values | changes))


class Contracts(unittest.TestCase):
    def test_roundtrip_exact_and_frozen(self):
        value = spec()
        self.assertEqual(DatasetSpec.from_json(value.to_json()), value)
        with self.assertRaises(FrozenInstanceError):
            value.provider_id = 'changed'

    def test_strict_wire_rejects_extras_duplicates_version_and_approval(self):
        for change in ({'live_enabled': True}, {'schema_version': True}, {'approved': True},
                       {'schema_version': 2}, {'tick': 0.1}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                DatasetSpec.from_dict(spec().to_dict() | change)
        raw = spec().to_json().replace('"tick":"0.0001"', '"tick":"0.0001","tick":"0.0001"')
        with self.assertRaises(ContractError):
            DatasetSpec.from_json(raw)

    def test_no_synthetic_or_ambiguous_price_basis(self):
        for changes in ({'data_origin': 'SYNTHETIC'}, {'kind': 'TICK'}, {'representation': 'UNKNOWN'},
                        {'tick': Decimal('NaN')}, {'interval_seconds': True}, {'tick': Decimal('0')},
                        {'interval_seconds': 0}, {'observed_at': instant(2)},
                        {'window_end': instant(0)}, {'raw_sha256': 'bad'}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                spec(**changes)

    def test_reviews_are_host_objects_never_an_input_approval_decoder(self):
        review = ReviewReceipt('fixture-provider', 'export-1', content_hash(spec()), 'b'*64,
                               'reviewer-1', 'external-evidence-1', instant(4))
        self.assertIn('LOCAL_REVIEW', review.method)
        with self.assertRaises(ContractError):
            ReviewReceipt.from_dict(review.to_dict())
        with self.assertRaises(ContractError):
            replace(review, method='HASH_IS_AUTHENTICITY')
