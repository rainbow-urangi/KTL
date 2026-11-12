"""Meaningful synthetic regression tests; no source artifact or CU mutation."""
import copy
import csv
import hashlib
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
import os
import subprocess
import sys
from unittest import mock
import numpy as np
from model.workflow_candidate_v1.src.analysis import segments
from model.workflow_candidate_v1.src.data import RAW_FIELDS, sanitize_raw
from model.workflow_candidate_v1_3.src.artifacts import materialize, digest
from model.workflow_candidate_v1_3.src.capture_lineage import load_capture, capture_view
from model.workflow_candidate_v1_3.src.compat import agglomerative, cluster
from model.workflow_candidate_v1_3.src.process_map import process_maps
from model.workflow_candidate_v1_3.src.adapter import canonical_for_generator
from model.workflow_candidate_v1_3.src.infer import _forward
from model.workflow_candidate_v1_3.src.infer_cli import main
from model.workflow_candidate_v1_3.src.artifacts import UPSTREAM, PINNED
from model.workflow_candidate_v1_3.src.errors import ValidationError


def event(i, **extra):
    row = dict(event_id=f'e{i}', session_id='s1', event_time=f'2026-11-09T00:00:{i:02}Z',
        event_type='DOM_EVENT', interaction_type='click', element_tag='button', api_method='',
        api_status_code='', api_path='', page_url='https://example.test/items', page_title='Rainbow',
        target_selector='button', source_dataset='synthetic')
    row.update(extra)
    return row


class CaptureFixture:
    def __init__(self, directory, rows):
        self.directory = Path(directory)
        self.csv_path = self.directory / 'events.csv'
        self.manifest_path = self.directory / 'capture-manifest.json'
        self.rows = copy.deepcopy(rows)
        for index, row in enumerate(self.rows, 1):
            row.update(id=str(index), capture_run_id='capture-synthetic', capture_tab_id='7',
                       capture_frame_id='0', capture_root_tab_id='7', capture_tab_path='[7]')
        self.manifest = dict(capture_scope_version=2, active=False, run_id='capture-synthetic',
                             target_tab_id=7, capture_tab_paths={'7': [7]})
        sequences = {}
        evidence = []
        for index, row in enumerate(self.rows, 1):
            sid = row['session_id']
            sequences[sid] = sequences.get(sid, 0) + 1
            evidence.append(dict(csv_row=index, tab_id=7, frame_id=0, event_sequence=sequences[sid],
                event_id=row['event_id'], session_id=sid, event_time=row['event_time']))
        self.manifest['event_evidence'] = evidence
        self.save()

    def save(self):
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(self.rows)
        raw = stream.getvalue().encode('utf-8-sig')
        self.csv_path.write_bytes(raw)
        self.manifest.update(csv_sha256=digest(raw), csv_byte_count=len(raw), columns=list(self.rows[0]), event_count=len(self.rows))
        self.manifest_path.write_text(json.dumps(self.manifest), encoding='utf-8')

    def load(self):
        return load_capture(self.csv_path, self.manifest_path)

    def analysis(self, *, split=True):
        streams = []
        for sid in dict.fromkeys(row['session_id'] for row in self.rows):
            streams.append([sanitize_raw(row, 'raw_input') for row in self.rows if row['session_id'] == sid])
        cuts = [[False] + [split] * (len(stream) - 1) for stream in streams]
        workflows = segments(streams, cuts)
        labels = np.arange(len(workflows), dtype=int)
        vectors = np.eye(len(workflows))
        tables = process_maps(workflows, labels, streams, vectors)
        canonical = [canonical_for_generator(tables, row['process_model_id']) for row in tables['process_models']]
        return dict(workflows=workflows, tables=tables, canonical=[row for row in canonical if row])


