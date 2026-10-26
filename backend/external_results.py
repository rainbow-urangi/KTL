"""외부 엔진의 원시 count 검증 및 중앙 산식. 실행 엔진은 포함하지 않습니다."""
from datetime import datetime
from .evaluators import require


def calculate(metric, payload):
    require(isinstance(payload, dict), 'JSON object required')
    for field in ('external_run_id','dataset_id','run_mode','source_module','source_version','submitted_at','dataset_manifest_sha256'):
        require(isinstance(payload.get(field), str) and 0 < len(payload[field].strip()) and len(payload[field]) <= 256, 'Required field: '+field)
    require(payload['run_mode'] in {'DEVELOPMENT','REFERENCE','OFFICIAL'}, 'Invalid run_mode')
    try:
        stamp = datetime.fromisoformat(payload['submitted_at'].replace('Z','+00:00'))
        require(stamp.tzinfo is not None, 'submitted_at requires timezone')
    except ValueError:
        require(False, 'Invalid submitted_at')
    require(isinstance(payload.get('details'), dict) or isinstance(payload.get('evidence'), (dict,list)), 'details or evidence required')
    if metric == 'M03':
        from .m03_integration import evaluate_scenarios
        return evaluate_scenarios(payload)
    counts = payload.get('counts'); require(isinstance(counts, dict), 'counts object required')
    def count(name, positive=False):
        value=counts.get(name)
        require(type(value) is int and value >= (1 if positive else 0), 'Invalid count: '+name)
        return value
    if metric == 'M01':
        defined=count('defined_required_event_count',True); collected=count('collected_required_event_count')
        total=count('total_collected_event_count',True); fields=count('required_field_count',True)
        missing=count('missing_required_field_count'); types=count('defined_event_type_count',True); seen=count('collected_event_type_count')
        require(collected<=defined and collected<=total and missing<=total*fields and seen<=types and seen<=total, 'Impossible M01 counts')
        c1=100*collected/defined;c2=100*missing/(total*fields);c3=100*seen/types
        score=.5*c1+.3*(100-c2)+.2*c3; sample=defined
        details={'C1':c1,'C2':c2,'C3':c3,'formula':'0.5*C1 + 0.3*(100-C2) + 0.2*C3'}
    elif metric == 'M04':
        sample=count('total_execution_count',True)
        success=count('successful_execution_count') if 'successful_execution_count' in counts else count('passed_execution_count')
        if 'passed_execution_count' in counts:require(count('passed_execution_count')==success,'Conflicting success counts')
        if 'failed_execution_count' in counts:require(count('failed_execution_count')==sample-success,'Failed count mismatch')
        if payload['run_mode']=='OFFICIAL':require(sample==10,'Official M04 requires 10 executions including failures')
        require(success<=sample,'successful_execution_count exceeds total')
        score=100*success/sample
        details={'formula':'successful_execution_count / total_execution_count * 100',
                 'denominator_note':'KTL 확정 시험 산식; 실패도 전체 실행 분모에 포함'}
    elif metric == 'M07':
        requests=count('generation_request_count',True);generated=count('generated_code_count',True);sample=generated;syntax=count('syntax_pass_count');execution=count('execution_pass_count');both=count('both_pass_count')
        require(generated<=requests and syntax<=generated and execution<=generated and both<=min(syntax,execution)
                and both>=syntax+execution-generated, 'Impossible M07 counts')
        official=payload['run_mode']=='OFFICIAL'
        if official:
            require(requests==20 and generated==20,'Official M07 requires 20 requests and 20 generated codes; C2 fixed 20')
            require(isinstance(payload.get('cases'),list),'Official M07 requires individual code cases')
            sample=20
        score=100*both/sample
        details={'formula':'both_pass_count / 20 * 100' if official else 'both_pass_count / generated_code_count * 100',
                 'denominator':sample,'denominator_policy':'OFFICIAL_FIXED_20' if official else 'NON_OFFICIAL_GENERATED_COUNT',
                 'generation_request_count':requests}
    else:
        require(False,'Unsupported external metric')
    cases=payload.get('cases')
    if cases is not None:
        require(isinstance(cases,list) and all(isinstance(c,dict) for c in cases),'cases must be objects')
        ids=[c.get('case_id') for c in cases]
        require(all(isinstance(x,str) and x for x in ids) and len(ids)==len(set(ids)), 'Unique case_id required')
        if metric in {'M04','M07'}:
            require(len(cases)==(requests if metric=='M07' else sample), 'Provided cases must cover all requests/executions; generated codes define M07 denominator')
        if metric=='M04':
            require(all(c.get('status') in {'PASS','FAIL','ERROR','TIMEOUT','SKIPPED'} for c in cases),'Invalid case status')
            require(sum(c['status']=='PASS' for c in cases)==success,'Cases/counts mismatch')
        if metric=='M07':
            for c in cases:
                require(all(c.get(k) in {'PASS','FAIL','ERROR','TIMEOUT','SKIPPED'} for k in ['generation_status','syntax_status','execution_status','final_status']),'Invalid M07 case status')
                require((c['final_status']=='PASS')==(c['generation_status']=='PASS' and c['syntax_status']=='PASS' and c['execution_status']=='PASS'),'Final status requires generation/syntax/execution PASS')
                require(c['generation_status']=='PASS' or (c['syntax_status']!='PASS' and c['execution_status']!='PASS'),'Ungenerated code cannot pass')
            calculated_both=sum(c['generation_status']=='PASS' and c['syntax_status']=='PASS' and c['execution_status']=='PASS' for c in cases)
            require(calculated_both==both,'Cases/counts mismatch: both_pass_count')
            score=100*calculated_both/sample
            details['calculated_both_pass_count']=calculated_both
            for key,n in [('generation_status',generated),('syntax_status',syntax),('execution_status',execution),('final_status',both)]:
                require(sum(c[key]=='PASS' for c in cases)==n,'Cases/counts mismatch: '+key)
    details.update(raw_counts=counts,external_details=payload.get('details',{}),external_evidence=payload.get('evidence',{}))
    return score,sample,details,cases or [counts]
