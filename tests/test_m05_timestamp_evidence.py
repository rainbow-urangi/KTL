"""Temporary synthetic timestamp evidence only; no real held-out predictions."""
import copy
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend import m05_full_context as fc
from backend import m05_timestamp_evidence as te
from backend.evaluators import EvaluationError

REPO = Path(__file__).resolve().parents[1]
FREEZE = json.loads((REPO / fc.FREEZE_PATH).read_text())
CONFIG = json.loads((REPO / 'evaluation_contracts/m05_engine.json').read_text())
UTC = '2026-11-10T00:00:00.123+00:00'


def payload_row(local='2026-11-10 09:00:00.123', instant=UTC):
    return dict(event_id='fixture-event', session_id='fixture-session', task_id='fixture-task',
                event_time=local, activity='fixture-activity', locators_json=json.dumps(dict(
                    event_context=dict(event_id='fixture-event', event_time=instant),
                    session=dict(page_session_id='fixture-session'),
                    analysis=dict(event_ts_ms=1794268800123))))


def payload_policy(zone='Asia/Seoul'):
    return dict(schema_version=te.POLICY_SCHEMA, timestamp_column='event_time', timezone=zone,
                raw_files=[dict(path='raw/events.csv', sha256='synthetic-hash')], payload_sources=[dict(
                    column='locators_json', event_id_path=['event_context', 'event_id'],
                    session_id_path=['session', 'page_session_id'], timestamps=[
                        dict(path=['event_context', 'event_time'], format='iso8601'),
                        dict(path=['analysis', 'event_ts_ms'], format='unix_ms')])])


