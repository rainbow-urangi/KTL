"""M03 생성 계약 및 중앙 시나리오 검증. Mock은 실제 모델을 호출하지 않습니다."""
import hashlib
from .evaluators import require, call_adapter


def nonempty(value):
    return isinstance(value,str) and bool(value.strip()) and len(value)<=256


def validate_scenario_result(value):
    """게시 JSON Schema의 필수 타입과 단계 순서를 중앙에서 검증합니다."""
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


def evaluate_scenarios(payload):
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


def generate(root,config,payload):
    require(isinstance(payload,dict),'JSON object required')
    require(set(payload)<= {'business_unit_id','workflow_id','run_mode','generator_mode'},'Unsupported generation request field')
    for k in ('business_unit_id','workflow_id'):require(nonempty(payload.get(k)),'Required field: '+k)
    mode=payload.get('run_mode','DEVELOPMENT');engine=payload.get('generator_mode','MOCK')
    require(mode in {'REFERENCE','DEVELOPMENT','OFFICIAL'},'Invalid run_mode')
    require(engine in {'MOCK','REAL'},'generator_mode must be MOCK or REAL')
    if engine=='MOCK':
        require(mode!='OFFICIAL','Mock generation cannot be OFFICIAL')
        identity=hashlib.sha256((payload['business_unit_id']+'\0'+payload['workflow_id']).encode()).hexdigest()[:12]
        result=dict(business_unit_id=payload['business_unit_id'],workflow_id=payload['workflow_id'],scenario_id='MOCK-SCN-'+identity,status='SUCCESS',
                    steps=[dict(order=1,action='open',target='mock workflow screen'),dict(order=2,action='click',target='mock action control')],description='합성 UI 연동 예시이며 실제 업무 시나리오가 아닙니다.')
    else:
        result=call_adapter(config,'scenario_generation',{k:payload[k] for k in ('business_unit_id','workflow_id')},root)
        require(result.get('business_unit_id')==payload['business_unit_id'] and result.get('workflow_id')==payload['workflow_id'],'Generator identity mismatch')
        require(result.get('status') in {'SUCCESS','FAILED'} and nonempty(result.get('scenario_id')) and isinstance(result.get('steps'),list),'Invalid generation response')
        if result['status']=='SUCCESS':require(validate_scenario_result(result)['success'],'Generator returned an invalid successful scenario')
    # Same response structure for mock and real generation; mode is explicit metadata.
    result.update(run_mode=mode,generator_mode=engine,synthetic=engine=='MOCK',official_pass=None)
    return result
