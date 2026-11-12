"""Frozen M03 batch transport. Generation and verdicts use the existing API core."""
from pathlib import Path
from .evaluators import digest, read_json, require, EvaluationError
from .m03_integration import generate, evaluate_scenarios
from .run_storage import save_run, now

DATASET = 'm03_final_10_frozen_20261112'
FREEZE = 'docs/agents/m03_development_freeze_20261112/freeze_manifest.json'
FREEZE_HASH = 'e2432a56e075fc6ae186c824d37316d7072d17f8a611edc7d78bf1ae671c9b95'
CANDIDATE = 'docs/agents/m03_final_10_candidate_20261112/M03_FINAL_10_CANDIDATE.json'
METHOD = '고정 프로세스맵에서 REAL generator로 10개 시나리오를 생성하고 기존 evaluator로 평가합니다. Workflow model 재추론은 하지 않습니다.'
# Only the web dispatch changes; the historical freeze manifest remains untouched.
TRANSPORT_EXCEPTION = 'backend/server.py'


def verify(root):
    root = Path(root)
    require(digest(root/FREEZE) == FREEZE_HASH, 'M03 freeze manifest changed')
    manifest = read_json(root/FREEZE)
    for name, expected in manifest['sha256'].items():
        if name != TRANSPORT_EXCEPTION:
            require(digest(root/name) == expected, 'M03 frozen artifact changed: '+name)
    candidate = read_json(root/CANDIDATE)
    require(candidate['business_unit_ids'] == manifest['candidate_ids'], 'M03 frozen selection changed')
    require(len(candidate['selection']) == 10, 'M03 requires frozen ten business units')
    return manifest, candidate


def readiness(root):
    try:
        manifest, candidate = verify(root)
        return dict(status='READY', dataset_id=DATASET, details=dict(total_scenarios=10,
            model_version=manifest['generator_version'], config_path=FREEZE,
            config_sha256=FREEZE_HASH, measurement_method=METHOD,
            business_units=[dict(business_unit_id=x['business_unit_id'], name=x['name']) for x in candidate['selection']],
            source_limitations='BU01/BU12 종료 경계는 불명확하며 BU03 원본 workflow에는 BU02 이벤트가 포함됩니다. 입력 및 평가 목록은 그대로 유지합니다.'))
    except (EvaluationError, OSError, ValueError, KeyError) as exc:
        return dict(status='BLOCKED', dataset_id=DATASET, details={'missing':[str(exc)]}, error=str(exc))


def run(root, config):
    root = Path(root); manifest, candidate = verify(root); started = now()
    require(config == read_json(root/'backend/config.json'), 'M03 active configuration mismatch')
    scenarios=[]
    for item in candidate['selection']:
        # Only IDs enter the same REAL implementation used by /api/m03/generate.
        scenarios.append(generate(root, config, dict(business_unit_id=item['business_unit_id'],
            workflow_id=item['mapping']['workflow_id'], run_mode='DEVELOPMENT', generator_mode='REAL')))
    score, total, details, validation = evaluate_scenarios(dict(run_mode='DEVELOPMENT', scenarios=scenarios))
    verify(root)
    rows=[]; cases=[]
    for item, scenario, verdict in zip(candidate['selection'], scenarios, validation):
        reasons=[key for key in ('schema_valid','step_order_valid','action_present','target_present') if not verdict[key]]
        if scenario['status'] != 'SUCCESS':
            reasons.extend(dict.fromkeys(issue['reason'] for issue in scenario.get('issues', [])))
        reason='; '.join(reasons)
        row=dict(verdict, name=item['name'], workflow_id=scenario['workflow_id'],
            source_process_id=scenario.get('source_process_id'), generated_steps=len(scenario['steps']),
            failure_reason=reason, generator_version=scenario['generator_version'],
            source_snapshot_sha256=scenario['source_snapshot_sha256'], candidate_sha256=manifest['candidate_sha256'])
        rows.append(row)
        # Boundary caveats are evidence, not additional score criteria.
        cases.append(dict(row, steps=scenario['steps'], issues=scenario.get('issues', []),
            source_execution_status=item['source_execution_status'],
            source_event_ids_outside_execution_window=item['mapping']['source_event_ids_outside_execution_window']))
    counts=details['raw_counts']
    details.update(total_scenarios=total, success=counts['successful_scenario_count'],
        failure=counts['failed_scenario_count'], per_business_unit=cases,
        model_version=manifest['generator_version'], config_sha256=FREEZE_HASH, measurement_method=METHOD)
    return save_run(root, 'M03', 'DEVELOPMENT', config, dict(status='COMPLETED', score=score,
        sample_count=total, dataset_id=DATASET, details=details, started_at=started,
        evaluator_version='existing-m03-evaluate-scenarios', input_sha256={name:value for name,value in manifest['sha256'].items() if name != TRANSPORT_EXCEPTION},
        freeze_manifest_sha256=FREEZE_HASH, transport_sha256=digest(root/TRANSPORT_EXCEPTION)), rows,
        received=dict(scenarios=scenarios, candidate_id=candidate['candidate_id']))