class ArtifactTests(unittest.TestCase):
    def test_exact_pinned_reproduction_preserves_original_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'source'
            source.mkdir()
            original = b'{\r\n  "value": 1\r\n}\r\n'
            canonical = original.replace(b'\r\n', b'\n')
            (source / 'settings.json').write_bytes(original)
            (source / 'weights.pt').write_bytes(b'synthetic binary')
            expected = {'settings.json': digest(canonical), 'weights.pt': digest(b'synthetic binary')}
            manifest = json.dumps({'artifact_sha256': expected}).encode()
            (source / 'model_manifest.json').write_bytes(manifest)
            proof = materialize(source, root / 'new-stage', expected=expected)
            self.assertEqual((source / 'settings.json').read_bytes(), original)
            self.assertEqual((root / 'new-stage/settings.json').read_bytes(), canonical)
            self.assertEqual((root / 'new-stage/model_manifest.json').read_bytes(), manifest)
            self.assertEqual(proof['files'][0]['method'], 'EXACT_PINNED_CRLF_TO_LF_REPRODUCTION')
            with self.assertRaisesRegex(ValueError, 'new directory'):
                materialize(source, root / 'new-stage', expected=expected)

    def test_semantic_json_and_binary_changes_do_not_become_valid(self):
        for name, actual, pinned in [('a.json', b'{"x":2}\r\n', b'{"x":1}\n'), ('m.pt', b'bad\r\n', b'bad\n')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                source = root / 'source'
                source.mkdir()
                (source / name).write_bytes(actual)
                expected = {name: digest(pinned)}
                (source / 'model_manifest.json').write_text(json.dumps({'artifact_sha256': expected}))
                with self.assertRaises(ValueError):
                    materialize(source, root / 'stage', expected=expected)
                self.assertFalse((root / 'stage').exists())

    def test_manifest_cannot_change_pinned_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'model_manifest.json').write_text(json.dumps({'artifact_sha256': {'x.json': 'f' * 64}}))
            with self.assertRaisesRegex(ValueError, 'pinned artifact contract'):
                materialize(root, root.parent / ('uncreated-' + root.name), expected={'x.json': '0' * 64})

    def test_stage_inside_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'new directory'):
                materialize(d, Path(d) / 'child')


class CompatibilityTests(unittest.TestCase):
    def test_old_and_new_distance_aliases_preserve_parameters(self):
        class Old:
            def __init__(self, n_clusters, distance_threshold, linkage, affinity):
                self.args = (n_clusters, distance_threshold, linkage, affinity)
        class New:
            def __init__(self, n_clusters, distance_threshold, linkage, metric):
                self.args = (n_clusters, distance_threshold, linkage, metric)
        self.assertEqual(agglomerative(.35, estimator=Old).args, (None, .35, 'average', 'cosine'))
        self.assertEqual(agglomerative(.35, estimator=New).args, (None, .35, 'average', 'cosine'))

    def test_installed_sklearn_real_geometry(self):
        x = np.array([[1., 0., .01], [1., 0., 0.], [0., 1., .01], [0., 1., 0.]])
        x /= np.linalg.norm(x, axis=1, keepdims=True)
        labels, result = cluster(x, {'cluster_distance_thresholds': [.15, .35]})
        self.assertEqual(labels[0], labels[1])
        self.assertEqual(labels[2], labels[3])
        self.assertNotEqual(labels[0], labels[2])
        self.assertEqual([row['threshold'] for row in result['candidates']], [.15, .35])


