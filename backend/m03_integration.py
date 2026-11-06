"""M03 생성 계약 및 중앙 시나리오 검증. Mock은 실제 모델을 호출하지 않습니다."""
import hashlib
import json
import csv
from copy import deepcopy
from pathlib import Path
from .evaluators import require, call_adapter, EvaluationError


# 확정된 개발용 업무 정의
DEVELOPMENT_SOURCE_VERSION='bu14-cards-dev-v1'
DEVELOPMENT_BUSINESS_UNIT=dict(
    business_unit_id='BU14',business_name='명함 목록 조회',definition_version='1',
    status='CONFIRMED',confirmed_on='2026-10-27',
    definition_source='USER_CONFIRMED_BUSINESS_DEFINITION',
    workflow_id='DEV-BU14-CARDS-SEARCH',workflow_id_source='DEVELOPMENT_ALIAS',
    start_screen='https://rainbowlab.ai.kr/mypage/cards',
    required_procedures=['명함 목록 열기','테스트 검색어 조회','검색어 비우고 전체 목록 조회'],
    end_condition='검색어가 비워지고 전체 명함 목록 확인',search_keyword='테스트')


def nonempty(value):
    return isinstance(value,str) and bool(value.strip()) and len(value)<=256


def _project_path(root, value):
    require(isinstance(value,str) and bool(value.strip()),'M03 input path required')
    path=root/Path(value)
    require(path.is_absolute() and path.is_relative_to(root) and '..' not in path.parts,'M03 input path must remain under the project root')
    current=root
    for part in path.relative_to(root).parts:
        current=current/part
        require(not current.is_symlink() and current.resolve()==current,'M03 input symlink paths are prohibited')
    forbidden=('ground_truth','ground-truth','groundtruth','expected_events','evaluation_pairing','match_result')
    require(not any(token in str(path.relative_to(root)).lower() for token in forbidden),'Ground Truth and evaluation evidence are prohibited as M03 generation inputs')
    return path


def _no_truth(value):
    if isinstance(value,dict):
        for key,item in value.items():
            normalized=str(key).lower().replace('-','_')
            require(normalized not in {'ground_truth','groundtruth','expected_events','expected_label','gt_steps','gt_label','evaluation_pairing','match_result','official_pass'},'Ground Truth and evaluation evidence are prohibited as M03 generation inputs')
            _no_truth(item)
    elif isinstance(value,list):
        for item in value:_no_truth(item)


def _file_sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):value.update(chunk)
    return value.hexdigest()


