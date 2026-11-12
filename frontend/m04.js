// M04 개발 실행 화면
let m04View=null;
let m04RequestNumber=0;
let m04PollTimer=null;
let m04PrepPollTimer=null;
const m04Names={QUEUED:'실행 대기',RUNNING:'실행 중',COMPLETED:'실행 완료',INTERRUPTED:'실행 중단',PENDING:'대기',PASS:'성공',FAIL:'실패',ERROR:'오류',TIMEOUT:'시간 초과',SKIPPED:'미실행'};
const m04ExecutionId=id=>/^M04-RUN-[0-9a-f]{32}$/.test(id||'');
const m04ScriptId=id=>/^[0-9a-f]{32}$/.test(id||'');
const m04ResultId=id=>/^DEV-M04-[0-9]{8}T[0-9]{6}-[0-9a-f]{12}$/.test(id||'');
const m04Active=token=>token===m04RequestNumber&&/^\/metrics\/m04\/?$/i.test(location.pathname);
const m04Running=job=>['QUEUED','RUNNING'].includes(job?.status);
const m04CaseName=status=>m04Names[status]||String(status||'대기');
function m04Artifact(id,name) {
  return m04ExecutionId(id)&&['report.json','log.jsonl','steps.csv','scripts.zip','screenshots.zip'].includes(name)?`/api/development/m04/executions/${id}/artifacts/${name}`:null;
}
function m04ResultArtifact(id,name='result.json') {
  return m04ResultId(id)&&['result.json','evidence.csv','run_manifest.json','received_payload.json'].includes(name)?`/api/evaluations/m04/runs/${id}/${name}`:null;
}
async function m04Json(url,payload) {
  const session=typeof catalog!=='undefined'?catalog?.server_session_id:null;
  const view=m04View;
  const providerRequest=url.startsWith('/api/development/m07/')&&view?.preparation?++view.preparation.providerRequest:0;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
  try {
    const response=await fetch(url,{signal:controller.signal,...(payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})});
    const data=await response.json();
    if(typeof ktlCheckServerSession==='function') ktlCheckServerSession(response,data,session);
    if(m04View===view&&m04Active(m04RequestNumber)&&url.startsWith('/api/development/m07/')) {
      const provider=data?.provider_state||data?.generation?.provider_state;
      if(provider&&typeof provider.blocked==='boolean'&&providerRequest>=view.preparation.providerResponse) {
        view.preparation.providerState=provider;view.preparation.providerResponse=providerRequest;
      }
    }
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
  query.delete('run_id');
  if(m04ExecutionId(id)) query.set('execution_id',id);else query.delete('execution_id');
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
function m04RememberResult(id) {
  if(typeof history==='undefined'||typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);query.delete('execution_id');
  if(m04ResultId(id)) query.set('run_id',id);else query.delete('run_id');
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
async function refreshM04() {
  const state=m04View,token=m04RequestNumber;
  if(state.busy||state.preparation.busy) return;
  state.busy=true;paintM04();m04Status('최신 접수 결과와 실행 이력을 확인하고 있습니다…');
  try {
    const data=await m04Json('/api/evaluations?mode=DEVELOPMENT');
    if(!m04Active(token)) return;
    const metric=Array.isArray(data.metrics)?data.metrics.find(row=>row.metric_id==='M04'):null;
    if(!metric) throw new Error('M04 평가 목록 응답을 확인하세요.');
    if(typeof catalog!=='undefined') catalog=data;
    if(state.resultSource==='external') m04RememberResult(null);
    renderM04(metric);
  } catch(error) {if(m04Active(token)) {state.busy=false;paintM04();m04Status(error.message);}}
}
function renderM04(metric) {
  clearTimeout(m04PollTimer);
  clearTimeout(m04PrepPollTimer);
  const token=++m04RequestNumber,query=new URLSearchParams(location.search);
  m04View={metric,scripts:[],selected:new Set(),code:new Map(),openCode:new Set(),executions:[],execution:null,externalResult:null,externalRunId:null,externalError:null,resultSource:'execution',readiness:null,busy:false,scenarios:[],scenarioRun:null,scenario:null,locked:!!query.get('scenario_id'),selection:0,pollRevision:0};
  m04View.preparation={context:null,providerState:null,providerRequest:0,providerResponse:0,sources:[],selectedKey:'',jobs:[],job:null,code:new Map(),proof:new Map(),openCode:new Set(),fixed:new Set(),busy:false,loading:true,selection:0,message:'저장 시나리오와 코드 준비 이력을 확인하고 있습니다…'};
  m04View.m01={datasets:[],selectedId:'',scope:null,context:null,parameters:{},loading:true,selection:0,fixedSignature:null,message:'수집 CSV 목록을 확인하고 있습니다…'};
  m04View.cu02={workflow:null,values:{date:'',title:'',description:'',browser:'chrome'},loading:true,fixedSignature:null,message:'일정 등록 준비 상태를 확인하고 있습니다…'};
  m04View.visibleBrowser=true;
  document.title='DEVELOPMENT · M04 · Rainbow';
  app.innerHTML=`${banner('고정 Selenium/Python 스크립트 실행')}<a class="back" href="${link('/')}">← 전체 평가</a>
    <section class="page-heading"><div><p class="eyebrow">M04 / DEVELOPMENT</p><h1>${labels.M04}</h1><p class="subtitle">시나리오로 코드를 준비하고 원본을 고정한 뒤, 별도로 실행합니다.</p></div><span class="badge neutral">로컬 실행</span></section>
    <section class="evaluation-panel m04-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2><button id="m04-refresh" class="m04-secondary" type="button">새로고침</button></div>
      <div class="dataset-grid"><div><label>실행 환경</label><strong id="m04-ready">확인 중…</strong></div><div><label>선택한 스크립트</label><strong id="m04-selected-count">0건</strong></div><div><label>M04 목표값</label><strong>≥ ${score(metric.target,'M04')}</strong></div></div>
      <div id="m04-cu02-panel" class="m04-cu02"><h2>CU02 · 일정 등록</h2><p class="subtitle">일정관리 → 날짜 선택 → 일정 입력 → 등록 → 종료</p><p id="m04-cu02-login" class="subtitle" role="status">로그인 준비 상태 확인 중…</p><div class="m04-cu02-fields"><label>등록 날짜<input id="m04-cu02-date" type="date" required></label><label>실행 브라우저<select id="m04-cu02-browser"><option value="chrome">Google Chrome</option><option value="edge">Microsoft Edge</option></select></label><label class="m04-cu02-title">일정 제목 · 10건 평가에서는 제목 앞부분으로 사용<input id="m04-cu02-title" type="text" maxlength="120" required autocomplete="off"><small>10건 평가는 105자까지 입력할 수 있으며, 각 제목에 평가 ID와 번호가 붙습니다.</small></label><label class="m04-cu02-description">일정 내용<textarea id="m04-cu02-description" rows="3" maxlength="2000"></textarea></label></div>
        <div class="m04-cu02-policy"><strong>평가 1건 = 일정 1건 등록부터 재조회 확인까지</strong><p>10건 평가 실행을 누르면 위 날짜·내용으로 제목이 서로 다른 일정 10건을 실제 등록합니다. 고정한 스크립트 10개를 각각 한 번 실행하고, 9건 이상 성공하면 목표 90%를 달성합니다.</p><p>실행 전에는 신규등록 화면의 제목·내용이 비었는지 확인하고, 실행 후에는 저장한 일정을 다시 열어 입력값과 비교합니다. 전후 화면과 항목별 확인 결과를 실행 기록에 남깁니다.</p></div>
        <div class="m04-run-actions"><button id="m04-cu02-evaluate" type="button" disabled>CU02 10건 평가 실행</button><button id="m04-cu02-prepare" class="m04-secondary" type="button" disabled>단건 실행 준비</button></div><p id="m04-cu02-status" class="subtitle" role="status"></p><p class="subtitle">단건 실행 준비는 스크립트만 만듭니다. 단건 확인은 아래 선택 스크립트 실행을 누르세요. 로그인은 창을 띄우기 전에 처리합니다.</p></div>
      <div id="m04-m01-panel" class="m04-m01"><h2>M01 수집 동작</h2><p class="subtitle">수집한 CSV의 동작을 고정 스크립트로 가져옵니다. 가져오기만으로 브라우저를 실행하지 않습니다.</p><label>수집 CSV<select id="m04-m01-dataset" aria-label="재현할 수집 CSV"></select></label><div id="m04-m01-fields"></div><p id="m04-m01-status" class="subtitle" role="status"></p><button id="m04-m01-import" class="m04-secondary" type="button" disabled>M01 동작 가져오기</button></div>
      <div id="m04-web-prepare" class="m04-prep"><h2>1. 시나리오로 코드 준비</h2><p class="subtitle">코드 생성은 GPT 요청을 보냅니다. 원본 확인·M04 고정·브라우저 실행은 각각 별도 동작입니다.</p>
        <label>M03 시나리오<select id="m04-prep-scenario" aria-label="코드를 준비할 M03 시나리오"></select></label>
        <div id="m04-prep-provider" role="status"></div><div class="m04-run-actions"><button id="m04-prep-generate" type="button" disabled>코드 생성</button><button id="m04-prep-cancel" class="m04-secondary" type="button" disabled>생성 중단</button></div>
        <label class="m04-prep-history">코드 준비 이력<select id="m04-prep-history" aria-label="코드 준비 이력"></select></label>
        <p id="m04-prep-status" class="subtitle" role="status"></p><div id="m04-prep-cases"></div>
        <button id="m04-prep-fix" class="m04-secondary" type="button" disabled>확인한 원본을 M04에 고정</button>
      </div>
      <details class="m04-advanced"><summary>고급 기능 · 외부 Python 파일 등록</summary><p class="subtitle">이미 준비한 .py 파일을 원본 그대로 등록할 때 사용합니다.</p><div id="m04-scenario"></div><div class="run-row"><p>선택한 Python 파일을 이 PC에서 실행합니다.<br>등록한 원본은 수정하지 않고 보관합니다.</p><button id="m04-register" class="m04-secondary" type="button" disabled>스크립트 등록</button><input id="m04-file" type="file" accept=".py" hidden></div></details>
      <h2 class="m04-execute-heading">2. 고정한 코드 선택·실행</h2><p class="subtitle">여러 번 준비한 코드를 최대 10건 선택할 수 있습니다. 실행 버튼을 눌러야 브라우저가 시작됩니다.</p>
      <div id="m04-scripts"></div><div class="m04-run-actions"><button id="m04-start" type="button" disabled>선택 스크립트 실행</button><button id="m04-cancel" class="m04-secondary" type="button" disabled>실행 중단</button><label class="m04-visible-option"><input id="m04-visible-browser" type="checkbox" checked>새 창으로 실행</label></div><p class="subtitle">브라우저 새 창에서 동작을 보여주고 종료 화면을 15초 표시합니다.</p>
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
  document.querySelector('#m04-refresh').addEventListener('click',refreshM04);
  for(const field of ['date','title','description','browser']) document.querySelector('#m04-cu02-'+field).addEventListener(field==='browser'?'change':'input',event=>{
    if(m04View.busy||m04PrepBlocking()||m04View.executions.some(m04Running)) return;
    m04View.cu02.values[field]=event.target.value;m04View.cu02.fixedSignature=null;
    document.querySelector('#m04-cu02-prepare').disabled=!m04Cu02CanPrepare();
    document.querySelector('#m04-cu02-evaluate').disabled=!m04Cu02CanEvaluate();
  });
  document.querySelector('#m04-cu02-prepare').addEventListener('click',prepareM04Cu02);
  document.querySelector('#m04-cu02-evaluate').addEventListener('click',evaluateM04Cu02);
  document.querySelector('#m04-m01-dataset').addEventListener('change',event=>selectM04M01Source(event.target.value));
  document.querySelector('#m04-m01-fields').addEventListener('input',event=>{
    const name=event.target.dataset?.m01Parameter,source=m04View.m01;
    if(m04View.busy||!source.context?.missing_inputs.some(row=>row.name===name)) return;
    source.parameters[name]=event.target.value;source.fixedSignature=null;
    document.querySelector('#m04-m01-import').disabled=!m04M01CanImport();
  });
  document.querySelector('#m04-m01-import').addEventListener('click',importM04M01Source);
  document.querySelector('#m04-visible-browser').addEventListener('change',event=>{if(!m04View.busy&&!m04View.executions.some(m04Running)) m04View.visibleBrowser=event.target.checked===true;});
  document.querySelector('#m04-prep-scenario').addEventListener('change',event=>selectM04PreparationSource(event.target.value));
  document.querySelector('#m04-prep-history').addEventListener('change',event=>selectM04Preparation(event.target.value));
  document.querySelector('#m04-prep-generate').addEventListener('click',generateM04Preparation);
  document.querySelector('#m04-prep-cancel').addEventListener('click',cancelM04Preparation);
  document.querySelector('#m04-prep-fix').addEventListener('click',fixM04Preparation);
  document.querySelector('#m04-prep-cases').addEventListener('click',event=>{const target=event.target.closest('[data-m04-prep-code]');if(target) readM04PreparationCode(target.dataset.m04PrepCode);});
  document.querySelector('#m04-history').addEventListener('change',event=>event.target.value.startsWith('result:')?selectM04Result(event.target.value.slice(7)):selectM04Execution(event.target.value));
  document.querySelector('#m04-scenario').addEventListener('change',event=>{
    if(event.target.id!=='m04-scenario-select'||m04View.busy||m04PrepBlocking()||m04View.executions.some(m04Running)) return;
    m04View.scenario=m04View.scenarios.find(row=>row.scenario_id===event.target.value)||null;paintM04();
  });
  document.querySelector('#m04-scripts').addEventListener('change',event=>{
    const id=event.target.dataset?.scriptId;
    if(!m04ScriptId(id)||m04View.busy||m04PrepBlocking()||m04View.executions.some(m04Running)) return;
    if(event.target.checked) m04View.selected.add(id);else m04View.selected.delete(id);
    paintM04();
  });
  document.querySelector('#m04-scripts').addEventListener('click',event=>{
    const target=event.target.closest('[data-script-code]');if(target) readM04Code(target.dataset.scriptCode);
  });
  paintM04();
  bootstrapM04(token,query).catch(error=>{if(m04Active(token)) m04Status(error.message);});
}
function m04Cu02Values() {
  const values=m04View.cu02.values;
  return {date:values.date,title:values.title.trim(),description:values.description.trim(),browser:values.browser};
}
function m04Cu02Valid(values) {
  if(!/^\d{4}-\d{2}-\d{2}$/.test(values.date)||!values.title||values.title.length>120||/[\r\n]/.test(values.title)||values.description.length>2000||!['edge','chrome'].includes(values.browser)) return false;
  const stamp=new Date(values.date+'T00:00:00Z');
  return !Number.isNaN(stamp.getTime())&&stamp.toISOString().slice(0,10)===values.date;
}
function m04Cu02Workflow(value) {
  if(!value||value.workflow_id!=='CU02'||value.run_mode!=='DEVELOPMENT'||typeof value.name!=='string'||typeof value.login_configured!=='boolean'
    ||value.target_url!=='https://rainbowlab.ai.kr/mypage/schedule'||!Array.isArray(value.steps)||value.steps.some(step=>typeof step!=='string')
    ||!value.defaults||!['date','title','description'].every(key=>typeof value.defaults[key]==='string')||!m04Cu02Valid(value.defaults)) throw new Error('CU02 일정 등록 준비 응답을 확인하세요.');
  return value;
}
function m04Cu02CanPrepare() {
  const state=m04View,source=state.cu02;
  return !!(source?.workflow?.login_configured&&!source.loading&&!state.busy&&!m04PrepBlocking()&&!state.executions.some(m04Running)
    &&m04Cu02Valid(m04Cu02Values())&&source.fixedSignature!==JSON.stringify(m04Cu02Values()));
}
function m04Cu02CanEvaluate() {
  const state=m04View,source=state.cu02,values=m04Cu02Values();
  return !!(source?.workflow?.login_configured&&!source.loading&&!state.busy&&!m04PrepBlocking()&&!state.executions.some(m04Running)
    &&state.readiness?.selenium&&state.readiness?.[values.browser]&&m04Cu02Valid(values)&&values.title.length<=105);
}
function m04Cu02Evaluation(value,cases) {
  return !!(value&&/^CU02-EVAL-[a-f0-9]{32}$/.test(value.evaluation_id||'')&&value.workflow_id==='CU02'
    &&value.case_count===10&&value.counting_unit==='SCHEDULE_REGISTRATION'&&Array.isArray(cases)&&cases.length===10
    &&new Set(cases.map(row=>row?.case_id)).size===10&&new Set(cases.map(row=>row?.script_id)).size===10
    &&cases.every((row,index)=>row?.case_id==='CASE-'+String(index+1).padStart(3,'0')&&m04ScriptId(row.script_id)
      &&row.cu02_evaluation_id===value.evaluation_id&&row.cu02_case_number===index+1));
}
async function evaluateM04Cu02() {
  if(!m04Cu02CanEvaluate()) return;
  const state=m04View,source=state.cu02,token=m04RequestNumber;
  state.busy=true;++state.selection;clearTimeout(m04PollTimer);
  source.message='CU02 일정 등록 10건을 고정하고 자동 실행을 요청하고 있습니다…';paintM04();m04Status(source.message);
  try {
    const data=await m04Json('/api/development/m04/cu02/evaluations',{...m04Cu02Values(),
      ...(state.visibleBrowser?{visible_browser:true,action_delay_ms:700,keep_open_seconds:15}:{})});
    if(!m04Active(token)) return;
    if(!m04Cu02Evaluation(data.evaluation,data.execution?.cases)||data.execution?.cu02_evaluation?.evaluation_id!==data.evaluation.evaluation_id)
      throw new Error('CU02 10건 평가와 실행 기록의 연결을 확인하세요. 새로고침으로 실행 이력을 확인하세요.');
    state.locked=false;state.selected=new Set(data.execution.cases.map(row=>row.script_id));
    if(typeof ktlDropQuery==='function') ktlDropQuery(['m03_run_id','scenario_id']);
    acceptM04Execution(data.execution);scheduleM04Poll(token);
    source.message='CU02 10건 평가를 시작했습니다. 아래에서 건별 결과와 전후 화면을 확인하세요.';m04Status(source.message);
    try {
      const listed=await m04Json('/api/development/m04/scripts');
      if(!m04Active(token)) return;
      if(listed.run_mode!=='DEVELOPMENT'||!Array.isArray(listed.scripts)) throw new Error('스크립트 목록 응답을 확인하세요.');
      state.scripts=listed.scripts.filter(row=>m04ScriptId(row?.script_id));state.readiness=listed.readiness;
    } catch(error) {
      if(error.status==='SESSION_EXPIRED'||!m04Active(token)) throw error;
      source.message+=' 스크립트 목록은 새로고침으로 확인하세요.';
    }
  } catch(error) {if(m04Active(token)) {source.message=error.message;m04Status(source.message);}}
  finally {if(m04Active(token)) {state.busy=false;paintM04();}}
}
async function bootstrapM04Cu02(token) {
  const state=m04View,source=state.cu02;
  try {
    const value=await m04Json('/api/development/m04/cu02');
    if(!m04Active(token)) return;
    source.workflow=m04Cu02Workflow(value);source.values={...value.defaults};
    source.message=value.login_configured?'날짜와 내용을 확인하고 실행을 준비하세요.':'로그인 계정 설정 후 새로고침하세요.';
  } catch(error) {if(m04Active(token)) source.message=error.message;}
  finally {if(m04Active(token)) {source.loading=false;paintM04();}}
}
function paintM04Cu02() {
  const state=m04View,source=state.cu02;if(!source) return;
  const blocked=source.loading||state.busy||m04PrepBlocking()||state.executions.some(m04Running)||!source.workflow;
  for(const field of ['date','title','description','browser']) {
    const input=document.querySelector('#m04-cu02-'+field);
    if(input.value!==source.values[field]) input.value=source.values[field];
    input.disabled=blocked;
  }
  document.querySelector('#m04-cu02-login').textContent=source.workflow?(source.workflow.login_configured?'로그인 계정 준비됨':'로그인 계정 설정 필요'):source.loading?'로그인 준비 상태 확인 중…':'로그인 준비 상태를 확인할 수 없습니다.';
  document.querySelector('#m04-cu02-status').textContent=source.message;
  document.querySelector('#m04-cu02-prepare').disabled=!m04Cu02CanPrepare();
  document.querySelector('#m04-cu02-evaluate').disabled=!m04Cu02CanEvaluate();
}
async function prepareM04Cu02() {
  if(!m04Cu02CanPrepare()) return;
  const state=m04View,source=state.cu02,token=m04RequestNumber,values=m04Cu02Values();
  state.busy=true;source.message='일정 등록 스크립트를 준비하고 있습니다…';paintM04();
  try {
    const data=await m04Json('/api/development/m04/cu02/scripts',values);
    if(!m04Active(token)) return;
    const script=data.script,workflow=m04Cu02Workflow(data.workflow);
    if(!script||!m04ScriptId(script.script_id)||!m04PrepHash(script.sha256)||script.source_kind!=='CU02_SCHEDULE_REGISTRATION'
      ||script.workflow_id!=='CU02'||!/^CU02-SCHEDULE-[a-f0-9]{12}$/.test(script.scenario_id||'')||script.generated_by_llm!==false||script.business_step_required!==true||script.execution_ready===false) throw new Error('준비한 CU02 스크립트의 연결을 확인하세요. 새로고침으로 준비 기록을 확인하세요.');
    source.workflow=workflow;source.fixedSignature=JSON.stringify(values);
    let refreshError='';
    try {
      const listed=await m04Json('/api/development/m04/scripts');
      if(!m04Active(token)) return;
      if(listed.run_mode!=='DEVELOPMENT'||!Array.isArray(listed.scripts)) throw new Error('스크립트 목록 응답을 확인하세요.');
      state.scripts=listed.scripts.filter(row=>m04ScriptId(row?.script_id));state.readiness=listed.readiness;
    } catch(error) {if(error.status==='SESSION_EXPIRED'||!m04Active(token)) throw error;refreshError=' 목록 새로고침에 실패했습니다. 준비한 스크립트는 선택했습니다.';}
    if(!m04Active(token)) return;
    const index=state.scripts.findIndex(row=>row.script_id===script.script_id);
    if(index<0) state.scripts.unshift(script);else state.scripts[index]=script;
    state.selected=new Set([script.script_id]);state.locked=false;
    if(typeof ktlDropQuery==='function') ktlDropQuery(['m03_run_id','scenario_id']);
    source.message='CU02 실행 준비를 완료했습니다. 아래 선택 스크립트 실행을 누르세요.'+refreshError;m04Status(source.message);
  } catch(error) {if(m04Active(token)) source.message=error.message;}
  finally {if(m04Active(token)) {state.busy=false;paintM04();}}
}
// M01 source inspection is read-only; import and browser execution require separate clicks.
const m04M01Id=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
const m04M01Hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
function m04M01Current(token,selection) {return m04Active(token)&&m04View.m01.selection===selection;}
function m04M01Stored() {
  try {
    if(typeof sessionStorage==='undefined') return null;
    const row=JSON.parse(sessionStorage.getItem('ktl.m01.replay-source.v1')||'null');
    if(row&&Object.keys(row).sort().join(',')==='comparison_id,server_session_id'&&m04M01Id(row.comparison_id)
      &&typeof row.server_session_id==='string'&&/^SERVER-[a-f0-9]{32}$/.test(row.server_session_id)
      &&row.server_session_id===catalog?.server_session_id) return {comparison_id:row.comparison_id};
    if(row) sessionStorage.removeItem('ktl.m01.replay-source.v1');
  } catch {}
  return null;
}
function m04M01Signature() {const source=m04View.m01;return JSON.stringify([source.scope,source.parameters]);}
function m04M01CanImport() {
  const state=m04View,source=state.m01,context=source?.context;
  return !!(context&&source.scope&&!source.loading&&!state.busy&&!m04PrepBlocking()&&!state.executions.some(m04Running)
    &&['READY','NEEDS_INPUT'].includes(context.status)&&!context.blockers.length&&context.steps.some(row=>['execute','check'].includes(row?.kind))
    &&context.missing_inputs.every(row=>typeof source.parameters[row.name]==='string'&&source.parameters[row.name].trim())
    &&source.fixedSignature!==m04M01Signature());
}
function validateM04M01Source(context,scope) {
  if(!m04M01Id(context?.dataset_id)||!m04M01Hash(context.source_sha256)||typeof context.filename!=='string'
    ||!Number.isInteger(context.event_count)||context.event_count<0||!Array.isArray(context.steps)
    ||!Array.isArray(context.missing_inputs)||!Array.isArray(context.blockers)||!['READY','NEEDS_INPUT','NOT_READY'].includes(context.status)
    ||!m04View.m01.datasets.some(row=>row.dataset_id===context.dataset_id)
    ||(scope.dataset_id&&context.dataset_id!==scope.dataset_id)||(scope.comparison_id&&context.comparison_id!==scope.comparison_id)
    ||context.missing_inputs.some(row=>!row||typeof row.name!=='string'||!row.name||['__proto__','constructor','prototype'].includes(row.name))
    ||new Set(context.missing_inputs.map(row=>row.name)).size!==context.missing_inputs.length) throw new Error('수집 CSV·평가 범위·원본 SHA 응답을 확인하세요.');
}
async function bootstrapM04M01(token) {
  const data=await m04Json('/api/development/m01/csv');
  if(!m04Active(token)) return;
  if(!Array.isArray(data.datasets)) throw new Error('수집 CSV 목록을 확인하세요.');
  const source=m04View.m01;source.datasets=data.datasets.filter(row=>m04M01Id(row?.dataset_id));source.loading=false;
  const saved=m04M01Stored();
  if(saved) {await loadM04M01Source(saved);return;}
  source.message=source.datasets.length?'수집 CSV를 선택하세요. 목록 순서는 현재 M01 선택을 뜻하지 않습니다.':'현재 서버 세션에 업로드한 CSV가 없습니다. M01에서 CSV를 업로드하세요.';paintM04();
}
async function selectM04M01Source(id) {
  if(m04View.busy||m04PrepBlocking()||m04View.executions.some(m04Running)) return;
  if(!id) {const source=m04View.m01;++source.selection;source.selectedId='';source.scope=null;source.context=null;source.parameters={};source.loading=false;source.fixedSignature=null;source.message='수집 CSV를 선택하세요.';paintM04();return;}
  if(!m04View.m01.datasets.some(row=>row.dataset_id===id)) return;
  await loadM04M01Source({dataset_id:id});
}
async function loadM04M01Source(scope) {
  const state=m04View,source=state.m01,token=m04RequestNumber,selection=++source.selection;
  source.scope=null;source.context=null;source.parameters={};source.fixedSignature=null;source.selectedId=scope.dataset_id||'';source.loading=true;source.message='수집 동작과 필요한 입력값을 확인하고 있습니다…';paintM04();
  try {
    const data=await m04Json('/api/development/m04/m01-source?'+new URLSearchParams(scope));
    if(!m04M01Current(token,selection)) return;
    validateM04M01Source(data,scope);source.scope=scope;source.context=data;source.selectedId=data.dataset_id;
    const executable=data.steps.filter(row=>['execute','check'].includes(row?.kind)).length;
    source.message=`${data.event_count}개 이벤트 · 실행·확인 ${executable}단계 · ${data.notice||'필요한 입력값을 확인한 후 가져오세요.'}`;
  } catch(error) {if(m04M01Current(token,selection)) source.message=error.message;}
  finally {if(m04M01Current(token,selection)) {source.loading=false;paintM04();}}
}
function paintM04M01() {
  const state=m04View,source=state.m01;if(!source) return;
  const blocked=state.busy||m04PrepBlocking()||state.executions.some(m04Running),context=source.context;
  document.querySelector('#m04-m01-dataset').innerHTML='<option value="">수집 CSV 선택</option>'+source.datasets.map(row=>`<option value="${esc(row.dataset_id)}" ${source.selectedId===row.dataset_id?'selected':''}>${esc(row.filename)} · ${esc(row.summary?.event_count??'—')}건</option>`).join('');
  document.querySelector('#m04-m01-dataset').value=source.selectedId;
  document.querySelector('#m04-m01-dataset').disabled=blocked||!source.datasets.length;
  document.querySelector('#m04-m01-fields').innerHTML=context?`${context.missing_inputs.map(row=>`<label>행 ${esc(row.row)} · ${esc(row.target)}<input type="text" data-m01-parameter="${esc(row.name)}" value="${esc(source.parameters[row.name]||'')}" autocomplete="off" spellcheck="false" ${blocked?'disabled':''}><small>${esc(row.reason||'재현에 사용할 값을 입력하세요.')}</small></label>`).join('')}${context.blockers.length?`<p class="notice">${context.blockers.map(row=>esc(typeof row==='string'?row:(row?.row!=null?'행 '+row.row+': ':'')+(row?.reason||'재현 조건 확인 필요'))).join(' · ')}</p>`:''}`:'';
  document.querySelector('#m04-m01-status').textContent=source.message;
  document.querySelector('#m04-m01-import').disabled=!m04M01CanImport();
}
async function importM04M01Source() {
  if(!m04M01CanImport()) return;
  const state=m04View,source=state.m01,token=m04RequestNumber,selection=source.selection,signature=m04M01Signature();
  const expected=source.context;state.busy=true;source.message='수집 동작의 고정 스크립트를 준비하고 있습니다…';paintM04();
  try {
    const data=await m04Json('/api/development/m04/import-m01',{...source.scope,parameters:{...source.parameters}});
    if(!m04M01Current(token,selection)) return;
    const script=data.script,actual=data.source;
    if(!script||!m04ScriptId(script.script_id)||script.source_kind!=='M01_OBSERVED_REPLAY'||script.business_step_required!==true
      ||script.execution_ready===false||!m04M01Hash(script.sha256)||script.source_m01_dataset_id!==expected.dataset_id
      ||script.source_m01_csv_sha256!==expected.source_sha256||(script.source_m01_session_id??null)!==(expected.session_id??null)
      ||actual?.dataset_id!==expected.dataset_id||actual.source_sha256!==expected.source_sha256||(actual.session_id??null)!==(expected.session_id??null)
      ||(source.scope.comparison_id&&actual.comparison_id!==source.scope.comparison_id)) throw new Error('가져온 스크립트의 수집 원본·세션·SHA 연결을 확인하세요.');
    const index=state.scripts.findIndex(row=>row.script_id===script.script_id);
    if(index<0) state.scripts.unshift(script);else state.scripts[index]=script;
    if(state.selected.size<10||state.selected.has(script.script_id)) state.selected.add(script.script_id);
    state.locked=false;if(typeof ktlDropQuery==='function') ktlDropQuery(['m03_run_id','scenario_id']);
    source.fixedSignature=signature;source.message='M01 수집 동작을 가져왔습니다. 원본 확인 후 선택 스크립트 실행을 별도로 누르세요.';
    m04Status(source.message);paintM04();
    if(!state.openCode.has(script.script_id)) await readM04Code(script.script_id);
  } catch(error) {if(m04M01Current(token,selection)) source.message=error.message;}
  finally {if(m04M01Current(token,selection)) {state.busy=false;paintM04();}}
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
  // Scope is resolved first; failure of this optional panel leaves fixed scripts usable.
  bootstrapM04Cu02(token);
  bootstrapM04M01(token).catch(error=>{if(m04Active(token)) {m04View.m01.loading=false;m04View.m01.message=error.message;paintM04();}});
  bootstrapM04Preparation(token).catch(error=>{if(m04Active(token)) {m04View.preparation.loading=false;m04View.preparation.message=error.message;paintM04();}});
  paintM04();
  const requested=query.get('execution_id'),stale=!!(typeof catalog!=='undefined'&&catalog?.server_session_id&&requested&&!m04View.executions.some(row=>row.execution_id===requested));
  const active=m04View.executions.find(m04Running)?.execution_id,latest=m04View.metric.latest;
  const latestId=latest?.metric_id==='M04'&&latest.run_mode==='DEVELOPMENT'&&m04ResultId(latest.run_id)?latest.run_id:null;
  const external=query.get('run_id')||(!requested&&!active&&latestId&&!m04View.executions.some(row=>row.execution_id===latest.provenance?.external_run_id)?latestId:null);
  const id=stale?null:requested||active||(!external?m04View.executions[0]?.execution_id:null);
  if(stale) m04Remember(null);
  if(!stale&&requested&&!m04ExecutionId(requested)) errors.push('실행 이력 주소를 확인하세요.');
  else if(external&&!requested) {
    const restored=await selectM04Result(external);
    if(m04Active(token)&&restored&&errors.length) m04Status('API 접수 결과 표시 완료 · '+errors.join(' · '));
    return;
  }
  else if(id) await selectM04Execution(id);
  if(m04Active(token)) m04Status(errors.length?errors.join(' · '):m04Running(m04View.execution)?'실행 중인 기록을 이어서 표시합니다.':'스크립트를 선택한 후 실행하세요.');
}
// M04-local observer for the existing M07 generation API. It never calls validation.
const m04PrepId=id=>/^M07-GEN-[0-9a-f]{32}$/.test(id||'');
const m04PrepCaseId=id=>/^CASE-0(?:0[1-9]|1[0-9]|20)$/.test(id||'');
const m04PrepHash=value=>/^[a-f0-9]{64}$/.test(value||'');
const m04PrepKey=row=>JSON.stringify([row.m03_run_id,row.scenario_id,row.source_scenario_sha256]);
const m04PrepRunning=job=>['QUEUED','GENERATING','VALIDATING'].includes(job?.status);
const m04PrepName=status=>({QUEUED:'생성 대기',GENERATING:'생성 중',GENERATED:'생성 완료 · 실행 전',VALIDATING:'M07 검사 중',COMPLETED:'M07 검사 완료',INTERRUPTED:'중단',ERROR:'오류'})[status]||String(status||'대기');
function m04PrepBlocking() {
  const prep=m04View?.preparation;
  return !!(prep&&(prep.busy||m04PrepRunning(prep.job)));
}
function m04PrepSource() {const prep=m04View.preparation;return prep.sources.find(row=>m04PrepKey(row)===prep.selectedKey)||null;}
function m04PrepMatches(row,source=m04PrepSource()) {
  return !!(row&&source&&row.source_m03_run_id===source.m03_run_id&&row.scenario_id===source.scenario_id&&row.source_scenario_sha256===source.source_scenario_sha256);
}
function m04PrepCurrent(token,selection) {return m04Active(token)&&m04View.preparation.selection===selection;}
function m04PrepRemember(id) {
  if(typeof history==='undefined'||typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);
  if(m04PrepId(id)) query.set('prep_generation_id',id);else query.delete('prep_generation_id');
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
function m04PrepReset() {
  const prep=m04View.preparation;clearTimeout(m04PrepPollTimer);prep.selection++;
  prep.job=null;prep.code.clear();prep.proof.clear();prep.openCode.clear();
}
function m04PrepAccept(job) {
  const prep=m04View.preparation;
  if(!job||!m04PrepId(job.generation_id)||job.run_mode!=='DEVELOPMENT'||!Array.isArray(job.cases)||job.cases.length!==1
    ||!m04PrepCaseId(job.cases[0]?.case_id)||!m04PrepMatches(job.cases[0])) throw new Error('선택한 M03 원본과 코드 준비 기록의 실행 ID·시나리오·SHA가 일치하지 않습니다. 단일 시나리오 기록을 선택하세요.');
  const old=prep.job?.cases?.[0],row=job.cases[0];
  if(prep.job?.generation_id===job.generation_id&&old?.code_sha256&&old.code_sha256!==row.code_sha256) {
    prep.code.clear();prep.proof.clear();prep.openCode.clear();
  }
  prep.job=job;
  const index=prep.jobs.findIndex(value=>value.generation_id===job.generation_id);
  if(index<0) prep.jobs.unshift(job);else prep.jobs[index]=job;
  if(Array.isArray(job.m04_exports)&&job.m04_exports.some(item=>item.case_ids?.includes(row.case_id))) prep.fixed.add(job.generation_id+':'+row.case_id);
  if(m04View.scripts.some(script=>script.source_m07_generation_id===job.generation_id&&script.source_m07_case_id===row.case_id&&m04PrepMatches(script)&&script.sha256===row.code_sha256)) prep.fixed.add(job.generation_id+':'+row.case_id);
  m04PrepRemember(job.generation_id);
}
async function bootstrapM04Preparation(token) {
  const outputs=await Promise.allSettled([m04Json('/api/development/m07/context'),m04Json('/api/development/m07/generations')]);
  if(!m04Active(token)) return;
  const prep=m04View.preparation,errors=[];
  if(outputs[0].status==='fulfilled') {
    const context=outputs[0].value;
    if(context.run_mode!=='DEVELOPMENT'||!Array.isArray(context.scenarios)) errors.push('코드 준비용 시나리오 응답을 확인하세요.');
    else {
      prep.context=context;
      prep.sources=context.scenarios.filter(row=>row&&/^DEV-M03-\d{8}T\d{6}-[0-9a-f]{12}$/.test(row.m03_run_id||'')&&typeof row.scenario_id==='string'&&row.scenario_id.trim()&&m04PrepHash(row.source_scenario_sha256)
        &&(!m04View.locked||(row.m03_run_id===m04View.scenarioRun&&row.scenario_id===m04View.scenario?.scenario_id)));
      const source=prep.sources.find(row=>row.m03_run_id===m04View.scenarioRun&&row.scenario_id===m04View.scenario?.scenario_id)||prep.sources[0];
      prep.selectedKey=source?m04PrepKey(source):'';
    }
  } else errors.push(outputs[0].reason.message);
  if(outputs[1].status==='fulfilled'&&Array.isArray(outputs[1].value.generations)) prep.jobs=outputs[1].value.generations.filter(row=>m04PrepId(row?.generation_id));
  else errors.push(outputs[1].status==='rejected'?outputs[1].reason.message:'코드 준비 이력 응답을 확인하세요.');
  prep.loading=false;
  prep.message=errors.length?errors.join(' · '):prep.sources.length?'시나리오를 선택하고 코드 생성을 누르세요. 조회·새로고침으로 생성하거나 실행하지 않습니다.':'저장된 M03 시나리오가 없습니다. M03에서 먼저 시나리오를 보관하세요.';
  paintM04();
  const requested=new URLSearchParams(location.search).get('prep_generation_id');
  const id=requested||prep.jobs.find(m04PrepRunning)?.generation_id;
  if(id) await selectM04Preparation(id,true);
}
function selectM04PreparationSource(key) {
  const state=m04View,prep=state.preparation;
  if(state.busy||m04PrepBlocking()||state.executions.some(m04Running)||!prep.sources.some(row=>m04PrepKey(row)===key)) return;
  m04PrepReset();prep.selectedKey=key;prep.message='선택한 시나리오의 원본으로 새 코드를 준비할 수 있습니다.';m04PrepRemember(null);paintM04();
}
async function selectM04Preparation(id,restore=false) {
  const state=m04View,prep=state.preparation;
  if(state.busy||prep.busy||prep.loading) return;
  if(!id) {m04PrepReset();m04PrepRemember(null);prep.message='코드 준비 이력을 선택하세요.';paintM04();return;}
  if(!m04PrepId(id)||!prep.jobs.some(row=>row.generation_id===id)) {prep.message='현재 서버 세션의 코드 준비 이력을 선택하세요.';paintM04();return;}
  m04PrepReset();const token=m04RequestNumber,selection=prep.selection;
  prep.message='코드 준비 기록의 원본 연결을 확인하고 있습니다…';paintM04();
  try {
    const data=await m04Json('/api/development/m07/generations/'+id);
    if(!m04PrepCurrent(token,selection)) return;
    if(data.generation?.generation_id!==id) throw new Error('요청한 코드 준비 기록과 응답이 다릅니다.');
    // Explicit history selection (or refresh restoration) may select its verified source.
    const row=data.generation.cases?.length===1?data.generation.cases[0]:null;
    const source=prep.sources.find(source=>m04PrepMatches(row,source));
    if(source) prep.selectedKey=m04PrepKey(source);
    m04PrepAccept(data.generation);
    prep.message=(restore?'저장된 코드 준비 기록을 조회했습니다. ':'')+'원본을 확인하고 M04 고정을 별도로 선택하세요. 브라우저는 실행하지 않았습니다.';
    scheduleM04PreparationPoll(token,selection);
  } catch(error) {if(m04PrepCurrent(token,selection)) prep.message=error.message;}
  finally {if(m04PrepCurrent(token,selection)) paintM04();}
}
function paintM04Preparation() {
  const state=m04View,prep=state.preparation,source=m04PrepSource(),job=prep.job,row=job?.cases?.[0];
  const disabled=state.busy||prep.loading||m04PrepBlocking()||state.executions.some(m04Running);
  const prepared=job?.code_source==='PREPARED'||row?.code_source==='PREPARED';
  const fixed=!!(job&&row&&prep.fixed.has(job.generation_id+':'+row.case_id));
  document.querySelector('#m04-prep-scenario').innerHTML=prep.sources.length?prep.sources.map(item=>`<option value="${esc(m04PrepKey(item))}" ${m04PrepKey(item)===prep.selectedKey?'selected':''}>${esc(item.scenario_name||item.business_unit_id||item.scenario_id)} · ${esc(item.scenario_id)} · ${esc(item.m03_run_id)}${item.execution_ready!==true?' · 실행 조건 준비 필요':''}</option>`).join(''):'<option value="">저장된 시나리오 없음</option>';
  document.querySelector('#m04-prep-scenario').disabled=disabled||!prep.sources.length;
  document.querySelector('#m04-prep-generate').disabled=disabled||prep.jobs.some(m04PrepRunning)||!prep.context?.readiness?.configured||source?.execution_ready!==true||prep.providerState?.blocked===true;
  document.querySelector('#m04-prep-cancel').disabled=state.busy||prep.busy||!['QUEUED','GENERATING'].includes(job?.status);
  document.querySelector('#m04-prep-history').innerHTML=`<option value="">코드 준비 기록 선택</option>${prep.jobs.map(item=>`<option value="${esc(item.generation_id)}" ${item.generation_id===job?.generation_id?'selected':''}>${esc(item.started_at||item.generation_id)} · ${esc(m04PrepName(item.status))}${item.code_source==='PREPARED'?' · 외부 준비 코드':''}</option>`).join('')}`;
  document.querySelector('#m04-prep-history').disabled=state.busy||prep.busy||prep.loading;
  const provider=prep.providerState;
  document.querySelector('#m04-prep-provider').innerHTML=(provider?.blocked?`<p class="notice">공급자 제한${provider.http_status===429?' (HTTP429)':''}으로 코드 생성을 대기합니다.${provider.reason?' '+esc(provider.reason):''}${provider.error_code?' · '+esc(provider.error_code):''}${provider.next_eligible_at?' · 다음 요청 가능 시각 하한: '+esc(provider.next_eligible_at):' · 다음 요청 가능 시각 확인 필요'}. 새로고침으로 확인하세요. 자동 재요청하지 않습니다. 기존 고정 코드 실행은 별도입니다.</p>`:'')+(prep.jobs.some(m04PrepRunning)&&!m04PrepRunning(job)?'<p class="notice">다른 M07 작업이 진행 중이라 새 코드 생성을 대기합니다. 기존 고정 코드는 실행할 수 있습니다. <a href="/metrics/m07?mode=DEVELOPMENT">M07에서 진행 상태·중단 확인</a> · 새로고침으로 상태를 다시 확인하세요.</p>':'')+(!prep.loading&&!prep.context?.readiness?.configured?'<p class="subtitle">서버의 LLM 연결 설정이 필요합니다. 기존 고정 코드와 실행 이력은 계속 확인할 수 있습니다.</p>':'')+(source?.execution_ready!==true&&source?`<p class="notice">${esc(source.execution_notice||'이 시나리오의 실행 조건을 먼저 준비하세요.')} <a href="${esc('/metrics/m07?'+new URLSearchParams({mode:'DEVELOPMENT',m03_run_id:source.m03_run_id,scenario_id:source.scenario_id}))}">시나리오 실행 조건 설정</a></p>`:'');
  document.querySelector('#m04-prep-status').textContent=prep.message;
  document.querySelector('#m04-prep-cases').innerHTML=row?`<article class="m04-prep-case"><strong>${esc(row.scenario_name||row.scenario_id)}</strong><p class="run-meta">${esc(job.generation_id)} · ${esc(row.case_id)}<br>M03 원본 SHA-256: ${esc(row.source_scenario_sha256)}</p><p>${esc(m04PrepName(job.status))} · 코드 ${row.generation_status==='PASS'?'준비됨':'미준비'}${prepared?' · 외부 준비 코드 (이 화면에서 생성한 GPT 코드 아님)':''}${fixed?' · M04 고정 완료':''}</p>${row.error||job.error?`<p class="notice">${esc(row.error||job.error)}</p>`:''}${row.generation_status==='PASS'?`<button class="m04-code-button" type="button" data-m04-prep-code="${esc(row.case_id)}" ${prep.busy?'disabled':''} aria-expanded="${prep.openCode.has(row.case_id)}">${prep.openCode.has(row.case_id)?'원본 접기':'생성 원본 보기'}</button>`:''}${prep.openCode.has(row.case_id)?`<div class="m04-code"><p class="run-meta">코드 SHA-256: ${esc(row.code_sha256||'—')}<br>${prep.proof.has(row.case_id)?'화면 원본 SHA 확인 완료 · 편집 불가':'원본 확인 대기'}</p><pre>${esc(prep.code.get(row.case_id)??'원본을 불러오는 중…')}</pre></div>`:''}</article>`:'<p class="empty">코드를 생성하거나 준비 이력을 선택하면 원본을 확인할 수 있습니다. 코드 준비 실패는 M04 실행 실패로 계산하지 않습니다.</p>';
  document.querySelector('#m04-prep-fix').disabled=disabled||prep.jobs.some(m04PrepRunning)||job?.status!=='GENERATED'||row?.generation_status!=='PASS'||!m04PrepMatches(row)||!m04PrepHash(row?.code_sha256)||prep.proof.get(row?.case_id)!==row?.code_sha256||prepared||fixed;
}
async function generateM04Preparation() {
  const state=m04View,prep=state.preparation,source=m04PrepSource();
  if(state.busy||prep.loading||m04PrepBlocking()||prep.jobs.some(m04PrepRunning)||state.executions.some(m04Running)||!prep.context?.readiness?.configured||source?.execution_ready!==true||prep.providerState?.blocked===true) return;
  m04PrepReset();const token=m04RequestNumber,selection=prep.selection;
  prep.busy=true;prep.message='선택한 원본으로 코드 생성을 요청하고 있습니다. 브라우저 실행은 요청하지 않습니다…';paintM04();
  try {
    const data=await m04Json('/api/development/m07/generations',{scenario_refs:[{m03_run_id:source.m03_run_id,scenario_id:source.scenario_id,source_scenario_sha256:source.source_scenario_sha256}]});
    if(!m04PrepCurrent(token,selection)) return;
    m04PrepAccept(data.generation);prep.message='코드 생성 요청을 접수했습니다. 생성 후 원본을 확인하세요.';scheduleM04PreparationPoll(token,selection);
  } catch(error) {if(m04PrepCurrent(token,selection)) prep.message=error.message;}
  finally {if(m04PrepCurrent(token,selection)) {prep.busy=false;paintM04();}}
}
function scheduleM04PreparationPoll(token,selection,delay=1500) {
  clearTimeout(m04PrepPollTimer);
  if(!m04PrepCurrent(token,selection)||!m04PrepRunning(m04View.preparation.job)) return;
  const id=m04View.preparation.job.generation_id;
  m04PrepPollTimer=setTimeout(async()=>{
    if(!m04PrepCurrent(token,selection)||m04View.preparation.job?.generation_id!==id) return;
    const prep=m04View.preparation;
    try {
      const data=await m04Json('/api/development/m07/generations/'+id);
      if(!m04PrepCurrent(token,selection)||prep.job?.generation_id!==id) return;
      if(data.generation?.generation_id!==id) throw new Error('코드 준비 상태 응답이 일치하지 않습니다.');
      m04PrepAccept(data.generation);prep.message=m04PrepRunning(prep.job)?'코드를 준비하고 있습니다…':prep.job.status==='GENERATED'?'코드를 준비했습니다. 원본 확인 후 M04에 고정하세요. 아직 실행하지 않았습니다.':'코드 준비가 종료되었습니다. 상태를 확인하세요. M04 실행 점수와 별개입니다.';
      paintM04();scheduleM04PreparationPoll(token,selection);
    } catch(error) {if(m04PrepCurrent(token,selection)) {prep.message=error.message;paintM04();if(error.status!=='SESSION_EXPIRED') scheduleM04PreparationPoll(token,selection,5000);}}
  },delay);
}
async function readM04PreparationCode(id) {
  const state=m04View,prep=state.preparation,job=prep.job,row=job?.cases?.find(row=>row.case_id===id);
  if(state.busy||prep.busy||!m04PrepCaseId(id)||row?.generation_status!=='PASS'||!m04PrepMatches(row)) return;
  if(prep.openCode.has(id)) {prep.openCode.delete(id);paintM04();return;}
  if(prep.code.has(id)&&prep.proof.get(id)===row.code_sha256) {prep.openCode.add(id);paintM04();return;}
  const token=m04RequestNumber,selection=prep.selection;prep.busy=true;paintM04();
  try {
    const data=await m04Json(`/api/development/m07/generations/${job.generation_id}/codes/${id}`);
    if(!m04PrepCurrent(token,selection)) return;
    if(typeof data.code!=='string'||!data.code.length||data.case?.case_id!==id||!m04PrepMatches(data.case)||data.case.generation_status!=='PASS'||!m04PrepHash(row.code_sha256)||data.case.code_sha256!==row.code_sha256) throw new Error('생성 원본의 시나리오·사례·SHA 연결을 확인하세요.');
    if(typeof crypto==='undefined'||!crypto.subtle||typeof TextEncoder==='undefined') throw new Error('이 브라우저에서 원본 SHA 확인을 사용할 수 없습니다. 안전한 로컬 접속으로 다시 확인하세요.');
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(data.code));
    if(!m04PrepCurrent(token,selection)) return;
    if(prep.job?.generation_id!==job.generation_id||prep.job.cases?.[0]?.code_sha256!==row.code_sha256) throw new Error('코드 준비 상태가 변경되었습니다. 원본을 다시 확인하세요.');
    const hash=Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');
    if(hash!==row.code_sha256) throw new Error('화면 원본 코드와 보관 코드의 SHA-256이 다릅니다. 고정하지 않습니다.');
    prep.code.set(id,data.code);prep.proof.set(id,hash);prep.openCode.add(id);prep.message='원본 코드의 SHA-256을 확인했습니다. 내용을 검토한 뒤 M04 고정을 선택하세요.';
  } catch(error) {if(m04PrepCurrent(token,selection)) prep.message=error.message;}
  finally {if(m04PrepCurrent(token,selection)) {prep.busy=false;paintM04();}}
}
async function fixM04Preparation() {
  const state=m04View,prep=state.preparation,job=prep.job,row=job?.cases?.[0];
  if(state.busy||m04PrepBlocking()||prep.jobs.some(m04PrepRunning)||state.executions.some(m04Running)||job?.status!=='GENERATED'||job.code_source==='PREPARED'||row?.code_source==='PREPARED'||row?.generation_status!=='PASS'||!m04PrepMatches(row)||prep.proof.get(row.case_id)!==row.code_sha256||prep.fixed.has(job.generation_id+':'+row.case_id)) return;
  const token=m04RequestNumber,selection=prep.selection;prep.busy=true;prep.message='확인한 원본을 M04 실행 코드로 고정하고 있습니다. 실행은 별도입니다…';paintM04();
  try {
    const current=await m04Json('/api/development/m07/generations/'+job.generation_id);
    if(!m04PrepCurrent(token,selection)) return;
    if(current.generation?.generation_id!==job.generation_id) throw new Error('고정할 코드 준비 기록이 일치하지 않습니다.');
    m04PrepAccept(current.generation);
    const fresh=prep.job.cases[0];
    if(prep.job.status!=='GENERATED'||prep.job.code_source==='PREPARED'||fresh.code_source==='PREPARED'||fresh.generation_status!=='PASS'||fresh.code_sha256!==row.code_sha256||prep.proof.get(fresh.case_id)!==fresh.code_sha256||prep.fixed.has(job.generation_id+':'+fresh.case_id)) throw new Error('코드 상태 또는 원본 SHA가 변경됐거나 이미 고정됐습니다. 새로 확인하세요.');
    const data=await m04Json(`/api/development/m07/generations/${job.generation_id}/export-m04`,{case_ids:[fresh.case_id]});
    if(!m04PrepCurrent(token,selection)) return;
    const script=data.scripts?.length===1?data.scripts[0]:null;
    if(!script||!m04ScriptId(script.script_id)||script.source_m07_generation_id!==job.generation_id||script.source_m07_case_id!==fresh.case_id||!m04PrepMatches(script)||script.sha256!==fresh.code_sha256||script.business_step_required!==true) throw new Error('M04 고정 응답의 원본 코드·시나리오 연결을 확인하세요. 다시 고정하기 전에 새로고침하세요.');
    prep.fixed.add(job.generation_id+':'+fresh.case_id);
    const index=state.scripts.findIndex(item=>item.script_id===script.script_id);
    if(index<0) state.scripts.unshift(script);else state.scripts[index]=script;
    state.code.set(script.script_id,prep.code.get(fresh.case_id));state.selected.add(script.script_id);state.openCode.add(script.script_id);
    prep.message='원본을 M04에 고정하고 실행 대상으로 선택했습니다. 아래 선택 스크립트 실행을 눌러야 브라우저가 시작됩니다.';
    m04Status(state.selected.size>10?'실행 대상을 10건 이하로 선택하세요.':'웹에서 준비한 원본을 고정했습니다. 선택 스크립트 실행을 눌러 시작하세요.');
  } catch(error) {if(m04PrepCurrent(token,selection)) prep.message=error.message;}
  finally {if(m04PrepCurrent(token,selection)) {prep.busy=false;paintM04();}}
}
async function cancelM04Preparation() {
  const state=m04View,prep=state.preparation,job=prep.job;
  if(state.busy||prep.busy||!['QUEUED','GENERATING'].includes(job?.status)) return;
  // Invalidate an already in-flight GET before cancel, so it cannot revive an old state.
  const token=m04RequestNumber,selection=++prep.selection;prep.busy=true;clearTimeout(m04PrepPollTimer);prep.message='코드 생성 중단을 요청하고 있습니다…';paintM04();
  try {
    const data=await m04Json('/api/development/m07/generations/'+job.generation_id+'/cancel',{});
    if(!m04PrepCurrent(token,selection)) return;
    if(data.generation?.generation_id!==job.generation_id) throw new Error('중단 요청과 코드 준비 기록이 다릅니다.');
    m04PrepAccept(data.generation);prep.message='코드 생성 중단 상태를 확인하세요. 준비 중단은 M04 실행 실패로 계산하지 않습니다.';
  } catch(error) {if(m04PrepCurrent(token,selection)) prep.message=error.message;}
  finally {if(m04PrepCurrent(token,selection)) {prep.busy=false;paintM04();scheduleM04PreparationPoll(token,selection);}}
}
function m04ScriptAllowed(script) {
  return script.business_step_required===true&&script.execution_ready!==false&&(!m04View.locked||(script.scenario_id===m04View.scenario?.scenario_id&&script.source_m03_run_id===m04View.scenarioRun));
}
function paintM04() {
  const state=m04View,job=state.execution,active=m04Running(job),blocked=state.busy||m04PrepBlocking()||state.executions.some(m04Running);
  const ready=state.readiness?.selenium&&(state.readiness?.chrome||state.readiness?.edge);
  document.querySelector('#m04-ready').textContent=state.readiness?.message||(state.readiness?(ready?'Selenium · 브라우저 준비 완료':'Selenium · 브라우저 실행 환경 확인 필요'):'확인 중…');
  document.querySelector('#m04-selected-count').textContent=state.selected.size+'건';
  document.querySelector('#m04-visible-browser').checked=state.visibleBrowser;
  document.querySelector('#m04-visible-browser').disabled=blocked;
  const scenario=state.scenario,isSynthetic=state.scenarioSynthetic||scenario?.synthetic===true||scenario?.generator_mode==='MOCK';
  document.querySelector('#m04-scenario').innerHTML=scenario?`<div class="m04-scenario-box"><p class="subtitle"><strong>${esc(scenario.scenario_name||scenario.business_unit_id||scenario.scenario_id)}</strong>${isSynthetic?' <span class="badge warning">샘플 시나리오</span>':''}</p><p class="run-meta">${esc(scenario.scenario_id)} · ${esc(state.scenarioRun)}</p>${!state.locked&&state.scenarios.length>1?`<label>등록할 시나리오<select id="m04-scenario-select" ${blocked?'disabled':''}>${state.scenarios.map(row=>`<option value="${esc(row.scenario_id)}" ${row.scenario_id===scenario.scenario_id?'selected':''}>${esc(row.scenario_name||row.business_unit_id||row.scenario_id)}</option>`).join('')}</select></label>`:''}<p class="subtitle">${state.scripts.some(row=>row.scenario_id===scenario.scenario_id&&row.source_m03_run_id===state.scenarioRun)?'저장된 시나리오에 연결된 실행 스크립트를 확인하세요.':'이 시나리오에 연결된 실행 스크립트를 등록하세요.'}</p><a class="download" href="${esc('/metrics/m07?'+new URLSearchParams({mode:'DEVELOPMENT',m03_run_id:state.scenarioRun,scenario_id:scenario.scenario_id}))}">시나리오 실행 조건 설정</a></div>`:'<p class="subtitle">스크립트를 등록하려면 M03에서 시나리오를 먼저 저장하세요.</p>';
  document.querySelector('#m04-register').disabled=blocked||!scenario;
  document.querySelector('#m04-file').disabled=blocked||!scenario;
  document.querySelector('#m04-refresh').disabled=state.busy||state.preparation.busy;
  document.querySelector('#m04-start').disabled=blocked||!ready||state.selected.size<1||state.selected.size>10;
  document.querySelector('#m04-cancel').disabled=state.busy||!active;
  document.querySelector('#m04-history').disabled=state.busy;
  document.querySelector('#m04-scripts').innerHTML=state.scripts.length?`<div class="m04-script-list">${state.scripts.map(script=>{
    const allowed=m04ScriptAllowed(script),open=state.openCode.has(script.script_id),code=state.code.get(script.script_id);
    return `<article class="m04-script"><label class="m04-script-select"><input type="checkbox" data-script-id="${esc(script.script_id)}" ${state.selected.has(script.script_id)?'checked':''} ${blocked||!allowed?'disabled':''}><span><strong>${esc(script.filename)}</strong><small>${esc(script.scenario_name||script.scenario_id)}${script.source_kind==='M01_OBSERVED_REPLAY'?' · M01 수집 동작':''}${script.source_synthetic?' · 샘플 시나리오 연결':''}${script.business_step_required!==true?' · 기존 원시 기록용 코드':script.execution_ready===false?' · '+esc(script.execution_notice||'실행 조건 준비 필요'):!allowed?' · 다른 시나리오':''}</small></span></label><button class="m04-code-button" type="button" data-script-code="${esc(script.script_id)}" aria-expanded="${open}">${open?'코드 접기':'코드 보기'}</button>${open?`<div class="m04-code"><p class="run-meta">고정 시각: ${esc(script.fixed_at)}<br>SHA-256: ${esc(script.sha256)}</p><pre>${esc(code??'원본 코드를 불러오는 중…')}</pre></div>`:''}</article>`;
  }).join('')}</div>`:'<p class="empty">등록된 실행 스크립트가 없습니다.</p>';
  const resultIds=[...new Set([state.externalRunId,state.metric.latest?.metric_id==='M04'&&state.metric.latest?.run_mode==='DEVELOPMENT'?state.metric.latest.run_id:null].filter(m04ResultId))];
  document.querySelector('#m04-history').innerHTML=`<option value="">실행 이력 선택</option>${resultIds.map(id=>`<option value="result:${id}" ${state.resultSource==='external'&&state.externalRunId===id?'selected':''}>API 접수 결과 · ${esc(id)}</option>`).join('')}${state.executions.map(row=>`<option value="${esc(row.execution_id)}" ${state.resultSource==='execution'&&row.execution_id===job?.execution_id?'selected':''}>${esc(row.started_at||row.created_at||row.execution_id)} · ${esc(m04CaseName(row.status))}</option>`).join('')}`;
  paintM04M01();
  paintM04Cu02();
  paintM04Preparation();
  paintM04Execution();
}
function paintM04Execution() {
  if(m04View.resultSource==='external') {paintM04Result();return;}
  const job=m04View.execution,cases=Array.isArray(job?.cases)?job.cases:[],result=job?.status==='COMPLETED'?job.result:null,counts=job?.counts||{};
  const done=cases.filter(row=>!['PENDING','RUNNING'].includes(row.status)).length;
  document.querySelector('#m04-progress').max=Math.max(1,cases.length);document.querySelector('#m04-progress').value=done;
  document.querySelector('#m04-progress-label').textContent=job?`${m04CaseName(job.status)} · ${done}/${cases.length}건${job.error?' · '+job.error:''}`:'실행 기록 대기';
  document.querySelector('#m04-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2>${result?.evidence_file?`<a class="download" href="${esc(m04Artifact(job.execution_id,'report.json'))}" download>실행 보고서 ↓</a>`:''}</div><div class="result-grid"><div><label>자동 실행 성공률</label><strong class="large-score">${score(result?.score,'M04')}</strong></div><div><label>정상 완료 테스트</label><strong>${esc(counts.successful_execution_count??'—')}</strong></div><div><label>전체 실행 테스트</label><strong>${esc(counts.total_execution_count??'—')}</strong></div><div><label>실행 상태</label><strong>${esc(job?m04CaseName(job.status):'미실행')}</strong></div></div><p class="subtitle">정상 완료 테스트 수 / 전체 자동 실행 테스트 수 × 100 · 실패는 분모에 포함합니다.</p>${m04Cu02Summary(job,cases,result)}${result?`<p class="run-meta">${esc(result.run_id)} · DEVELOPMENT · 공식 시험성적 아님</p>`:'<p class="subtitle">실행과 평가가 완료되면 성공률을 표시합니다.</p>'}`;
  document.querySelector('#m04-cases').innerHTML=cases.length?`<p class="run-meta">실행 ID: ${esc(job.execution_id)}</p><div class="table-scroll"><table><thead><tr><th>스크립트</th><th>시나리오</th><th>상태·업무 단계</th><th>실행 시각·소요 시간</th><th>반환 코드</th></tr></thead><tbody>${cases.map(row=>`<tr><td>${esc(row.script_name||row.script_id)}</td><td>${esc(row.scenario_id)}</td><td><span class="badge ${row.status==='PASS'?'pass':['FAIL','ERROR','TIMEOUT'].includes(row.status)?'fail':'neutral'}">${esc(m04CaseName(row.status))}</span>${row.error_message||row.error?`<p>${esc(row.error_message||row.error)}</p>`:''}${m04Cu02Expectation(row,job.cu02_evaluation)}${m04StepDetails(row)}</td><td><span>${esc(row.started_at||'—')}</span><br><span>${esc(row.completed_at||'—')}</span><br>${row.duration_ms==null?'—':esc(row.duration_ms)+' ms'}</td><td>${esc(row.returncode??'—')}</td></tr>`).join('')}</tbody></table></div>`:'<p class="empty">실행하면 스크립트별 상태와 업무 단계가 표시됩니다.</p>';
  document.querySelector('#m04-logs').textContent=Array.isArray(job?.logs)&&job.logs.length?job.logs.map(row=>`${row.time||''}${row.case_id?' ['+row.case_id+']':''} ${row.message||''}`).join('\n'):'실행 로그가 없습니다.';
  document.querySelector('#m04-downloads').innerHTML=job?['report.json','log.jsonl','steps.csv','scripts.zip','screenshots.zip'].map((name,index)=>`<a class="download" href="${m04Artifact(job.execution_id,name)}" download>${['실행 보고서','전체 로그','단계 기록 CSV','고정 스크립트 원본','마스킹된 실행 화면'][index]} ↓</a>`).join(''):'';
}
function m04Cu02Summary(job,cases,result) {
  const evaluation=job?.cu02_evaluation;
  if(!evaluation) return '';
  if(!m04Cu02Evaluation(evaluation,cases)) return '<p class="notice">CU02 10건 평가와 실행 항목의 연결을 확인하세요. 목표 달성 여부를 판정할 수 없습니다.</p>';
  const passed=cases.filter(row=>row.status==='PASS').length,failed=cases.filter(row=>['FAIL','ERROR','TIMEOUT','SKIPPED'].includes(row.status)).length;
  const running=cases.filter(row=>row.status==='RUNNING').length,pending=10-passed-failed-running;
  const confirmed=job.status==='COMPLETED'&&passed+failed===10&&result&&Number.isFinite(result.score)
    &&job.counts?.total_execution_count===10&&job.counts?.successful_execution_count===passed&&Math.abs(result.score-passed*10)<1e-8;
  const verdict=confirmed?`<span class="badge ${passed>=9?'pass':'fail'}">${passed>=9?'개발 목표 달성':'개발 목표 미달'}</span>`
    :`<span class="badge neutral">${m04Running(job)?'집계 중':'판정 확인 필요'}</span>`;
  return `<div class="m04-cu02-summary"><div class="panel-heading"><h3>CU02 일정 등록 · 10건 평가</h3>${verdict}</div>
    <p class="subtitle">일정 1건을 등록하고 재조회까지 확인하면 평가 1건입니다. 업무 단계 5개를 5건으로 집계하지 않습니다.</p>
    <div class="m04-cu02-counts"><div><label>전체</label><strong>10건</strong></div><div><label>성공</label><strong>${passed}건</strong></div><div><label>실패·오류·미실행</label><strong>${failed}건</strong></div><div><label>실행 중</label><strong>${running}건</strong></div><div><label>대기·확인 필요</label><strong>${pending}건</strong></div></div>
    <p class="subtitle">목표 90% · 9/10건 이상 성공${confirmed?' · 최종 성공률 '+esc(score(result.score,'M04')):' · 10건 실행과 결과 저장이 완료되면 최종 판정합니다.'}</p><p class="run-meta">평가 ID: ${esc(evaluation.evaluation_id)}</p></div>`;
}
function m04Cu02Expectation(row,evaluation) {
  if(!evaluation||row.cu02_evaluation_id!==evaluation.evaluation_id||!Array.isArray(evaluation.cases)) return '';
  const fixed=evaluation.cases.find(item=>item.case_id===row.case_id&&item.script_id===row.script_id),expected=fixed?.expected;
  if(!expected||!['date','title','description'].every(key=>typeof expected[key]==='string')) return '<p class="notice">이 항목의 사전 기대값을 확인할 수 없습니다.</p>';
  const steps=Array.isArray(row.steps)?row.steps:[],before=steps.find(step=>step.sequence===2),after=steps.find(step=>step.sequence===5);
  const comparison=(step,pass)=>!step||['PENDING','RUNNING'].includes(step.status)?'확인 대기':step.status==='PASS'?pass:'확인 실패';
  return `<div class="m04-cu02-expected"><strong>평가 ${esc(row.cu02_case_number)} · 사전 기대값</strong><dl><dt>날짜</dt><dd>${esc(expected.date)}</dd><dt>제목</dt><dd>${esc(expected.title)}</dd><dt>내용</dt><dd>${expected.description?esc(expected.description):'비어 있음'}</dd></dl>
    <p>실행 전 빈 제목·내용: ${comparison(before,'빈 상태 확인')}</p><p>저장 후 재조회: ${comparison(after,'기대 제목·내용과 일치')}</p></div>`;
}
function paintM04Result() {
  const saved=m04View.externalResult,result=saved?.result,raw=saved?.payload,counts=raw?.counts||{},cases=Array.isArray(raw?.cases)?raw.cases:[];
  const provided=value=>value==null?'미제공':typeof value==='object'?JSON.stringify(value,null,2):String(value);
  const logs=raw?.details?.logs??raw?.evidence?.logs;
  document.querySelector('#m04-progress').max=1;document.querySelector('#m04-progress').value=result?1:0;
  document.querySelector('#m04-progress-label').textContent=result?'API 결과 접수 완료 · 이 화면에서 실행한 기록과 구분합니다.':m04View.externalError?'접수 결과 확인 실패':'API 접수 결과를 불러오는 중…';
  document.querySelector('#m04-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2></div><div class="result-grid"><div><label>자동 실행 성공률</label><strong class="large-score">${score(result?.score,'M04')}</strong></div><div><label>정상 완료 테스트</label><strong>${esc(counts.successful_execution_count??counts.passed_execution_count??'—')}</strong></div><div><label>전체 실행 테스트</label><strong>${esc(counts.total_execution_count??'—')}</strong></div><div><label>결과 출처</label><strong>외부 API 접수</strong></div></div><p class="subtitle">정상 완료 테스트 수 / 전체 자동 실행 테스트 수 × 100 · 실패는 분모에 포함합니다.</p>${result?`<p class="run-meta">${esc(result.run_id)} · DEVELOPMENT · 공식 시험성적 아님</p><p class="run-meta">데이터셋: ${esc(result.dataset_id)} · 원실행 ID: ${esc(raw.external_run_id)}<br>출처: ${esc(raw.source_module)} · ${esc(raw.source_version)} · 제출 시각: ${esc(raw.submitted_at)}</p>`:''}`;
  document.querySelector('#m04-cases').innerHTML=cases.length?`<div class="table-scroll"><table><thead><tr><th>케이스</th><th>시나리오</th><th>제공 상태</th><th>실패 단계</th><th>제공 근거</th></tr></thead><tbody>${cases.map(row=>`<tr><td>${esc(row.case_id)}</td><td>${esc(provided(row.scenario_id))}</td><td>${esc(m04CaseName(row.status))}</td><td>${esc(provided(row.failed_step))}</td><td><details><summary>접수 케이스 원문</summary><pre>${esc(JSON.stringify(row,null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:result?'<p class="empty">개별 케이스는 제공되지 않았습니다. 접수된 집계 건수만 표시합니다.</p>':'<p class="empty">접수 원본 확인 전입니다.</p>';
  document.querySelector('#m04-logs').textContent=logs==null?'실행 로그 미제공':provided(logs);
  const links=result?['result.json','evidence.csv','received_payload.json','run_manifest.json'].map((name,index)=>`<a class="download" href="${m04ResultArtifact(result.run_id,name)}" download>${['접수 결과','판정 근거 CSV','접수 원본 JSON','실행 메타데이터'][index]} ↓</a>`).join(''):'';
  document.querySelector('#m04-downloads').innerHTML=links+(raw&&Object.hasOwn(raw,'evidence')?`<details><summary>제공 evidence</summary><pre>${esc(JSON.stringify(raw.evidence,null,2))}</pre></details>`:'');
}
async function selectM04Result(id) {
  if(m04View.busy) return false;
  if(!m04ResultId(id)) {m04Status('M04 접수 결과 주소를 확인하세요.');return false;}
  const token=m04RequestNumber,selection=++m04View.selection;
  m04View.resultSource='external';m04View.externalRunId=id;m04View.externalResult=null;m04View.externalError=null;paintM04();scheduleM04Poll(token);
  m04Status('API 접수 결과와 원본을 불러오고 있습니다…');
  try {
    const result=await m04Json(m04ResultArtifact(id));
    if(!m04Active(token)||selection!==m04View.selection) return false;
    if(result.metric_id!=='M04'||result.run_mode!=='DEVELOPMENT'||result.run_id!==id||result.status!=='COMPLETED'||(result.score!==null&&(!Number.isFinite(result.score)||result.score<0||result.score>100))) throw new Error('저장된 M04 DEVELOPMENT 접수 결과를 확인하세요.');
    const payload=await m04Json(m04ResultArtifact(id,'received_payload.json'));
    if(!m04Active(token)||selection!==m04View.selection) return false;
    const provenance=result.provenance||{},raw=result.details?.raw_counts;
    const counts=value=>value&&typeof value==='object'&&!Array.isArray(value)?JSON.stringify(Object.keys(value).sort().map(key=>[key,value[key]])):null;
    if(payload.run_mode!=='DEVELOPMENT'||payload.dataset_id!==result.dataset_id||['external_run_id','source_module','source_version','submitted_at'].some(key=>typeof payload[key]!=='string'||!payload[key]||payload[key]!==provenance[key])||!counts(raw)||counts(raw)!==counts(payload.counts)||result.sample_count!==payload.counts.total_execution_count||(payload.cases!==undefined&&(!Array.isArray(payload.cases)||payload.cases.some(row=>!row||typeof row!=='object'||Array.isArray(row))))) throw new Error('접수 결과와 보관 원본의 연결을 확인하세요.');
    m04View.externalResult={result,payload};m04RememberResult(id);paintM04();m04Status('외부 API 접수 결과를 불러왔습니다. 별도 실행을 요청하지 않았습니다.');return true;
  } catch(error) {
    if(m04Active(token)&&selection===m04View.selection) {m04View.externalError=error.message;paintM04();m04Status(error.message);}
    return false;
  }
}
function m04ScreenDetails(row) {
  const id=row.execution_id||m04View?.execution?.execution_id,caseId=row.case_id;
  const valid=m04ExecutionId(id)&&/^CASE-[0-9]{3}$/.test(caseId||'');
  const records=Array.isArray(row.screenshots)?row.screenshots:[];
  return `<details class="m04-screenshots"><summary>실행 전·후 화면</summary><p class="subtitle">문자·이미지가 마스킹된 실행 화면입니다. 판정은 독립 DOM/API 검사로 확인하며 이미지 일치 점수를 계산하지 않습니다.</p><div class="m04-screenshot-pair">${['before','after'].map((phase,index)=>{
    const record=records.find(item=>item.phase===phase),captured=valid&&record?.status==='CAPTURED'&&record?.file===phase+'.png'&&record?.policy==='text-and-images-masked-v1';
    const url=captured?`/api/development/m04/executions/${id}/screenshots/${caseId}/${phase}.png`:null;
    const cu02=captured&&row.source_kind==='CU02_SCHEDULE_REGISTRATION'&&row.workflow_id==='CU02'
      &&record.capture_mode==='EXPLICIT_BUSINESS_CHECKPOINT'&&record.business_step_order===(index?5:2);
    const caption=`실행 ${index?'후':'전'}${cu02?index?' · 저장값 재조회 화면':' · 빈 신규등록 화면':''}`;
    return `<article><strong>${caption}</strong>${url?`<a href="${url}" target="_blank" rel="noopener"><img src="${url}" loading="lazy" alt="문자와 이미지가 마스킹된 ${caption}"></a><p class="run-meta">${esc(record.captured_at||'')}</p>`:`<p class="subtitle">캡처되지 않음${record?.reason?' · '+esc(record.reason):' · 저장된 화면 근거 없음'}</p>`}</article>`;
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
  if(!file||state.busy||m04PrepBlocking()||state.executions.some(m04Running)||!state.scenario) return;
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
  if(m04View.resultSource==='external'||m04View.execution?.execution_id!==job.execution_id) ++m04View.selection;
  m04View.execution=job;m04View.resultSource='execution';
  const index=m04View.executions.findIndex(row=>row.execution_id===job.execution_id);
  if(index<0) m04View.executions.unshift(job);else m04View.executions[index]=job;
  m04Remember(job.execution_id);paintM04();
}
async function startM04() {
  const state=m04View;
  if(state.busy||m04PrepBlocking()||state.executions.some(m04Running)||!state.readiness?.selenium||!(state.readiness?.chrome||state.readiness?.edge)) return;
  const ids=[...state.selected];
  if(!ids.length||ids.length>10||ids.some(id=>!state.scripts.some(row=>row.script_id===id&&m04ScriptAllowed(row)))) {m04Status('실행할 스크립트를 1~10건 선택하세요.');return;}
  const token=m04RequestNumber;++state.selection;state.busy=true;clearTimeout(m04PollTimer);paintM04();m04Status('고정한 스크립트 실행을 요청하고 있습니다…');
  try {
    const data=await m04Json('/api/development/m04/executions',{script_ids:ids,...(state.visibleBrowser?{visible_browser:true,action_delay_ms:700,keep_open_seconds:15}:{})});
    if(!m04Active(token)) return;
    acceptM04Execution(data.execution);scheduleM04Poll(token);m04Status('실행 요청을 접수했습니다. 진행 상태와 로그를 확인하세요.');
  } catch(error) {if(m04Active(token)) m04Status(error.message);}
  finally {if(m04Active(token)) {state.busy=false;paintM04();}}
}
async function selectM04Execution(id) {
  if(!m04ExecutionId(id)||m04View.busy) return;
  const token=m04RequestNumber,selection=++m04View.selection;scheduleM04Poll(token);
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
  if(!m04Active(token)) return;
  const revision=++m04View.pollRevision;
  const running=m04Running(m04View.execution)?m04View.execution:m04View.executions.find(m04Running);
  if(!running) return;
  const id=running.execution_id;
  m04PollTimer=setTimeout(async()=>{
    if(!m04Active(token)||revision!==m04View.pollRevision) return;
    try {
      const data=await m04Json('/api/development/m04/executions/'+id);
      if(!m04Active(token)||revision!==m04View.pollRevision) return;
      if(data.execution?.execution_id!==id) throw new Error('실행 상태 응답이 일치하지 않습니다.');
      const state=m04View,index=state.executions.findIndex(row=>row.execution_id===id);
      if(index<0) return;
      state.executions[index]=data.execution;
      if(state.execution?.execution_id===id) state.execution=data.execution;
      paintM04();
      if(state.resultSource==='execution'&&state.execution?.execution_id===id&&!m04Running(data.execution)) m04Status(data.execution.status==='COMPLETED'?'실행과 결과 저장을 완료했습니다.':'실행이 종료되었습니다. 상태와 로그를 확인하세요.');
      scheduleM04Poll(token);
    } catch(error) {if(error.status!=='SESSION_EXPIRED'&&m04Active(token)&&revision===m04View.pollRevision) {if(m04View.resultSource==='execution'&&m04View.execution?.execution_id===id) m04Status(error.message);scheduleM04Poll(token,5000);}}
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
