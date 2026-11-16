"""Temporary synthetic fixtures ONLY. Never labels or predicts a real new raw file."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import m05_full_context as fc
from backend.m05_full_context_csv import recalculate_csv
from backend.m05_baseline_adapter import load_rules, predict
from backend.evaluators import EvaluationError
from scripts.recalculate_m05_full_context_csv import verify

REPO = Path(__file__).resolve().parents[1]
CONFIG = json.loads((REPO / 'evaluation_contracts/m05_engine.json').read_text())
FREEZE = json.loads((REPO / fc.FREEZE_PATH).read_text())


class Fixture:
    def __init__(self, root, count=300):
        self.root = root
        self.base = 'data/held_out/m05/synthetic_only/'
        self.normalizer = fc.frozen_normalizer(FREEZE)
        self.start = '2026-11-10T00:00:00+00:00'
        self.end = '2026-11-10T00:10:00+00:00'
        self.locked = '2026-11-10T00:11:00+00:00'
        self.reviewed = '2026-11-10T00:12:00+00:00'
        self.rows = []
        for i in range(count):
            self.rows.append(dict(event_id='synthetic-' + str(i), task_id='101', session_id='synthetic-session',
                                 event_time=f'2026-11-10T00:{i // 60:02}:{i % 60:02}+00:00', activity='ACT-' + str(i)))
        self.rows[0]['activity'] = self.rows[1]['activity'] = 'CONTEXT_A'
        for i in (2, 3, 4):
            self.rows[i]['activity'] = 'API:GET_/static/fixture_2xx'
        self.raw = self.csv(self.base + 'raw/events.csv', self.rows)
        mapping = dict(case_id='task_id', source_event_pk='event_id', ts='event_time', activity='activity')
        self.raw.update(row_count=count, column_mapping=mapping)
        ids = [r['event_id'] for r in self.rows]
        common = dict(event_ids=ids, complete=True, completion_evidence='Synthetic completion only',
                      started_at_utc=self.start, ended_at_utc=self.end, source_session_id='synthetic-session')
        sessions = self.write(self.base + 'sessions.json', {'sessions': [common]})
        tasks = self.write(self.base + 'tasks.json', {'tasks': [dict(common, source_case_id='101')]})
        evidence = self.write(self.base + 'collection_evidence.json', {'dataset_id': 'synthetic_only', 'findings': 'Synthetic collector proof'})
        self.collection = dict(dataset_id='synthetic_only', scope='COMPLETE_SESSIONS_AND_TASKS',
                               collection_started_at_utc=self.start, collection_ended_at_utc=self.end,
                               collector_id='synthetic', collector_version='fixture', timezone='UTC',
                               completion_reason='Synthetic test only', clock_evidence=evidence, export_evidence=evidence,
                               raw_files=[self.raw], event_count=count, sessions=sessions, tasks=tasks)
        self.manifest = dict(schema_version=fc.SCHEMA, dataset_id='synthetic_only', used_for_training=False,
                             used_for_development=False, collection=self.write(self.base + 'collection.json', self.collection))
        events, provenance, raw_sha, _ = fc.load_full_sequence(root, self.manifest, self.collection, self.normalizer, fc.instant(FREEZE['frozen_at_utc']))
        self.events, self.provenance, self.raw_sha = events, provenance, raw_sha
        self.labels = []
        categories = ['duplicate'] * 3 + ['noise'] * 3 + ['repeated_action'] * 2 + ['irrelevant_action'] * 2
        for i in range(1, 21):
            p = provenance[ids[i]]
            self.labels.append(dict(event_id=ids[i], expected_label='REMOVE' if i <= 10 else 'KEEP',
                                    remove_category=categories[i - 1] if i <= 10 else '', held_out='true',
                                    **{k: p[k] for k in fc.PROVENANCE_FIELDS}, label_rationale='Independent synthetic fixture label',
                                    labeler='synthetic-labeler', labeled_at_utc=self.locked))
        self.manifest['target_labels'] = self.csv(self.base + 'labels.csv', self.labels, fc.LABEL_FIELDS)
        self.manifest['target_selection'] = self.write(self.base + 'selection.json', dict(event_ids=ids[1:21], raw_sequence_sha256=raw_sha, selection_principle='Synthetic fixed first 20 after context'))
        self.lock = dict(target_labels_sha256=self.manifest['target_labels']['sha256'],
                         target_selection_sha256=self.manifest['target_selection']['sha256'], raw_sequence_sha256=raw_sha,
                         normalized_input_sha256=fc.digest({'events': events}), locked_at_utc=self.locked,
                         prediction_blind=True, labeler='synthetic-labeler')
        self.manifest['label_lock'] = self.write(self.base + 'lock.json', self.lock)
        access = self.write(self.base + 'access_log.json', dict(raw_sequence_sha256=raw_sha, entries=[], coverage_started_at_utc=self.start, coverage_ended_at_utc=self.reviewed))
        self.access_audit = dict(label_lock_sha256=self.manifest['label_lock']['sha256'], raw_sequence_sha256=raw_sha,
                                 coverage_complete=True, prediction_runs=[], prediction_views=[],
                                 method='EXECUTION_AND_ACCESS_LOG_RECONCILIATION', findings='Synthetic only', reviewer='synthetic-auditor',
                                 reviewed_until_utc=self.reviewed, source_logs=[access])
        self.manifest['prediction_access_audit'] = self.write(self.base + 'access_audit.json', self.access_audit)
        historical = self.csv('data/development/synthetic_history/events.csv', [dict(self.rows[0], event_id='old-synthetic', task_id='999', event_time='2026-11-01T00:00:00+00:00')])
        _, standards, _ = fc.raw_rows(root / historical['path'], self.normalizer)
        history_events = [{'event_id': r['source_event_pk'], 'feature_sha256': fc.digest({k: r[k] for k in ('case_id', 'activity', 'ts')})} for r in standards]
        histories = [self.write('synthetic_' + scope + '.json', dict(scope=scope, source_files=[historical], events=history_events)) for scope in ('training', 'development')]
        audit = self.write('synthetic_history_audit.json', dict(raw_sequence_sha256=raw_sha, inventory_sha256=[h['sha256'] for h in histories], method='SOURCE_HISTORY_RECONCILIATION', coverage_complete=True, findings='Synthetic history audit'))
        self.manifest['provenance'] = dict(reviewer='synthetic-preparer', reviewed_at_utc=self.reviewed, complete_history_attested=True,
                                          training_inventories=histories[:1], development_inventories=histories[1:], audit_evidence=[audit])
        (root / 'evaluation_contracts').mkdir(exist_ok=True)
        (root / 'evaluation_contracts/m05_engine.json').write_text(json.dumps(CONFIG))
        self.approve()

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))
        return {'path': name, 'sha256': fc.sha(path)}

    def csv(self, name, rows, fields=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return {'path': name, 'sha256': fc.sha(path)}

    def approve(self):
        binding = dict(manifest_sha256=fc.digest(self.manifest), raw_sequence_sha256=self.raw_sha,
                       normalized_input_sha256=fc.digest({'events': self.events}), engine_freeze_sha256=fc.FREEZE_SHA256)
        self.approval = dict(status='PASS', binding=binding, reviewer='synthetic-independent-reviewer',
                             evidence_review='SOURCE_COMPLETENESS_POST_FREEZE_HISTORY_AND_BLIND_LABEL_LOCK', reviewed_at_utc=self.reviewed)
        self.write(fc.APPROVALS_PATH, {'approvals': [self.approval]})
        self.write(self.base + 'manifest.json', self.manifest)


class M05FullContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fx = Fixture(self.root)
        self.patch_freeze = patch.object(fc, 'validate_freeze', return_value=FREEZE)
        self.patch_freeze.start()
        self.addCleanup(self.patch_freeze.stop)

    def validate(self):
        return fc.validate_bundle(self.root, self.fx.manifest, CONFIG)

    def test_full_sequence_preserved_and_targets_separate(self):
        prepared = self.validate()
        self.assertEqual(len(prepared['events']), 300)
        self.assertEqual(len(prepared['targets']), 20)
        self.assertEqual(prepared['events'], self.fx.events)
        self.assertEqual(set(prepared['events'][0]), {'id', 'features'})
        self.assertEqual(set(prepared['events'][0]['features']), {'case_id', 'activity', 'ts'})

    def test_full_context_effect_and_single_batch_csv(self):
        from backend.evaluators import call_adapter
        with patch.object(fc, 'call_adapter', wraps=call_adapter) as adapter:
            result, rows = fc.evaluate(self.root, self.fx.manifest, CONFIG)
            self.assertEqual(adapter.call_count, 1)
            self.assertEqual(len(adapter.call_args.args[2]['events']), 300)
            self.assertEqual(len(rows), 20)
            self.assertEqual(rows[0]['predicted_label'], 'REMOVE')
            self.assertEqual(rows[0]['duplicate_of_event_id'], 'synthetic-0')
            self.assertEqual(result['context_event_count'], 280)
            self.assertEqual(sum(result[k] for k in ('TP', 'FP', 'FN', 'TN')), 20)
            self.assertIsNone(result['official_pass'])
            self.assertEqual(verify(self.root / 'results/development/m05_full_context' / result['run_id'])['status'], 'PASS')
            rules, _ = load_rules(CONFIG['model_artifact']['path'])
            isolated = predict(self.fx.events[1:21], rules)
            self.assertEqual(isolated['predictions'][0]['label'], 'KEEP')
            with self.assertRaisesRegex(EvaluationError, 'ALREADY_ATTEMPTED'):
                fc.evaluate(self.root, self.fx.manifest, CONFIG)
            self.assertEqual(adapter.call_count, 1)

    def test_missing_approval_blocks_before_adapter_and_score(self):
        (self.root / fc.APPROVALS_PATH).unlink()
        with patch.object(fc, 'call_adapter') as adapter, patch.object(fc, 'calculate') as score:
            with self.assertRaisesRegex(EvaluationError, 'APPROVAL_MISSING'):
                fc.evaluate(self.root, self.fx.manifest, CONFIG)
            adapter.assert_not_called()
            score.assert_not_called()

    def test_locked_content_tamper_blocks(self):
        path = self.root / self.fx.manifest['target_labels']['path']
        path.write_text(path.read_text().replace('REMOVE', 'KEEP', 1))
        with self.assertRaisesRegex(EvaluationError, 'HASH_MISMATCH'):
            self.validate()

    def test_contract_and_provenance_fail_closed(self):
        mutations = [('held_out', 'True'), ('expected_label', 'KEEP'), ('remove_category', 'irrelevant_action'),
                     ('source_session_id', 'wrong'), ('raw_sequence_index', '999'), ('csv_record_number', '0'),
                     ('event_id', 'missing'), ('label_rationale', ''), ('labeler', 'other')]
        original = copy.deepcopy(self.fx.labels)
        for key, value in mutations:
            with self.subTest(key=key):
                labels = copy.deepcopy(original)
                labels[0][key] = value
                self.fx.manifest['target_labels'] = self.fx.csv(self.fx.base + 'labels.csv', labels, fc.LABEL_FIELDS)
                self.fx.lock['target_labels_sha256'] = self.fx.manifest['target_labels']['sha256']
                self.fx.manifest['label_lock'] = self.fx.write(self.fx.base + 'lock.json', self.fx.lock)
                with self.assertRaises(EvaluationError):
                    self.validate()

    def test_postfreeze_and_completeness(self):
        original = copy.deepcopy(self.fx.collection)
        for key, value in [('collection_started_at_utc', '2026-11-01T00:00:00+00:00'),
                           ('collection_started_at_utc', '2026-11-10T00:00:00'),
                           ('event_count', 20), ('scope', 'TARGET_WINDOWS_ONLY')]:
            with self.subTest(key=key):
                collection = dict(original, **{key: value})
                self.fx.manifest['collection'] = self.fx.write(self.fx.base + 'collection.json', collection)
                with self.assertRaises(EvaluationError):
                    self.validate()

    def test_case_collision_and_row_loss(self):
        rows = copy.deepcopy(self.fx.rows)
        rows[100]['session_id'] = 'different-session-same-task'
        ref = self.fx.csv(self.fx.base + 'raw/events.csv', rows)
        self.fx.raw['sha256'] = ref['sha256']
        with self.assertRaisesRegex(EvaluationError, 'CASE_ID_COLLISION'):
            fc.load_full_sequence(self.root, self.fx.manifest, self.fx.collection, self.fx.normalizer, fc.instant(FREEZE['frozen_at_utc']))

    def test_missing_independent_logs_or_changed_label_lock(self):
        self.fx.access_audit['prediction_views'] = ['seen-before-lock']
        self.fx.manifest['prediction_access_audit'] = self.fx.write(self.fx.base + 'access_audit.json', self.fx.access_audit)
        self.fx.approve()
        with self.assertRaisesRegex(EvaluationError, 'BLINDNESS'):
            self.validate()

    def test_history_overlap_or_stale_registry_rejected(self):
        path = self.root / 'data/development/synthetic_history/events.csv'
        path.write_text(path.read_text().replace('old-synthetic', 'synthetic-0'))
        with self.assertRaises(EvaluationError):
            self.validate()
        self.fx.manifest['used_for_training'] = True
        with self.assertRaisesRegex(EvaluationError, 'PRIOR_USE'):
            self.validate()

    def test_bad_predictions_persist_attempt_without_score(self):
        with patch.object(fc, 'call_adapter', return_value={'model_version': CONFIG['cleaning_model_version'], 'predictions': []}), patch.object(fc, 'calculate') as score:
            with self.assertRaisesRegex(EvaluationError, 'PREDICTION_ID_MISMATCH'):
                fc.evaluate(self.root, self.fx.manifest, CONFIG)
            score.assert_not_called()
        directory = next(p for p in (self.root / 'results/development/m05_full_context').iterdir() if p.name != 'attempts')
        self.assertTrue((directory / 'attempt.json').is_file())
        self.assertTrue((directory / 'blocked.json').is_file())
        self.assertFalse((directory / 'evidence.csv').exists())
        with self.assertRaisesRegex(EvaluationError, 'ALREADY_ATTEMPTED'):
            fc.evaluate(self.root, self.fx.manifest, CONFIG)

    def test_output_id_validation_and_category_independence(self):
        rules, _ = load_rules(CONFIG['model_artifact']['path'])
        response = predict(self.fx.events, rules)
        for mutate in (lambda p: p.pop(), lambda p: p.append(p[0]), lambda p: p[0].update(id='other'),
                       lambda p: p[0].update(label='MAYBE'), lambda p: p[0].update(source_row_index=99)):
            damaged = copy.deepcopy(response)
            mutate(damaged['predictions'])
            with self.assertRaises(EvaluationError):
                fc.validate_predictions(damaged, self.fx.events, CONFIG)
        # GT semantic category differs from engine reason, still binary TP.
        with patch.object(fc, 'call_adapter', return_value=response):
            result, rows = fc.evaluate(self.root, self.fx.manifest, CONFIG)
        self.assertEqual(rows[1]['remove_category'], 'duplicate')
        self.assertEqual(rows[1]['remove_reason'], 'drop_prefix')
        self.assertEqual(rows[1]['classification'], 'TP')
        evidence = fc.csv_text(rows)
        self.assertEqual(recalculate_csv(evidence)['f1'], result['f1'])
        rows.append(dict(rows[0], event_id='context-extra'))
        with self.assertRaises(ValueError):
            recalculate_csv(fc.csv_text(rows))

    def test_changed_approval_cannot_reopen_exposed_input(self):
        fc.evaluate(self.root, self.fx.manifest, CONFIG)
        self.fx.manifest['annotation_note'] = 'New metadata must not authorize a rerun'
        self.fx.approve()
        with patch.object(fc, 'call_adapter') as adapter:
            with self.assertRaisesRegex(EvaluationError, 'ALREADY_ATTEMPTED'):
                fc.evaluate(self.root, self.fx.manifest, CONFIG)
            adapter.assert_not_called()

    def test_approval_is_exact_and_reviewer_independent(self):
        self.fx.approval['reviewer'] = 'synthetic-labeler'
        self.fx.write(fc.APPROVALS_PATH, {'approvals': [self.fx.approval]})
        with self.assertRaisesRegex(EvaluationError, 'APPROVAL_MISSING'):
            self.validate()
        self.fx.approve()
        self.fx.manifest['annotation_note'] = 'Unreviewed edit'
        with self.assertRaisesRegex(EvaluationError, 'APPROVAL_MISSING'):
            self.validate()

    def test_history_overlap_reconciled_source_is_rejected(self):
        path = self.root / 'data/development/synthetic_history/events.csv'
        path.write_text(path.read_text().replace('old-synthetic', 'synthetic-0'))
        ref = self.fx.manifest['provenance']['training_inventories'][0]
        history = json.loads((self.root / ref['path']).read_text())
        history['source_files'][0]['sha256'] = fc.sha(path)
        history['events'][0]['event_id'] = 'synthetic-0'
        ref.update(self.fx.write(ref['path'], history))
        with self.assertRaisesRegex(EvaluationError, 'HELD_OUT_OVERLAP'):
            self.validate()

    def test_omitted_context_file_rejected(self):
        self.fx.csv(self.fx.base + 'raw/omitted.csv', [self.fx.rows[0]])
        with self.assertRaisesRegex(EvaluationError, 'OMITTED_RAW_FILE'):
            self.validate()

    def test_missing_or_duplicate_targets_and_keep_category(self):
        original = copy.deepcopy(self.fx.labels)
        variants = [original[:-1], original + [original[0]], [original[0]] + original[:-1],
                    original[:10] + [dict(original[10], remove_category='noise')] + original[11:]]
        for labels in variants:
            self.fx.manifest['target_labels'] = self.fx.csv(self.fx.base + 'labels.csv', labels, fc.LABEL_FIELDS)
            with self.assertRaises(EvaluationError):
                self.validate()

    def test_csv_all_keep_zero_denominator_and_tampering(self):
        rules, _ = load_rules(CONFIG['model_artifact']['path'])
        response = predict(self.fx.events, rules)
        for prediction in response['predictions']:
            prediction.update(label='KEEP', remove_reason=None, duplicate_of_event_id=None)
        with patch.object(fc, 'call_adapter', return_value=response):
            result, rows = fc.evaluate(self.root, self.fx.manifest, CONFIG)
        self.assertEqual([result[k] for k in ('TP', 'FP', 'FN', 'TN')], [0, 0, 10, 10])
        self.assertEqual(result['precision'], 0)
        self.assertEqual(result['f1'], 0)
        rows[0]['classification'] = 'TP'
        with self.assertRaisesRegex(ValueError, 'Confusion'):
            recalculate_csv(fc.csv_text(rows))
        directory = self.root / 'results/development/m05_full_context' / result['run_id']
        (directory / 'evidence.csv').write_text(fc.csv_text(rows))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verify(directory)

    def test_web_measure_download_and_repeated_click(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import HTTPServer
        from backend import m05_readiness_web as web
        with patch.object(web, 'ROOT', self.root):
            server = HTTPServer(('127.0.0.1', 0), web.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = 'http://127.0.0.1:' + str(server.server_port)
                req = urllib.request.Request(url + '/measure', data=json.dumps({'dataset': 'synthetic_only'}).encode(), headers={'Content-Type': 'application/json'})
                measured = json.load(urllib.request.urlopen(req))
                self.assertEqual(measured['status'], 'COMPLETE')
                self.assertEqual(measured['full_event_count'], 300)
                evidence_url = url + '/runs/' + measured['run_id'] + '/evidence.csv'
                evidence = urllib.request.urlopen(evidence_url).read().decode()
                self.assertEqual(len(list(csv.DictReader(io.StringIO(evidence)))), 20)
                self.assertEqual(recalculate_csv(evidence)['f1'], measured['f1'])
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req)
                self.assertIn('ALREADY_ATTEMPTED', json.load(caught.exception)['reason'])
                directory = self.root / 'results/development/m05_full_context' / measured['run_id']
                (directory / 'evidence.csv').write_text('tampered')
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(evidence_url)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_web_blocks_missing_bundle_and_lists_new_schema(self):
        import threading
        import urllib.request
        import urllib.error
        from http.server import HTTPServer
        from backend import m05_readiness_web as web
        with patch.object(web, 'ROOT', self.root):
            server = HTTPServer(('127.0.0.1', 0), web.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = 'http://127.0.0.1:' + str(server.server_port)
                self.assertEqual(json.load(urllib.request.urlopen(url + '/datasets')), ['synthetic_only'])
                req = urllib.request.Request(url + '/validate', data=json.dumps({'dataset': 'synthetic_only'}).encode(), headers={'Content-Type': 'application/json'})
                ready = json.load(urllib.request.urlopen(req))
                self.assertEqual(ready['status'], 'READY')
                self.assertIsNone(ready['f1'])
                (self.root / fc.APPROVALS_PATH).unlink()
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req)
                blocked = json.load(caught.exception)
                self.assertEqual(blocked['status'], 'BLOCKED')
                self.assertIsNone(blocked['score'])
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(url + '/evidence.csv')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


class FrozenIntegrityTests(unittest.TestCase):
    def test_real_frozen_artifacts_unchanged(self):
        self.assertEqual(fc.validate_freeze(REPO, CONFIG), FREEZE)


if __name__ == '__main__':
    unittest.main()