def _real_input(root,config):
    # 실제 분석 입력과 업무 정의 검증
    settings=config.get('m03',{})
    require(isinstance(settings,dict),'m03 configuration object required')
    transport=settings.get('transport','SUBPROCESS')
    require(transport in {'SUBPROCESS','HTTP'},'M03 transport must be SUBPROCESS or HTTP')
    if transport=='HTTP':
        from .m03_http import http_settings
        http_settings(config)
    elif not config.get('adapters',{}).get('scenario_generation'):
        raise EvaluationError('backend/config.json의 adapters.scenario_generation에 실제 생성기 명령을 설정하세요.')
    units=settings.get('business_units')
    require(isinstance(units,list) and 1<=len(units)<=10 and all(isinstance(row,dict) for row in units),'m03.business_units에 1~10개 업무 정의를 설정하세요.')
    definitions=[]
    fields=('business_unit_id','workflow_id','business_name','start_screen','end_condition')
    for row in units:
        require(all(nonempty(row.get(key)) for key in fields),'M03 업무 정의에 ID, 업무명, 시작 화면, 종료 조건이 필요합니다.')
        require(isinstance(row.get('required_procedures'),list) and bool(row['required_procedures']) and all(nonempty(x) for x in row['required_procedures']),'M03 required_procedures must contain procedure descriptions')
        _no_truth(row)
        definitions.append(deepcopy(row))
    require(len({row['business_unit_id'] for row in definitions})==len(definitions),'M03 business_unit_id must be unique')
    for key in ('source_module','source_version'):
        require(nonempty(settings.get(key)),'m03.'+key+' 설정이 필요합니다.')
    path=_project_path(root,settings.get('input_manifest'))
    if not path.is_file():raise EvaluationError('M03 analysis input manifest required; maximum 1 MiB','NOT_READY')
    require(path.stat().st_size<=1048576,'M03 analysis input manifest required; maximum 1 MiB')
    raw=path.read_bytes()
    try:manifest=json.loads(raw.decode('utf-8-sig'))
    except (ValueError,UnicodeError) as exc:raise EvaluationError('M03 input manifest must be UTF-8 JSON','ERROR') from exc
    require(isinstance(manifest,dict) and nonempty(manifest.get('dataset_id')),'M03 input manifest dataset_id required')
    require(manifest.get('synthetic') is not True,'REAL M03 cannot use a synthetic input manifest')
    _no_truth(manifest)
    entries=manifest.get('files')
    require(isinstance(entries,list) and 1<=len(entries)<=100 and all(isinstance(x,dict) for x in entries),'M03 input manifest files must contain relative path and SHA-256')
    files=[];total_bytes=0
    for entry in entries:
        require(isinstance(entry.get('path'),str) and bool(entry['path'].strip()) and not Path(entry['path']).is_absolute(),'M03 manifest file path must be relative')
        source=_project_path(root,str(path.parent.relative_to(root)/entry.get('path','')))
        if not source.is_file():raise EvaluationError('M03 analysis input file missing','NOT_READY')
        require(source.suffix.lower() in {'.csv','.json','.jsonl'},'M03 analysis input must be CSV, JSON or JSONL')
        total_bytes+=source.stat().st_size
        if transport=='HTTP':require(total_bytes<=4*1024*1024,'M03 HTTP 분석 입력은 총 4 MiB 이하여야 합니다. 더 큰 입력은 subprocess 어댑터를 사용하세요.')
        actual=_file_sha(source)
        require(actual==entry.get('sha256'),'M03 analysis input SHA-256 mismatch: '+source.name)
        if source.suffix.lower()=='.csv':
            try:
                with source.open(encoding='utf-8-sig',newline='') as stream:
                    _no_truth({key:None for key in next(csv.reader(stream),[])})
            except (UnicodeError,csv.Error) as exc:raise EvaluationError('M03 analysis input must be UTF-8 CSV','ERROR') from exc
        elif source.suffix.lower()=='.json':
            require(source.stat().st_size<=33554432,'M03 JSON analysis input maximum 32 MiB; use CSV or JSONL for larger input')
            try:_no_truth(json.loads(source.read_bytes().decode('utf-8-sig')))
            except (ValueError,UnicodeError) as exc:raise EvaluationError('M03 analysis input must be UTF-8 JSON','ERROR') from exc
        else:
            try:
                with source.open(encoding='utf-8-sig') as stream:
                    for line in stream:
                        if line.strip():_no_truth(json.loads(line))
            except (ValueError,UnicodeError) as exc:raise EvaluationError('M03 analysis input must be UTF-8 JSONL','ERROR') from exc
        files.append(dict(path=source.relative_to(root).as_posix(),sha256=actual))
    require(len({entry['path'] for entry in files})==len(files),'M03 analysis input paths must be unique')
    workflow_ids=manifest.get('workflow_ids')
    if workflow_ids is not None:
        require(isinstance(workflow_ids,list) and all(row['workflow_id'] in workflow_ids for row in definitions),'M03 workflow IDs do not match the analysis input manifest')
    verified=dict(dataset_id=manifest['dataset_id'],manifest_path=path.relative_to(root).as_posix(),manifest_sha256=hashlib.sha256(raw).hexdigest(),files=files)
    if nonempty(manifest.get('source_run_id')):verified['source_run_id']=manifest['source_run_id']
    return definitions,verified


