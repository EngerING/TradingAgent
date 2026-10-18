"""V3.1 contracts: synthetic metadata, no accounts or services."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import unittest

from trading_agent.core_v3.contracts import (
    AssetClass, ContractError, Environment, EvidenceRef, Instrument, Money,
    Price, Quantity, SourceKind, canonical_bytes, content_hash, strict_json,
)


AT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def eurusd():
    # Illustrative research metadata, not verified broker trading restrictions.
    return Instrument(
        instrument_id='fx-eurusd', specification_version=1,
        asset_class=AssetClass.FOREX, symbol='EUR/USD', base_currency='EUR',
        quote_currency='USD', quantity_unit='EUR', multiplier=Decimal('1'),
        tick=Price(Decimal('0.00005'), 'USD', 'EUR'),
        minimum_quantity=Quantity(Decimal('1'), 'EUR'),
        quantity_step=Quantity(Decimal('1'), 'EUR'), calendar_id='fx-synthetic-calendar',
    )


def synthetic_equity():
    return Instrument(
        instrument_id='synthetic-equity-eur', specification_version=2,
        asset_class=AssetClass.EQUITY, symbol='SYNTH', base_currency=None,
        quote_currency='EUR', quantity_unit='SHARE', multiplier=Decimal('1'),
        tick=Price(Decimal('0.01'), 'EUR', 'SHARE'),
        minimum_quantity=Quantity(Decimal('2'), 'SHARE'),
        quantity_step=Quantity(Decimal('2'), 'SHARE'), calendar_id='equity-synthetic-calendar',
    )


class CommonTypeTests(unittest.TestCase):
    def test_decimal_addition_is_exact_independent_of_ambient_precision(self):
        with localcontext() as context:
            context.prec = 2
            result = Money(Decimal('12345.10'), 'EUR').add(Money(Decimal('0.02'), 'EUR'))
        self.assertEqual(Decimal('12345.12'), result.amount)
        self.assertEqual({'amount': '12345.12', 'currency': 'EUR'}, result.to_dict())

    def test_money_rejects_implicit_currency_conversion(self):
        with self.assertRaisesRegex(ContractError, 'CURRENCY_MISMATCH'):
            Money(Decimal('1'), 'USD').add(Money(Decimal('1'), 'EUR'))

    def test_nonfinite_float_bool_exponent_and_excess_precision_are_rejected(self):
        for value in (float('nan'), float('inf'), 1.1, True, '1',
                      Decimal('NaN'), Decimal('Infinity'), Decimal('1E100000'),
                      Decimal('0.0000000000001')):
            with self.subTest(value=str(value)), self.assertRaises(ContractError):
                Money(value, 'USD')
        for value in ('NaN', 'Infinity', '1e2', '01', '+1', ' 1', '0.0000000000001'):
            with self.subTest(value=value), self.assertRaises(ContractError):
                Money.from_dict(dict(amount=value, currency='USD'))

    def test_negative_pnl_and_zero_are_explicit_and_not_missing_defaults(self):
        self.assertEqual('-0.1', Money(Decimal('-0.10'), 'JPY').to_dict()['amount'])
        self.assertEqual('0', Money(Decimal('-0.000'), 'JPY').to_dict()['amount'])
        for value in ({'currency': 'USD'}, {'amount': None, 'currency': 'USD'}):
            with self.assertRaises(ContractError):
                Money.from_dict(value)

    def test_common_types_are_closed_and_immutable(self):
        for value in (Money(Decimal('1'), 'EUR'), Quantity(Decimal('1'), 'SHARE'),
                      Price(Decimal('2'), 'EUR', 'SHARE')):
            with self.assertRaises((FrozenInstanceError, AttributeError)):
                value.amount = Decimal('7')
            data = value.to_dict()
            data['execution_authority'] = True
            with self.assertRaises(ContractError):
                type(value).from_dict(data)

    def test_metadata_environment_never_creates_authority(self):
        self.assertEqual({'RESEARCH', 'SIMULATION', 'PAPER', 'LIVE'}, {e.value for e in Environment})
        for environment in Environment:
            ref = EvidenceRef('fixture', SourceKind.SYNTHETIC, environment, None, None, None)
            self.assertEqual(ref, EvidenceRef.from_dict(ref.to_dict()))
            data = ref.to_dict()
            data['live_enabled'] = True
            with self.assertRaises(ContractError):
                EvidenceRef.from_dict(data)

    def test_unknown_expired_future_and_naive_evidence_cannot_be_current(self):
        ref = EvidenceRef('fixture', SourceKind.CALLER_UNVERIFIED, Environment.RESEARCH,
                          'a' * 64, AT, AT + timedelta(seconds=30))
        ref.require_current(AT)
        for now in (AT - timedelta(microseconds=1), AT + timedelta(seconds=30), AT.replace(tzinfo=None)):
            with self.assertRaises(ContractError):
                ref.require_current(now)
        with self.assertRaisesRegex(ContractError, 'EVIDENCE_TIME_UNKNOWN'):
            replace(ref, observed_at=None, valid_until=None).require_current(AT)
        with self.assertRaises(ContractError):
            replace(ref, valid_until=AT)

    def test_time_canonicalization_and_unrepresentable_utc_are_controlled(self):
        ref = EvidenceRef('fixture', SourceKind.SYNTHETIC, Environment.RESEARCH,
                          None, AT, AT + timedelta(seconds=30))
        data = ref.to_dict()
        data['observed_at'] = '2026-10-18T08:00:00-04:00'
        self.assertEqual(ref, EvidenceRef.from_dict(data))
        data['observed_at'] = '0001-01-01T00:00:00+23:00'
        with self.assertRaises(ContractError):
            EvidenceRef.from_dict(data)
        boundary = datetime.min.replace(tzinfo=timezone(timedelta(hours=23)))
        with self.assertRaises(ContractError):
            ref.require_current(boundary)


class InstrumentTests(unittest.TestCase):
    def test_forex_and_non_usd_synthetic_equity_roundtrip(self):
        for instrument in (eurusd(), synthetic_equity()):
            with self.subTest(instrument=instrument.instrument_id):
                self.assertEqual(instrument, Instrument.from_json(instrument.to_json()))
                instrument.check_terms(instrument.minimum_quantity, instrument.tick)
        self.assertNotEqual(eurusd().calendar_id, synthetic_equity().calendar_id)
        self.assertEqual('EUR', synthetic_equity().quote_currency)

    def test_unit_currency_grid_and_tick_mismatches_rejected(self):
        instrument = synthetic_equity()
        cases = [
            (Quantity(Decimal('2'), 'EUR'), Price(Decimal('10'), 'EUR', 'SHARE')),
            (Quantity(Decimal('2'), 'SHARE'), Price(Decimal('10'), 'USD', 'SHARE')),
            (Quantity(Decimal('2'), 'SHARE'), Price(Decimal('10'), 'EUR', 'EUR')),
            (Quantity(Decimal('3'), 'SHARE'), Price(Decimal('10'), 'EUR', 'SHARE')),
            (Quantity(Decimal('2'), 'SHARE'), Price(Decimal('10.001'), 'EUR', 'SHARE')),
        ]
        for quantity, price in cases:
            with self.subTest(quantity=quantity, price=price), self.assertRaises(ContractError):
                instrument.check_terms(quantity, price)

    def test_invalid_metadata_versions_extra_fields_and_permissions_rejected(self):
        for field, value in (
            ('instrument_id', '../outside'), ('specification_version', True),
            ('specification_version', 0), ('asset_class', 'CRYPTO'),
            ('schema_version', 2), ('schema_version', True), ('schema', 'FOREX_V2'),
            ('quote_currency', 'usd'), ('quantity_unit', ''), ('calendar_id', '../calendar'),
            ('multiplier', '0'), ('execution_authority', True), ('paper_execution_eligible', True),
            ('live_enabled', True), ('unknown', 0),
        ):
            data = eurusd().to_dict()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                Instrument.from_dict(data)

    def test_nested_metadata_is_immutable_and_inputs_are_copied(self):
        original = eurusd()
        with self.assertRaises(FrozenInstanceError):
            original.tick.amount = Decimal('2')
        data = original.to_dict()
        restored = Instrument.from_dict(data)
        data['tick']['amount'] = '2'
        self.assertEqual(original, restored)

    def test_specification_version_and_metadata_affect_identity_hash(self):
        instrument = eurusd()
        self.assertNotEqual(content_hash(instrument), content_hash(replace(instrument, specification_version=2)))
        self.assertNotEqual(content_hash(instrument), content_hash(replace(instrument, calendar_id='another-calendar')))


class SerializationTests(unittest.TestCase):
    def test_schema_describes_exact_closed_wire_fields_and_resolves_local_references(self):
        path = Path(__file__).resolve().parents[2] / 'contracts/core-v3/v1/core.schema.json'
        schema = strict_json(path.read_bytes())
        for name, value in [('instrument', eurusd()), ('money', Money(Decimal('1'), 'EUR')),
                            ('price', Price(Decimal('1'), 'EUR', 'SHARE')),
                            ('quantity', Quantity(Decimal('1'), 'SHARE')),
                            ('evidence', EvidenceRef('fixture', SourceKind.SYNTHETIC,
                                                     Environment.SIMULATION, None, None, None))]:
            definition = schema['$defs'][name]
            self.assertFalse(definition['additionalProperties'])
            self.assertEqual(set(value.to_dict()), set(definition['required']))
            self.assertEqual(set(value.to_dict()), set(definition['properties']))

        def references(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    self.assertTrue(value['$ref'].startswith('#/$defs/'))
                    self.assertIn(value['$ref'].split('/')[-1], schema['$defs'])
                for child in value.values():
                    references(child)
            elif isinstance(value, list):
                for child in value:
                    references(child)
        references(schema)

    def test_canonical_golden_vector_and_decimal_equivalence(self):
        expected = b'{"amount":"1.23","currency":"EUR"}'
        self.assertEqual(expected, canonical_bytes(Money(Decimal('1.2300'), 'EUR')))
        self.assertEqual(hashlib.sha256(expected).hexdigest(), content_hash(Money(Decimal('1.23'), 'EUR')))
        self.assertEqual(b'{"a":"\\u00e1","b":2}', canonical_bytes({'b': 2, 'a': '\u00e1'}))

    def test_duplicate_keys_nonfinite_oversized_and_wrong_json_types_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":{"a":1,"a":2}}', '{"x":NaN}',
                    '{"x":Infinity}', '{} trailing', '[]', 'null', ' ' * 131073):
            with self.subTest(raw=raw[:30]), self.assertRaises(ContractError):
                Instrument.from_json(raw)
        for value in (float('nan'), 1.0, {1: 'not-a-string-key'}):
            with self.assertRaises(ContractError):
                canonical_bytes(value)

    def test_strict_json_rejects_surrogates_and_invalid_utf8(self):
        for raw in ('{"x":"\\ud800"}', b'\xff'):
            with self.assertRaises(ContractError):
                strict_json(raw)