class MedoidTests(unittest.TestCase):
    def test_empty_workflow_is_not_the_medoid_even_when_geometrically_central(self):
        streams = [[event(0, interaction_type='page_close')], [event(1)], [event(2)]]
        workflows = segments(streams, [[False]] * 3)
        x = np.array([[1., 0.], [.8, .6], [.8, -.6]])
        tables = process_maps(workflows, np.zeros(3, dtype=int), streams, x)
        row = tables['process_models'][0]
        self.assertEqual(row['canonical_instance_id'], 'WF-0002')
        self.assertEqual(row['eligible_canonical_instance_ids'], ['WF-0002', 'WF-0003'])
        self.assertEqual(len(tables['process_instances']), 3)

    def test_lifecycle_only_cluster_remains_explicit_and_has_no_canonical(self):
        streams = [[event(0, interaction_type='collector_boot')]]
        tables = process_maps(segments(streams, [[False]]), np.array([0]), streams, np.ones((1, 2)))
        self.assertEqual(tables['process_models'][0]['canonical_status'], 'NO_ACTIONFUL_WORKFLOW')
        self.assertIsNone(canonical_for_generator(tables, 'PM-001'))
        self.assertEqual(tables['process_instances'][0]['event_count'], 1)

    def test_aba_preserves_node_revisit_and_event_evidence(self):
        events = [event(i, interaction_type='api_transaction', api_method=method,
                        api_path='/api/items', api_status_code='200') for i, method in enumerate(('GET', 'POST', 'GET'))]
        tables = process_maps(segments([events], [[False] * 3]), np.array([0]), [events], np.ones((1, 2)))
        canonical = canonical_for_generator(tables, 'PM-001')['procedures']
        self.assertEqual([p['http_method'] for p in canonical], ['GET', 'POST', 'GET'])
        self.assertEqual(canonical[0]['id'], canonical[2]['id'])
        self.assertEqual([p['evidence'] for p in canonical], [['e0'], ['e1'], ['e2']])