class TimestampResolutionTests(unittest.TestCase):
    def resolve(self, row=None, policy=None):
        return te.resolve_event_time(row or payload_row(), policy or payload_policy())

    def test_payload_utc_epoch_and_naive_kst_reconcile_without_mutation(self):
        row, policy = payload_row(), payload_policy()
        before = copy.deepcopy((row, policy))
        actual, method = self.resolve(row, policy)
        self.assertEqual(actual, fc.instant(UTC))
        self.assertEqual(method, 'bound_payload')
        self.assertEqual((row, policy), before)

    def test_non_korean_zone_and_fixed_offset_are_generic(self):
        for zone, wall in [('America/New_York', '2026-11-09 19:00:00.123'),
                           ('Europe/London', '2026-11-10 00:00:00.123'),
                           ('+05:30', '2026-11-10 05:30:00.123'), ('UTC', '2026-11-10 00:00:00.123')]:
            with self.subTest(zone=zone):
                self.assertEqual(self.resolve(payload_row(wall), payload_policy(zone))[0], fc.instant(UTC))

    def test_aware_without_policy_is_unchanged(self):
        for value in [UTC, '2026-11-10T09:00:00.123+09:00']:
            self.assertEqual(te.resolve_event_time(dict(event_time=value), None),
                             (fc.instant(UTC), 'raw_explicit_offset'))

    def test_aware_offset_must_match_declared_exporter_timezone(self):
        row = payload_row('2026-11-10T09:00:00.123+09:00')
        self.assertEqual(self.resolve(row)[0], fc.instant(UTC))
        with self.assertRaisesRegex(EvaluationError, 'EXPORT_TIMEZONE_CONFLICT'):
            self.resolve(row, payload_policy('UTC'))
        with self.assertRaisesRegex(EvaluationError, 'EXPORT_TIMEZONE_CONFLICT'):
            self.resolve(payload_row(UTC), payload_policy('Asia/Seoul'))
        authority = dict(payload_policy('UTC'), payload_sources=[], timezone_authority={'path': 'verified'})
        with self.assertRaisesRegex(EvaluationError, 'EXPORT_TIMEZONE_CONFLICT'):
            self.resolve(row, authority)

    def test_arbitrary_decimal_precision_never_rounds_away(self):
        for form, value in [('unix_ms', '1794268800123.000000000000000000000001'),
                            ('unix_s', '1794268800.123000000000000000000000001'),
                            ('unix_us', '1794268800123000.000000000000000000001')]:
            with self.subTest(form=form), self.assertRaisesRegex(EvaluationError, 'EPOCH_PRECISION'):
                te.epoch_instant(value, form)
        self.assertEqual(te.epoch_instant('1794268800123.000000000000000000000000', 'unix_ms'), fc.instant(UTC))
        self.assertEqual(te.epoch_instant('1794268800123' + '0' * 24 + 'e-24', 'unix_ms'), fc.instant(UTC))
        self.assertEqual(te.epoch_instant('0e999999', 'unix_ms'), datetime(1970, 1, 1, tzinfo=timezone.utc))
        for value in ['1e999999', '-1e999999', '0.000000000000000000000001']:
            with self.subTest(value=value), self.assertRaises(EvaluationError):
                te.epoch_instant(value, 'unix_ms')

    def test_json_decimal_precision_is_also_exact(self):
        row = payload_row()
        row['locators_json'] = row['locators_json'].replace('1794268800123', '1794268800123.000000000000000000000001')
        with self.assertRaisesRegex(EvaluationError, 'EPOCH_PRECISION'):
            self.resolve(row)

    def test_raw_iso_submicrosecond_precision_never_truncates(self):
        for value in ['2026-11-10 09:00:00.1230009', '2026-11-10T09:00:00.1230009+09:00',
                      '2026-11-10T09:00:00.123000000000000000001+09:00', '2026-11-10 09:00:00,1230009']:
            with self.subTest(value=value), self.assertRaisesRegex(EvaluationError, 'PRECISION_UNSUPPORTED'):
                self.resolve(payload_row(value))
        with self.assertRaisesRegex(EvaluationError, 'PRECISION_UNSUPPORTED'):
            te.resolve_event_time(dict(event_time='2026-11-10T00:00:00.1230009Z'), None)

    def test_payload_iso_submicrosecond_precision_never_truncates(self):
        for value in ['2026-11-10T00:00:00.1230009Z', '2026-11-10T00:00:00.123000000000000000001Z',
                      '2026-11-10T00:00:00,1230009Z']:
            with self.subTest(value=value), self.assertRaisesRegex(EvaluationError, 'PRECISION_UNSUPPORTED'):
                self.resolve(payload_row(instant=value))
        self.assertEqual(self.resolve(payload_row('2026-11-10 09:00:00.123000', '2026-11-10T00:00:00.123000Z'))[0], fc.instant(UTC))

    def test_unsupported_offset_precision_and_short_time_fail(self):
        for value in ['2026-11-10T00:00:00.123+00:00:00.000001', '2026-11-10T00:00.123Z',
                      '20261110T000000.123Z', '2026-11-10']:
            with self.subTest(value=value), self.assertRaisesRegex(EvaluationError, 'INVALID_TIMESTAMP_FORMAT'):
                te.parsed_datetime(value)

    def test_malformed_explicit_offsets_never_normalize(self):
        for suffix in ['+09:99', '+00:60', '-09:99', '+24:00', '-24:00']:
            value = '2026-11-10T00:00:00.123' + suffix
            with self.subTest(suffix=suffix):
                with self.assertRaisesRegex(EvaluationError, 'INVALID_TIMESTAMP_OFFSET'):
                    te.resolve_event_time(dict(event_time=value), None)
                with self.assertRaisesRegex(EvaluationError, 'INVALID_TIMESTAMP_OFFSET'):
                    self.resolve(payload_row(instant=value))
        self.assertEqual(te.aware_instant('2026-11-10T09:00:00.123+09:00'), fc.instant(UTC))

    def test_decimal_comma_is_lossless_and_runtime_independent(self):
        row = payload_row('2026-11-10 09:00:00,123', '2026-11-10T00:00:00,123Z')
        before = copy.deepcopy(row)
        self.assertEqual(self.resolve(row)[0], fc.instant(UTC))
        self.assertEqual(row, before)
        self.assertEqual(te.resolve_event_time(dict(event_time='2026-11-10T00:00:00,123Z'), None)[0], fc.instant(UTC))

    def test_naive_without_policy_fails_closed(self):
        with self.assertRaisesRegex(EvaluationError, 'TIMEZONE_REQUIRED'):
            te.resolve_event_time(payload_row(), None)

    def test_payload_sources_must_all_agree(self):
        row = payload_row()
        data = json.loads(row['locators_json'])
        data['analysis']['event_ts_ms'] += 1
        row['locators_json'] = json.dumps(data)
        with self.assertRaisesRegex(EvaluationError, 'EVIDENCE_CONFLICT'):
            self.resolve(row)

    def test_export_offset_or_calendar_mismatch_fails(self):
        for wall in ['2026-11-10 00:00:00.123', '2026-11-09 09:00:00.123', '2026-11-10 09:00:00.124']:
            with self.subTest(wall=wall), self.assertRaisesRegex(EvaluationError, 'EXPORT_PAYLOAD_CONFLICT'):
                self.resolve(payload_row(wall))

    def test_aware_raw_cannot_override_conflicting_payload(self):
        with self.assertRaisesRegex(EvaluationError, 'EVIDENCE_CONFLICT'):
            self.resolve(payload_row('2026-11-10T09:00:01.123+09:00'))

    def test_payload_identity_must_match_event_and_session(self):
        for group, field in [('event_context', 'event_id'), ('session', 'page_session_id')]:
            row = payload_row()
            data = json.loads(row['locators_json'])
            data[group][field] = 'other'
            row['locators_json'] = json.dumps(data)
            with self.subTest(field=field), self.assertRaisesRegex(EvaluationError, 'IDENTITY_MISMATCH'):
                self.resolve(row)

    def test_missing_invalid_duplicate_json_and_missing_configured_field_fail(self):
        row = payload_row()
        for text in ['', '{bad', '[]', '{"event_context": {}, "event_context": {}}']:
            with self.subTest(text=text), self.assertRaises(EvaluationError):
                self.resolve(dict(row, locators_json=text))
        data = json.loads(row['locators_json'])
        del data['analysis']['event_ts_ms']
        with self.assertRaisesRegex(EvaluationError, 'FIELD_MISSING'):
            self.resolve(dict(row, locators_json=json.dumps(data)))

    def test_naive_payload_never_inherits_export_timezone(self):
        with self.assertRaisesRegex(EvaluationError, 'TIMEZONE_REQUIRED'):
            self.resolve(payload_row(instant='2026-11-10 00:00:00.123'))

    def test_epoch_units_and_precision(self):
        for form, number in [('unix_s', '1794268800.123'), ('unix_ms', 1794268800123),
                             ('unix_us', 1794268800123000)]:
            with self.subTest(form=form):
                self.assertEqual(te.epoch_instant(number, form), fc.instant(UTC))
        for value in [True, None, 'NaN', 'Infinity', '1e50', '1794268800123.0001']:
            with self.subTest(value=value), self.assertRaises(EvaluationError):
                te.epoch_instant(value, 'unix_ms')

    def test_epoch_only_and_iso_only_are_supported(self):
        for index in (0, 1):
            policy = payload_policy()
            policy['payload_sources'][0]['timestamps'] = [policy['payload_sources'][0]['timestamps'][index]]
            self.assertEqual(self.resolve(policy=policy)[0], fc.instant(UTC))

    def test_authority_without_payload(self):
        policy = dict(payload_policy(), payload_sources=[], timezone_authority={'path': 'already-verified'})
        row = payload_row()
        del row['locators_json']
        self.assertEqual(self.resolve(row, policy), (fc.instant(UTC), 'timezone_authority'))

    def test_timezone_abbreviation_unknown_or_invalid_offset_fails(self):
        for name in ['KST', 'CST', 'No/SuchZone', '+24:00', '+14:01', '+09:99', None]:
            with self.subTest(name=name), self.assertRaises(EvaluationError):
                te.named_timezone(name)

    def test_dst_gap_and_ambiguous_fold_fail_without_utc(self):
        policy = dict(payload_policy('America/New_York'), payload_sources=[], timezone_authority={'path': 'verified'})
        for wall in ['2026-03-08 02:30:00', '2026-11-01 01:30:00']:
            with self.subTest(wall=wall), self.assertRaisesRegex(EvaluationError, 'AMBIGUOUS_OR_NONEXISTENT'):
                self.resolve(payload_row(wall), policy)

    def test_utc_payload_disambiguates_dst_fold(self):
        for instant in ['2026-11-01T05:30:00Z', '2026-11-01T06:30:00Z']:
            policy = payload_policy('America/New_York')
            policy['payload_sources'][0]['timestamps'] = [policy['payload_sources'][0]['timestamps'][0]]
            self.assertEqual(self.resolve(payload_row('2026-11-01 01:30:00', instant), policy)[0], fc.instant(instant))


