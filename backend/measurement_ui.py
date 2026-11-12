"""Read-only active presentation catalog. No evaluator/model invocation or score math.
Internal result modes remain intact. The legacy API is unchanged.
"""
from .evaluators import METRICS, read_json

STORED = {
    'M02': 'results/recovery-validation/m02_recovery_data_05',
    'M03': 'results/development/m03_current_semantics_20261109',
}

def stored_file(root, metric, filename):
    if metric not in STORED or filename not in ('result.json', 'evidence.csv'):
        return None
    return root / STORED[metric] / filename

def catalog(service):
    root = service.root
    config = service.config()
    metrics = []
    for metric, (name, _, count, operator) in METRICS.items():
        item = dict(metric_id=metric, metric_name=name, dataset=None,
                    expected_sample_count=count, target=config['targets'][metric], operator=operator,
                    status='NOT_CONFIGURED', details={}, latest=None,
                    execution_available=False, execution_url=None)
        if metric in STORED:
            path = stored_file(root, metric, 'result.json')
            if path.is_file():
                raw = read_json(path)
                item['dataset'] = path.parent.name
                if metric == 'M02':
                    values = raw['overall']
                    details = dict(accuracy=values['accuracy'], completeness=values['completeness'],
                                   evaluated_procedures=values['generated'], correctly_mapped=values['matched'],
                                   included_required=values['satisfied'], defined_required=values['required'],
                                   ground_truth_count=len(raw['per_business_unit']))
                    score, passed = values['score'], values['target_met']
                    from .m02_main_web import readiness, DATASET, METHOD
                    prepared = readiness(root)
                    details.update(prepared['details'])
                    item.update(dataset=DATASET, execution_available=prepared['status']=='READY',
                                execution_url='/api/evaluations/m02/run?mode=DEVELOPMENT&dataset_id='+DATASET)
                    item['presentation_note'] = METHOD
                else:
                    values = raw['details']['raw_counts']
                    details = dict(total_scenarios=values['total_business_units'],
                                   success=values['successful_scenario_count'], failure=values['failed_scenario_count'])
                    score, passed = raw['score'], raw['threshold_met']
                    from .m03_main_web import readiness, DATASET, METHOD
                    prepared = readiness(root)
                    details.update(prepared['details'])
                    item.update(dataset=DATASET, execution_available=prepared['status']=='READY',
                                execution_url='/api/evaluations/m03/run?mode=DEVELOPMENT&dataset_id='+DATASET)
                    item['presentation_note'] = METHOD
                item.update(status='COMPLETED', details=details,
                            latest=dict(status='COMPLETED', score=score, threshold_met=passed,
                                        details=details, dataset_id=item['dataset'], target=item['target'],
                                        operator=operator, completed_at=raw.get('completed_at'),
                                        evidence_file=f'/api/measurement/{metric.lower()}/evidence.csv'))
        elif metric in ('M05', 'M06'):
            if metric == 'M05':
                from .m05_main_web import readiness
            else:
                from .m06_candidate import prepare as readiness
            prepared = readiness(root)
            dataset = prepared.get('dataset_id')
            item.update(status=prepared['status'], dataset=dataset, details=prepared.get('details', {}),
                        execution_available=prepared['status']=='READY',
                        execution_url=f'/api/evaluations/{metric.lower()}/run?mode=DEVELOPMENT' +
                                      (f'&dataset_id={dataset}' if metric == 'M06' else ''))
            latest = root / 'results/development' / f'latest-{metric}.json'
            if latest.is_file():
                saved = read_json(latest)
                if saved.get('dataset_id') == dataset:
                    item['latest'] = saved
            if metric == 'M05':
                item['expected_sample_count'] = 20
        else:
            # External integration functionality is unchanged, not expanded here.
            latest = root / 'results/development' / f'latest-{metric}.json'
            if latest.is_file():
                item['latest'] = read_json(latest)
                item['dataset'] = item['latest'].get('dataset_id')
        metrics.append(item)
    return {'metrics': metrics}