class CaptureTests(unittest.TestCase):
    def test_multiple_sessions_and_models_preserve_whole_observed_execution(self):
        rows = [event(0, interaction_type='page_close'), event(1, session_id='s2', interaction_type='collector_boot'),
                event(2, session_id='s2', interaction_type='page_view'), event(3, session_id='s2'),
                event(4, session_id='s2', interaction_type='page_close'),
                event(5, session_id='s3', interaction_type='collector_boot'),
                event(6, session_id='s3', interaction_type='page_view'), event(7, session_id='s3')]
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, rows)
            capture = fixture.load()
            result = capture_view(capture, fixture.analysis())
            procedures = result['canonical']['procedures']
            self.assertEqual([p['evidence'] for p in procedures], [['e2'], ['e3'], ['e6'], ['e7']])
            self.assertEqual(len(result['lineage']), 8)
            self.assertEqual(len(result['transitions']), 2)
            self.assertEqual(result['diagnostics']['capture_canonical_event_count'], 4)
            self.assertTrue(result['process_model']['process_model_id'].startswith('CAPTURE-PM-'))
            self.assertGreater(len(result['canonical']['source_process_model_ids']), 1)
            self.assertEqual({p['source_session_id'] for p in procedures}, {'s2', 's3'})
            self.assertEqual({row['session_id'] for row in fixture.rows}, {'s1', 's2', 's3'})

    def test_timestamp_inversion_does_not_reorder_capture_procedures(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, [event(2), event(1, interaction_type='api_transaction', api_path='/api/items', api_method='GET', api_status_code='200')])
            result = capture_view(fixture.load(), fixture.analysis())
            self.assertEqual([p['evidence'] for p in result['canonical']['procedures']], [['e2'], ['e1']])
            self.assertFalse(result['diagnostics']['timestamp_reordering'])

    def test_only_adjacent_same_signature_within_same_workflow_is_compressed(self):
        rows = [event(i, interaction_type='api_transaction', api_path='/api/items', api_method=m,
                      api_status_code='200') for i, m in enumerate(('GET', 'GET', 'POST', 'GET'))]
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, rows)
            result = capture_view(fixture.load(), fixture.analysis(split=False))
            p = result['canonical']['procedures']
            self.assertEqual([x['http_method'] for x in p], ['GET', 'POST', 'GET'])
            self.assertEqual(p[0]['evidence'], ['e0', 'e1'])
            self.assertEqual(p[0]['source_csv_rows'], [1, 2])
            self.assertEqual(p[0]['id'], p[2]['id'])

    def test_lifecycle_does_not_break_existing_actionful_subsequence_compression(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, [event(1), event(2, interaction_type='screen_change'), event(3)])
            result = capture_view(fixture.load(), fixture.analysis(split=False))
            self.assertEqual(len(result['canonical']['procedures']), 1)
            self.assertEqual(result['canonical']['procedures'][0]['evidence'], ['e1', 'e3'])
            self.assertEqual(result['canonical']['procedures'][0]['source_csv_rows'], [1, 3])
            self.assertEqual(len(result['lineage']), 3)
            self.assertEqual(result['diagnostics']['excluded_events'][0]['csv_row'], 2)

    def test_forged_bytes_or_row_binding_are_rejected(self):
        for field in ('hash', 'event_id', 'session_id', 'event_time', 'csv_row', 'tab_id', 'frame_id'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                fixture = CaptureFixture(d, [event(1)])
                if field == 'hash':
                    fixture.manifest['csv_sha256'] = '0' * 64
                else:
                    fixture.manifest['event_evidence'][0][field] = 'wrong'
                fixture.manifest_path.write_text(json.dumps(fixture.manifest))
                with self.assertRaises(ValueError):
                    fixture.load()

    def test_unproven_session_join_is_rejected(self):
        variants = [
            [event(1), event(2, session_id='s2', interaction_type='collector_boot'), event(3, session_id='s2', interaction_type='page_view')],
            [event(1, interaction_type='page_close'), event(2, session_id='s2', interaction_type='page_view')],
            [event(1, interaction_type='page_close'), event(2, session_id='s2', interaction_type='collector_boot'),
             event(3, session_id='s2', interaction_type='page_view'), event(4)],
        ]
        for rows in variants:
            with self.subTest(rows=len(rows)), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):
                    CaptureFixture(d, rows).load()

    def test_concurrent_frame_or_tab_tree_is_rejected(self):
        for change in ('frame', 'tree', 'root'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                fixture = CaptureFixture(d, [event(1), event(2)])
                if change == 'frame':
                    fixture.rows[1]['capture_frame_id'] = '1'
                    fixture.manifest['event_evidence'][1]['frame_id'] = 1
                elif change == 'tree':
                    fixture.manifest['capture_tab_paths']['8'] = [7, 8]
                else:
                    fixture.rows[1]['capture_root_tab_id'] = '8'
                fixture.save()
                with self.assertRaises(ValueError):
                    fixture.load()

    def test_local_sequence_can_reset_across_sessions_but_cannot_reverse_within_one(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, [event(1), event(2)])
            fixture.manifest['event_evidence'][1]['event_sequence'] = 1
            fixture.save()
            with self.assertRaisesRegex(ValueError, 'duplicated or reversed'):
                fixture.load()

    def test_empty_capture_is_not_invented_into_a_procedure(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, [event(1, interaction_type='collector_boot')])
            with self.assertRaisesRegex(ValueError, 'actionful source events'):
                capture_view(fixture.load(), fixture.analysis())

    def test_missing_model_action_evidence_is_not_filled_from_raw_rows(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, [event(1), event(2)])
            analysis = fixture.analysis()
            analysis['tables']['process_steps'].pop()
            with self.assertRaisesRegex(ValueError, 'omit or add actionful'):
                capture_view(fixture.load(), analysis)

    def test_model_features_stay_twelve_fields_and_do_not_consume_capture_sidecar(self):
        base = event(1)
        changed = dict(base, capture_run_id='new-capture', business_unit_id='different', reference='must-not-enter',
                       source_csv_rows=[999], workflow_index='private')
        self.assertEqual(sanitize_raw(base, 'raw_input'), sanitize_raw(changed, 'raw_input'))
        self.assertEqual(len(RAW_FIELDS), 12)


class ForwardEvidenceTests(unittest.TestCase):
    def test_normal_cli_synthetic_capture_actual_pinned_weight_forward(self):
        """A synthetic-input product CLI run, separate from the CU real-data trial."""
        with tempfile.TemporaryDirectory() as d:
            fixture = CaptureFixture(d, [event(1, interaction_type='page_view'), event(2),
                event(3, interaction_type='api_transaction', api_method='GET', api_path='/api/items', api_status_code='200')])
            before = {name: digest((UPSTREAM / name).read_bytes()) for name in PINNED}
            output = Path(d) / 'actual-product-cli.json'
            command = [sys.executable, '-X', 'utf8', '-B', '-m', 'model.workflow_candidate_v1_3.src.infer_cli',
                       '--events', str(fixture.csv_path), '--capture-manifest', str(fixture.manifest_path), '--output', str(output)]
            result = subprocess.run(command, cwd=Path(__file__).resolve().parents[3],
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1'),
                capture_output=True, text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(output.read_text(encoding='utf-8'))
            self.assertTrue(actual['forward_evidence']['completed'])
            self.assertEqual(actual['forward_evidence']['boundary_forward_calls'], 1)
            self.assertEqual(actual['forward_evidence']['representation_forward_calls'], 1)
            self.assertEqual(actual['capture_view']['diagnostics']['capture_canonical_event_count'], 3)
            self.assertEqual(before, {name: digest((UPSTREAM / name).read_bytes()) for name in PINNED})

    def test_cli_failure_preserves_fixed_stage_and_reason_without_raw_input(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'result.json'
            with mock.patch('model.workflow_candidate_v1_3.src.infer_cli.materialize', return_value={}), \
                    mock.patch('model.workflow_candidate_v1_3.src.infer_cli.infer_capture',
                               side_effect=ValidationError(
                                   'CAPTURE_PROVENANCE_INVALID', 'Capture CSV bytes do not match the manifest')), \
                    mock.patch('sys.stderr', new_callable=io.StringIO) as stderr:
                self.assertEqual(main(['--events', 'private-name.csv', '--capture-manifest', 'private-name.json', '--output', str(output)]), 1)
            value = json.loads(stderr.getvalue())
            self.assertEqual(value['failure_code'], 'CAPTURE_PROVENANCE_INVALID')
            self.assertNotIn('private-name', stderr.getvalue())
            self.assertFalse(output.exists())

    def test_only_completed_callbacks_count_as_forward_evidence(self):
        class Model:
            def register_forward_hook(self, callback):
                self.callback = callback
                return mock.Mock(remove=lambda: None)
        model = Model()
        def called(m, streams, config):
            for _ in streams:
                m.callback()
            return 'synthetic-callback-result'
        self.assertEqual(_forward(model, called, [[1], [2]], {}), ('synthetic-callback-result', 2))
        with self.assertRaisesRegex(ValueError, 'forward evidence'):
            _forward(model, lambda *_: [], [[1]], {})

    def test_cli_uses_product_pipeline_without_monkeypatching_dependencies(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'result.json'
            result = dict(candidate_id='workflow_candidate_v1_3', policy_sha256='f' * 64,
                          workflows=[], tables={'process_models': []}, capture_view={'canonical': {'procedures': []}})
            with mock.patch('model.workflow_candidate_v1_3.src.infer_cli.materialize', return_value={'test_fixture': True}) as stage, \
                    mock.patch('model.workflow_candidate_v1_3.src.infer_cli.infer_capture', return_value=result) as infer, \
                    mock.patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(main(['--events', 'synthetic.csv', '--capture-manifest', 'synthetic.json', '--output', str(output)]), 0)
            self.assertEqual(stage.call_count, 1)
            self.assertEqual(infer.call_count, 1)
            self.assertNotIn('forward_evidence', json.loads(output.read_text()))


if __name__ == '__main__':
    unittest.main()