class TimestampBundleTests(unittest.TestCase):
    """Only load/validate full synthetic sequences; never invoke an adapter."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'data/held_out/m05/synthetic_time'
        self.bundle.mkdir(parents=True)
        self.normalizer = fc.frozen_normalizer(FREEZE)
        self.rows = [payload_row()]
        self.raw = self.write_raw()
        self.policy = dict(payload_policy(), raw_files=[dict(path=self.raw['path'], sha256=self.raw['sha256'])])
        common = dict(event_ids=['fixture-event'], complete=True, completion_evidence='Synthetic only',
                      started_at_utc='2026-11-10T00:00:00Z', ended_at_utc='2026-11-10T00:00:01Z',
                      source_session_id='fixture-session')
        self.collection = dict(dataset_id='synthetic_time', scope='COMPLETE_SESSIONS_AND_TASKS',
                               collection_started_at_utc=common['started_at_utc'], collection_ended_at_utc=common['ended_at_utc'],
                               collector_id='synthetic', collector_version='fixture-v1', timezone='Asia/Seoul',
                               completion_reason='Synthetic only', raw_files=[self.raw], event_count=1,
                               sessions=self.write('sessions.json', dict(sessions=[common])),
                               tasks=self.write('tasks.json', dict(tasks=[dict(common, source_case_id='fixture-task')])))
        self.collection['export_evidence'] = self.write('export.json', dict(dataset_id='synthetic_time', findings='Synthetic only'))
        self.manifest = dict(dataset_id='synthetic_time', schema_version=fc.SCHEMA, used_for_training=False, used_for_development=False)
        self.rebind_clock()

    def write(self, name, obj):
        path = self.bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))
        return dict(path=str(path.relative_to(self.root)), sha256=fc.sha(path))

    def write_raw(self):
        path = self.bundle / 'raw/events.csv'
        path.parent.mkdir(exist_ok=True)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        _, _, mapping = fc.raw_rows(path, self.normalizer)
        return dict(path=str(path.relative_to(self.root)), sha256=fc.sha(path), row_count=len(self.rows), column_mapping=mapping)

    def rebind_clock(self):
        self.collection['clock_evidence'] = self.write('clock.json', dict(dataset_id='synthetic_time', findings='Synthetic only', timestamp_policy=self.policy))
        self.manifest['collection'] = self.write('collection.json', self.collection)

    def load(self):
        return fc.load_full_sequence(self.root, self.manifest, self.collection, self.normalizer, fc.instant(FREEZE['frozen_at_utc']))

    def authority(self):
        source = self.write('exporter_config.json', dict(timestamp_timezone='Asia/Seoul'))
        authority = dict(schema_version=te.AUTHORITY_SCHEMA, dataset_id='synthetic_time',
                         collector_id='synthetic', collector_version='fixture-v1', raw_files=self.policy['raw_files'],
                         timestamp_column='event_time', timezone='Asia/Seoul', authority='Synthetic exporter configuration',
                         reviewer='synthetic-reviewer', findings='Synthetic only', recorded_at_utc='2026-11-10T00:01:00Z',
                         source_artifacts=[source])
        self.policy['timezone_authority'] = self.write('authority.json', authority)
        self.policy['payload_sources'] = []
        self.rebind_clock()
        return authority

    def test_complete_sequence_keeps_frozen_features_and_raw_bytes(self):
        path = self.root / self.raw['path']
        before = path.read_bytes()
        _, standards, _ = fc.raw_rows(path, self.normalizer)
        events, provenance, _, _ = self.load()
        self.assertEqual(events, [dict(id='fixture-event', features={k: standards[0][k] for k in ('case_id', 'activity', 'ts')})])
        self.assertEqual(provenance['fixture-event']['raw_event_timestamp'], self.rows[0]['event_time'])
        self.assertEqual(provenance['fixture-event']['validated_event_timestamp_utc'], fc.instant(UTC).isoformat())
        self.assertEqual(provenance['fixture-event']['timestamp_evidence_sha256'], self.collection['clock_evidence']['sha256'])
        self.assertEqual(path.read_bytes(), before)

    def test_session_and_task_use_resolved_utc_and_still_enforce_bounds(self):
        self.load()
        for kind in ['sessions', 'tasks']:
            ref = self.collection[kind]
            data = json.loads((self.root / ref['path']).read_text())
            data[kind][0]['started_at_utc'] = '2026-11-10T00:00:00.500Z'
            self.collection[kind] = self.write(kind + '.json', data)
            with self.subTest(kind=kind), self.assertRaisesRegex(EvaluationError, 'EVENT_OUTSIDE_SESSION_TASK'):
                self.load()
            data[kind][0]['started_at_utc'] = '2026-11-10T00:00:00Z'
            self.collection[kind] = self.write(kind + '.json', data)

    def test_policy_hash_and_exact_raw_binding_required(self):
        self.policy['raw_files'][0]['sha256'] = 'wrong'
        self.rebind_clock()
        with self.assertRaisesRegex(EvaluationError, 'RAW_BINDING_MISMATCH'):
            self.load()
        (self.root / self.collection['clock_evidence']['path']).write_text('{}')
        with self.assertRaisesRegex(EvaluationError, 'HASH_MISMATCH'):
            self.load()

    def test_collection_timezone_alone_never_authorizes_naive_rows(self):
        self.policy = None
        self.rebind_clock()
        with self.assertRaisesRegex(EvaluationError, 'TIMEZONE_REQUIRED'):
            self.load()

    def test_no_sources_or_authority_fails(self):
        self.policy['payload_sources'] = []
        self.rebind_clock()
        with self.assertRaisesRegex(EvaluationError, 'TIMEZONE_EVIDENCE_REQUIRED'):
            self.load()

    def test_policy_schema_paths_and_timezone_conflicts_fail(self):
        original = copy.deepcopy(self.policy)
        mutations = [lambda p: p.update(schema_version='other'), lambda p: p.update(timezone='UTC'),
                     lambda p: p.update(timestamp_column='other'),
                     lambda p: p['payload_sources'][0].pop('event_id_path'),
                     lambda p: p['payload_sources'][0].update(session_id_path=[]),
                     lambda p: p['payload_sources'][0]['timestamps'][0].update(format='guess'),
                     lambda p: p['payload_sources'][0]['timestamps'][0].update(path=[])]
        for change in mutations:
            self.policy = copy.deepcopy(original)
            change(self.policy)
            self.rebind_clock()
            with self.assertRaises(EvaluationError):
                self.load()

    def test_authority_supports_no_payload_and_requires_hash_verified_sources(self):
        authority = self.authority()
        self.assertEqual(self.load()[1]['fixture-event']['timestamp_resolution_method'], 'timezone_authority')
        (self.root / authority['source_artifacts'][0]['path']).write_text('changed')
        with self.assertRaisesRegex(EvaluationError, 'HASH_MISMATCH'):
            self.load()

    def test_authority_requires_identity_binding_and_substantive_record(self):
        original = self.authority()
        for field, value in [('dataset_id', 'other'), ('collector_version', 'other'), ('timezone', 'UTC'),
                             ('raw_files', []), ('source_artifacts', []), ('reviewer', ''),
                             ('recorded_at_utc', '2026-11-10T00:01:00')]:
            damaged = dict(original, **{field: value})
            self.policy['timezone_authority'] = self.write('authority.json', damaged)
            self.rebind_clock()
            with self.subTest(field=field), self.assertRaises(EvaluationError):
                self.load()

    def test_authority_cannot_escape_bundle(self):
        authority = self.authority()
        outside = self.root / 'outside.json'
        outside.write_text('original')
        authority['source_artifacts'] = [dict(path='outside.json', sha256=fc.sha(outside))]
        self.policy['timezone_authority'] = self.write('authority.json', authority)
        self.rebind_clock()
        with self.assertRaisesRegex(EvaluationError, 'OUTSIDE_HELDOUT_BUNDLE'):
            self.load()

    def test_postfreeze_is_still_checked_on_resolved_utc(self):
        with self.assertRaisesRegex(EvaluationError, 'NOT_POST_FREEZE'):
            fc.load_full_sequence(self.root, self.manifest, self.collection, self.normalizer, fc.instant('2026-11-10T00:00:00.124Z'))

    def test_timestamp_conflict_blocks_before_adapter_or_score(self):
        self.rows[0]['event_time'] = '2026-11-10 00:00:00.123'
        self.raw = self.write_raw()
        self.collection['raw_files'] = [self.raw]
        self.policy['raw_files'] = [dict(path=self.raw['path'], sha256=self.raw['sha256'])]
        self.rebind_clock()
        with patch.object(fc, 'validate_freeze', return_value=FREEZE), patch.object(fc, 'call_adapter') as adapter, patch.object(fc, 'calculate') as score:
            with self.assertRaisesRegex(EvaluationError, 'EXPORT_PAYLOAD_CONFLICT'):
                fc.evaluate(self.root, self.manifest, CONFIG)
            adapter.assert_not_called()
            score.assert_not_called()
        self.assertFalse((self.root / 'results').exists())


if __name__ == '__main__':
    unittest.main()
