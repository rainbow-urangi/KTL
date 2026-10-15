"""최신 KTL 제시 기준의 고정 시험 계약. 모델 실행 정책과 분리합니다."""
from .evaluators import require

OFFICIAL_SPEC = {
    'M01': {'scenario_count':5,'executions_per_scenario':2,'independent_session_count':10,
            'required_events_per_execution':10,'defined_required_event_count':100,'required_field_count':6,'defined_event_type_count':8},
    'M02': {'business_unit_count':20,'ground_truth_process_count':5},
    'M03': {'business_unit_count':20,'generation_attempt_per_business_unit':1,'official_denominator':20},
    'M04': {'fixed_script_count':20,'execution_per_script':1},
    'M05': {'official_event_count':200,'keep':100,'remove':100,'official_dataset_must_be_held_out':True},
    'M06': {'source':'approved_v6_2_measurement_bundle','workflow_count':563,'embedding_dimension':128,'cluster_count':12},
}
M01_FIELDS=['session_id','event_time','event_type','page_url','page_title','target_key']
M01_TYPES=['화면 이동','클릭','입력','선택/변경','제출/저장','팝업','네트워크 요청','키 입력']


def validate_official_contract(metric, manifest, counts=None):
    contract=manifest.get('official_contract')
    if metric in OFFICIAL_SPEC:
        require(isinstance(contract,dict),'official_contract required: '+metric)
        for key,value in OFFICIAL_SPEC[metric].items():
            require(type(contract.get(key)) is type(value) and contract[key]==value,'Official '+metric+' requires '+key+' = '+str(value))
    if metric=='M01':
        require(contract.get('required_fields')==M01_FIELDS and contract.get('event_types')==M01_TYPES,'Official M01 requires fixed six fields and eight event types')
        if counts:
            for key in ['defined_required_event_count','required_field_count','defined_event_type_count']:
                require(counts.get(key)==contract[key],'Official M01 count mismatch: '+key)
    elif metric=='M04' and counts:
        require(counts.get('total_execution_count')==20,'Official M04 requires 20 executions including failures')
    elif metric=='M05':
        require(manifest.get('held_out') is True and manifest.get('used_for_training') is False
                and manifest.get('used_for_development') is False,'Official M05 must be held-out from training and development')
