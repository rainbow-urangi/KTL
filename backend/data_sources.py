"""읽기 전용 데이터 source와 evaluator 공통 입력 정규화."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .evaluators import EvaluationError, REFERENCE, require, read_json, unique_ids, M02Evaluator
from .contracts import validate_business_unit, cleaning_payload
from .registry import EXTERNAL
from .official_contracts import validate_official_contract
from .m02_contracts import official_m02_inputs, validate_fixed_at


class EvaluationDataSource:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = {}
        self.m02_aliases = None
        self.started_at = datetime.now(timezone.utc)

    def prepare(self, metric):
        raise NotImplementedError


def pending(status, missing, **details):
    return {'status': status, 'details': {'missing': missing, **details}, 'inputs': None}


class V62ReferenceProvider(EvaluationDataSource):
    base = 'model/v6_2/frozen/'
    dataset_id = 'V6.2 Historical Reference'
    source_type = 'V62_FROZEN_REFERENCE'

    def __init__(self, root):
        super().__init__(root)
        self.index = read_json(self.root / 'backend/reference_manifest.json')['files']

    def read(self, relative, optional=False):
        name = self.base + relative
        path = self.root / name
        if not path.is_file():
            if optional:
                return None
            raise EvaluationError('Missing reference artifact: ' + name, 'REFERENCE_PARTIAL')
        require(path.resolve().is_relative_to((self.root / self.base).resolve()), 'Reference path escaped frozen directory')
        raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        require(self.index.get(name) == digest, 'Reference SHA-256 mismatch: ' + name)
        self.sources[name] = digest
        if name.endswith('.json'):
            return json.loads(raw)
        return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))

    def prepare(self, metric):
        if metric in EXTERNAL:
            return pending('EXTERNAL_MODULE_PENDING', ['외부 모듈 연동 예정'])
        if metric == 'M05':
            return pending('NOT_CONFIGURED', ['CleaningModelAdapter', '200-event evaluation dataset'])
        manifest = self.read('run_manifest.json')
        keys = {**REFERENCE, 'session_safe_process_instances': REFERENCE['process_instances']}
        require(all(manifest.get(k) == v for k, v in keys.items() if k != 'process_instances'), 'V6.2 reference count mismatch')
        if metric == 'M06':
            assignments = self.read('diagnostics/workflow_consensus_assignments.csv')
            require(len(assignments) == 563 and len({r['workflow_id'] for r in assignments}) == 563, 'Workflow count/IDs mismatch')
            counts = Counter(r['consensus_cluster'] for r in assignments)
            require(len(counts) == 12, 'Cluster count mismatch')
            return pending('REFERENCE_PARTIAL', ['검증된 80-d consensus feature matrix (workflow ID 순서 포함)'],
                           workflow_count=len(assignments), cluster_count=len(counts), consensus_k=manifest['prototype_consensus']['workflow']['k'],
                           feature_space='5 seed prototype one-hot (5 × 16) / sqrt(5) = 80-d consensus',
                           raw_embedding_available=False,
                           rows=[{'cluster': k, 'workflow_count': v} for k, v in sorted(counts.items(), key=lambda x:int(x[0]))])
        models = self.read('main_results/process_models.csv')
        instances = self.read('main_results/process_instances.csv')
        require(len(models) == 12 and len(instances) == 1619, 'Process reference count mismatch')
        details = {'process_model_count': len(models), 'process_instance_count': len(instances)}
        if metric == 'M03':
            units = []
            for row in models:
                labels = row['representative_path'].split(' → ')
                unit = {'id': row['model_id'], 'name': row.get('process_name') or row['model_id'],
                        'steps': [{'id': str(i), 'label': label} for i, label in enumerate(labels, 1)]}
                units.append(validate_business_unit(unit))
            return pending('REFERENCE_PARTIAL', ['ScenarioGeneratorAdapter', '공식 사전 정의 Business Unit 20개'],
                           **details, input_preview=units, preview_only=True,
                           rows=[{'model_id': u['id'], 'representative_path': ' → '.join(s['label'] for s in u['steps'])} for u in units])
        alias_path = self.root / 'evaluation_contracts/m02_aliases.json'
        alias_metadata = {'alias_file': None, 'alias_sha256': None}
        if alias_path.is_file():
            raw = alias_path.read_bytes()
            self.m02_aliases = json.loads(raw)
            M02Evaluator(self.m02_aliases)
            alias_sha = hashlib.sha256(raw).hexdigest()
            self.sources['evaluation_contracts/m02_aliases.json'] = alias_sha
            alias_metadata = {'alias_file': 'evaluation_contracts/m02_aliases.json', 'alias_sha256': alias_sha}
        details.update(alias_metadata)
        comparison = self.read('main_results/poc_scenario_comparison.csv', optional=True)
        steps = self.read('main_results/process_instance_steps.csv', optional=True)
        details.update(ground_truth_name='V6.2 Legacy Reference Ground Truth', ground_truth_notice='공식 KTL Ground Truth 아님',
                       selection_method='V6.2 Legacy Reference Selection',
                       selection_note='저장된 best_instance_id만 사용. 재검색 및 trajectory 보조 증거 제외.')
        if not comparison or not steps:
            return pending('REFERENCE_PARTIAL', [name for name, data in [('poc_scenario_comparison.csv', comparison), ('process_instance_steps.csv', steps)] if not data],
                           **details, rows=[{'model_id': m['model_id'], 'representative_path': m['representative_path']} for m in models])
        actual, truth = [], []
        for row in comparison:
            labels = row['ground_truth_steps'].split(' → ')
            require(len(labels) == int(row['ground_truth_step_count']), 'Legacy GT step count mismatch')
            selected = sorted((s for s in steps if s['instance_id'] == row['best_instance_id']), key=lambda s:int(s['step_order']))
            require(not row['best_instance_id'] or bool(selected), 'Legacy selected instance missing')
            actual.append({'id': row['scenario_id'], 'procedures': [{'id': s['instance_step_id'], 'label': s['display_label'], 'evidence_type': 'direct'} for s in selected]})
            truth.append({'id': row['scenario_id'], 'procedures': [{'id': str(i), 'label': label} for i, label in enumerate(labels, 1)]})
        details['ground_truth_count'] = len(truth)
        return {'status': 'REFERENCE_READY', 'details': details, 'inputs': ({'processes': actual}, {'processes': truth})}


class OfficialEvaluationDataSource(EvaluationDataSource):
    source_type = 'OFFICIAL'
    dataset_id = None

    def __init__(self, root, config):
        super().__init__(root)
        self.config = config

    def prepare(self, metric):
        if metric in EXTERNAL:
            return pending('EXTERNAL_MODULE_PENDING', ['외부 모듈 연동 예정'])
        manifest_path = self.config.get('official_manifests', {}).get(metric)
        if not manifest_path:
            return pending('OFFICIAL_M06_BUNDLE_MISSING' if metric == 'M06' else 'WAITING_FOR_DATA', ['공식 dataset manifest 및 입력 SHA-256'])
        allowed = (self.root / 'data/evaluation').resolve()
        def verified_file(name, expected=None):
            require(isinstance(name, str), 'Official input path required')
            path = (self.root / name).resolve()
            require(path.is_relative_to(allowed), 'Official inputs must be inside data/evaluation')
            if not path.is_file():
                raise EvaluationError('Missing official input: ' + name, 'OFFICIAL_M06_BUNDLE_MISSING' if metric == 'M06' else 'WAITING_FOR_DATA')
            require('current_site_dev_01' not in path.parts, 'Development dataset cannot become OFFICIAL')
            raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
            for dev_manifest in allowed.glob('*/data_manifest.json'):
                dev = read_json(dev_manifest)
                if dev.get('official') is False:
                    entries = dev.get('files', [])
                    entries = entries.values() if isinstance(entries, dict) else entries
                    require(sha not in [e.get('sha256') for e in entries if isinstance(e, dict)], 'Development input prohibited in OFFICIAL')
            if expected is not None:
                require(sha == expected, 'Official SHA-256 mismatch: ' + name)
            reference_hashes = read_json(self.root / 'backend/reference_manifest.json')['files'].values()
            require(metric == 'M06' or sha not in reference_hashes, 'Historical reference cannot be official input')
            value = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))) if path.suffix.lower() == '.csv' else json.loads(raw)
            def forbidden(v):
                if isinstance(v, dict):
                    if v.get('dev_only') is True or v.get('synthetic') is True or v.get('official') is False:
                        return True
                    if any(str(v.get(k, '')).upper() in {'DEV', 'DEV_ONLY', 'DEVELOPMENT', 'REFERENCE', 'V62_FROZEN_REFERENCE'} for k in ('source_type', 'run_mode', 'data_class')):
                        return True
                    return any(forbidden(x) for x in v.values())
                return any(forbidden(x) for x in v) if isinstance(v, list) else False
            require(not forbidden(value), 'DEV/reference inputs are prohibited in OFFICIAL')
            self.sources[name] = sha
            return value
        manifest = verified_file(manifest_path)
        require(manifest.get('run_mode') == 'OFFICIAL' and manifest.get('source_type') == 'OFFICIAL'
                and manifest.get('metric_id') == metric and manifest.get('approved_for_official') is True, 'Official manifest provenance required')
        require(isinstance(manifest.get('dataset_id'), str) and manifest['dataset_id'].strip(), 'dataset_id required')
        self.dataset_id = manifest['dataset_id']
        files = manifest.get('files'); require(isinstance(files, dict) and bool(files), 'Official input hashes required')
        loaded = {}
        for role, item in files.items():
            require(isinstance(item, dict) and isinstance(item.get('sha256'), str) and len(item['sha256']) == 64, 'Input SHA-256 required')
            loaded[role] = verified_file(item.get('path'), item['sha256'])
        validate_official_contract(metric, manifest)
        if metric in {'M02', 'M03'}:
            units = manifest.get('business_unit_ids', [])
            require(isinstance(units, list) and len(units) == 20 and all(isinstance(u, str) and u.strip() for u in units) and len(set(units)) == 20, 'Official TD-03 requires 20 unique business unit IDs')
            require('event_log' in loaded, 'TD-03 event_log with SHA-256 required')
            other_path = self.config.get('official_manifests', {}).get('M03' if metric == 'M02' else 'M02')
            if other_path:
                other = verified_file(other_path)
                require(other.get('files', {}).get('event_log', {}).get('sha256') == files['event_log']['sha256'], 'M02/M03 must reuse the same TD-03')
                require(set(other.get('business_unit_ids', [])) == set(units), 'M02/M03 business units must match')
        if metric == 'M02':
            require(isinstance(manifest.get('model_version'), str) and manifest['model_version'], 'Model version required')
            require(manifest.get('model_connected') is True, 'Verified model output connection required')
        if metric == 'M02':
            require({'process_result', 'ground_truth'} <= loaded.keys(), 'M02 process_result and ground_truth required')
            inputs = official_m02_inputs(loaded['process_result'], loaded['ground_truth'], loaded.get('pairing'), self.started_at)
            m02_metadata = {'selection_method': 'Preassigned process IDs; all generated procedures in denominator',
                            'alias_file': None, 'alias_sha256': None}
            if 'pairing' in loaded:
                m02_metadata.update(selection_method='Explicit GT-independent pairing; all generated procedures in denominator',
                    pairing_file=files['pairing']['path'], pairing_sha256=self.sources[files['pairing']['path']],
                    pairing_fixed_at=loaded['pairing']['fixed_at'], pairing_pairs=loaded['pairing']['pairs'])
            if 'aliases' in loaded:
                validate_fixed_at(files['aliases'].get('fixed_at'), self.started_at, 'Aliases')
                self.m02_aliases = loaded['aliases']
                M02Evaluator(self.m02_aliases)
                m02_metadata.update(alias_file=files['aliases']['path'], alias_sha256=self.sources[files['aliases']['path']])
        elif metric == 'M06':
            if 'clustering' not in loaded:
                return pending('OFFICIAL_M06_BUNDLE_MISSING', ['승인 V6.2 563 × 128 workflow embedding bundle'])
            c = loaded['clustering']
            validate_fixed_at(manifest.get('fixed_at'), self.started_at, 'M06 bundle')
            require(manifest.get('feature_space') == 'workflow_embedding_128', 'Official M06 requires workflow_embedding_128; no development fallback')
            require(manifest.get('model_version') in {'V6.2', 'v6.2', 'v6_2'}, 'Approved V6.2 bundle required')
            require(len(c.get('features', [])) == 563 and all(isinstance(v,list) and len(v) == 128 for v in c['features']), '563 × 128 workflow embeddings required')
            require(len(c.get('labels', [])) == 563 and len(set(c['labels'])) == 12, '563 final labels / 12 clusters required')
            require(len(c.get('workflow_ids', [])) == 563 and all(isinstance(w,str) and w for w in c['workflow_ids']) and len(set(c['workflow_ids'])) == 563, 'Aligned unique workflow IDs required')
            require(c.get('row_order') == 'workflow_ids', 'features and labels must follow workflow_ids row ordering')
            inputs = (c['features'], c['labels'])
        elif metric == 'M05':
            if not self.config.get('adapters', {}).get('cleaning') or not self.config.get('cleaning_model_version'):
                return pending('NOT_CONFIGURED', ['CleaningModelAdapter 및 model version'])
            require('events' in loaded, 'M05 events input required')
            events = loaded['events'].get('events', [])
            require(len(events) == 200 and Counter(e.get('label') for e in events) == {'KEEP':100, 'REMOVE':100}, '200 events, 100 KEEP/100 REMOVE required')
            require(Counter(e.get('category') for e in events if e['label'] == 'REMOVE') == dict.fromkeys(['duplicate','noise','repeated_action','irrelevant_action'],25), 'REMOVE category counts must each be 25')
            cleaning_payload(events)
            inputs = (events,)
        else:
            return pending('NOT_CONFIGURED', ['ScenarioGeneratorAdapter; 공식 생성 평가 연결 대기'])
        return {'status': 'READY', 'inputs': inputs, 'details': {'model_version': manifest.get('model_version') or self.config.get('cleaning_model_version'), 'dataset_manifest': manifest_path, **(m02_metadata if metric == 'M02' else {})}}
