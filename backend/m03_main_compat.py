"""Main 32aa412 structural measurement, isolated from the strict M03 evaluator.

Only the DEVELOPMENT main-page transport calls this compatibility calculation.
The predicates and ratio below retain that commit's original implementation;
they do not compare a scenario with an independent business-order reference.
"""
from .evaluators import require


SOURCE_COMMIT = '32aa412c34a3355e4e9e2d236b6bd5fd707127b5'


def nonempty(value):
    return isinstance(value,str) and bool(value.strip()) and len(value)<=256


def validate_scenario_result(value):
    """The original main commit's structure and contiguous-order predicates."""
    value=value if isinstance(value,dict) else {}
    steps=value.get('steps')
    step_objects=isinstance(steps,list) and bool(steps) and all(isinstance(s,dict) for s in steps)
    action_present=step_objects and all(nonempty(s.get('action')) for s in steps)
    target_present=step_objects and all(nonempty(s.get('target')) for s in steps)
    order_valid=step_objects and all(type(s.get('order')) is int and s['order']==i for i,s in enumerate(steps,1))
    schema_valid=(nonempty(value.get('business_unit_id')) and nonempty(value.get('scenario_id')) and step_objects
                  and action_present and target_present and all(type(s.get('order')) is int and s['order']>=1 for s in steps))
    if 'workflow_id' in value:schema_valid=schema_valid and nonempty(value['workflow_id'])
    if 'status' in value:schema_valid=schema_valid and value['status'] in ('SUCCESS','FAILED')
    success=bool(schema_valid and order_valid and action_present and target_present and value.get('status','SUCCESS')=='SUCCESS')
    return dict(schema_valid=bool(schema_valid),step_order_valid=bool(order_valid),action_present=bool(action_present),target_present=bool(target_present),success=success)


def _evaluate_main(payload):
    rows=payload.get('scenarios')
    require(isinstance(rows,list) and 1<=len(rows)<=10 and all(isinstance(r,dict) for r in rows),'scenarios must contain 1..10 result objects')
    ids=[r.get('business_unit_id') for r in rows]
    require(all(nonempty(x) for x in ids) and len(set(ids))==len(ids),'Unique business_unit_id required for every attempt')
    scenario_ids=[r['scenario_id'] for r in rows if nonempty(r.get('scenario_id'))]
    require(len(scenario_ids)==len(set(scenario_ids)),'Duplicate scenario_id')
    official=payload['run_mode']=='OFFICIAL'
    require(not official or len(rows)==10,'Official M03 requires exactly 10 business units')
    evidence=[dict(business_unit_id=r['business_unit_id'],scenario_id=r.get('scenario_id'),**validate_scenario_result(r)) for r in rows]
    successful=sum(r['success'] for r in evidence);total=10 if official else len(rows)
    counts=dict(total_business_units=total,successful_scenario_count=successful,failed_scenario_count=total-successful)
    if 'counts' in payload:
        require(isinstance(payload['counts'],dict),'counts object required')
        for k,v in payload['counts'].items():
            if k in counts:require(type(v) is int and v==counts[k],'M03 counts do not match scenario validation: '+k)
    details=dict(formula='successful_scenario_count / total_business_units * 100',raw_counts=counts,
                 successful_scenario_count=successful,total_scenario_count=total,denominator=total,
                 schema='evaluation_contracts/m03-scenario.schema.json',denominator_policy='OFFICIAL_FIXED_10' if official else 'NON_OFFICIAL_SAMPLE_SIZE',
                 external_details=payload.get('details',{}),external_evidence=payload.get('evidence',{}))
    return 100*successful/total,total,details,evidence


def evaluate_development(payload):
    require(isinstance(payload,dict) and payload.get('run_mode')=='DEVELOPMENT',
            'Main compatibility measurement is DEVELOPMENT only')
    return _evaluate_main(payload)