def _real_context(root,config):
    definitions,verified=_real_input(root,config)
    settings=config['m03']
    units=[{key:row[key] for key in ('business_unit_id','workflow_id')} for row in definitions]
    inputs=dict(metric_id='M03',run_mode='DEVELOPMENT',official=False,synthetic=False,data_class='DEVELOPMENT',
                source_module=settings['source_module'],source_version=settings['source_version'],business_units=units,
                business_definitions=definitions,analysis_input=verified)
    encoded=lambda value:(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    raw=encoded(inputs);input_sha=hashlib.sha256(raw).hexdigest();dataset_id='m03-real-development-'+input_sha[:12]
    directory=_project_path(root,'data/evaluation/'+dataset_id)
    manifest=dict(dataset_id=dataset_id,metric_id='M03',run_mode='DEVELOPMENT',source_type='DEVELOPMENT',data_class='DEVELOPMENT',
                  official=False,synthetic=False,source_module=settings['source_module'],source_version=settings['source_version'],
                  purpose='M03 DEVELOPMENT actual generator integration; not official KTL evidence',files=[dict(path='real_inputs.json',sha256=input_sha)])
    manifest_bytes=encoded(manifest)
    files=[(_project_path(root,str((directory/'real_inputs.json').relative_to(root))),raw),(_project_path(root,str((directory/'data_manifest.json').relative_to(root))),manifest_bytes)]
    for path,value in files:
        require(not path.exists() or (path.is_file() and path.read_bytes()==value),'Existing development M03 real input differs: '+path.name)
    directory.mkdir(parents=True,exist_ok=True)
    for path,value in files:
        if not path.exists():
            with path.open('xb') as output:output.write(value)
    registered=dict(manifest=(directory/'data_manifest.json').relative_to(root).as_posix(),run_mode='DEVELOPMENT')
    datasets=config.setdefault('integration_datasets',{})
    require(isinstance(datasets,dict),'Integration dataset configuration required')
    require(dataset_id not in datasets or datasets[dataset_id]==registered,'Development M03 real dataset registration differs')
    datasets[dataset_id]=registered
    result=dict(dataset_id=dataset_id,dataset_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),run_mode='DEVELOPMENT',
                generator_mode='REAL',synthetic=False,source_module=settings['source_module'],source_version=settings['source_version'],
                business_units=units,business_definitions=definitions,verified_input=verified,real_generator_configured=True)
    if len(definitions)==1:result['business_definition']=definitions[0]
    return result


