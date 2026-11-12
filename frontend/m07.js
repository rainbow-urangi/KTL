// M07 코드 생성·검사 화면
let m07View=null;
let m07RequestNumber=0;
let m07PollTimer=null;
const m07Names={QUEUED:'생성 대기',GENERATING:'코드 생성 중',GENERATED:'생성 완료',VALIDATING:'문법·실행 검사 중',COMPLETED:'검사 완료',INTERRUPTED:'중단',PENDING:'대기',RUNNING:'진행 중',PASS:'통과',FAIL:'실패',ERROR:'오류',TIMEOUT:'시간 초과',SKIPPED:'미실행'};
const m07Id=id=>/^M07-GEN-[0-9a-f]{32}$/.test(id||'');
const m07CaseId=id=>/^CASE-0(?:0[1-9]|1[0-9]|20)$/.test(id||'');
const m07RunId=id=>/^DEV-M03-\d{8}T\d{6}-[0-9a-f]{12}$/.test(id||'');
const m07Running=job=>['QUEUED','GENERATING','VALIDATING'].includes(job?.status);
const m07Active=token=>token===m07RequestNumber&&/^\/metrics\/m07\/?$/i.test(location.pathname)&&new URLSearchParams(location.search).get('mode')==='DEVELOPMENT';
const m07Name=status=>m07Names[status]||String(status||'대기');
function m07JobName(job) {
  return job?.code_source==='PREPARED'?({QUEUED:'코드 준비 대기',GENERATING:'원본 준비 중',GENERATED:'준비 완료'}[job.status]||m07Name(job.status)):m07Name(job?.status);
}
function m07AcceptProvider(value) {
  if(m07View&&value&&typeof value==='object'&&!Array.isArray(value)&&typeof value.blocked==='boolean') m07View.providerState=value;
}
function m07ProviderBlocked(state=m07View) {return state?.providerState?.blocked===true;}
function m07ProviderNotice(state=m07View) {
  const value=state?.providerState;if(!value?.blocked) return '';
  const reason=value.error_type==='tokens'?'토큰 사용량 제한':value.error_type==='requests'?'요청 횟수 제한':'공급자 요청 제한';
  const when=typeof value.next_eligible_at==='string'&&!Number.isNaN(Date.parse(value.next_eligible_at))?value.next_eligible_at:null;
  return `<p class="notice" id="m07-provider-blocker">${reason}${value.http_status===429?' (HTTP429)':''}으로 GPT 생성을 중단했습니다.${value.error_code?` 사유: ${esc(value.error_code)}.`:''}${when?` 다음 요청 가능 시각 하한: <time datetime="${esc(when)}">${esc(new Date(when).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))} KST</time>.`:' 다음 요청 가능 시각은 확인되지 않았습니다.'} 대기창 이후 새로고침으로 다시 확인하세요. 자동 재시도는 하지 않습니다. 기존 코드 검사·취소는 계속 사용할 수 있습니다.</p>`;
}
function m07Artifact(id,name) {
  return m07Id(id)&&['report.json','code.zip','steps.csv','log.jsonl','screenshots.zip'].includes(name)?`/api/development/m07/generations/${id}/artifacts/${name}`:null;
}
async function m07Json(url,payload) {
  const session=typeof catalog!=='undefined'?catalog?.server_session_id:null;
  const view=m07View;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
  try {
    const response=await fetch(url,{signal:controller.signal,...(payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})});
    const data=await response.json();
    if(typeof ktlCheckServerSession==='function') ktlCheckServerSession(response,data,session);
    if(m07View===view) m07AcceptProvider(data?.provider_state||data?.generation?.provider_state);
    if(!response.ok) throw new Error(data?.error||`요청 오류 (${response.status})`);
    if(!data||typeof data!=='object'||Array.isArray(data)) throw new Error('코드 생성 API 응답 형식을 확인하세요.');
    return data;
  } catch(error) {if(error.name==='AbortError') throw new Error('코드 생성 API 응답 대기 시간을 초과했습니다.');throw error;}
  finally {clearTimeout(timer);}
}
function m07Status(message) {document.querySelector('#m07-status').textContent=message;}
function m07Remember(id) {
  if(typeof history==='undefined'||typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);
  if(m07Id(id)) query.set('generation_id',id);else query.delete('generation_id');
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
function renderM07(metric) {
  clearTimeout(m07PollTimer);
  const token=++m07RequestNumber,query=new URLSearchParams(location.search);
  m07View={metric,context:null,providerState:null,selected:new Set(),source:query.get('m03_run_id')||'',requestedScenario:query.get('scenario_id')||'',generations:[],generation:null,code:new Map(),codeProof:new Map(),openCode:new Set(),exportSelected:new Set(),exportInitialized:false,exportLink:null,busy:false,selection:0,pollRevision:0,contextError:'',contextEditor:null,bulkRefs:new Map(),preparedCodes:[],preparedSelected:false,preparedLoading:false,preparedError:'',mode:query.get('m03_run_id')?'llm':'meeting',meeting:{loading:true,context:null,error:'',items:[],validText:null,message:'시험 입력 20건을 JSON으로 붙여넣거나 파일을 선택하세요.'},workflows:{loading:true,error:'',catalog:null,selected:new Set(),parameters:{},preparedSignature:null,message:'업무별 준비 코드를 확인하고 있습니다…'}};
  m07View.expandedCases=new Set();
  m07View.autoPreviewJobs=new Set();m07View.autoPreviewRequests=new Map();
  document.title='DEVELOPMENT · M07 · Rainbow';
  app.innerHTML=`${banner('Selenium/Python 코드 확인 · Chrome 실행 검사')}<a class="back" href="${link('/')}">← 전체 평가</a>
    <section class="page-heading"><div><p class="eyebrow">M07 / DEVELOPMENT</p><h1>${labels.M07}</h1><p class="subtitle">${esc(metric.metric_name||'LLM Generated Code Validation')}</p></div><span class="badge neutral m07-browser">Chrome</span></section>
    <div class="m07-mode-bar"><p class="subtitle">입력 20건 · 실제 LLM 생성 · 별도 문법·실행 검사</p><button id="m07-refresh" class="m07-secondary" type="button">새로고침</button></div>
    <section id="m07-meeting-panel" class="evaluation-panel m07-panel"><div class="panel-heading"><h2>시험 입력 20건</h2><span id="m07-meeting-count" class="badge neutral">0 / 20건</span></div>
      <div class="dataset-grid"><div><label>LLM 연결</label><strong id="m07-meeting-ready">확인 중…</strong></div><div><label>생성 방식</label><strong>입력별 1회 · 총 20건</strong></div><div><label>통과 기준</label><strong>16 / 20건 · 80%</strong></div></div>
      <p id="m07-meeting-environment" class="subtitle"></p><div id="m07-meeting-provider" role="status"></div>
      <label for="m07-meeting-input">시험 입력 20건 (JSON)</label><textarea id="m07-meeting-input" rows="9" class="m07-json-input" aria-label="시험 입력 20건 JSON" spellcheck="false"></textarea>
      <div class="m07-actions"><label>JSON 파일<input id="m07-meeting-file" type="file" accept=".json,application/json" aria-label="시험 입력 20건 JSON 파일"></label><button id="m07-meeting-draft" class="m07-secondary" type="button">입력 초안 불러오기</button><button id="m07-meeting-check" class="m07-secondary" type="button">입력 확인</button><button id="m07-meeting-generate" type="button" disabled>LLM 코드 20건 생성</button></div>
      <p id="m07-meeting-status" class="subtitle" role="status"></p><details class="m07-step-detail"><summary>입력 형식과 실행 조건</summary><p class="subtitle">서로 다른 시나리오 20건을 배열로 입력합니다. 각 입력에는 input_id와 scenario가 필요하며, scenario에 단계별 조작·대상·입력값·기대 결과와 execution_contract를 지정합니다. 실제 요소와 확인 조건은 사전에 정하고 인증정보·토큰·평가 정답을 넣지 마세요. 생성 후 검사 버튼으로 Chrome 실행을 시작합니다.</p><pre id="m07-meeting-schema"></pre></details>
    </section>
    <details id="m07-auxiliary" class="evaluation-panel m07-panel m07-auxiliary" ${query.get('m03_run_id')?'open':''}><summary>M03 연결·준비 코드 (보조 도구)</summary><p class="subtitle">M03 연결과 PREPARED 코드는 별도 개발 기록입니다. 위의 실제 LLM 20건 시험을 대신하지 않습니다.</p><div class="m07-source-tabs" role="group" aria-label="보조 코드 준비 방식"><button id="m07-mode-meeting" type="button" aria-pressed="true">시험 입력 20건</button><button id="m07-mode-llm" type="button" aria-pressed="false">M03 연결</button><button id="m07-mode-prepared" type="button" aria-pressed="false">준비 코드 · PREPARED</button></div>
    <section id="m07-workflow-panel" class="m07-panel" hidden><div class="panel-heading"><h2>준비 코드 · PREPARED</h2><span id="m07-workflow-count" class="badge neutral">선택 0건</span></div>
      <p class="subtitle">업무별로 준비한 Selenium 원본을 사용합니다. LLM 생성 실적과 구분해 코드 검사 결과를 기록합니다.</p>
      <div class="m07-workflow-toolbar"><span id="m07-workflow-login" class="subtitle">로그인 준비 확인 중…</span><button id="m07-workflow-all" class="m07-secondary" type="button">사용 가능한 업무 선택</button></div>
      <div id="m07-workflows" class="m07-workflow-grid"></div>
      <div class="m07-workflow-inputs"><label>시험 날짜<input id="m07-workflow-date" type="date"></label><label>제목<input id="m07-workflow-title" type="text" maxlength="90" autocomplete="off"></label><label class="m07-input-wide">내용<textarea id="m07-workflow-description" rows="3" maxlength="2000"></textarea></label></div>
      <details id="m07-workflow-extra" class="m07-step-detail"><summary>업무별 추가 입력</summary><div id="m07-workflow-extra-fields" class="m07-workflow-inputs"></div></details>
      <div class="m07-actions"><button id="m07-workflow-prepare" type="button" disabled>선택 업무 코드 준비</button></div><p id="m07-workflow-status" class="subtitle" role="status"></p>
    </section>
    <section id="m07-llm-panel" class="m07-panel" hidden><div class="panel-heading"><h2>M03 시나리오 및 생성 설정</h2><span class="badge neutral">LLM API 사용</span></div>
      <div class="dataset-grid"><div><label>LLM 연결</label><strong id="m07-ready">확인 중…</strong></div><div><label>선택 시나리오</label><strong id="m07-selected-count">0건</strong></div><div><label>목표값</label><strong>≥ ${score(metric.target,'M07')}</strong></div></div>
      <p id="m07-environment" class="subtitle"></p><div id="m07-provider-state" role="status"></div><div id="m07-scenarios"></div>
      <details class="m07-step-detail"><summary>시나리오 일괄 선택</summary>
        <p class="subtitle">저장된 M03 시나리오 원본 JSON 배열 또는 실행 ID·시나리오 ID·원본 해시 참조를 최대 20건 입력하세요. 입력 내용이 저장 원본과 일치하는지 검사한 뒤 선택하며, 생성·실행은 별도 버튼으로 시작합니다.</p>
        <textarea id="m07-bulk-input" rows="7" class="m07-json-input" aria-label="일괄 시나리오 JSON" spellcheck="false"></textarea>
        <div class="m07-actions"><button id="m07-bulk-current" class="m07-secondary" type="button">현재 선택 목록 가져오기</button><label>JSON 파일<input id="m07-bulk-file" type="file" accept=".json,application/json" aria-label="일괄 시나리오 JSON 파일"></label><button id="m07-bulk-apply" class="m07-secondary" type="button">원본 확인·일괄 선택</button></div>
        <p id="m07-bulk-status" class="subtitle" role="status">검증 후 선택 목록에 적용합니다. 새 M03 결과를 만들지 않습니다.</p>
      </details>
      <details id="m07-context-editor" class="m07-step-detail"><summary>시나리오 실행 조건 설정</summary>
        <p class="subtitle">M03 원본을 보존하고 새 생성·등록 작업에 적용할 조건을 저장합니다. 각 단계의 CSS 선택자 또는 URL과 실제 확인할 상태를 입력하세요. 인증정보·토큰·정답 데이터는 넣지 마세요.</p>
        <label>설정할 시나리오<select id="m07-context-scenario" aria-label="실행 조건을 설정할 시나리오"></select></label>
        <button id="m07-context-load" class="m07-secondary" type="button">조건 불러오기</button>
        <label>단계별 기대 결과 (JSON)<textarea id="m07-context-expected" rows="6" class="m07-json-input" aria-label="단계별 기대 결과 JSON" spellcheck="false"></textarea></label>
        <label>실행 대상·검사 조건 (JSON)<textarea id="m07-context-contract" rows="12" class="m07-json-input" aria-label="실행 계약 JSON" spellcheck="false"></textarea></label>
        <p class="subtitle">검사 종류: visible, focus, value, text_equals, text_contains, url_path, count. CSS 대상은 {"by":"css selector","value":"#save"}, 조건은 {"kind":"visible"} 또는 {"kind":"value","expected":"검사할 값"} 형태입니다. URL에는 query·fragment를 넣지 마세요.</p>
        <button id="m07-context-save" class="m07-secondary" type="button" disabled>조건 검증·저장</button><p id="m07-context-status" class="subtitle" role="status">시나리오를 선택하고 조건을 불러오세요.</p>
      </details>
      <details class="m07-step-detail"><summary>기존 코드 파일 등록</summary><div class="m07-actions"><label>코드 파일<input id="m07-code-files" type="file" accept=".py" multiple aria-label="코드 파일"></label></div>
      <p id="m07-code-status" class="subtitle" role="status">파일을 선택하지 않으면 GPT로 코드를 생성합니다. 파일 선택은 새로고침으로 해제합니다.</p>
      </details><div class="m07-actions"><button id="m07-generate" type="button" disabled>선택 시나리오 코드 생성</button></div>
    </section></details>
    <section class="evaluation-panel m07-panel"><div class="panel-heading"><h2>실행 및 검사</h2></div><p id="m07-current-source" class="subtitle">업무 코드를 준비하면 원본과 실행 대상을 표시합니다.</p><div class="run-row"><p>원본 코드를 확인한 뒤 문법·실행 검사를 시작하세요.</p><div class="m07-actions"><button id="m07-validate" type="button" disabled>Chrome 문법·실행 검사</button><button id="m07-cancel" class="m07-secondary" type="button" disabled>작업 중단</button></div></div><p id="m07-status" role="status">준비 상태를 확인하고 있습니다…</p></section>
    <section id="m07-result" class="result-panel"></section>
    <section class="result-panel m07-panel"><div class="panel-heading"><h2>코드와 검사 기록</h2><label class="m07-history-label">작업 이력<select id="m07-history" aria-label="생성 및 검사 이력"></select></label></div>
      <div id="m07-progress-label" class="subtitle">작업 기록 대기</div><progress id="m07-progress" max="1" value="0" aria-label="코드 생성 및 검사 진행률"></progress>
      <div id="m07-cases"></div><div id="m07-export"></div><details class="m07-log"><summary>작업 로그</summary><pre id="m07-logs">작업 로그가 없습니다.</pre></details><div id="m07-downloads" class="m07-downloads"></div>
    </section>`;
  document.querySelector('#m07-generate').addEventListener('click',startM07);
  for(const mode of ['meeting','prepared','llm']) document.querySelector('#m07-mode-'+mode).addEventListener('click',()=>selectM07Mode(mode));
  document.querySelector('#m07-meeting-input').addEventListener('input',()=>{m07View.meeting.items=[];m07View.meeting.validText=null;m07View.meeting.message='입력이 변경되었습니다. 입력 확인 후 코드를 생성하세요.';paintM07Meeting();});
  document.querySelector('#m07-meeting-check').addEventListener('click',checkM07MeetingInput);
  document.querySelector('#m07-meeting-generate').addEventListener('click',startM07Meeting);
  document.querySelector('#m07-meeting-file').addEventListener('change',loadM07MeetingFile);
  document.querySelector('#m07-meeting-draft').addEventListener('click',loadM07MeetingDraft);
  document.querySelector('#m07-workflow-prepare').addEventListener('click',prepareM07Workflows);
  document.querySelector('#m07-workflow-all').addEventListener('click',()=>{
    if(m07View.busy||m07View.generations.some(m07Running)) return;
    const source=m07View.workflows,available=(source.catalog?.workflows||[]).filter(row=>row.available);
    source.selected=new Set(available.every(row=>source.selected.has(row.workflow_id))?[]:available.map(row=>row.workflow_id));paintM07Workflows();
  });
  document.querySelector('#m07-workflows').addEventListener('change',event=>{
    const id=event.target.dataset?.workflowId,source=m07View.workflows;
    if(m07View.busy||m07View.generations.some(m07Running)||!source.catalog?.workflows.some(row=>row.workflow_id===id&&row.available)) return;
    if(event.target.checked) source.selected.add(id);else source.selected.delete(id);paintM07Workflows();
  });
  for(const field of ['date','title','description']) document.querySelector('#m07-workflow-'+field).addEventListener('input',event=>{
    if(m07View.busy||m07View.generations.some(m07Running)) return;
    m07View.workflows.parameters[field]=event.target.value;paintM07WorkflowActions();
  });
  document.querySelector('#m07-workflow-extra-fields').addEventListener('input',event=>{
    const field=event.target.dataset?.workflowParameter,source=m07View.workflows;
    if(!field||!Object.hasOwn(source.parameters,field)||m07View.busy||m07View.generations.some(m07Running)) return;
    source.parameters[field]=typeof source.catalog?.defaults?.[field]==='number'?Number(event.target.value):event.target.value;paintM07WorkflowActions();
  });
  document.querySelector('#m07-validate').addEventListener('click',validateM07);
  document.querySelector('#m07-cancel').addEventListener('click',cancelM07);
  document.querySelector('#m07-code-files').addEventListener('change',loadM07PreparedCodes);
  document.querySelector('#m07-refresh').addEventListener('click',()=>{if(!m07View.busy) renderM07(metric);});
  document.querySelector('#m07-history').addEventListener('change',event=>selectM07Generation(event.target.value));
  document.querySelector('#m07-context-load').addEventListener('click',loadM07ExecutionContext);
  document.querySelector('#m07-context-save').addEventListener('click',saveM07ExecutionContext);
  document.querySelector('#m07-context-scenario').addEventListener('change',()=>{
    m07View.contextEditor=null;document.querySelector('#m07-context-expected').value='';document.querySelector('#m07-context-contract').value='';
    document.querySelector('#m07-context-status').textContent='조건 불러오기를 눌러 선택한 시나리오의 설정을 확인하세요.';paintM07ContextEditor();
  });
  document.querySelector('#m07-bulk-apply').addEventListener('click',applyM07BulkSelection);
  document.querySelector('#m07-bulk-current').addEventListener('click',()=>{
    const rows=m07Scenarios().filter(row=>m07View.selected.has(row.scenario_id));
    document.querySelector('#m07-bulk-input').value=JSON.stringify(rows.map(m07SelectedRef),null,2);
  });
  document.querySelector('#m07-bulk-file').addEventListener('change',async event=>{
    const file=event.target.files?.[0],token=m07RequestNumber;if(!file) return;
    if(file.size>262144) {document.querySelector('#m07-bulk-status').textContent='JSON 파일은 256 KiB 이하로 선택하세요.';return;}
    try {const value=await file.text();if(m07Active(token)) document.querySelector('#m07-bulk-input').value=value;}
    catch {if(m07Active(token)) document.querySelector('#m07-bulk-status').textContent='JSON 파일을 읽을 수 없습니다.';}
  });
  document.querySelector('#m07-scenarios').addEventListener('change',event=>{
    const state=m07View;if(state.busy||state.generations.some(m07Running)) return;
    const id=event.target.dataset?.scenarioId;
    if(!id||!m07Scenarios().some(row=>row.scenario_id===id&&row.execution_ready!==false)) return;
    if(event.target.checked) {if(state.selected.size>=20) {event.target.checked=false;m07Status('시나리오는 한 번에 최대 20건까지 선택할 수 있습니다.');return;}state.selected.add(id);}
    else state.selected.delete(id);
    paintM07();
  });
  document.querySelector('#m07-cases').addEventListener('click',event=>{
    const code=event.target.closest('[data-m07-code]'),download=event.target.closest('[data-m07-download]');
    if(code) readM07Code(code.dataset.m07Code);
    else if(download) downloadM07Code(download.dataset.m07Download);
  });
  document.querySelector('#m07-cases').addEventListener('toggle',event=>{
    const id=event.target.dataset?.m07Case;
    if(!m07CaseId(id)||event.target.isConnected===false) return;
    if(event.target.open)m07View.expandedCases.add(id);else m07View.expandedCases.delete(id);
  },true);
  document.querySelector('#m07-cases').addEventListener('change',event=>{
    const state=m07View,id=event.target.dataset?.m07Export;
    if(state.busy||state.generation?.status!=='GENERATED'||!m07CaseId(id)||!state.generation.cases.some(row=>row.case_id===id)) return;
    if(event.target.checked) {if(state.exportSelected.size>=10) {event.target.checked=false;m07Status('M04에는 한 번에 최대 10건까지 고정 등록할 수 있습니다.');return;}state.exportSelected.add(id);}
    else state.exportSelected.delete(id);
    paintM07Generation();
  });
  document.querySelector('#m07-export').addEventListener('click',event=>{if(event.target.closest('#m07-export-button')) exportM07ToM04();});
  paintM07();bootstrapM07Meeting(token);bootstrapM07Workflows(token);bootstrapM07(token,query).catch(error=>{if(m07Active(token)) m07Status(error.message);});
}
function selectM07Mode(mode) {
  if(!['meeting','prepared','llm'].includes(mode)||m07View.busy||m07View.generations.some(m07Running)) return;
  m07View.mode=mode;paintM07();
  if(!m07View.generation)m07Status(mode==='meeting'?'시험 입력 20건을 확인한 후 LLM 코드 생성을 시작하세요.':mode==='prepared'?'업무와 입력값을 확인한 후 준비 코드를 불러오세요.':'저장된 M03 시나리오를 선택한 후 실제 LLM 코드를 생성하세요.');
}
async function bootstrapM07Meeting(token) {
  const state=m07View,meeting=state.meeting;
  try {
    const value=await m07Json('/api/development/m07/meeting-context');
    if(!m07Active(token)||m07View!==state) return;
    if(value.run_mode!=='DEVELOPMENT'||value.required_count!==20||value.target_percent!==80||typeof value.readiness?.configured!=='boolean') throw new Error('20건 시험의 입력·연결 설정 응답을 확인하세요.');
    meeting.context=value;
  } catch(error) {if(m07Active(token)&&m07View===state)meeting.error=error.message;}
  finally {
    if(m07Active(token)&&m07View===state) {
      meeting.loading=false;paintM07();
      if(state.mode==='meeting'&&!state.generation)m07Status(meeting.error||(!meeting.context?.readiness?.configured?'GPT 루나 업무 PC 연결 설정이 필요합니다. 서버의 실제 LLM API 키와 모델을 설정한 후 생성하세요.':'시험 입력 20건을 확인하고 LLM 코드 생성을 누르세요. 생성 후 검사는 별도로 시작합니다.'));
    }
  }
}
function m07Canonical(value) {
  if(Array.isArray(value)) return value.map(m07Canonical);
  if(value&&typeof value==='object') return Object.fromEntries(Object.keys(value).sort().filter(key=>!['scenario_id','scenario_name'].includes(key)).map(key=>[key,m07Canonical(value[key])]));
  return value;
}
function parseM07MeetingInput(text) {
  if(new TextEncoder().encode(text).length>262144)throw new Error('시험 입력은 256 KiB 이하로 입력하세요.');
  let value;try {value=JSON.parse(text);}catch {throw new Error('시험 입력의 JSON 형식을 확인하세요.');}
  const items=Array.isArray(value)?value:value?.items;
  if(!Array.isArray(items)||items.length!==20)throw new Error('서로 다른 시험 입력을 정확히 20건 등록하세요.');
  const ids=new Set(),scenarios=new Set(),contents=new Set();
  for(let index=0;index<items.length;index++) {
    const item=items[index],scenario=item?.scenario,prefix=`입력 ${index+1}: `;
    if(!item||typeof item!=='object'||Array.isArray(item)||typeof item.input_id!=='string'||!item.input_id.trim())throw new Error(prefix+'고유한 input_id가 필요합니다.');
    if(!scenario||typeof scenario!=='object'||Array.isArray(scenario))throw new Error(prefix+'scenario 객체가 필요합니다.');
    if(['scenario_id','scenario_name','business_unit_id','workflow_id'].some(key=>typeof scenario[key]!=='string'||!scenario[key].trim()))throw new Error(prefix+'시나리오 ID·이름·업무 ID·흐름 ID가 필요합니다.');
    if(!Array.isArray(scenario.steps)||!scenario.steps.length||scenario.steps.some(step=>!step||typeof step!=='object'||Array.isArray(step)||!Number.isInteger(step.order)||typeof step.action!=='string'||!step.action.trim()||typeof step.target!=='string'||!step.target.trim()))throw new Error(prefix+'steps에 순서·조작·대상을 지정하세요.');
    if(!scenario.execution_contract||typeof scenario.execution_contract!=='object'||Array.isArray(scenario.execution_contract)||!Array.isArray(scenario.execution_contract.steps)||!scenario.execution_contract.steps.length)throw new Error(prefix+'execution_contract의 대상·확인 조건을 지정하세요.');
    if(ids.has(item.input_id)||scenarios.has(scenario.scenario_id))throw new Error(prefix+'입력 ID와 시나리오 ID는 중복할 수 없습니다.');
    const canonical=JSON.stringify(m07Canonical(scenario));
    if(contents.has(canonical))throw new Error(prefix+'이름과 ID만 다른 동일 시나리오는 중복 입력할 수 없습니다.');
    ids.add(item.input_id);scenarios.add(scenario.scenario_id);contents.add(canonical);
  }
  return items;
}
function checkM07MeetingInput() {
  const state=m07View,meeting=state.meeting;
  if(state.busy||meeting.fileLoading||state.generations.some(m07Running))return false;
  const text=document.querySelector('#m07-meeting-input').value;
  meeting.items=[];meeting.validText=null;
  try {meeting.items=parseM07MeetingInput(text);meeting.validText=text;meeting.message='서로 다른 입력 20건을 확인했습니다. 코드 생성 시 서버가 실행 조건을 검증하고 실제 LLM에 입력별 1회 요청합니다.';}
  catch(error){meeting.message=error.message;}
  paintM07Meeting();if(!state.generation)paintM07Generation();return meeting.items.length===20;
}
async function loadM07MeetingFile(event) {
  const state=m07View,meeting=state.meeting,token=m07RequestNumber,file=event.target.files?.[0];
  if(!file||state.busy||meeting.fileLoading||state.generations.some(m07Running))return;
  meeting.items=[];meeting.validText=null;meeting.fileLoading=true;meeting.message='시험 입력 파일을 읽고 있습니다…';paintM07Meeting();
  try {
    if(file.size>262144)throw new Error('JSON 파일은 256 KiB 이하로 선택하세요.');
    const text=await file.text();if(!m07Active(token)||m07View!==state)return;
    document.querySelector('#m07-meeting-input').value=text;
    meeting.fileLoading=false;checkM07MeetingInput();
  } catch(error){if(m07Active(token)&&m07View===state)meeting.message=error.message;}
  finally {if(m07Active(token)&&m07View===state){meeting.fileLoading=false;paintM07Meeting();}}
}
async function loadM07MeetingDraft() {
  const state=m07View,meeting=state.meeting,token=m07RequestNumber;
  if(state.busy||meeting.fileLoading||state.generations.some(m07Running))return;
  meeting.fileLoading=true;meeting.message='검토용 시험 입력 초안을 불러오고 있습니다…';paintM07Meeting();
  try {
    const value=await m07Json('/api/development/m07/meeting-input-draft');
    if(!m07Active(token)||m07View!==state)return;
    if(value.draft!==true||!Array.isArray(value.items)||value.items.length!==20)throw new Error('검토용 입력 초안의 출처와 20건 구성을 확인하세요.');
    const text=JSON.stringify({items:value.items},null,2);
    meeting.items=parseM07MeetingInput(text);meeting.validText=text;document.querySelector('#m07-meeting-input').value=text;
    meeting.message=(value.description||'업무별 두 변형으로 구성한 검토용 초안입니다. 시험 입력으로 자동 확정하지 않습니다.')+' 대상·입력값·기대 결과를 검토하고 코드 생성 버튼으로 시작하세요.';
    if(!state.generation)paintM07Generation();
  } catch(error){if(m07Active(token)&&m07View===state)meeting.message=error.message;}
  finally {if(m07Active(token)&&m07View===state){meeting.fileLoading=false;paintM07Meeting();}}
}
function m07MeetingCanGenerate() {
  const state=m07View,meeting=state.meeting;
  return !!(state.mode==='meeting'&&!state.busy&&!meeting.fileLoading&&!meeting.loading&&!meeting.error&&!state.generations.some(m07Running)
    &&meeting.context?.readiness?.configured&&!m07ProviderBlocked(state)&&meeting.items.length===20&&meeting.validText===document.querySelector('#m07-meeting-input').value);
}
function paintM07Meeting() {
  const state=m07View,meeting=state.meeting;if(!meeting)return;
  const ready=meeting.context?.readiness,blocked=state.busy||meeting.fileLoading||state.generations.some(m07Running);
  document.querySelector('#m07-meeting-panel').hidden=state.mode!=='meeting';
  document.querySelector('#m07-meeting-ready').textContent=meeting.loading?'확인 중…':ready?.configured?(m07ProviderBlocked(state)?'공급자 제한 대기':ready.model_display_name||ready.model||'LLM 연결 준비 완료'):`${ready?.model_display_name||'GPT 루나'} · 업무 PC 연결 필요`;
  document.querySelector('#m07-meeting-environment').textContent=meeting.error||[ready?.message,ready?`Selenium · Chrome ${ready.selenium&&ready.chrome?'준비 완료':'설치·연결 확인 필요'}`:''].filter(Boolean).join(' · ');
  document.querySelector('#m07-meeting-count').textContent=meeting.items.length+' / 20건';
  document.querySelector('#m07-meeting-provider').innerHTML=state.mode==='meeting'?m07ProviderNotice(state):'';
  document.querySelector('#m07-meeting-status').textContent=meeting.message;
  document.querySelector('#m07-meeting-schema').textContent=JSON.stringify(meeting.context?.example_item||meeting.context?.input_schema||{items:[{input_id:'고유 입력 ID',scenario:{scenario_id:'고유 시나리오 ID',scenario_name:'시험 이름',business_unit_id:'업무 ID',workflow_id:'흐름 ID',steps:[{order:1,action:'조작',target:'대상',expected_result:'기대 결과'}],execution_contract:{version:1,scenario_id:'고유 시나리오 ID',steps:[]}}}]},null,2);
  for(const id of ['input','file','check','draft'])document.querySelector('#m07-meeting-'+id).disabled=blocked;
  document.querySelector('#m07-meeting-generate').disabled=!m07MeetingCanGenerate();
}
async function startM07Meeting() {
  if(!m07MeetingCanGenerate()||!checkM07MeetingInput())return;
  const state=m07View,token=m07RequestNumber,items=JSON.parse(JSON.stringify(state.meeting.items));
  state.busy=true;paintM07();m07Status('20건의 입력을 검증하고 실제 LLM 코드 생성을 요청하고 있습니다…');
  try {
    const data=await m07Json('/api/development/m07/meeting-generations',{items});
    if(!m07Active(token)||m07View!==state)return;
    const job=data.generation;
    if(job?.meeting_protocol!==true||job.code_source==='PREPARED'||job.generated_by_llm===false||!Array.isArray(job.cases)||job.cases.length!==20
      ||job.cases.some((row,index)=>row.scenario_id!==items[index].scenario.scenario_id))throw new Error('실제 LLM 20건 생성 작업의 입력과 출처를 확인하세요. 작업 이력에서 다시 확인할 수 있습니다.');
    ++state.selection;acceptM07Generation(job);scheduleM07Poll(token);m07Status('실제 LLM에 입력별 1회씩 코드 생성을 요청합니다. 생성이 끝나면 별도 검사 버튼을 누르세요.');
  } catch(error){if(m07Active(token)&&m07View===state)m07Status(error.message);}
  finally {if(m07Active(token)&&m07View===state){state.busy=false;paintM07();}}
}
function m07WorkflowCatalog(value) {
  if(!value||value.run_mode!=='DEVELOPMENT'||value.browser!=='chrome'||typeof value.login_configured!=='boolean'
    ||!Array.isArray(value.workflows)||value.workflows.length>10||!value.defaults||typeof value.defaults!=='object'||Array.isArray(value.defaults)
    ||new Set(value.workflows.map(row=>row?.workflow_id)).size!==value.workflows.length
    ||value.workflows.some(row=>!/^CU(?:0[1-9]|10)$/.test(row?.workflow_id||'')||typeof row.name!=='string'||typeof row.available!=='boolean'||!Array.isArray(row.steps)||row.steps.some(step=>typeof step!=='string'))
    ||Object.entries(value.defaults).some(([key,item])=>!/^[a-z][a-z0-9_]{0,50}$/.test(key)||!['string','number','boolean'].includes(typeof item)))
    throw new Error('준비 업무의 목록과 입력 기본값을 확인하세요.');
  return value;
}
async function bootstrapM07Workflows(token) {
  const source=m07View.workflows;
  try {
    const value=m07WorkflowCatalog(await m07Json('/api/development/m07/workflows'));
    if(!m07Active(token)) return;
    source.catalog=value;source.parameters={...value.defaults};
    const available=value.workflows.filter(row=>row.available);
    source.selected=new Set(available.map(row=>row.workflow_id));
    source.message=available.length?'업무와 입력값을 확인한 후 코드를 준비하세요.':'사용 가능한 업무의 준비 상태를 확인하세요.';
  } catch(error) {if(m07Active(token)) source.error=error.message;}
  finally {if(m07Active(token)) {source.loading=false;paintM07Workflows();if(m07View.mode==='prepared'&&!m07View.generation)m07Status(source.error||source.message);}}
}
function m07WorkflowValues() {return {...m07View.workflows.parameters};}
function m07WorkflowSignature() {
  return JSON.stringify({workflow_ids:[...m07View.workflows.selected].sort(),parameters:m07WorkflowValues()});
}
function m07WorkflowCanPrepare() {
  const state=m07View,source=state.workflows,values=source.parameters;
  return !!(source.catalog?.login_configured&&!source.loading&&!source.error&&!state.busy&&!state.generations.some(m07Running)
    &&source.selected.size>0&&source.selected.size<=10&&[...source.selected].every(id=>source.catalog.workflows.some(row=>row.workflow_id===id&&row.available))
    &&(!Object.hasOwn(values,'date')||typeof values.date==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(values.date)&&!Number.isNaN(Date.parse(values.date+'T00:00:00Z'))&&new Date(values.date+'T00:00:00Z').toISOString().slice(0,10)===values.date)
    &&(!Object.hasOwn(values,'title')||typeof values.title==='string'&&values.title.trim().length>0&&values.title.length<=90&&!/[\r\n]/.test(values.title))
    &&(!Object.hasOwn(values,'description')||typeof values.description==='string'&&values.description.trim().length>0&&values.description.length<=2000)
    &&(!Object.hasOwn(values,'cases_per_workflow')||Number.isInteger(values.cases_per_workflow)&&[1,2].includes(values.cases_per_workflow))
    &&source.preparedSignature!==m07WorkflowSignature());
}
function paintM07WorkflowActions() {
  const state=m07View,source=state.workflows;if(!source) return;
  const each=Number.isInteger(source.parameters.cases_per_workflow)?source.parameters.cases_per_workflow:1;
  document.querySelector('#m07-workflow-count').textContent=source.selected.size+'개 업무 · '+source.selected.size*each+'개 코드';
  document.querySelector('#m07-workflow-prepare').disabled=!m07WorkflowCanPrepare();
  document.querySelector('#m07-workflow-status').textContent=source.error||source.message;
}
function paintM07Workflows() {
  const state=m07View,source=state.workflows;if(!source) return;
  const blocked=source.loading||state.busy||state.generations.some(m07Running),rows=source.catalog?.workflows||[];
  document.querySelector('#m07-workflow-panel').hidden=state.mode!=='prepared';
  document.querySelector('#m07-llm-panel').hidden=state.mode!=='llm';
  for(const mode of ['meeting','prepared','llm']) {
    const button=document.querySelector('#m07-mode-'+mode);button.setAttribute('aria-pressed',String(state.mode===mode));button.disabled=state.busy||state.generations.some(m07Running);
  }
  document.querySelector('#m07-workflow-login').textContent=source.loading?'업무 준비 상태 확인 중…':source.catalog?.login_configured?'시험 계정 준비됨 · Chrome 실행':'시험 계정 설정 필요';
  document.querySelector('#m07-workflow-all').disabled=blocked||!rows.some(row=>row.available);
  document.querySelector('#m07-workflow-all').textContent=rows.some(row=>row.available)&&rows.filter(row=>row.available).every(row=>source.selected.has(row.workflow_id))?'전체 선택 해제':'사용 가능한 업무 선택';
  document.querySelector('#m07-workflows').innerHTML=source.error?`<p class="notice">${esc(source.error)}</p>`:rows.length?rows.map(row=>`<label class="m07-workflow-card ${source.selected.has(row.workflow_id)?'is-selected':''} ${!row.available?'is-unavailable':''}"><input type="checkbox" data-workflow-id="${esc(row.workflow_id)}" ${source.selected.has(row.workflow_id)?'checked':''} ${blocked||!row.available?'disabled':''}><span class="m07-workflow-card-body"><span class="m07-workflow-meta"><small>${esc(row.workflow_id)}</small><small>${esc(row.type||'업무')}</small></span><strong>${esc(row.name)}</strong><span class="m07-workflow-steps">${esc(row.steps.join(' → '))}</span>${!row.available?`<span class="m07-fail">${esc(row.notice||'실행 준비 필요')}</span>`:''}</span></label>`).join(''):`<p class="empty">${source.loading?'준비 코드를 불러오고 있습니다…':'표시할 준비 업무가 없습니다.'}</p>`;
  for(const field of ['date','title','description']) {
    const input=document.querySelector('#m07-workflow-'+field);input.disabled=blocked||!source.catalog;
    if(input.value!==String(source.parameters[field]??'')) input.value=String(source.parameters[field]??'');
  }
  const labels={week:'대상 주차',month:'대상 월',card_name:'명함 이름',contact_name:'명함 이름',company:'회사',department:'부서',position:'직책',phone:'연락처',email:'이메일',lookup_title:'조회할 일정 제목 (선택)',cases_per_workflow:'업무당 코드 수 (1~2)'};
  const extra=Object.keys(source.parameters).filter(key=>!['date','title','description','browser'].includes(key));
  document.querySelector('#m07-workflow-extra').hidden=!extra.length;
  document.querySelector('#m07-workflow-extra-fields').innerHTML=extra.map(key=>{
    const field=(source.catalog?.parameter_fields||source.catalog?.parameters_fields)?.find(item=>item.name===key);
    const type=typeof source.catalog.defaults[key]==='number'?'number':['date','email'].includes(field?.type)?field.type:key==='email'?'email':'text';
    return `<label>${esc(field?.label||labels[key]||key)}<input data-workflow-parameter="${esc(key)}" type="${type}" ${key==='cases_per_workflow'?'min="1" max="2" step="1"':''} value="${esc(String(source.parameters[key]))}" ${blocked?'disabled':''} autocomplete="off"></label>`;
  }).join('');
  paintM07WorkflowActions();
}
async function prepareM07Workflows() {
  if(!m07WorkflowCanPrepare()) return;
  const state=m07View,source=state.workflows,token=m07RequestNumber,signature=m07WorkflowSignature();
  const payload={workflow_ids:[...source.selected].sort(),parameters:m07WorkflowValues()};
  state.busy=true;source.message='선택 업무의 원본 코드와 실행 조건을 준비하고 있습니다…';paintM07();
  try {
    const data=await m07Json('/api/development/m07/workflows/prepare',payload);
    if(!m07Active(token)) return;
    const job=data.generation;
    const each=payload.parameters.cases_per_workflow??1;
    if(!job||job.code_source!=='PREPARED'||job.source_kind!=='RBEM_PREPARED_WORKFLOW'||job.generated_by_llm!==false
      ||!Array.isArray(job.workflow_ids)||JSON.stringify([...job.workflow_ids].sort())!==JSON.stringify(payload.workflow_ids)
      ||!Array.isArray(job.cases)||job.cases.length!==payload.workflow_ids.length*each||job.cases.length>20
      ||job.cases.some(row=>row.code_source!=='PREPARED'||row.generated_by_llm!==false||row.browser!=='chrome'
        ||!payload.workflow_ids.includes(row.workflow_id)||!Number.isInteger(row.workflow_case_number)||row.workflow_case_number<1||row.workflow_case_number>each)
      ||new Set(job.cases.map(row=>row.workflow_id+':'+row.workflow_case_number)).size!==job.cases.length)
      throw new Error('준비 코드의 출처와 실행 기록을 확인하세요. 이력에서 준비 결과를 다시 확인하세요.');
    ++state.selection;state.autoPreviewJobs.add(job.generation_id);source.preparedGenerationId=job.generation_id;
    const preview=acceptM07Generation(job);scheduleM07Poll(token);source.preparedSignature=signature;
    source.message=job.status==='GENERATED'?'원본 코드를 준비했습니다. 아래에서 코드를 확인한 뒤 Chrome 문법·실행 검사를 누르세요.':'원본 코드를 준비 중입니다. 완료되면 첫 번째 코드가 자동으로 표시됩니다.';
    await preview;if(!m07Active(token)) return;
    m07Status(source.message);
  } catch(error) {if(m07Active(token)) {source.message=error.message;m07Status(error.message);}}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
function m07Scenarios() {
  const rows=m07View.context?.scenarios||[],unique=new Map();
  for(const row of rows) {
    const preferred=m07View.bulkRefs?.get(row.scenario_id)?.m03_run_id||m07View.source;
    if(!unique.has(row.scenario_id)||row.m03_run_id===preferred) unique.set(row.scenario_id,row);
  }
  return [...unique.values()];
}
function m07ValidationReady(job) {
  return Array.isArray(job?.cases)&&job.cases.every(row=>row.generation_status!=='PASS'||/^[0-9a-f]{64}$/.test(row.execution_contract_sha256||''));
}
function m07RunReadiness(job=m07View.generation) {
  return job?.meeting_protocol?m07View.meeting?.context?.readiness:job?.source_kind==='RBEM_PREPARED_WORKFLOW'?(m07View.workflows.catalog?.readiness||m07View.context?.readiness):m07View.context?.readiness;
}
function m07SelectedRef(row) {
  const pinned=m07View.bulkRefs?.get(row.scenario_id),value={m03_run_id:row.m03_run_id,scenario_id:row.scenario_id};
  const hash=pinned?.m03_run_id===row.m03_run_id?pinned.source_scenario_sha256:row.source_scenario_sha256;
  if(/^[a-f0-9]{64}$/.test(hash||'')) value.source_scenario_sha256=hash;
  return value;
}
function m07PreparedReady(state=m07View) {
  return state.preparedSelected&&!state.preparedLoading&&!state.preparedError
    &&state.preparedCodes.length===state.selected.size&&state.selected.size>0
    &&state.preparedCodes.every(row=>state.selected.has(row.scenario_id));
}
async function m07CodeSha(bytes) {
  if(typeof crypto==='undefined'||!crypto.subtle) throw new Error('코드 원본 해시를 확인할 수 없습니다. 로컬 서버 주소로 접속하세요.');
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),value=>value.toString(16).padStart(2,'0')).join('');
}
async function loadM07PreparedCodes(event) {
  const state=m07View,token=m07RequestNumber;
  if(state.busy||state.generations.some(m07Running)) return;
  const files=Array.from(event.target.files||[]);
  state.preparedSelected=files.length>0;state.preparedCodes=[];state.preparedError='';
  if(!files.length) {paintM07();return;}
  state.busy=true;state.preparedLoading=true;paintM07();
  try {
    if(files.length>20) throw new Error('코드 파일은 최대 20개까지 선택하세요.');
    const codes=[];
    for(const file of files) {
      if(typeof file.name!=='string'||!/\.py$/i.test(file.name)||/[\\/\r\n\0]/.test(file.name)||!file.size||file.size>262144)
        throw new Error('각 코드 파일은 256 KiB 이하의 Python(.py) 파일이어야 합니다.');
      const bytes=new Uint8Array(await file.arrayBuffer());
      if(bytes.length!==file.size) throw new Error('코드 파일을 완전히 읽을 수 없습니다. 다시 선택하세요.');
      let code;
      try {code=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);}
      catch {throw new Error('코드 파일은 UTF-8이어야 합니다. 원본 인코딩을 확인하세요.');}
      // 화면의 보조 매핑만 수행한다. Python 문법과 실제 선언은 서버에서 검사한다.
      const ids=[...code.matchAll(/^(?:\uFEFF)?SCENARIO_ID[ \t]*=[ \t]*(["'])([^\r\n"'\\]+)\1[ \t]*(?:#[^\r\n]*)?\r?$/gm)];
      if(ids.length!==1) throw new Error('파일마다 SCENARIO_ID = "시나리오 ID" 형태의 단순 문자열 선언이 하나 있어야 합니다.');
      if(codes.some(row=>row.scenario_id===ids[0][2])) throw new Error('같은 SCENARIO_ID의 코드 파일을 중복 선택할 수 없습니다.');
      let binary='';
      for(let offset=0;offset<bytes.length;offset+=32768) binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
      codes.push({scenario_id:ids[0][2],filename:file.name,code_base64:btoa(binary),sha256:await m07CodeSha(bytes)});
    }
    if(m07Active(token)) state.preparedCodes=codes;
  } catch(error) {if(m07Active(token)) state.preparedError=error.message;}
  finally {if(m07Active(token)) {state.busy=false;state.preparedLoading=false;paintM07();}}
}
async function bootstrapM07(token,query) {
  const output=await Promise.allSettled([m07Json('/api/development/m07/context'),m07Json('/api/development/m07/generations')]);
  if(!m07Active(token)) return;
  const state=m07View,errors=[];
  if(output[0].status==='fulfilled') {
    const value=output[0].value;
    if(value.run_mode!=='DEVELOPMENT'||!Array.isArray(value.scenarios)) errors.push('개발용 시나리오 응답 형식을 확인하세요.');
    else {
      state.context={...value,scenarios:value.scenarios.filter(row=>row&&typeof row.scenario_id==='string'&&row.scenario_id.trim()&&m07RunId(row.m03_run_id)&&!['FAILED','FAIL','ERROR'].includes(row.status))};
      if(typeof catalog!=='undefined'&&catalog?.server_session_id
        &&((state.source&&!state.context.scenarios.some(row=>row.m03_run_id===state.source))
          ||(state.requestedScenario&&!state.context.scenarios.some(row=>row.scenario_id===state.requestedScenario&&(!state.source||row.m03_run_id===state.source))))) {
        state.source='';state.requestedScenario='';state.contextError='';state.selected.clear();
        if(typeof ktlDropQuery==='function') ktlDropQuery(['m03_run_id','scenario_id']);
      }
      if(state.source&&!m07RunId(state.source)) {state.contextError='M03 실행 주소를 확인하세요.';errors.push(state.contextError);}
      else if(state.source&&!state.context.scenarios.some(row=>row.m03_run_id===state.source)) {state.contextError='요청한 M03 실행의 시나리오가 없습니다.';errors.push(state.contextError);}
      if(state.requestedScenario) {
        const requested=m07Scenarios().find(row=>row.scenario_id===state.requestedScenario&&(!state.source||row.m03_run_id===state.source));
        if(requested?.execution_ready===false) errors.push(requested.execution_notice||'시나리오의 실행 조건을 먼저 준비하세요.');
        else if(requested) state.selected.add(state.requestedScenario);
        else {state.contextError='요청한 시나리오가 저장된 M03 실행에 없습니다.';errors.push(state.contextError);}
      } else {
        const first=m07Scenarios().find(row=>row.execution_ready!==false);
        if(first) state.selected.add(first.scenario_id);
      }
      for(const id of state.selected) if(!m07Scenarios().some(row=>row.scenario_id===id&&row.execution_ready!==false)) state.selected.delete(id);
    }
  } else errors.push(output[0].reason.message);
  if(output[1].status==='fulfilled'&&Array.isArray(output[1].value.generations)) state.generations=output[1].value.generations.filter(row=>m07Id(row.generation_id));
  else errors.push(output[1].status==='rejected'?output[1].reason.message:'작업 이력 응답 형식을 확인하세요.');
  paintM07();
  const requested=query.get('generation_id'),stale=!!(typeof catalog!=='undefined'&&catalog?.server_session_id&&requested&&!state.generations.some(row=>row.generation_id===requested));
  const id=stale?null:requested||state.generations.find(m07Running)?.generation_id||state.generations[0]?.generation_id;
  if(stale) m07Remember(null);
  if(!stale&&requested&&!m07Id(requested)) errors.push('작업 이력 주소를 확인하세요.');
  else if(id) {try {await selectM07Generation(id);} catch(error) {errors.push(error.message);}}
  if(m07Active(token)) m07Status(m07Running(state.generation)?'진행 중인 작업을 이어서 표시합니다.':state.mode==='meeting'?(state.meeting.error||(state.meeting.context?.readiness?.configured?'시험 입력 20건을 확인하고 LLM 코드 생성을 누르세요. 생성 후 검사는 별도로 시작합니다.':'GPT 루나 업무 PC 연결 설정이 필요합니다. 서버의 실제 LLM API 키와 모델을 설정한 후 생성하세요.')):state.mode==='prepared'?(state.workflows.error||state.workflows.message):errors.length?errors.join(' · '):state.context?.readiness?.configured?'시나리오를 선택한 뒤 코드를 생성하세요. 생성 후 문법·실행 검사를 별도로 실행합니다.':'서버의 LLM 연결 설정을 확인하세요. 기존 생성 기록은 계속 확인할 수 있습니다.');
}
function paintM07() {
  const state=m07View,job=state.generation,blocked=state.busy||state.generations.some(m07Running),ready=state.context?.readiness,rows=m07Scenarios();
  document.querySelector('#m07-ready').textContent=ready?(ready.configured?(m07ProviderBlocked(state)?'공급자 제한 대기':ready.model||'LLM 연결 준비 완료'):'서버 LLM 설정 필요'):'확인 중…';
  document.querySelector('#m07-selected-count').textContent=state.selected.size+'건';
  document.querySelector('#m07-environment').textContent=[ready?.message,state.context?.target_url?`실행 대상: ${state.context.target_url}`:'',ready?`Selenium · Chrome ${ready.selenium&&ready.chrome?'준비 완료':'설치·연결 확인 필요'}`:''].filter(Boolean).join(' · ');
  document.querySelector('#m07-provider-state').innerHTML=state.mode==='llm'?m07ProviderNotice(state):'';
  const renderScenario=row=>`<label class="m07-scenario"><input type="checkbox" data-scenario-id="${esc(row.scenario_id)}" ${state.selected.has(row.scenario_id)?'checked':''} ${blocked||row.execution_ready===false?'disabled':''}><span><strong>${esc(row.scenario_name||row.business_unit_id||row.scenario_id)}</strong><small>${esc(row.scenario_id)}${row.source_synthetic||row.synthetic||row.generator_mode==='MOCK'?' · 샘플 시나리오':''}<br>${esc(row.m03_run_id)}</small>${row.execution_ready===false?`<small class="m07-fail">${esc(row.execution_notice||'시나리오 실행 조건을 먼저 준비하세요.')}</small>`:''}</span></label>`;
  const prepared=rows.filter(row=>row.execution_ready!==false),unprepared=rows.filter(row=>row.execution_ready===false);
  document.querySelector('#m07-scenarios').innerHTML=state.contextError?`<p class="notice">${esc(state.contextError)}</p>`:rows.length?`${prepared.length?`<div class="m07-scenario-list">${prepared.map(renderScenario).join('')}</div>`:'<p class="notice">실행할 시나리오의 대상 요소와 기대 결과를 먼저 준비하세요.</p>'}${unprepared.length?`<details class="m07-step-detail"><summary>실행 조건 준비 필요 ${unprepared.length}건</summary><div class="m07-scenario-list">${unprepared.map(renderScenario).join('')}</div></details>`:''}<p class="run-meta">서로 다른 시나리오 최대 20건 · 저장된 M03 원본 연결</p>`:'<p class="empty">M03에서 시나리오를 생성·저장한 후 코드 생성을 진행하세요.</p>';
  document.querySelector('#m07-generate').disabled=blocked||(state.preparedSelected?!m07PreparedReady(state):!ready?.configured||m07ProviderBlocked(state))||!!state.contextError||!state.selected.size||state.selected.size>20||[...state.selected].some(id=>!rows.some(row=>row.scenario_id===id&&row.execution_ready!==false));
  document.querySelector('#m07-code-files').disabled=blocked;
  document.querySelector('#m07-code-status').textContent=state.preparedLoading?'코드 파일의 UTF-8 원본과 SHA-256을 확인하고 있습니다…':state.preparedError||(!state.preparedSelected?'파일을 선택하지 않으면 GPT로 코드를 생성합니다. 파일 선택은 새로고침으로 해제합니다.':!m07PreparedReady(state)?'선택한 시나리오와 코드 파일의 SCENARIO_ID가 정확히 일치해야 합니다.':`등록한 원본 코드 ${state.preparedCodes.length}건 · GPT를 호출하지 않습니다.\n${state.preparedCodes.map(row=>`${row.filename} · ${row.scenario_id} · SHA-256: ${row.sha256}`).join('\n')}`);
  const runReady=m07RunReadiness(job);
  document.querySelector('#m07-validate').disabled=blocked||job?.status!=='GENERATED'||!runReady?.selenium||!runReady?.chrome||!m07ValidationReady(job);
  document.querySelector('#m07-cancel').disabled=state.busy||!m07Running(job);
  document.querySelector('#m07-refresh').disabled=state.busy;
  document.querySelector('#m07-history').disabled=state.busy;
  document.querySelector('#m07-history').innerHTML=`<option value="">작업 이력 선택</option>${state.generations.map(row=>`<option value="${esc(row.generation_id)}" ${row.generation_id===job?.generation_id?'selected':''}>${row.code_source==='PREPARED'?'준비 코드':'LLM 기록'} · ${esc(row.created_at||row.started_at||row.generation_id)} · ${esc(m07JobName(row))}</option>`).join('')}`;
  document.querySelector('#m07-current-source').textContent=job?`${job.code_source==='PREPARED'?'준비한 원본 코드 · LLM 호출 없음':job.meeting_protocol?'실제 LLM 20건 시험':'기존 LLM 생성 기록'} · ${job.cases.length}건 · ${runReady?.selenium&&runReady?.chrome?'Chrome 실행 검사 준비됨':'Chrome·Selenium 설치 및 연결 확인 필요'}`:'LLM 코드 20건을 생성하면 원본을 확인하고 별도 검사를 시작할 수 있습니다.';
  document.querySelector('#m07-generate').textContent=state.preparedSelected?'원본 코드 파일 등록':'실제 LLM 코드 생성';
  paintM07ContextEditor();
  for(const id of ['m07-bulk-input','m07-bulk-file','m07-bulk-current','m07-bulk-apply']) {const node=document.querySelector('#'+id);if(node) node.disabled=blocked;}
  paintM07Meeting();paintM07Workflows();paintM07Generation();
}
async function applyM07BulkSelection() {
  const state=m07View,token=m07RequestNumber;if(state.busy||state.generations.some(m07Running)) return;
  let input;
  try {input=JSON.parse(document.querySelector('#m07-bulk-input').value);}
  catch {document.querySelector('#m07-bulk-status').textContent='시나리오 목록의 JSON 형식을 확인하세요.';return;}
  const items=Array.isArray(input)?input:Array.isArray(input?.scenarios)?input.scenarios:input?.scenario_refs;
  if(!Array.isArray(items)||items.length<1||items.length>20) {document.querySelector('#m07-bulk-status').textContent='서로 다른 시나리오 1~20건을 입력하세요.';return;}
  const payload={items};
  if(new TextEncoder().encode(JSON.stringify(payload)).length>262144) {document.querySelector('#m07-bulk-status').textContent='일괄 입력은 256 KiB 이하로 입력하세요.';return;}
  state.busy=true;paintM07();
  try {
    const data=await m07Json('/api/development/m07/scenario-selection',payload);
    if(!m07Active(token)) return;
    if(!Array.isArray(data.scenario_refs)||data.scenario_refs.length!==items.length||new Set(data.scenario_refs.map(row=>row.scenario_id)).size!==items.length||data.scenario_refs.some(row=>!m07RunId(row.m03_run_id)||!/^[a-f0-9]{64}$/.test(row.source_scenario_sha256||'')||!state.context.scenarios.some(source=>source.m03_run_id===row.m03_run_id&&source.scenario_id===row.scenario_id&&source.execution_ready!==false))) throw new Error('일괄 선택 검증 응답을 확인하세요.');
    state.bulkRefs=new Map(data.scenario_refs.map(row=>[row.scenario_id,{...row}]));
    state.selected=new Set(data.scenario_refs.map(row=>row.scenario_id));
    document.querySelector('#m07-bulk-status').textContent=`원본 확인 완료 · ${data.scenario_refs.length}건을 선택했습니다. 코드 생성 버튼으로 시작하세요.`;
  } catch(error) {if(m07Active(token)) document.querySelector('#m07-bulk-status').textContent=error.message;}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
function m07ContextRef(row) {return JSON.stringify([row.m03_run_id,row.scenario_id]);}
function m07ContextSource() {
  const value=document.querySelector('#m07-context-scenario')?.value;
  return m07Scenarios().find(row=>m07ContextRef(row)===value)||null;
}
function paintM07ContextEditor() {
  const state=m07View,select=document.querySelector('#m07-context-scenario');if(!select) return;
  const rows=m07Scenarios(),blocked=state.busy||state.generations.some(m07Running),current=select.value;
  const first=rows.find(row=>row.scenario_id===state.requestedScenario)||rows.find(row=>row.execution_ready===false)||rows[0];
  select.innerHTML=rows.map(row=>`<option value="${esc(m07ContextRef(row))}">${esc(row.scenario_name||row.scenario_id)} · ${row.execution_ready===false?'준비 필요':'준비됨'}</option>`).join('');
  select.value=rows.some(row=>m07ContextRef(row)===current)?current:first?m07ContextRef(first):'';
  select.disabled=blocked||!rows.length;
  document.querySelector('#m07-context-load').disabled=blocked||!rows.length;
  document.querySelector('#m07-context-save').disabled=blocked||!state.contextEditor||state.contextEditor.ref!==select.value;
  document.querySelector('#m07-context-expected').disabled=blocked||!state.contextEditor;
  document.querySelector('#m07-context-contract').disabled=blocked||!state.contextEditor;
}
function acceptM07ExecutionContext(value,row) {
  if(!value||value.m03_run_id!==row.m03_run_id||value.scenario_id!==row.scenario_id||!Array.isArray(value.expected_results)||!value.execution_contract||typeof value.execution_contract!=='object') throw new Error('실행 조건 응답을 확인하세요.');
  m07View.contextEditor={ref:m07ContextRef(row),value};
  document.querySelector('#m07-context-expected').value=JSON.stringify(value.expected_results,null,2);
  document.querySelector('#m07-context-contract').value=JSON.stringify(value.execution_contract,null,2);
  document.querySelector('#m07-context-status').textContent=value.execution_ready?`실행 조건 준비됨${value.saved_revision_id?' · 저장 개정 '+value.saved_revision_id.slice(0,12):''}`:value.execution_notice||'비어 있는 선택자와 단계별 검사 조건을 입력하세요.';
}
async function loadM07ExecutionContext() {
  const state=m07View,row=m07ContextSource(),token=m07RequestNumber;if(!row||state.busy||state.generations.some(m07Running)) return;
  state.busy=true;paintM07();
  try {
    const query=new URLSearchParams({m03_run_id:row.m03_run_id,scenario_id:row.scenario_id});
    const data=await m07Json('/api/development/m07/execution-contexts?'+query);
    if(!m07Active(token)||m07ContextSource()?.scenario_id!==row.scenario_id) return;
    acceptM07ExecutionContext(data.execution_context,row);
  } catch(error) {if(m07Active(token)) document.querySelector('#m07-context-status').textContent=error.message;}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
async function saveM07ExecutionContext() {
  const state=m07View,row=m07ContextSource(),token=m07RequestNumber;if(!row||state.busy||!state.contextEditor||state.contextEditor.ref!==m07ContextRef(row)) return;
  let execution_contract,expected_results;
  try {execution_contract=JSON.parse(document.querySelector('#m07-context-contract').value);expected_results=JSON.parse(document.querySelector('#m07-context-expected').value);}
  catch {document.querySelector('#m07-context-status').textContent='실행 조건과 기대 결과의 JSON 형식을 확인하세요.';return;}
  const payload={m03_run_id:row.m03_run_id,scenario_id:row.scenario_id,execution_contract,expected_results};
  if(new TextEncoder().encode(JSON.stringify(payload)).length>65536) {document.querySelector('#m07-context-status').textContent='실행 조건은 64 KiB 이하로 입력하세요.';return;}
  state.busy=true;paintM07();
  try {
    const data=await m07Json('/api/development/m07/execution-contexts',payload);
    if(!m07Active(token)) return;
    acceptM07ExecutionContext(data.execution_context,row);
    state.context.scenarios=state.context.scenarios.map(item=>item.m03_run_id===row.m03_run_id&&item.scenario_id===row.scenario_id?{...item,execution_ready:data.execution_context.execution_ready,execution_notice:data.execution_context.execution_notice}:item);
    document.querySelector('#m07-context-status').textContent='조건을 검증·저장했습니다. 시나리오를 선택해 새 작업을 시작하세요. 기존 코드와 실행 기록은 보존됩니다.';
  } catch(error) {if(m07Active(token)) document.querySelector('#m07-context-status').textContent=error.message;}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
function m07Measurement(job,counts) {
  const value=job?.measurement;
  if(job?.meeting_protocol) {
    const cases=job.cases||[],terminal=status=>['PASS','FAIL','ERROR','TIMEOUT','SKIPPED'].includes(status);
    const both=cases.filter(row=>row.generation_status==='PASS'&&row.syntax_status==='PASS'&&row.execution_status==='PASS'&&row.final_status==='PASS').length;
    const ready=job.status==='COMPLETED'&&cases.length===20&&value?.evaluation_status==='COMPLETED'&&value.registered_count===20
      &&value.provider_http_attempt_count===20&&value.provider_http_unknown_count===0&&cases.every(row=>terminal(row.generation_status)&&terminal(row.syntax_status)&&terminal(row.execution_status));
    return {...value,...counts,version:1,registered_count:20,both_pass_count:both,evaluation_status:ready?'COMPLETED':'NOT_READY',
      generation_percent:ready?counts.generated_code_count/20*100:null,syntax_percent:ready?counts.syntax_pass_count/20*100:null,
      integrated_percent:ready?both/20*100:null,syntax_target_percent:80,syntax_target_met:ready?counts.syntax_pass_count>=16:null,
      integrated_reference_target_percent:80,integrated_reference_target_met:ready?both>=16:null};
  }
  if(value?.version===1) return value;
  const cases=job?.cases||[],registered=Math.max(cases.length,Number.isInteger(job?.counts?.generation_request_count)?job.counts.generation_request_count:0,counts.generated_code_count);
  const ready=!!job?.result&&job?.status==='COMPLETED'&&registered>0&&counts.generated_code_count===registered&&cases.length===registered
    &&cases.every(row=>['PASS','FAIL','ERROR','TIMEOUT','SKIPPED'].includes(row.syntax_status)&&['PASS','FAIL','ERROR','TIMEOUT','SKIPPED'].includes(row.execution_status));
  return {version:0,evaluation_status:ready?'COMPLETED':'NOT_READY',registered_count:registered,provider_http_attempt_count:null,
    provider_http_unknown_count:registered,not_attempted_count:null,...counts,
    generation_percent:ready?100*counts.generated_code_count/registered:null,syntax_percent:ready?100*counts.syntax_pass_count/registered:null,
    integrated_percent:ready?100*counts.both_pass_count/registered:null,syntax_target_percent:80,
    syntax_target_met:ready?100*counts.syntax_pass_count/registered>=80:null,integrated_reference_target_percent:80,
    integrated_reference_target_met:ready?100*counts.both_pass_count/registered>=80:null};
}
function m07MeasurementEvidence(job,counts,result) {
  const value=m07Measurement(job,counts),ready=value.evaluation_status==='COMPLETED';
  const count=n=>Number.isInteger(n)&&n>=0?esc(n):'확인 불가';
  const percent=n=>ready&&typeof n==='number'&&Number.isFinite(n)?score(n,'M07'):'—';
  const verdict=met=>!ready||met==null?'판정 대기':met?'기준 충족':'기준 미달';
  const fields=[['등록 요청','registered_count'],['실제 HTTP 시도','provider_http_attempt_count'],['시도 근거 미확인','provider_http_unknown_count'],['생성 코드','generated_code_count'],['문법 통과','syntax_pass_count'],['실제 브라우저 시작','browser_started_count'],['실행 통과','execution_pass_count'],['문법·실행 모두 통과','both_pass_count'],['미시도','not_attempted_count']];
  const legacy=job?.legacy_result||result;
  return `<div class="panel-heading"><h2>등록 요청 기준 측정</h2><span class="badge neutral">${esc(value.evaluation_status||'NOT_READY')}</span></div><div class="result-grid m07-summary">${fields.map(([label,key])=>`<div><label>${label}</label><strong data-m07-summary="${key}">${job?count(value[key]):'—'}</strong></div>`).join('')}<div><label>생성 성공률 · 등록 수 분모</label><strong data-m07-rate="generation">${percent(value.generation_percent)}</strong></div><div><label>문법 통과율 · 등록 수 분모</label><strong data-m07-rate="syntax">${percent(value.syntax_percent)}</strong></div><div><label>최종 성공률 · 문법·실행 모두 통과</label><strong data-m07-rate="integrated">${percent(value.integrated_percent)}</strong></div><div><label>목표 ≥ ${score(value.integrated_reference_target_percent??80,'M07')}</label><strong>${verdict(value.integrated_reference_target_met)}</strong></div></div><p class="subtitle">생성·문법·통합의 각 통과 건수 / 등록 요청 ${job?count(value.registered_count):'—'}건 × 100 · DEVELOPMENT · 공식 시험성적 아님</p>${!ready?'<p class="notice">등록 작업이 미완료이거나 실제 시도 근거가 부족합니다. 표시 건수는 중간 진행이며 최종 비율과 판정은 대기(null)입니다.</p>':''}${value.version===0&&job?'<p class="run-meta">이전 기록에는 실제 HTTP 시도·미시도 집계가 없습니다. 생성 시작시각으로 실제 호출 수를 추정하지 않습니다.</p>':''}${legacy&&!job?.meeting_protocol?`<details class="m07-step-detail" data-m07-legacy-result><summary>생성코드 수 분모의 이전 부분 결과</summary><p class="run-meta">저장 점수 ${score(legacy.score,'M07')} · ${esc(legacy.run_id||'이전 기록')}${legacy.threshold_met!=null?' · '+(legacy.threshold_met?'기준 충족':'기준 미달'):''}</p><p class="subtitle">저장된 결과는 변경하지 않았습니다. 이 비율을 등록 전체의 완료·품질 판정으로 사용하지 않습니다.</p></details>`:''}`;
}
function m07MeasurementSummary(job,counts,result) {
  const value=m07Measurement(job,counts),ready=value.evaluation_status==='COMPLETED';
  const number=key=>job&&Number.isInteger(value[key])?esc(value[key]):'—';
  const percentage=ready&&Number.isFinite(value.integrated_percent)?score(value.integrated_percent,'M07'):'—';
  const met=ready&&value.integrated_reference_target_met!=null?value.integrated_reference_target_met:null;
  return `<div class="panel-heading"><h2>${job?.meeting_protocol?'실제 LLM 20건 시험 결과':'실제 LLM 생성 검사'}</h2><span class="badge ${met===true?'pass':met===false?'fail':'neutral'}">${met===true?'기준 충족':met===false?'기준 미달':'검사 대기'}</span></div>
    <div class="result-grid m07-result-overview"><div><label>문법·실행 통합 성공률</label><strong class="large-score">${percentage}</strong></div><div><label>등록 시나리오</label><strong>${number('registered_count')}건</strong></div><div><label>문법·실행 모두 통과</label><strong>${number('both_pass_count')}건</strong></div><div><label>목표 기준</label><strong>80%</strong></div></div>
    <p class="subtitle">${job?.meeting_protocol?'문법·실행 모두 통과한 코드 / 20건 × 100 · 16건 이상 통과 · 생성 실패와 검사 실패도 분모 20건에 포함':'문법과 실제 실행을 모두 통과한 코드 / 등록 시나리오 수 × 100 · 20건 시험 기준 16건 이상 통과'}</p>
    ${!ready?'<p class="m07-inline-note">생성·검사와 요청 근거 확인이 완료되면 최종 성공률을 표시합니다.</p>':''}
    <details class="m07-step-detail m07-evidence"><summary>요청 근거와 세부 집계</summary>${m07MeasurementEvidence(job,counts,result)}</details>`;
}
function m07CaseStatus(status,final=false) {
  if(status==='PASS')return '<span class="m07-pass">PASS</span>';
  if(['FAIL','ERROR','TIMEOUT'].includes(status)||final&&status==='SKIPPED')return '<span class="m07-fail">FAIL</span>';
  return `<span class="subtitle">${esc(m07Name(status))}</span>`;
}
function m07FinalStatus(row) {
  if(!row)return 'PENDING';
  const states=[row.generation_status,row.syntax_status,row.execution_status];
  if(row.final_status==='PASS'&&states.every(status=>status==='PASS'))return 'PASS';
  if(states.some(status=>['FAIL','ERROR','TIMEOUT'].includes(status))||['FAIL','ERROR','TIMEOUT','SKIPPED'].includes(row.final_status))return 'FAIL';
  return 'PENDING';
}
function m07MeetingTable(job) {
  const state=m07View,registered=state.meeting?.items||[],cases=job?.cases||[];
  return `<div class="m07-table-wrap"><table class="m07-case-table"><caption>시험 입력 20건의 생성·검사 결과</caption><thead><tr><th scope="col">번호</th><th scope="col">시험 입력</th><th scope="col">생성</th><th scope="col">문법</th><th scope="col">실행</th><th scope="col">최종</th><th scope="col">원본</th></tr></thead><tbody>${Array.from({length:20},(_,index)=>{
    const row=cases[index],input=registered[index],label=row?.scenario_name||row?.scenario_id||input?.scenario?.scenario_name||'입력 대기';
    return `<tr data-m07-result-row="${index+1}"><td>${index+1}</td><th scope="row">${esc(label)}${row?.input_id||input?.input_id?`<small>${esc(row?.input_id||input.input_id)}</small>`:''}</th><td>${m07CaseStatus(row?.generation_status)}</td><td>${m07CaseStatus(row?.syntax_status)}</td><td>${m07CaseStatus(row?.execution_status)}</td><td>${m07CaseStatus(m07FinalStatus(row),true)}</td><td>${row&&(row.generation_status==='PASS'||row.code_sha256)?`<a href="#m07-case-${esc(row.case_id)}" data-m07-code="${esc(row.case_id)}">${state.openCode.has(row.case_id)?'접기':'보기'}</a>`:'—'}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}
function paintM07Generation() {
  const state=m07View,job=state.generation,cases=Array.isArray(job?.cases)?job.cases:[],result=job?.status==='COMPLETED'?job.result:null;
  const generated=cases.filter(row=>row.generation_status==='PASS').length,both=cases.filter(row=>row.final_status==='PASS').length;
  const counts={generated_code_count:generated,syntax_pass_count:cases.filter(row=>row.syntax_status==='PASS').length,execution_pass_count:cases.filter(row=>row.execution_status==='PASS').length,both_pass_count:both,...job?.counts};
  const met=result?.threshold_met,prepared=job?.code_source==='PREPARED';
  const progress=cases.reduce((total,row)=>total+(!['PENDING','RUNNING'].includes(row.generation_status)?1:0)+(!['PENDING','RUNNING',undefined].includes(row.execution_status)?1:0),0);
  document.querySelector('#m07-progress').max=Math.max(1,cases.length*2);document.querySelector('#m07-progress').value=progress;
  document.querySelector('#m07-progress-label').textContent=job?`${m07JobName(job)} · ${prepared?'코드 준비':'생성'} ${generated}/${cases.length}건 · 최종 통과 ${both}건${job.error?' · '+job.error:''}`:'업무를 선택하고 코드를 준비하세요.';
  document.querySelector('#m07-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2></div><div class="result-grid m07-summary"><div><label>코드 유효성·정확도</label><strong class="large-score">${score(result?.score,'M07')}</strong></div>${[['생성 코드 (GeneratedCode)','generated_code_count'],['문법 통과 (SyntaxPASS)','syntax_pass_count'],['실행 통과 (ExecutionPASS)','execution_pass_count'],['문법·실행 모두 통과 (BothPASS)','both_pass_count']].map(([label,key])=>`<div><label>${label}</label><strong data-m07-summary="${key}">${job?esc(counts[key]):'—'}</strong></div>`).join('')}<div><label>목표 ≥ ${score(state.metric.target,'M07')}</label><strong class="${met===true?'m07-pass':met===false?'m07-fail':''}">${met===true?'기준 충족':met===false?'기준 미달':'판정 대기'}</strong></div></div><p class="subtitle">문법검사와 실행테스트를 모두 통과한 코드 수 / 실제 생성 코드 수 × 100 · DEVELOPMENT 평가</p>${result?`<p class="run-meta">${esc(result.run_id)} · DEVELOPMENT · 공식 시험성적 아님</p>`:'<p class="empty">문법·실행 검사와 결과 저장이 완료되면 서버 평가 점수를 표시합니다.</p>'}`;
  if(prepared) document.querySelector('#m07-result').innerHTML=`<div class="panel-heading"><h2>준비 코드 검사 결과</h2><span class="badge neutral">준비한 원본</span></div><div class="result-grid m07-result-overview"><div><label>준비 코드 검사 통과율</label><strong class="large-score">${score(result?.score,'M07')}</strong></div><div><label>준비 코드</label><strong data-m07-summary="generated_code_count">${esc(counts.generated_code_count)}건</strong></div><div><label>문법 통과</label><strong data-m07-summary="syntax_pass_count">${esc(counts.syntax_pass_count)}건</strong></div><div><label>실행 통과</label><strong data-m07-summary="execution_pass_count">${esc(counts.execution_pass_count)}건</strong></div></div><p class="subtitle">문법·실행 모두 통과 ${esc(counts.both_pass_count)} / 준비 코드 ${esc(counts.generated_code_count)}건 · LLM 호출 없음 · LLM 생성 성능 집계에서 제외</p>${result?`<p class="run-meta">${esc(result.run_id)} · DEVELOPMENT</p>`:'<p class="m07-inline-note">원본 코드를 확인한 후 Chrome 문법·실행 검사를 시작하세요.</p>'}`;
  else {
    document.querySelector('#m07-result').innerHTML=m07MeasurementSummary(job,counts,result);
    if(job) {
      const value=m07Measurement(job,counts),actual=Number.isInteger(value.provider_http_attempt_count)?value.provider_http_attempt_count:'확인 불가';
      document.querySelector('#m07-progress-label').textContent=`${value.evaluation_status==='COMPLETED'?'등록 작업 측정 완료':'평가 대기 (NOT_READY)'} · 등록 ${value.registered_count}건 · 실제 HTTP 시도 ${actual}건 · 생성 ${value.generated_code_count}건${job.error?' · '+job.error:''}`;
    }
  }
  if(!job) document.querySelector('#m07-result').innerHTML=state.mode==='meeting'?'<div class="panel-heading"><h2>실제 LLM 20건 시험 결과</h2><span class="badge neutral">검사 대기</span></div><div class="result-grid"><div><label>문법·실행 통합 성공률</label><strong class="large-score">—</strong></div><div><label>시험 입력</label><strong>20건</strong></div><div><label>모두 통과</label><strong>—</strong></div><div><label>목표 기준</label><strong>80%</strong></div></div><p class="empty">실행 결과가 이곳에 표시됩니다. 실제 LLM 코드 생성 후 별도 검사 버튼을 누르면 최종 성공률을 확인할 수 있습니다.</p>':'<div class="panel-heading"><h2>Development Result</h2></div><div class="result-grid"><div><label>코드 검사 통과율</label><strong class="large-score">—</strong></div><div><label>준비 코드</label><strong>—</strong></div><div><label>문법 통과</label><strong>—</strong></div><div><label>실행 통과</label><strong>—</strong></div></div><p class="empty">실행 결과가 이곳에 표시됩니다. 코드를 준비하고 검사하면 문법·실행 결과와 원본 근거를 확인할 수 있습니다.</p>';
  const meeting=job?.meeting_protocol||!job&&state.mode==='meeting';
  document.querySelector('#m07-cases').innerHTML=(meeting?m07MeetingTable(job):'')+(cases.length?cases.map(row=>{
    const open=state.openCode.has(row.case_id),code=state.code.get(row.case_id),canRead=row.generation_status==='PASS'||!!row.code_sha256;
    const origin=row.code_source==='PREPARED'||prepared?`<details class="m07-metadata"><summary>준비한 원본 · ${esc(row.source_filename||'Python')} ${state.codeProof.has(row.case_id)?' · 원본 일치 확인':''}</summary><p class="run-meta">원본 SHA-256: ${esc(row.source_file_sha256||row.code_sha256||'—')}${row.validation_code_sha256?'<br>검사 원본 SHA-256: '+esc(row.validation_code_sha256):''}</p></details>`:'<p class="run-meta">LLM 생성 기록</p>';
    const canExport=job.status==='GENERATED'&&job.source_kind!=='RBEM_PREPARED_WORKFLOW'&&!job.meeting_protocol;
    return `<details id="m07-case-${esc(row.case_id)}" class="m07-case" data-m07-case="${esc(row.case_id)}" ${state.expandedCases.has(row.case_id)?'open':''}><summary class="m07-case-heading"><div><strong>${esc(row.scenario_name||row.scenario_id)}</strong><small>${esc(row.case_id)} · ${row.workflow_id?esc(row.workflow_id)+' · ':''}문법 ${esc(m07Name(row.syntax_status))} · 실행 ${esc(m07Name(row.execution_status))}</small></div><span class="badge ${row.final_status==='PASS'?'pass':row.final_status==='FAIL'?'fail':'neutral'}">${esc(m07Name(row.final_status))}</span></summary><div class="m07-case-body">${origin}
      ${canExport?`<label class="m07-export-choice"><input type="checkbox" data-m07-export="${esc(row.case_id)}" ${state.exportSelected.has(row.case_id)?'checked':''} ${state.busy?'disabled':''}>M04 고정 등록 대상</label>`:''}
      <div class="m07-checks">${[[prepared?'준비':'생성',row.generation_status],['문법',row.syntax_status],['실행',row.execution_status]].map(([label,status])=>`<div><label>${label}</label><strong class="${status==='PASS'?'m07-pass':['FAIL','ERROR','TIMEOUT'].includes(status)?'m07-fail':''}">${esc(m07Name(status))}</strong></div>`).join('')}</div>
      ${row.error?`<p class="notice">${esc(row.error)}</p>`:''}${row.syntax_error?`<p class="notice">문법: ${esc(typeof row.syntax_error==='object'?JSON.stringify(row.syntax_error):row.syntax_error)}</p>`:''}${row.execution_error?`<p class="notice">실행: ${esc(row.execution_error)}</p>`:''}
      <div class="m07-case-actions">${canRead?`<button class="m07-secondary" type="button" data-m07-code="${esc(row.case_id)}" aria-expanded="${open}">${open?'코드 접기':prepared?'준비 원본 보기':'생성 원본 보기'}</button><button class="m07-secondary" type="button" data-m07-download="${esc(row.case_id)}">Python 다운로드 ↓</button>`:''}</div>
      ${open?`<div class="m07-code"><p class="run-meta">SHA-256: ${esc(row.code_sha256||'—')}</p><pre>${esc(code??'원본 코드를 불러오는 중…')}</pre></div>`:''}${m07ScreenshotDetails(job.generation_id,row)}${m07StepDetails(row)}</div></details>`;
  }).join(''):meeting?'':'<p class="empty">코드를 생성하면 시나리오별 문법·실행 상태가 표시됩니다.</p>');
  const exportReady=state.exportSelected.size>0&&state.exportSelected.size<=10&&[...state.exportSelected].every(id=>cases.some(row=>row.case_id===id&&row.generation_status==='PASS'));
  document.querySelector('#m07-export').innerHTML=`${job?.status==='GENERATED'&&job.source_kind!=='RBEM_PREPARED_WORKFLOW'&&!job.meeting_protocol?`<div class="m07-actions"><button id="m07-export-button" class="m07-secondary" type="button" ${state.busy||!exportReady?'disabled':''}>M04에 고정 등록 (${state.exportSelected.size}건)</button></div><p class="subtitle">실행 검사 전에 M04 시험 코드를 고정합니다. 생성 완료 코드 중 최대 10건을 선택하세요. 등록 후 M04에서 별도로 실행합니다.</p>`:''}${state.exportLink?`<p class="m07-export-link"><a class="download" href="${esc(state.exportLink)}">고정 등록한 M04 스크립트 확인 →</a></p>`:''}`;
  document.querySelector('#m07-logs').textContent=Array.isArray(job?.logs)&&job.logs.length?job.logs.map(row=>`${row.time||''}${row.case_id?' ['+row.case_id+']':''} ${row.message||''}`).join('\n'):'작업 로그가 없습니다.';
  document.querySelector('#m07-downloads').innerHTML=job?[['report.json','생성·검사 보고서'],['code.zip','생성 코드 원본'],['steps.csv','실행 단계 CSV'],['log.jsonl','전체 로그'],['screenshots.zip','마스킹 화면 근거']].filter(([name])=>name!=='code.zip'||job.archive_sha256||['GENERATED','VALIDATING','COMPLETED'].includes(job.status)).map(([name,label])=>`<a class="download" href="${m07Artifact(job.generation_id,name)}" download>${label} ↓</a>`).join(''):'';
  if(job?.status==='GENERATED'&&!m07ValidationReady(job)) document.querySelector('#m07-export').insertAdjacentHTML?.('beforeend','<p class="notice">이전 생성 기록에는 독립 실행 조건이 없습니다. 원본을 보관하고 현재 조건으로 새로 생성하세요.</p>');
}
function m07ScreenshotDetails(generationId,row) {
  if(!m07Id(generationId)||!m07CaseId(row.case_id)||!Array.isArray(row.screenshots)) return '';
  const entries=row.screenshots.filter(frame=>frame&&['before','after'].includes(frame.phase));
  if(!entries.length) return '';
  return `<div class="m07-downloads">${entries.map(frame=>frame.status==='CAPTURED'&&frame.policy==='text-and-images-masked-v1'&&/^[a-f0-9]{64}$/.test(frame.sha256||'')?`<a class="download" href="/api/development/m07/generations/${generationId}/screenshots/${row.case_id}/${frame.phase}.png" target="_blank" rel="noopener">${frame.phase==='before'?'실행 전':'실행 후'} 마스킹 화면</a>`:`<span class="subtitle">${frame.phase==='before'?'실행 전':'실행 후'} 화면 미확보${frame.reason?' · '+esc(frame.reason):''}</span>`).join('')}</div>`;
}
function m07StepDetails(row) {
  const business=row.step_evidence_mode==='BUSINESS_STEPS',steps=Array.isArray(row.steps)?row.steps:[];
  const independent=business?`<p class="run-meta">${row.independent_checks_passed===true?'독립 기대 결과 검사 통과':row.execution_contract_sha256?'독립 기대 결과 검사 '+(row.execution_status==='PASS'?'확인 필요':['FAIL','ERROR','TIMEOUT'].includes(row.execution_status)?'실패':'대기'):'기존 단계 기록 · 독립 기대 결과 검사 도입 전'}</p>`:'';
  const summary=business?`업무 단계 통과 ${row.success_step_count??0} / ${row.required_step_count??steps.length}`:'실행 동작 기록';
  const detail=steps.length?`<details class="m07-step-detail"><summary>${esc(summary)}</summary>${business&&row.failed_step?`<p class="notice">실패 단계: ${esc(typeof row.failed_step==='object'?JSON.stringify(row.failed_step):row.failed_step)}</p>`:''}<ol>${steps.map(step=>`<li><strong>${esc(step.order??step.sequence)} · ${esc(step.action)}</strong> ${esc(step.target)} <span>${esc(m07Name(step.status))}${step.duration_ms!=null?' · '+esc(step.duration_ms)+'ms':''}</span>${step.expected_result?`<span>기대 결과: ${esc(typeof step.expected_result==='object'?JSON.stringify(step.expected_result):step.expected_result)}</span>`:''}${step.error?`<span class="m07-fail">${esc(step.error)}</span>`:''}</li>`).join('')}</ol></details>`:'';
  const actions=business&&Array.isArray(row.action_logs)&&row.action_logs.length?`<details class="m07-step-detail"><summary>세부 동작 로그 ${row.action_logs.length}건</summary><ol>${row.action_logs.map(step=>`<li><strong>${esc(step.sequence)} · ${esc(step.action)}</strong> ${esc(step.target)} <span>${esc(m07Name(step.status))}</span></li>`).join('')}</ol></details>`:'';
  return `${row.step_evidence_mode==='LEGACY_TRACE'?'<p class="run-meta">이전 실행 기록 · 업무 단계별 검증 근거 없음</p>':''}${independent}${detail}${actions}`;
}
function autoPreviewM07Prepared(job) {
  const state=m07View,token=m07RequestNumber,id=job?.generation_id;
  if(state.generation?.generation_id!==id||!state.autoPreviewJobs.has(id)||job.code_source!=='PREPARED'
    ||job.source_kind!=='RBEM_PREPARED_WORKFLOW'||!['GENERATED','COMPLETED'].includes(job.status)) return Promise.resolve();
  if(state.autoPreviewRequests.has(id)) return state.autoPreviewRequests.get(id);
  const first=job.cases.find(row=>row.generation_status==='PASS');
  if(!first) return Promise.resolve();
  if(state.workflows.preparedGenerationId===id) {
    state.workflows.message='원본 코드를 준비했습니다. 아래에서 코드를 확인한 뒤 Chrome 문법·실행 검사를 누르세요.';paintM07WorkflowActions();
  }
  state.openCode.add(first.case_id);state.expandedCases.add(first.case_id);paintM07Generation();
  const request=(async()=>{
    try {await fetchM07Code(first.case_id);}
    catch(error) {
      if(m07Active(token)&&m07View===state&&state.generation?.generation_id===id) {
        const message=error.message+' 원본 보기 버튼으로 다시 확인하세요.';
        state.openCode.delete(first.case_id);
        if(state.workflows.preparedGenerationId===id){state.workflows.message=message;paintM07WorkflowActions();}
        m07Status(message);
      }
    } finally {if(m07Active(token)&&m07View===state&&state.generation?.generation_id===id)paintM07Generation();}
  })();
  state.autoPreviewRequests.set(id,request);return request;
}
function acceptM07Generation(job) {
  if(!job||!m07Id(job.generation_id)||!Array.isArray(job.cases)||job.cases.length>20||new Set(job.cases.map(row=>row.case_id)).size!==job.cases.length||job.cases.some(row=>!m07CaseId(row.case_id))||job.meeting_protocol&&(job.cases.length!==20||job.code_source!=='LLM')) throw new Error('생성·검사 기록 형식을 확인하세요.');
  if(m07View.generation?.generation_id!==job.generation_id) {m07View.code.clear();m07View.codeProof.clear();m07View.openCode.clear();m07View.exportSelected.clear();m07View.exportInitialized=false;m07View.exportLink=null;m07View.expandedCases=new Set(job.cases.length?[job.cases[0].case_id]:[]);}
  m07View.generation=job;
  if(job.status==='GENERATED'&&!m07View.exportInitialized) {m07View.exportSelected=new Set(job.cases.slice(0,10).map(row=>row.case_id));m07View.exportInitialized=true;}
  const index=m07View.generations.findIndex(row=>row.generation_id===job.generation_id);
  if(index<0) m07View.generations.unshift(job);else m07View.generations[index]=job;
  m07Remember(job.generation_id);paintM07();return autoPreviewM07Prepared(job);
}
async function selectM07Generation(id) {
  clearTimeout(m07PollTimer);
  const token=m07RequestNumber,state=m07View,selection=++state.selection;++state.pollRevision;
  if(!id) {state.generation=null;state.code.clear();state.codeProof.clear();state.openCode.clear();state.exportSelected.clear();state.exportInitialized=false;state.exportLink=null;m07Remember(null);paintM07();scheduleM07Poll(token);return;}
  if(!m07Id(id)) {m07Status('작업 이력 주소를 확인하세요.');return;}
  try {
    const data=await m07Json('/api/development/m07/generations/'+id);
    if(!m07Active(token)||selection!==state.selection) return;
    if(data.generation?.generation_id!==id) throw new Error('요청한 생성·검사 기록과 응답이 다릅니다.');
    acceptM07Generation(data.generation);scheduleM07Poll(token,selection);
  } catch(error) {if(m07Active(token)&&selection===state.selection) {m07Status(error.message);scheduleM07Poll(token);}}
}
function scheduleM07Poll(token) {
  clearTimeout(m07PollTimer);
  if(!m07Active(token)) return;
  const state=m07View,revision=++state.pollRevision;
  const running=m07Running(state.generation)?state.generation:state.generations.find(m07Running);
  if(!running) return;
  const id=running.generation_id;
  m07PollTimer=setTimeout(async()=>{
    if(!m07Active(token)||revision!==m07View.pollRevision) return;
    try {
      const data=await m07Json('/api/development/m07/generations/'+id);
      if(!m07Active(token)||revision!==m07View.pollRevision) return;
      const job=data.generation;
      if(job?.generation_id!==id||!Array.isArray(job.cases)||job.cases.some(row=>!m07CaseId(row.case_id))) throw new Error('요청한 작업과 응답이 다릅니다.');
      const index=state.generations.findIndex(row=>row.generation_id===id),cached=state.generations[index];
      if(cached&&!m07Running(cached)&&m07Running(job)) {scheduleM07Poll(token);return;}
      if(index<0)state.generations.unshift(job);else state.generations[index]=job;
      if(state.generation?.generation_id===id) {
        acceptM07Generation(job);
        m07Status(m07Running(job)?'진행 상태를 확인하고 있습니다.':job.status==='GENERATED'?(job.code_source==='PREPARED'?'원본 코드 준비를 완료했습니다.':'코드 생성을 완료했습니다.')+' 문법·실행 검사를 실행하세요.':job.error||'작업 결과를 확인하세요.');
      } else paintM07();
      scheduleM07Poll(token);
    } catch(error) {if(error.status!=='SESSION_EXPIRED'&&m07Active(token)&&revision===m07View.pollRevision) {if(state.generation?.generation_id===id)m07Status(error.message);scheduleM07Poll(token);}}
  },1500);
}
async function startM07() {
  const state=m07View,ready=state.context?.readiness,rows=m07Scenarios();
  if(state.busy||state.generations.some(m07Running)||(state.preparedSelected?!m07PreparedReady(state):!ready?.configured||m07ProviderBlocked(state))||state.contextError||!state.selected.size||state.selected.size>20||[...state.selected].some(id=>!rows.some(row=>row.scenario_id===id&&row.execution_ready!==false))) return;
  const token=m07RequestNumber;state.busy=true;paintM07();m07Status(state.preparedSelected?'등록한 원본 코드를 요청하고 있습니다…':'LLM 코드 생성을 요청하고 있습니다…');
  try {
    const scenario_refs=[...state.selected].map(id=>m07SelectedRef(rows.find(item=>item.scenario_id===id)));
    const payload={scenario_refs};
    if(state.preparedSelected) payload.prepared_codes=scenario_refs.map(ref=>state.preparedCodes.find(row=>row.scenario_id===ref.scenario_id));
    const data=await m07Json('/api/development/m07/generations',payload);
    if(!m07Active(token)) return;
    ++state.selection;acceptM07Generation(data.generation);scheduleM07Poll(token);m07Status(state.preparedSelected?(data.generation.status==='GENERATED'?'등록한 원본 코드를 보관했습니다. 문법·실행 검사를 실행하세요.':'등록한 원본 코드를 보관하고 있습니다.'):'코드 생성 중입니다. 생성 원본과 오류를 기록합니다.');
  } catch(error) {if(m07Active(token)) m07Status(error.message);}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
async function validateM07() {
  const state=m07View,job=state.generation,ready=m07RunReadiness(job);
  if(state.busy||state.generations.some(m07Running)||job?.status!=='GENERATED'||!ready?.selenium||!ready?.chrome||!m07ValidationReady(job)) return;
  const token=m07RequestNumber,selection=state.selection,id=job.generation_id;state.busy=true;paintM07();m07Status('생성 원본의 문법 검사와 Selenium 실행을 요청하고 있습니다…');
  try {
    const data=await m07Json(`/api/development/m07/generations/${id}/validate`,{});
    if(!m07Active(token)||selection!==state.selection) return;
    if(data.generation?.generation_id!==id) throw new Error('요청한 검사와 응답이 다릅니다.');
    acceptM07Generation(data.generation);scheduleM07Poll(token,selection);m07Status('문법·실행 검사 상태를 확인하세요.');
  } catch(error) {if(m07Active(token)&&selection===state.selection) m07Status(error.message);}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
async function cancelM07() {
  const state=m07View,job=state.generation;
  if(state.busy||!m07Running(job)) return;
  const token=m07RequestNumber,selection=state.selection,id=job.generation_id;state.busy=true;paintM07();m07Status('작업 중단을 요청하고 있습니다…');
  try {
    const data=await m07Json(`/api/development/m07/generations/${id}/cancel`,{});
    if(!m07Active(token)||selection!==state.selection) return;
    if(data.generation?.generation_id!==id) throw new Error('요청한 중단 작업과 응답이 다릅니다.');
    acceptM07Generation(data.generation);scheduleM07Poll(token,selection);m07Status('중단 상태를 확인하세요. 미완료 작업은 평가 점수로 표시하지 않습니다.');
  } catch(error) {if(m07Active(token)&&selection===state.selection) {m07Status(error.message);scheduleM07Poll(token,selection);}}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
// 실행 전 M04 원본 고정
async function exportM07ToM04() {
  const state=m07View,job=state.generation,ids=[...state.exportSelected];
  if(state.busy||job?.status!=='GENERATED'||job.source_kind==='RBEM_PREPARED_WORKFLOW'||job.meeting_protocol||!ids.length||ids.length>10||ids.some(id=>!job.cases.some(row=>row.case_id===id&&row.generation_status==='PASS'))) return;
  const token=m07RequestNumber,selection=state.selection,id=job.generation_id;state.busy=true;paintM07();m07Status('선택 코드를 M04 실행 원본으로 고정하고 있습니다…');
  try {
    const data=await m07Json(`/api/development/m07/generations/${id}/export-m04`,{case_ids:ids});
    if(!m07Active(token)||selection!==state.selection) return;
    const url=data.m04_url,query=typeof url==='string'&&/^\/metrics\/m04\/?\?/.test(url)?new URLSearchParams(url.slice(url.indexOf('?')+1)):null;
    if(!Array.isArray(data.scripts)||data.scripts.length!==ids.length||!query||query.get('mode')!=='DEVELOPMENT'||/[\r\n\\]/.test(url)) throw new Error('M04 고정 등록 응답을 확인하세요.');
    state.exportLink=url;m07Status(`${data.scripts.length}건을 M04에 고정 등록했습니다. 링크를 눌러 실행 대상을 확인하세요.`);
  } catch(error) {if(m07Active(token)&&selection===state.selection) m07Status(error.message);}
  finally {if(m07Active(token)) {state.busy=false;paintM07();}}
}
async function fetchM07Code(id) {
  const state=m07View,job=state.generation,token=m07RequestNumber;
  if(!job||!m07CaseId(id)||!job.cases.some(row=>row.case_id===id)) return null;
  if(state.code.has(id)) return state.code.get(id);
  const data=await m07Json(`/api/development/m07/generations/${job.generation_id}/codes/${id}`);
  if(!m07Active(token)||state.generation?.generation_id!==job.generation_id) return null;
  if(typeof data.code!=='string'||data.case?.case_id!==id) throw new Error('생성 원본 응답을 확인하세요.');
  const row=job.cases.find(value=>value.case_id===id);
  if(job.code_source==='PREPARED'||row.code_source==='PREPARED') {
    const proof=data.identity_verification,hash=await m07CodeSha(new TextEncoder().encode(data.code));
    if(proof?.verified!==true||hash!==row.code_sha256||hash!==row.source_file_sha256
      ||hash!==data.case.code_sha256||hash!==data.case.source_file_sha256
      ||hash!==proof.source_sha256||hash!==proof.display_sha256) throw new Error('화면 코드와 등록한 원본의 SHA-256이 일치하지 않습니다.');
    if(!m07Active(token)||state.generation?.generation_id!==job.generation_id) return null;
    state.codeProof.set(id,hash);
  }
  else if(job.meeting_protocol) {
    const proof=data.identity_verification,hash=await m07CodeSha(new TextEncoder().encode(data.code));
    if(proof?.verified!==true||hash!==row.code_sha256||hash!==data.case.code_sha256||hash!==proof.source_sha256||hash!==proof.display_sha256)throw new Error('화면 코드와 실제 LLM 생성 원본의 SHA-256이 일치하지 않습니다.');
    if(!m07Active(token)||state.generation?.generation_id!==job.generation_id)return null;
    state.codeProof.set(id,hash);
  }
  state.code.set(id,data.code);return data.code;
}
async function readM07Code(id) {
  const token=m07RequestNumber,state=m07View,generation=state.generation?.generation_id;
  if(!m07CaseId(id)||!state.generation?.cases.some(row=>row.case_id===id)) return;
  if(state.openCode.has(id)) {state.openCode.delete(id);paintM07Generation();return;}
  state.openCode.add(id);state.expandedCases.add(id);paintM07Generation();
  try {await fetchM07Code(id);if(m07Active(token)&&state.generation?.generation_id===generation) paintM07Generation();}
  catch(error) {if(m07Active(token)&&state.generation?.generation_id===generation) {state.openCode.delete(id);paintM07Generation();m07Status(error.message);}}
}
async function downloadM07Code(id) {
  const token=m07RequestNumber,generation=m07View.generation?.generation_id;
  try {
    const code=await fetchM07Code(id);if(code==null||!m07Active(token)||m07View.generation?.generation_id!==generation) return;
    const url=URL.createObjectURL(new Blob([code],{type:'text/x-python;charset=utf-8'})),anchor=document.createElement('a');
    anchor.href=url;anchor.download=`${generation}_${id}.py`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  } catch(error) {if(m07Active(token)) m07Status(error.message);}
}
