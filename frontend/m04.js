// M04 개발 실행 화면
let m04View=null;
let m04RequestNumber=0;
let m04PollTimer=null;
const m04Names={QUEUED:'실행 대기',RUNNING:'실행 중',COMPLETED:'실행 완료',INTERRUPTED:'실행 중단',PENDING:'대기',PASS:'성공',FAIL:'실패',ERROR:'오류',TIMEOUT:'시간 초과',SKIPPED:'미실행'};
const m04ExecutionId=id=>/^M04-RUN-[0-9a-f]{32}$/.test(id||'');
const m04ScriptId=id=>/^[0-9a-f]{32}$/.test(id||'');
const m04Active=token=>token===m04RequestNumber&&/^\/metrics\/m04\/?$/i.test(location.pathname);
const m04Running=job=>['QUEUED','RUNNING'].includes(job?.status);
const m04CaseName=status=>m04Names[status]||String(status||'대기');
function m04Artifact(id,name) {
  return m04ExecutionId(id)&&['report.json','log.jsonl','steps.csv','scripts.zip','screenshots.zip'].includes(name)?`/api/development/m04/executions/${id}/artifacts/${name}`:null;
}
async function m04Json(url,payload) {
  const session=typeof catalog!=='undefined'?catalog?.server_session_id:null;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
  try {
    const response=await fetch(url,{signal:controller.signal,...(payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})});
    const data=await response.json();
    if(typeof ktlCheckServerSession==='function') ktlCheckServerSession(response,data,session);
    if(!response.ok) throw new Error(data?.error||`요청 오류 (${response.status})`);
    if(!data||typeof data!=='object'||Array.isArray(data)) throw new Error('실행 API 응답 형식을 확인하세요.');
    return data;
  } catch(error) {if(error.name==='AbortError') throw new Error('실행 API 응답 대기 시간을 초과했습니다.');throw error;}
  finally {clearTimeout(timer);}
}
function m04Status(message) {document.querySelector('#m04-status').textContent=message;}
function m04Remember(id) {
  if(typeof history==='undefined'||typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);
  if(m04ExecutionId(id)) query.set('execution_id',id);else query.delete('execution_id');
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
function renderM04(metric) {
  clearTimeout(m04PollTimer);
  const token=++m04RequestNumber,query=new URLSearchParams(location.search);
  m04View={metric,scripts:[],selected:new Set(),code:new Map(),openCode:new Set(),executions:[],execution:null,readiness:null,busy:false,scenarios:[],scenarioRun:null,scenario:null,locked:!!query.get('scenario_id'),selection:0};
  document.title='DEVELOPMENT · M04 · Rainbow';
  app.innerHTML=`${banner('고정 Selenium/Python 스크립트 실행')}<a class="back" href="${link('/')}">← 전체 평가</a>
    <section class="page-heading"><div><p class="eyebrow">M04 / DEVELOPMENT</p><h1>${labels.M04}</h1><p class="subtitle">고정한 스크립트의 실행 상태와 검증 결과를 확인합니다.</p></div><span class="badge neutral">로컬 실행</span></section>
    <section class="evaluation-panel m04-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2><button id="m04-refresh" class="m04-secondary" type="button">새로고침</button></div>
      <div class="dataset-grid"><div><label>실행 환경</label><strong id="m04-ready">확인 중…</strong></div><div><label>선택한 스크립트</label><strong id="m04-selected-count">0건</strong></div><div><label>M04 목표값</label><strong>≥ ${score(metric.target,'M04')}</strong></div></div>
      <div id="m04-scenario"></div><div class="run-row"><p>선택한 Python 파일을 이 PC에서 실행합니다.<br>등록한 원본은 수정하지 않고 보관합니다.</p><button id="m04-register" class="m04-secondary" type="button" disabled>스크립트 등록</button><input id="m04-file" type="file" accept=".py" hidden></div>
      <div id="m04-scripts"></div><div class="m04-run-actions"><button id="m04-start" type="button" disabled>선택 스크립트 실행</button><button id="m04-cancel" class="m04-secondary" type="button" disabled>실행 중단</button></div>
      <p id="m04-status" role="status">등록 스크립트와 실행 이력을 확인하고 있습니다…</p>
    </section>
    <section id="m04-result" class="result-panel"></section>
    <section class="result-panel m04-panel"><div class="panel-heading"><h2>실행 기록</h2><label class="m04-history-label">실행 이력<select id="m04-history" aria-label="실행 이력"></select></label></div>
      <div id="m04-progress-label" class="subtitle">실행 기록 대기</div><progress id="m04-progress" max="1" value="0" aria-label="스크립트 실행 진행률"></progress>
      <div id="m04-cases"></div><details class="m04-log" open><summary>실행 로그</summary><pre id="m04-logs">실행 로그가 없습니다.</pre></details><div id="m04-downloads" class="m04-downloads"></div>
    </section>`;
  document.querySelector('#m04-register').addEventListener('click',()=>{const input=document.querySelector('#m04-file');input.value='';input.click();});
  document.querySelector('#m04-file').addEventListener('change',registerM04);
  document.querySelector('#m04-start').addEventListener('click',startM04);
  document.querySelector('#m04-cancel').addEventListener('click',cancelM04);
  document.querySelector('#m04-refresh').addEventListener('click',()=>{if(!m04View.busy) renderM04(metric);});
  document.querySelector('#m04-history').addEventListener('change',event=>selectM04Execution(event.target.value));
  document.querySelector('#m04-scenario').addEventListener('change',event=>{
    if(event.target.id!=='m04-scenario-select'||m04View.busy||m04View.executions.some(m04Running)) return;
    m04View.scenario=m04View.scenarios.find(row=>row.scenario_id===event.target.value)||null;paintM04();
  });
  document.querySelector('#m04-scripts').addEventListener('change',event=>{
    const id=event.target.dataset?.scriptId;
    if(!m04ScriptId(id)||m04View.busy||m04View.executions.some(m04Running)) return;
    if(event.target.checked) m04View.selected.add(id);else m04View.selected.delete(id);
    paintM04();
  });
  document.querySelector('#m04-scripts').addEventListener('click',event=>{
    const target=event.target.closest('[data-script-code]');if(target) readM04Code(target.dataset.scriptCode);
  });
  paintM04();
  bootstrapM04(token,query).catch(error=>{if(m04Active(token)) m04Status(error.message);});
}
// 저장 시나리오와 원본 스크립트 연결
async function loadM04Scenario(token,query) {
  let explicit=query.get('m03_run_id'),requested=query.get('scenario_id');
  const latest=typeof catalog!=='undefined'?catalog?.metrics?.find(row=>row.metric_id==='M03')?.latest:null;
  let runId=explicit||(latest?.run_mode==='DEVELOPMENT'?latest.run_id:null);
  if(typeof catalog!=='undefined'&&catalog?.server_session_id) {
    const current=await m04Json('/api/development/m03/runs');
    if(!m04Active(token)) return;
    if(!Array.isArray(current.runs)) throw new Error('저장 시나리오 목록 형식을 확인하세요.');
    if((runId&&!current.runs.some(row=>row.run_id===runId))||(!runId&&requested)) {
      explicit=null;requested=null;m04View.locked=false;
      if(typeof ktlDropQuery==='function') ktlDropQuery(['m03_run_id','scenario_id']);
      runId=latest?.run_mode==='DEVELOPMENT'&&current.runs.some(row=>row.run_id===latest.run_id)?latest.run_id:null;
    }
  }
  if(!runId&&!requested) return;
  if(!/^DEV-M03-\d{8}T\d{6}-[0-9a-f]{12}$/.test(runId||'')) throw new Error('M03 실행 주소를 확인하세요.');
  const result=await m04Json(m03ResultPath(runId));
  if(!m04Active(token)) return;
  if(result.metric_id!=='M03'||result.run_mode!=='DEVELOPMENT'||result.run_id!==runId) throw new Error('저장된 M03 DEVELOPMENT 결과를 확인하세요.');
  const raw=await m04Json(m03ResultPath(runId,'received_payload.json'));
  if(!m04Active(token)) return;
  if(!Array.isArray(raw.scenarios)) throw new Error('저장 시나리오 형식을 확인하세요.');
  const rows=raw.scenarios.filter(row=>row&&typeof row.scenario_id==='string'&&row.scenario_id.trim()&&row.status!=='FAILED');
  let chosen=requested?rows.find(row=>row.scenario_id===requested):rows[0];
  if(requested&&!chosen) {
    if(typeof catalog!=='undefined'&&catalog?.server_session_id) {
      m04View.locked=false;chosen=rows[0];
      if(typeof ktlDropQuery==='function') ktlDropQuery(['m03_run_id','scenario_id']);
    } else throw new Error('요청한 시나리오가 저장된 M03 결과에 없습니다.');
  }
  m04View.scenarios=rows;m04View.scenarioRun=runId;m04View.scenario=chosen||null;
  m04View.scenarioSynthetic=raw.details?.synthetic===true||result.details?.external_details?.synthetic===true;
}
async function bootstrapM04(token,query) {
  const outputs=await Promise.allSettled([m04Json('/api/development/m04/scripts'),m04Json('/api/development/m04/executions'),loadM04Scenario(token,query)]);
  if(!m04Active(token)) return;
  const errors=[];
  for(let index=0;index<outputs.length;index++) {
    const item=outputs[index];
    if(item.status==='rejected') {errors.push(item.reason.message);continue;}
    if(index===0) {
      if(item.value.run_mode!=='DEVELOPMENT'||!Array.isArray(item.value.scripts)) {errors.push('개발용 스크립트 목록 형식을 확인하세요.');continue;}
      m04View.scripts=item.value.scripts.filter(row=>m04ScriptId(row.script_id));m04View.readiness=item.value.readiness;
    } else if(index===1) {
      if(!Array.isArray(item.value.executions)) {errors.push('실행 이력 형식을 확인하세요.');continue;}
      m04View.executions=item.value.executions.filter(row=>m04ExecutionId(row.execution_id));
    }
  }
  paintM04();
  const requested=query.get('execution_id'),stale=!!(typeof catalog!=='undefined'&&catalog?.server_session_id&&requested&&!m04View.executions.some(row=>row.execution_id===requested));
  const id=stale?null:requested||m04View.executions.find(m04Running)?.execution_id||m04View.executions[0]?.execution_id;
  if(stale) m04Remember(null);
  if(!stale&&requested&&!m04ExecutionId(requested)) errors.push('실행 이력 주소를 확인하세요.');
  else if(id) await selectM04Execution(id);
  if(m04Active(token)) m04Status(errors.length?errors.join(' · '):m04Running(m04View.execution)?'실행 중인 기록을 이어서 표시합니다.':'스크립트를 선택한 후 실행하세요.');
}
function m04ScriptAllowed(script) {
  return script.business_step_required===true&&script.execution_ready!==false&&(!m04View.locked||(script.scenario_id===m04View.scenario?.scenario_id&&script.source_m03_run_id===m04View.scenarioRun));
}
function paintM04() {
  const state=m04View,job=state.execution,active=m04Running(job),blocked=state.busy||state.executions.some(m04Running);
  const ready=state.readiness?.selenium&&state.readiness?.chrome;
  document.querySelector('#m04-ready').textContent=state.readiness?.message||(state.readiness?(ready?'Selenium · Chrome 준비 완료':'Selenium · Chrome 실행 환경 확인 필요'):'확인 중…');
  document.querySelector('#m04-selected-count').textContent=state.selected.size+'건';
  const scenario=state.scenario,isSynthetic=state.scenarioSynthetic||scenario?.synthetic===true||scenario?.generator_mode==='MOCK';
  document.querySelector('#m04-scenario').innerHTML=scenario?`<div class="m04-scenario-box"><p class="subtitle"><strong>${esc(scenario.scenario_name||scenario.business_unit_id||scenario.scenario_id)}</strong>${isSynthetic?' <span class="badge warning">샘플 시나리오</span>':''}</p><p class="run-meta">${esc(scenario.scenario_id)} · ${esc(state.scenarioRun)}</p>${!state.locked&&state.scenarios.length>1?`<label>등록할 시나리오<select id="m04-scenario-select" ${blocked?'disabled':''}>${state.scenarios.map(row=>`<option value="${esc(row.scenario_id)}" ${row.scenario_id===scenario.scenario_id?'selected':''}>${esc(row.scenario_name||row.business_unit_id||row.scenario_id)}</option>`).join('')}</select></label>`:''}<p class="subtitle">${state.scripts.some(row=>row.scenario_id===scenario.scenario_id&&row.source_m03_run_id===state.scenarioRun)?'저장된 시나리오에 연결된 실행 스크립트를 확인하세요.':'이 시나리오에 연결된 실행 스크립트를 등록하세요.'}</p><a class="download" href="${esc('/metrics/m07?'+new URLSearchParams({mode:'DEVELOPMENT',m03_run_id:state.scenarioRun,scenario_id:scenario.scenario_id}))}">시나리오 실행 조건 설정</a></div>`:'<p class="subtitle">스크립트를 등록하려면 M03에서 시나리오를 먼저 저장하세요.</p>';
  document.querySelector('#m04-register').disabled=blocked||!scenario;
  document.querySelector('#m04-file').disabled=blocked||!scenario;
  document.querySelector('#m04-refresh').disabled=state.busy;
  document.querySelector('#m04-start').disabled=blocked||!ready||state.selected.size<1||state.selected.size>10;
  document.querySelector('#m04-cancel').disabled=state.busy||!active;
  document.querySelector('#m04-history').disabled=state.busy;
  document.querySelector('#m04-scripts').innerHTML=state.scripts.length?`<div class="m04-script-list">${state.scripts.map(script=>{
    const allowed=m04ScriptAllowed(script),open=state.openCode.has(script.script_id),code=state.code.get(script.script_id);
    return `<article class="m04-script"><label class="m04-script-select"><input type="checkbox" data-script-id="${esc(script.script_id)}" ${state.selected.has(script.script_id)?'checked':''} ${blocked||!allowed?'disabled':''}><span><strong>${esc(script.filename)}</strong><small>${esc(script.scenario_name||script.scenario_id)}${script.source_synthetic?' · 샘플 시나리오 연결':''}${script.business_step_required!==true?' · 기존 원시 기록용 코드':script.execution_ready===false?' · '+esc(script.execution_notice||'실행 조건 준비 필요'):!allowed?' · 다른 시나리오':''}</small></span></label><button class="m04-code-button" type="button" data-script-code="${esc(script.script_id)}" aria-expanded="${open}">${open?'코드 접기':'코드 보기'}</button>${open?`<div class="m04-code"><p class="run-meta">고정 시각: ${esc(script.fixed_at)}<br>SHA-256: ${esc(script.sha256)}</p><pre>${esc(code??'원본 코드를 불러오는 중…')}</pre></div>`:''}</article>`;
  }).join('')}</div>`:'<p class="empty">등록된 실행 스크립트가 없습니다.</p>';
  document.querySelector('#m04-history').innerHTML=`<option value="">실행 이력 선택</option>${state.executions.map(row=>`<option value="${esc(row.execution_id)}" ${row.execution_id===job?.execution_id?'selected':''}>${esc(row.started_at||row.created_at||row.execution_id)} · ${esc(m04CaseName(row.status))}</option>`).join('')}`;
  paintM04Execution();
}
function paintM04Execution() {
  const job=m04View.execution,cases=Array.isArray(job?.cases)?job.cases:[],result=job?.status==='COMPLETED'?job.result:null,counts=job?.counts||{};
  const done=cases.filter(row=>!['PENDING','RUNNING'].includes(row.status)).length;
  document.querySelector('#m04-progress').max=Math.max(1,cases.length);document.querySelector('#m04-progress').value=done;
  document.querySelector('#m04-progress-label').textContent=job?`${m04CaseName(job.status)} · ${done}/${cases.length}건${job.error?' · '+job.error:''}`:'실행 기록 대기';
  document.querySelector('#m04-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2>${result?.evidence_file?`<a class="download" href="${esc(m04Artifact(job.execution_id,'report.json'))}" download>실행 보고서 ↓</a>`:''}</div><div class="result-grid"><div><label>자동 실행 성공률</label><strong class="large-score">${score(result?.score,'M04')}</strong></div><div><label>정상 완료 테스트</label><strong>${esc(counts.successful_execution_count??'—')}</strong></div><div><label>전체 실행 테스트</label><strong>${esc(counts.total_execution_count??'—')}</strong></div><div><label>실행 상태</label><strong>${esc(job?m04CaseName(job.status):'미실행')}</strong></div></div><p class="subtitle">정상 완료 테스트 수 / 전체 자동 실행 테스트 수 × 100 · 실패는 분모에 포함합니다.</p>${result?`<p class="run-meta">${esc(result.run_id)} · DEVELOPMENT · 공식 시험성적 아님</p>`:'<p class="subtitle">실행과 평가가 완료되면 성공률을 표시합니다.</p>'}`;
  document.querySelector('#m04-cases').innerHTML=cases.length?`<p class="run-meta">실행 ID: ${esc(job.execution_id)}</p><div class="table-scroll"><table><thead><tr><th>스크립트</th><th>시나리오</th><th>상태·업무 단계</th><th>실행 시각·소요 시간</th><th>반환 코드</th></tr></thead><tbody>${cases.map(row=>`<tr><td>${esc(row.script_name||row.script_id)}</td><td>${esc(row.scenario_id)}</td><td><span class="badge ${row.status==='PASS'?'pass':['FAIL','ERROR','TIMEOUT'].includes(row.status)?'fail':'neutral'}">${esc(m04CaseName(row.status))}</span>${row.error_message||row.error?`<p>${esc(row.error_message||row.error)}</p>`:''}${m04StepDetails(row)}</td><td><span>${esc(row.started_at||'—')}</span><br><span>${esc(row.completed_at||'—')}</span><br>${row.duration_ms==null?'—':esc(row.duration_ms)+' ms'}</td><td>${esc(row.returncode??'—')}</td></tr>`).join('')}</tbody></table></div>`:'<p class="empty">실행하면 스크립트별 상태와 업무 단계가 표시됩니다.</p>';
  document.querySelector('#m04-logs').textContent=Array.isArray(job?.logs)&&job.logs.length?job.logs.map(row=>`${row.time||''}${row.case_id?' ['+row.case_id+']':''} ${row.message||''}`).join('\n'):'실행 로그가 없습니다.';
  document.querySelector('#m04-downloads').innerHTML=job?['report.json','log.jsonl','steps.csv','scripts.zip','screenshots.zip'].map((name,index)=>`<a class="download" href="${m04Artifact(job.execution_id,name)}" download>${['실행 보고서','전체 로그','단계 기록 CSV','고정 스크립트 원본','마스킹된 실행 화면'][index]} ↓</a>`).join(''):'';
}
function m04ScreenDetails(row) {
  const id=row.execution_id||m04View?.execution?.execution_id,caseId=row.case_id;
  const valid=m04ExecutionId(id)&&/^CASE-[0-9]{3}$/.test(caseId||'');
  const records=Array.isArray(row.screenshots)?row.screenshots:[];
  return `<details class="m04-screenshots"><summary>실행 전·후 화면</summary><p class="subtitle">문자·이미지가 마스킹된 실행 화면입니다. 판정은 독립 DOM/API 검사로 확인하며 이미지 일치 점수를 계산하지 않습니다.</p><div class="m04-screenshot-pair">${['before','after'].map((phase,index)=>{
    const record=records.find(item=>item.phase===phase),captured=valid&&record?.status==='CAPTURED'&&record?.file===phase+'.png'&&record?.policy==='text-and-images-masked-v1';
    const url=captured?`/api/development/m04/executions/${id}/screenshots/${caseId}/${phase}.png`:null;
    return `<article><strong>실행 ${index?'후':'전'}</strong>${url?`<a href="${url}" target="_blank" rel="noopener"><img src="${url}" loading="lazy" alt="문자와 이미지가 마스킹된 실행 ${index?'후':'전'} 화면"></a><p class="run-meta">${esc(record.captured_at||'')}</p>`:`<p class="subtitle">캡처되지 않음${record?.reason?' · '+esc(record.reason):' · 저장된 화면 근거 없음'}</p>`}</article>`;
  }).join('')}</div></details>`;
}
function m04StepDetails(row) {
  const strict=row.step_evidence_mode==='BUSINESS_STEPS',steps=Array.isArray(row.steps)?row.steps:[];
  const traces=Array.isArray(row.action_logs)?row.action_logs:strict?[]:steps;
  const business=strict?`<p>성공 단계 ${esc(row.success_step_count??steps.filter(step=>step.status==='PASS').length)} / ${esc(row.required_step_count??steps.length)}</p>${row.failed_step!=null?`<p>실패 단계: ${esc(row.failed_step)}</p>`:''}${row.failure_selector?`<p>실패 선택자: <code>${esc(row.failure_selector)}</code></p>`:''}<details><summary>업무 단계 ${steps.length}건</summary><ol class="m04-steps">${steps.map(step=>`<li><strong>${esc(step.sequence)} · ${esc(step.action)}</strong> ${esc(step.target)} <span>${esc(m04CaseName(step.status))}</span><span>기대 결과: ${esc(typeof step.expected_result==='object'?JSON.stringify(step.expected_result):step.expected_result||'—')}</span>${step.failure_selector?`<span>실패 선택자: <code>${esc(step.failure_selector)}</code></span>`:''}${step.error?`<span>${esc(step.error)}</span>`:''}</li>`).join('')}</ol></details>`:'<p class="subtitle">기존 스크립트 · 업무 단계별 완료 근거 없음</p>';
  return business+m04ScreenDetails(row)+(traces.length?`<details class="m04-traces"><summary>브라우저·assert 원시 기록 ${traces.length}건</summary><ol class="m04-steps">${traces.map(step=>`<li><strong>${esc(step.sequence)} · ${esc(step.action)}</strong> ${esc(step.target)} <span>${esc(m04CaseName(step.status))}${step.selector?' · '+esc(step.selector):''}</span>${step.error?`<span>${esc(step.error)}</span>`:''}</li>`).join('')}</ol></details>`:'');
}
async function readM04Code(id) {
  if(!m04ScriptId(id)||!m04View.scripts.some(row=>row.script_id===id)) return;
  if(m04View.openCode.has(id)) {m04View.openCode.delete(id);paintM04();return;}
  const token=m04RequestNumber;m04View.openCode.add(id);paintM04();
  if(m04View.code.has(id)) return;
  try {
    const data=await m04Json('/api/development/m04/scripts/'+id);
    if(!m04Active(token)) return;
    if(data.script?.script_id!==id||typeof data.code!=='string') throw new Error('원본 스크립트 응답을 확인하세요.');
    m04View.code.set(id,data.code);paintM04();
  } catch(error) {if(m04Active(token)) {m04View.openCode.delete(id);paintM04();m04Status(error.message);}}
}
async function registerM04() {
  const file=document.querySelector('#m04-file').files?.[0],state=m04View;
  if(!file||state.busy||state.executions.some(m04Running)||!state.scenario) return;
  if(!/\.py$/i.test(file.name)||!file.size||file.size>256*1024) {m04Status('256KB 이하의 Python(.py) 파일을 선택하세요.');return;}
  const token=m04RequestNumber;state.busy=true;paintM04();m04Status('원본 스크립트를 등록하고 있습니다…');
  try {
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let start=0;start<bytes.length;start+=32768) binary+=String.fromCharCode(...bytes.subarray(start,start+32768));
    if(!m04Active(token)) return;
    const row=state.scenario,data=await m04Json('/api/development/m04/scripts',{filename:file.name,python_base64:btoa(binary),scenario_id:row.scenario_id,scenario_name:row.scenario_name||row.business_unit_id||row.scenario_id,m03_run_id:state.scenarioRun,require_business_steps:true});
    if(!m04Active(token)) return;
    if(!m04ScriptId(data.script?.script_id)) throw new Error('등록 스크립트 ID를 확인하세요.');
    const existing=state.scripts.findIndex(script=>script.script_id===data.script.script_id);
    if(existing<0) state.scripts.unshift(data.script);else state.scripts[existing]=data.script;
    state.selected.add(data.script.script_id);m04Status('원본 스크립트를 등록했습니다. 선택 스크립트 실행을 누르세요.');
  } catch(error) {if(m04Active(token)) m04Status(error.message);}
  finally {if(m04Active(token)) {state.busy=false;paintM04();}}
}
function acceptM04Execution(job) {
  if(!job||!m04ExecutionId(job.execution_id)||!Array.isArray(job.cases)) throw new Error('실행 기록 형식을 확인하세요.');
  m04View.execution=job;
  const index=m04View.executions.findIndex(row=>row.execution_id===job.execution_id);
  if(index<0) m04View.executions.unshift(job);else m04View.executions[index]=job;
  m04Remember(job.execution_id);paintM04();
}
async function startM04() {
  const state=m04View;
  if(state.busy||state.executions.some(m04Running)||!state.readiness?.selenium||!state.readiness?.chrome) return;
  const ids=[...state.selected];
  if(!ids.length||ids.length>10||ids.some(id=>!state.scripts.some(row=>row.script_id===id&&m04ScriptAllowed(row)))) {m04Status('실행할 스크립트를 1~10건 선택하세요.');return;}
  const token=m04RequestNumber;state.busy=true;clearTimeout(m04PollTimer);paintM04();m04Status('고정한 스크립트 실행을 요청하고 있습니다…');
  try {
    const data=await m04Json('/api/development/m04/executions',{script_ids:ids});
    if(!m04Active(token)) return;
    acceptM04Execution(data.execution);scheduleM04Poll(token);m04Status('실행 요청을 접수했습니다. 진행 상태와 로그를 확인하세요.');
  } catch(error) {if(m04Active(token)) m04Status(error.message);}
  finally {if(m04Active(token)) {state.busy=false;paintM04();}}
}
async function selectM04Execution(id) {
  if(!m04ExecutionId(id)||m04View.busy) return;
  const token=m04RequestNumber,selection=++m04View.selection;clearTimeout(m04PollTimer);
  m04Status('실행 기록을 불러오고 있습니다…');
  try {
    const data=await m04Json('/api/development/m04/executions/'+id);
    if(!m04Active(token)||selection!==m04View.selection) return;
    if(data.execution?.execution_id!==id) throw new Error('요청한 실행 기록과 응답이 다릅니다.');
    acceptM04Execution(data.execution);scheduleM04Poll(token);m04Status(m04Running(data.execution)?'실행 중인 기록을 표시합니다.':'저장된 실행 결과를 불러왔습니다.');
  } catch(error) {if(m04Active(token)&&selection===m04View.selection) m04Status(error.message);}
}
function scheduleM04Poll(token,delay=1500) {
  clearTimeout(m04PollTimer);
  if(!m04Active(token)||!m04Running(m04View.execution)) return;
  const id=m04View.execution.execution_id,selection=m04View.selection;
  m04PollTimer=setTimeout(async()=>{
    if(!m04Active(token)||m04View.execution?.execution_id!==id||selection!==m04View.selection) return;
    try {
      const data=await m04Json('/api/development/m04/executions/'+id);
      if(!m04Active(token)||m04View.execution?.execution_id!==id||selection!==m04View.selection) return;
      if(data.execution?.execution_id!==id) throw new Error('실행 상태 응답이 일치하지 않습니다.');
      acceptM04Execution(data.execution);
      if(m04Running(data.execution)) scheduleM04Poll(token);
      else m04Status(data.execution.status==='COMPLETED'?'실행과 결과 저장을 완료했습니다.':'실행이 종료되었습니다. 상태와 로그를 확인하세요.');
    } catch(error) {if(error.status!=='SESSION_EXPIRED'&&m04Active(token)&&selection===m04View.selection&&m04View.execution?.execution_id===id) {m04Status(error.message);scheduleM04Poll(token,5000);}}
  },delay);
}
async function cancelM04() {
  if(m04View.busy||!m04Running(m04View.execution)) return;
  const token=m04RequestNumber,id=m04View.execution.execution_id,selection=m04View.selection;
  m04View.busy=true;clearTimeout(m04PollTimer);paintM04();m04Status('실행 중단을 요청하고 있습니다…');
  try {
    const data=await m04Json('/api/development/m04/executions/'+id+'/cancel',{});
    if(!m04Active(token)||selection!==m04View.selection) return;
    if(data.execution?.execution_id!==id) throw new Error('중단 응답의 실행 ID가 다릅니다.');
    acceptM04Execution(data.execution);scheduleM04Poll(token);m04Status('실행 중단 상태를 확인하세요. 미완료 실행은 성공률로 표시하지 않습니다.');
  } catch(error) {if(m04Active(token)) {m04Status(error.message);scheduleM04Poll(token);}}
  finally {if(m04Active(token)) {m04View.busy=false;paintM04();}}
}