def development_context(root,config):
    """M03 개발용 Mock 입력과 실행 정보."""
    root=Path(root).resolve()
    settings=config.get('m03',{})
    require(isinstance(settings,dict) and settings.get('generator_mode','MOCK') in {'MOCK','REAL'},'m03.generator_mode must be MOCK or REAL')
    if settings.get('generator_mode')=='REAL':return _real_context(root,config)

    def safe_path(path):
        require(path.is_relative_to(root),'Development path must remain under the project root')
        current=root
        for part in path.relative_to(root).parts:
            current=current/part
            require(not current.is_symlink() and current.resolve()==current,'Development symlink paths are prohibited')
        return path

    definition=deepcopy(DEVELOPMENT_BUSINESS_UNIT)
    source_version=DEVELOPMENT_SOURCE_VERSION
    units=[{key:definition[key] for key in ('business_unit_id','workflow_id')}]
    inputs=dict(metric_id='M03',run_mode='DEVELOPMENT',source_type='DEVELOPMENT',data_class='DEVELOPMENT',
                official=False,synthetic=True,source_module='scenario-generator-mock',source_version=source_version,
                business_units=units,business_definition=definition,definition_version=definition['definition_version'],
                confirmation=dict(status=definition['status'],confirmed_on=definition['confirmed_on']))

    def encoded(value):
        return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')

    input_bytes=encoded(inputs);input_sha=hashlib.sha256(input_bytes).hexdigest()
    dataset_id='m03-mock-development-'+input_sha[:12]
    directory=safe_path(root/'data/evaluation'/dataset_id)
    manifest=dict(dataset_id=dataset_id,metric_id='M03',run_mode='DEVELOPMENT',source_type='DEVELOPMENT',
                  data_class='DEVELOPMENT',official=False,synthetic=True,
                  source_version=source_version,definition_version=definition['definition_version'],
                  purpose='M03 DEVELOPMENT Mock integration; not KTL performance evidence',
                  files=[dict(path='mock_inputs.json',sha256=input_sha)])
    manifest_bytes=encoded(manifest)
    files=[(safe_path(directory/'mock_inputs.json'),input_bytes),(safe_path(directory/'data_manifest.json'),manifest_bytes)]
    for path,raw in files:
        require(not path.exists() or (path.is_file() and path.read_bytes()==raw),'Existing development mock input differs: '+path.name)
    directory.mkdir(parents=True,exist_ok=True)
    for path,raw in files:
        if not path.exists():
            with path.open('xb') as output:output.write(raw)
    registered=dict(manifest=(directory/'data_manifest.json').relative_to(root).as_posix(),run_mode='DEVELOPMENT')
    datasets=config.setdefault('integration_datasets',{})
    require(isinstance(datasets,dict),'Integration dataset configuration required')
    require(dataset_id not in datasets or datasets[dataset_id]==registered,'Development mock dataset registration differs')
    datasets[dataset_id]=registered
    return dict(dataset_id=dataset_id,dataset_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                run_mode='DEVELOPMENT',generator_mode='MOCK',synthetic=True,source_module='scenario-generator-mock',
                source_version=source_version,business_units=units,business_definition=definition,
                real_generator_configured=bool(config.get('adapters',{}).get('scenario_generation')))


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
        if (mode=='DEVELOPMENT' and payload['business_unit_id']==DEVELOPMENT_BUSINESS_UNIT['business_unit_id']
                and payload['workflow_id']==DEVELOPMENT_BUSINESS_UNIT['workflow_id']):
            definition=DEVELOPMENT_BUSINESS_UNIT
            result.update(
                scenario_name=definition['business_unit_id']+' '+definition['business_name'],
                definition_version=definition['definition_version'],source_version=DEVELOPMENT_SOURCE_VERSION,
                workflow_id_source=definition['workflow_id_source'],
                description='확정 업무 정의 기반 개발용 Mock이며 실제 AI 생성 결과가 아닙니다.',
                steps=[
                    dict(order=1,action='open',target='명함 목록 화면',url=definition['start_screen'],expected_result='명함 목록 화면 표시'),
                    dict(order=2,action='click',target='명함 검색어 입력란',expected_result='검색어 입력 가능'),
                    dict(order=3,action='input',target='명함 검색어 입력란',value=definition['search_keyword'],expected_result='테스트 검색어 입력'),
                    dict(order=4,action='click',target='명함 검색 버튼',expected_result='테스트 검색어에 해당하는 명함 목록 표시'),
                    dict(order=5,action='click',target='명함 검색어 입력란',expected_result='검색어 수정 가능'),
                    dict(order=6,action='clear',target='명함 검색어 입력란',expected_result='검색어가 비워짐'),
                    dict(order=7,action='click',target='명함 검색 버튼',expected_result='전체 명함 목록 조회'),
                    dict(order=8,action='verify',target='명함 목록 화면',expected_result=definition['end_condition'])])
    else:
        adapter_input={k:payload[k] for k in ('business_unit_id','workflow_id')}
        definitions,verified=_real_input(Path(root).resolve(),config)
        definition=next((row for row in definitions if all(row[key]==payload[key] for key in ('business_unit_id','workflow_id'))),None)
        require(definition is not None,'Generation request does not match configured M03 business definitions')
        adapter_input.update(business_definition=definition,analysis_input=verified)
        proof=None
        if config['m03'].get('transport','SUBPROCESS')=='HTTP':
            from .m03_http import call_http
            result,proof=call_http(root,config,adapter_input)
        else:
            result=call_adapter(config,'scenario_generation',adapter_input,root)
        try:
            require(result.get('synthetic') is not True and result.get('generator_mode')!='MOCK','REAL generator returned synthetic Mock evidence')
            require(result.get('business_unit_id')==payload['business_unit_id'] and result.get('workflow_id')==payload['workflow_id'],'Generator identity mismatch')
            require(result.get('status') in {'SUCCESS','FAILED'} and nonempty(result.get('scenario_id')) and isinstance(result.get('steps'),list),'Invalid generation response')
            if result['status']=='SUCCESS':require(validate_scenario_result(result)['success'],'Generator returned an invalid successful scenario')
        except EvaluationError as exc:
            if proof is not None:raise EvaluationError(str(exc)+' 근거 ID: '+proof['attempt_id'],exc.status) from None
            raise
        result.setdefault('source_module',config['m03']['source_module'])
        result.setdefault('source_version',config['m03']['source_version'])
        if proof is not None:result['transport_evidence']=proof
    # 생성 응답의 실행 모드 구분
    result.update(run_mode=mode,generator_mode=engine,synthetic=engine=='MOCK',official_pass=None)
    return result
