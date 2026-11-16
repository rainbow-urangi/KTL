"""Main's frozen DEVELOPMENT structure measurement with original receipts.

The verified archive supplies inputs, never an old score or executable imports.
Official and external result ingestion retain the independent-order evaluator.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import uuid

from .evaluators import digest, read_json, require, EvaluationError
from .m03_integration import uses_observed_generator
from .m03_main_compat import SOURCE_COMMIT, evaluate_development, validate_scenario_result
from .m03_provenance import assess_origins, generate_recorded
from .run_storage import now, save_run


DATASET = 'm03_final_10_frozen_20261112'
FREEZE = 'docs/agents/m03_development_freeze_20261112/freeze_manifest.json'
FREEZE_HASH = 'e2432a56e075fc6ae186c824d37316d7072d17f8a611edc7d78bf1ae671c9b95'
CANDIDATE = 'docs/agents/m03_final_10_candidate_20261112/M03_FINAL_10_CANDIDATE.json'
BUNDLE = 'data/runtime/rainbow-m03-frozen-20261112'
INPUTS = 'data/evaluation/rainbow-m03-frozen-20261112'
INPUT_MANIFEST = INPUTS + '/data_manifest.json'
METHOD = ('고정 프로세스맵에서 REAL generator로 10개 시나리오를 생성하고 main의 구조 검사로 평가합니다. '
          'Workflow model 재추론은 하지 않으며 정답 업무 순서 평가는 별도입니다.')
# This is the sole exception in the original Rainbow transport, not a new exemption.
TRANSPORT_EXCEPTION = 'backend/server.py'


def _path(root, relative):
    supplied = Path(relative)
    require(not supplied.is_absolute() and not supplied.drive and '..' not in supplied.parts,
            'M03 runtime requires a project-relative path')
    root = Path(root).resolve()
    path = root / supplied
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        require(not current.is_symlink() and current.resolve() == current,
                'Linked M03 runtime paths are prohibited')
    return path


def _data_manifest(manifest):
    return dict(schema_version='m03-observed-runtime-input-v1', dataset_id=DATASET, metric_id='M03',
                run_mode='DEVELOPMENT', source_type='DEVELOPMENT', data_class='DEVELOPMENT',
                official=False, synthetic=False, business_unit_ids=manifest['candidate_ids'],
                frozen_bundle_manifest_sha256=FREEZE_HASH,
                files=[dict(path='business_steps.json', sha256=manifest['binding']['snapshot_sha256']),
                       dict(path='candidate.json', sha256=manifest['candidate_sha256'])])


def _manifest_bytes(manifest):
    return (json.dumps(_data_manifest(manifest), ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def verify(root):
    root = Path(root).resolve()
    bundle = _path(root, BUNDLE)
    freeze = _path(bundle, FREEZE)
    require(digest(freeze) == FREEZE_HASH, 'M03 original freeze manifest changed')
    manifest = read_json(freeze)
    for name, expected in manifest['sha256'].items():
        if name != TRANSPORT_EXCEPTION:
            require(digest(_path(bundle, name)) == expected, 'M03 frozen artifact changed: ' + name)
    candidate = read_json(_path(bundle, CANDIDATE))
    require(candidate['business_unit_ids'] == manifest['candidate_ids'], 'M03 frozen selection changed')
    require(len(candidate['selection']) == 10 and len(set(manifest['candidate_ids'])) == 10
            and [item['business_unit_id'] for item in candidate['selection']] == manifest['candidate_ids'],
            'M03 requires frozen ten business units in original order')
    require(digest(_path(root, manifest['binding']['snapshot_path'])) == manifest['binding']['snapshot_sha256'],
            'M03 active observed snapshot changed')
    require(digest(_path(root, INPUTS + '/business_steps.json')) == manifest['binding']['snapshot_sha256']
            and digest(_path(root, INPUTS + '/candidate.json')) == manifest['candidate_sha256'],
            'M03 staged evaluation input changed')
    require(digest(_path(root, INPUT_MANIFEST)) == hashlib.sha256(_manifest_bytes(manifest)).hexdigest(),
            'M03 runtime dataset manifest changed')
    return manifest, candidate


def _request_config(config, manifest):
    require(isinstance(config, dict) and config.get('m03_real_generator') == manifest['binding'],
            'M03 active observed binding differs from the frozen input')
    result = deepcopy(config)
    registry = result.setdefault('integration_datasets', {})
    require(isinstance(registry, dict), 'M03 integration dataset registry must be an object')
    registration = dict(manifest=INPUT_MANIFEST, run_mode='DEVELOPMENT')
    require(DATASET not in registry or registry[DATASET] == registration,
            'M03 runtime dataset registration conflicts with active configuration')
    registry[DATASET] = registration
    return result


def readiness(root):
    try:
        manifest, candidate = verify(root)
        _request_config(read_json(_path(Path(root), 'backend/config.json')), manifest)
        return dict(status='READY', dataset_id=DATASET, details=dict(total_scenarios=10,
            model_version=manifest['generator_version'], config_path=BUNDLE + '/' + FREEZE,
            config_sha256=FREEZE_HASH, measurement_method=METHOD,
            business_units=[dict(business_unit_id=item['business_unit_id'], name=item['name'])
                            for item in candidate['selection']],
            source_limitations='BU01/BU12 종료 경계는 불명확하며 BU03 원본 workflow에는 BU02 이벤트가 포함됩니다. '
                               '고정 입력과 실패를 보존하며 구조 성공률을 정답 순서 평가로 사용하지 않습니다.'))
    except (EvaluationError, OSError, ValueError, KeyError) as exc:
        return dict(status='BLOCKED', dataset_id=DATASET, details={'missing': [str(exc)]}, error=str(exc))


def run(root, config):
    root = Path(root).resolve()
    manifest, candidate = verify(root)
    started = now()
    require(config == read_json(_path(root, 'backend/config.json')), 'M03 active configuration mismatch')
    request_config = _request_config(config, manifest)
    requests = [dict(business_unit_id=item['business_unit_id'], workflow_id=item['mapping']['workflow_id'],
                     run_mode='DEVELOPMENT', generator_mode='REAL') for item in candidate['selection']]
    require(all(uses_observed_generator(request_config, request) for request in requests),
            'M03 frozen selection conflicts with an explicit canonical generator binding')
    scenarios, attempts = [], []
    for item, request in zip(candidate['selection'], requests):
        try:
            scenario = generate_recorded(root, request_config, request)
            attempt = dict(business_unit_id=item['business_unit_id'], status='COMPLETED',
                           origin_generation_id=scenario['origin_generation_id'])
        except EvaluationError as exc:
            # A transport failure is an attempted business unit, never a missing
            # denominator or a fabricated completed generation receipt.
            scenario = dict(request, scenario_id='M03-FAILED-' + uuid.uuid4().hex, status='FAILED',
                            steps=[], synthetic=False, official=False, data_class='DEVELOPMENT',
                            issues=[dict(reason='ORIGINAL_GENERATION_ERROR')])
            attempt = dict(business_unit_id=item['business_unit_id'], status='ERROR',
                           reason='ORIGINAL_GENERATION_ERROR', origin_generation_id=getattr(exc, 'origin_generation_id', None))
        scenarios.append(scenario)
        attempts.append(attempt)
    verify(root)
    score, total, details, validation = evaluate_development(dict(run_mode='DEVELOPMENT', scenarios=scenarios))
    rows, cases = [], []
    for item, scenario, verdict in zip(candidate['selection'], scenarios, validation):
        reasons = [key for key in ('schema_valid', 'step_order_valid', 'action_present', 'target_present')
                   if not verdict[key]]
        if scenario['status'] != 'SUCCESS':
            reasons.extend(dict.fromkeys(issue['reason'] for issue in scenario.get('issues', [])))
        row = dict(verdict, name=item['name'], workflow_id=scenario['workflow_id'],
                   source_process_id=scenario.get('source_process_id'), generated_steps=len(scenario['steps']),
                   failure_reason='; '.join(reasons), generator_version=scenario.get('generator_version'),
                   source_snapshot_sha256=scenario.get('source_snapshot_sha256'),
                   candidate_sha256=manifest['candidate_sha256'])
        rows.append(row)
        cases.append(dict(row, steps=scenario['steps'], issues=scenario.get('issues', []),
                          generation_status=scenario['status'], structure_valid=verdict['success'],
                          source_execution_status=item['source_execution_status'],
                          source_event_ids_outside_execution_window=item['mapping']['source_event_ids_outside_execution_window']))
    counts = details['raw_counts']
    payload = dict(external_run_id='M03-FROZEN-' + uuid.uuid4().hex, dataset_id=DATASET,
                   run_mode='DEVELOPMENT', source_module='rainbow-m03-observed-runtime',
                   source_version=manifest['generator_version'], submitted_at=now(),
                   dataset_manifest_sha256=digest(_path(root, INPUT_MANIFEST)), scenarios=scenarios,
                   details=dict(candidate_id=candidate['candidate_id'], candidate_sha256=manifest['candidate_sha256'],
                       frozen_bundle_manifest_sha256=FREEZE_HASH, measurement_method=METHOD,
                       historical_score_used=False, per_business_unit=cases, generation_attempts=attempts,
                       transport_sha256=digest(Path(__file__)),
                       generation_summary=dict(attempt_count=len(scenarios), successful_count=counts['successful_scenario_count'],
                           failed_count=counts['failed_scenario_count'], model_inference_executed=False,
                           generation_method='OBSERVED_PROCESS_SNAPSHOT_PROJECTION')))
    provenance, _ = assess_origins(root, payload, None, {}, payload['dataset_manifest_sha256'])
    details.update(payload['details'])
    details.update(total_scenarios=total, success=counts['successful_scenario_count'],
                   failure=counts['failed_scenario_count'], model_version=manifest['generator_version'],
                   config_sha256=FREEZE_HASH, measurement_method=METHOD,
                   evaluation_status='COMPLETED', success_policy='MAIN_COMPAT_STRUCTURE',
                   compatibility_source_commit=SOURCE_COMMIT, reference_order_evaluated=False,
                   order_evaluation=dict(status='NOT_EVALUATED', score=None), official_eligible=False,
                   generation_provenance=provenance)
    hashes = {BUNDLE + '/' + name: value for name, value in manifest['sha256'].items()
              if name != TRANSPORT_EXCEPTION}
    hashes.update({manifest['binding']['snapshot_path']: manifest['binding']['snapshot_sha256'],
                   INPUT_MANIFEST: payload['dataset_manifest_sha256'],
                   INPUTS + '/business_steps.json': manifest['binding']['snapshot_sha256'],
                   INPUTS + '/candidate.json': manifest['candidate_sha256']})
    return save_run(root, 'M03', 'DEVELOPMENT', config,
                    dict(status='COMPLETED', score=score, sample_count=total, dataset_id=DATASET,
                         details=details, started_at=started, evaluator_version='main-32aa412-m03-structure-compat',
                         input_sha256=hashes, freeze_manifest_sha256=FREEZE_HASH,
                         transport_sha256=digest(Path(__file__))), rows, received=payload)
