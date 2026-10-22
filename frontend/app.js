const labels = {M01:'수집 정확도',M02:'프로세스맵 정확도 및 완전성',M03:'테스트 시나리오 자동생성률',M04:'자동 실행 성공률',M05:'AI 데이터 정제 F1 Score',M06:'워크플로우 클러스터링 품질',M07:'LLM 생성 코드 유효성 및 정확도'};
const descriptions = {M01:'5개 시나리오 · 2회 실행 · 필수 이벤트 100건',M02:'TD-03 업무 20종 · Ground Truth 5종 사후 비교',M03:'M02와 동일 TD-03 · 20개 업무당 1회 생성',M04:'시험 전 고정한 Selenium/Python 20건 · 각 1회 실행',M05:'학습·개발 미사용 held-out · KEEP 100건 / REMOVE 100건',M06:'OFFICIAL: 승인 V6.2 563×128 embedding · 12개 군집 DBI',M07:'구문·실행 모두 PASS / 실제 생성 코드 수 × 100'};
const app = document.querySelector('#app');
const requestedMode = new URLSearchParams(location.search).get('mode');
const mode = ['OFFICIAL','DEVELOPMENT'].includes(requestedMode) ? requestedMode : 'REFERENCE';
const dev = mode === 'DEVELOPMENT';
const nonofficial = mode !== 'OFFICIAL';
const ref = mode === 'REFERENCE';
let catalog;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link = path => `${path}?mode=${mode}`;
const score = (value,id) => value == null ? '—' : `${Number(value).toFixed(['M05','M06'].includes(id) ? 4 : 2)}${['M05','M06'].includes(id) ? '' : '%'}`;
const statuses = {OFFICIAL_M06_BUNDLE_MISSING:'공식 M06 측정 bundle 없음',BLOCKED:'실행 조건 미충족',INSUFFICIENT_DATA_FOR_CONSENSUS:'Consensus 데이터 부족',NOT_CONFIGURED:'모델/모듈 미설정',WAITING_FOR_DATA:'공식 평가 데이터 대기 중',REFERENCE_READY:'Reference 실행 준비',READY:'공식 평가 준비',RUNNING:'실행 중',COMPLETED:'측정 완료',REFERENCE_PARTIAL:'Reference 부분 동작',EXTERNAL_MODULE_PENDING:'외부 모듈 연동 예정',ERROR:'오류'};
function badge(r) {
  if (!r) return '<span class="badge neutral">미실행</span>';
  if (dev && r.metric_id === 'M01') return '<span class="badge neutral">CSV 개발 평가 가능</span>';
  if (!ref && r.run_mode === 'OFFICIAL' && r.status === 'COMPLETED' && typeof r.official_pass === 'boolean') return `<span class="badge ${r.official_pass ? 'pass':'fail'}">${r.official_pass ? 'PASS':'FAIL'}</span>`;
  return `<span class="badge ${r.status === 'COMPLETED' ? 'neutral':'warning'}">${esc(r.status === 'READY' && dev ? '개발 평가 실행 가능' : statuses[r.status] || r.status)}</span>`;
}
function banner(datasetLabel='current_site_dev_01') {
  return `<div class="mode-switch" aria-label="평가 모드"><a class="${ref?'selected':''}" href="${location.pathname}?mode=REFERENCE">REFERENCE</a><a class="${mode==='OFFICIAL'?'selected':''}" href="${location.pathname}?mode=OFFICIAL">OFFICIAL</a><a class="${dev?'selected':''}" href="${location.pathname}?mode=DEVELOPMENT">DEVELOPMENT</a></div><p class="notice">${dev?'DEVELOPMENT DATASET · '+esc(datasetLabel)+' · 공식 시험성적 아님':ref?'V6.2 Historical Reference를 사용한 평가 프로그램 검증 모드입니다. 공식 시험성적이 아닙니다.':'OFFICIAL · 공식 dataset manifest, 입력 해시 및 필요한 모델/모듈 연결이 있어야 실행할 수 있습니다.'}</p>`;
}
function render() {
  const id = location.pathname.match(/\/metrics\/(m0[1-7])/i)?.[1].toUpperCase();
  document.querySelector('#navigation').innerHTML = catalog.metrics.map(m => `<a href="${link('/metrics/'+m.metric_id.toLowerCase())}" ${id === m.metric_id ? 'aria-current="page"' : ''}><span>${m.metric_id}</span>${labels[m.metric_id]}</a>`).join('');
  document.querySelector('.overview-link').href = link('/');
  document.querySelector('.brand').href = link('/');
  document.querySelector('.overview-link').classList.toggle('active', !id);
  document.querySelector('#breadcrumb').textContent = `${mode} / ${id ? id+' · '+labels[id] : '성능평가 대시보드'}`;
  if (id) return renderMetric(catalog.metrics.find(m => m.metric_id === id));
  app.innerHTML = `${banner()}<section class="page-heading"><div><p class="eyebrow">KTL PERFORMANCE EVALUATION</p><h1>성능평가 대시보드</h1><p class="subtitle">${dev?'Development Result · 실제 개발 데이터 연결 시험':ref?'Reference Result · 실제 보관 산출물 기반 검증':'공식 평가 데이터 및 연동 준비 상태'}</p></div></section><section class="cards">${catalog.metrics.map(m=>`<a class="metric-card" href="${link('/metrics/'+m.metric_id.toLowerCase())}"><div class="card-top"><span class="metric-id">${m.metric_id}</span>${badge(m)}</div><h3>${labels[m.metric_id]}</h3><p class="english">${esc(m.metric_name)}</p><p class="description">${esc(m.details.missing?.join(' · ') || (dev ? 'current_site_dev_01 · 개발 평가' : ref && m.metric_id==='M02' ? 'Legacy GT 7종 · 공식 KTL Ground Truth 아님' : descriptions[m.metric_id]))}</p><div class="card-bottom"><strong>${score(m.latest?.score,m.metric_id)}</strong><span>${m.latest?'최근 실행 결과':'미실행'} ↗</span></div></a>`).join('')}</section><section class="model-note"><div><strong>V6.2 승인 기준값 · Frozen</strong><p>32,273 이벤트 · 5,167 세그먼트 · 563 워크플로우 · 1,619 프로세스 인스턴스 · 12 모델</p><small>Ground Truth는 평가에만 사용합니다. 현재 상태와 최근 실행 결과는 별도로 표시합니다.</small></div></section>`;
}
function table(rows) {
  if (!rows?.length) return '';
  const fields = [...new Set(rows.flatMap(Object.keys))];
  return `<div class="table-scroll"><table><thead><tr>${fields.map(f=>`<th>${esc(f)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${fields.map(f=>`<td>${esc(typeof r[f]==='object'?JSON.stringify(r[f]):r[f])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function detailView(d) {
  const fields = {process_model_count:'Process models',process_instance_count:'Process instances',ground_truth_count:'Ground Truth 종류',accuracy:'Accuracy (%)',completeness:'Completeness (%)',correctly_mapped:'직접 일치 절차',evaluated_procedures:'평가 절차',defined_required:'필수 절차',workflow_count:'Workflow count',cluster_count:'Cluster count',consensus_k:'Consensus K',precision:'Precision',recall:'Recall',f1:'F1',tp:'TP',fp:'FP',fn:'FN',tn:'TN'};
  return `${d.ground_truth_name?`<p class="notice">${esc(d.ground_truth_name)} · ${esc(d.ground_truth_notice)}</p>`:''}${d.missing?.length?`<p class="notice">연결/자료 대기: ${esc(d.missing.join(' · '))}</p>`:''}<div class="detail-stats">${Object.entries(fields).filter(([k])=>d[k]!=null).map(([k,v])=>`<div><label>${v}</label><strong>${esc(typeof d[k]==='number'&&!Number.isInteger(d[k])?d[k].toFixed(4):d[k])}</strong></div>`).join('')}</div>${d.selection_method?`<p class="subtitle">${esc(d.selection_method)}</p>`:''}${d.feature_space?`<p class="subtitle">${esc(d.feature_space)} · DBI는 검증된 feature matrix 확보 후 계산합니다.</p>`:''}${d.preview_only?'<p class="notice">Scenario Generator 입력 미리보기입니다. 생성된 시나리오나 공식 20개 업무 단위가 아닙니다.</p>':''}${table(d.rows)}${d.input_preview?`<details><summary>Business Unit 입력 JSON 미리보기</summary><pre>${esc(JSON.stringify(d.input_preview,null,2))}</pre></details>`:''}`;
}
function renderMetric(m) {
  if (dev && m.metric_id === 'M01') return renderM01Csv(m);
  const r=m.latest;
  document.title=`${mode} · ${m.metric_id} · Rainbow`;
  app.innerHTML=`${banner()}<a class="back" href="${link('/')}">← 전체 평가</a><section class="page-heading"><div><p class="eyebrow">${m.metric_id} / ${mode}</p><h1>${labels[m.metric_id]}</h1><p class="subtitle">${esc(m.metric_name)}</p></div>${badge(m)}</section><section class="evaluation-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2></div><div class="dataset-grid"><div><label>테스트 데이터셋</label><code>${esc(m.dataset || '공식 평가 데이터 대기 중')}</code></div><div><label>${dev?'개발 데이터 입력 수':ref?'Reference 케이스 / 입력 수':'공식 설계 케이스 수'}</label><strong>${dev?(m.latest?.sample_count??'—'):ref?(m.details.ground_truth_count??m.details.workflow_count??m.details.process_model_count??'—'):(m.expected_sample_count??'실제 생성 코드 수')}</strong></div><div><label>${ref?'Target Reference':'Target'}</label><strong>${m.target==null?'미설정':esc(m.operator)+' '+score(m.target,m.metric_id)}</strong></div></div>${detailView(m.details)}${m.error?`<p class="notice">${esc(m.error)}</p>`:''}<div class="run-row"><p>실행 또는 준비 상태 확인 결과를 근거 파일로 저장합니다.</p><button id="run">${dev && ['M02','M06'].includes(m.metric_id)?'개발 모델 및 M02/M06 실행':['READY','REFERENCE_READY'].includes(m.status)?'평가 실행':'준비 상태 기록'} →</button></div></section><p id="run-status" role="status"></p><section class="result-panel"><div class="panel-heading"><h2>${dev?'DEVELOPMENT RESULT':ref?'Reference Result':'공식 실행 결과'}</h2>${r?`<a class="download" href="${esc(r.evidence_file)}" download>CSV 다운로드 ↓</a>`:''}</div><div class="result-grid"><div><label>${ref?'Reference Score':'Measured Score'}</label><strong class="large-score">${score(r?.score,m.metric_id)}</strong></div><div><label>실행 시 목표값</label><strong>${r?.target==null?'—':esc(r.operator)+' '+score(r.target,m.metric_id)}</strong></div><div><label>${nonofficial?'Threshold Met (비공식)':'공식 판정'}</label><strong>${nonofficial?(r?.threshold_met==null?'—':r.threshold_met?'YES':'NO'):''}</strong>${nonofficial?'':badge(r)}</div><div><label>실행 상태</label>${badge(r)}</div></div>${r?`<p class="run-meta">${esc(r.run_id)} · ${esc(r.completed_at)}</p>${r.error?`<p class="notice">${esc(r.error)}</p>`:''}${detailView(r.details)}<a class="download" href="${esc(r.manifest_file)}">Run manifest</a><details><summary>결과 및 입력 해시</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`:'<p class="empty">아직 이 모드의 실행 기록이 없습니다.</p>'}</section>`;
  document.querySelector('#run').addEventListener('click',()=>run(m.metric_id));
}
let csvReport = null;
let prodReport = null;
let csvRequestNumber = 0;
let prodRequestNumber = 0;
let csvDatasetListRequestNumber = 0;
let truthListRequestNumber = 0;
let truthDetailRequestNumber = 0;
let truthDetailBusy = false;
let m01TruthReport = null;
let comparisonRequestNumber = 0;
let comparisonVerificationRequestNumber = 0;
let comparisonBusy = false;
function m01ComparisonUrl(comparisonId) {
  if(typeof history==='undefined' || typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);
  if(comparisonId) query.set('comparison_id',comparisonId);
  else query.delete('comparison_id');
  history.replaceState(null,'',`${location.pathname}?${query.toString()}`);
}
function m01ComparisonPanel() {
  return `<details class="m01-input-card" id="m01-truth-card"><summary><h2>저장된 정답 이벤트</h2></summary><div class="m01-card-content"><p class="subtitle">선택한 시험 시나리오의 사전 정답입니다. 시험 중에는 정답을 수정하지 않으며 평가마다 사용한 버전과 정답을 보관합니다.</p><p id="truth-status" role="status">상단에서 시험 시나리오를 선택하세요.</p><div id="truth-events"></div><p id="comparison-selection" class="subtitle">수집 CSV와 시험 시나리오를 선택하세요.</p></div></details>`;
}
function m01EmptyResult(message='아직 이 모드의 정답 비교 결과가 없습니다.') {
  return `<div class="panel-heading"><h2>Development Result</h2></div><div class="result-grid"><div><label>최종 수집정확도</label><strong class="large-score">—</strong></div><div><label>C1 필수 이벤트 수집률</label><strong>—</strong></div><div><label>C2 필수 필드 누락률</label><strong>—</strong></div><div><label>C3 유형 커버리지</label><strong>—</strong></div></div><p class="empty">${esc(message)}</p>`;
}
function openM01Upload() {
  const input=document.querySelector('#csv-file');
  input.value='';
  input.click();
}
function m01ComparisonSelection() {
  return {
    dataset_id:document.querySelector('#csv-dataset').value,
    truth_id:document.querySelector('#truth-dataset').value,
    session_id:document.querySelector('#csv-session').value,
  };
}
function updateM01CompareButton() {
  const selected=m01ComparisonSelection();
  const truthReady=!truthDetailBusy && m01TruthReport?.truth?.truth_id===selected.truth_id;
  document.querySelector('#compare-events').disabled=comparisonBusy || !selected.dataset_id || !selected.truth_id || !truthReady;
  document.querySelector('#comparison-selection').textContent=selected.dataset_id
    ?`수집 CSV: ${selected.dataset_id} · 세션: ${selected.session_id==='__all__'?'전체 세션':selected.session_id||'(session_id 공백)'}`
    :'위에서 수집 CSV를 업로드하거나 선택하세요.';
  const report=csvReport?.dataset?.dataset_id===selected.dataset_id?csvReport:null;
  document.querySelector('#m01-dataset-name').textContent=report?.dataset.filename||(selected.dataset_id?'CSV 불러오는 중…':'CSV 업로드 대기');
  document.querySelector('#m01-event-count').textContent=report?String(report.summary.event_count):'—';
  document.querySelector('#m01-ready-status').textContent=!selected.truth_id?'시험 시나리오를 선택하고 수집기의 events.csv를 업로드하세요.':truthDetailBusy?'선택한 시나리오의 저장된 정답을 불러오고 있습니다.':!truthReady?'저장된 정답을 불러오지 못했습니다. 정답 카드를 확인하거나 시나리오를 다시 선택하세요.':!selected.dataset_id?'수집기의 events.csv를 업로드하세요.':comparisonBusy?'정답 이벤트를 비교하고 있습니다.':'선택한 시나리오의 저장된 정답으로 평가할 수 있습니다.';
}
function invalidateM01Comparison(message='선택이 변경되었습니다. 정답과 다시 비교하세요.') {
  comparisonRequestNumber++;
  comparisonVerificationRequestNumber++;
  comparisonBusy=false;
  document.querySelector('#comparison-status').textContent=message;
  document.querySelector('#comparison-result').innerHTML=m01EmptyResult('정답과 수집 CSV를 선택한 후 평가 실행을 누르세요.');
  m01ComparisonUrl(null);
  updateM01CompareButton();
}
function renderM01Csv(m) {
  const requestedComparisonId=new URLSearchParams(location.search).get('comparison_id');
  document.title='DEVELOPMENT · M01 · Rainbow';
  app.innerHTML=`${banner('수집 CSV · 정답 이벤트 비교')}<a class="back" href="${link('/')}">← 전체 평가</a>
    <section class="page-heading"><div><p class="eyebrow">M01 / DEVELOPMENT</p><h1>${labels.M01}</h1><p class="subtitle">${esc(m.metric_name)}</p></div>${badge(m)}</section>
    <section class="evaluation-panel" id="m01-input-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2></div>
      <div class="dataset-grid"><div><label>테스트 데이터셋</label><code id="m01-dataset-name">CSV 업로드 대기</code></div><div><label>개발 데이터 입력 수</label><strong id="m01-event-count">—</strong></div><div><label>M01 목표값</label><strong>${m.target==null?'미설정':esc(m.operator||'>=')+' '+score(m.target,'M01')}</strong></div></div>
      <div class="csv-controls m01-scenario-controls"><label>시험 시나리오<select id="truth-dataset"><option value="">시험 시나리오를 선택하세요</option></select></label></div>
      <div class="run-row"><p id="m01-ready-status">수집 CSV와 정답을 선택하면 평가할 수 있습니다.</p><div class="m01-input-actions"><button id="m01-open-upload" type="button" class="m01-upload-button">CSV 업로드</button><button id="compare-events" type="button" disabled>평가 실행 →</button></div></div>
      <input id="csv-file" type="file" accept=".csv,text/csv" aria-label="수집 이벤트 CSV" hidden><p id="csv-status" role="status"></p>
    </section>
    <details class="m01-detail-tools" id="m01-input-cards"><summary>상세 보기</summary><div class="m01-detail-tools-content">
      ${m01ComparisonPanel()}
      <details class="m01-input-card" id="m01-diagnostics-card"><summary><h2>CSV 진단 및 수집 이벤트 로그</h2></summary><div class="m01-card-content"><details class="m01-advanced-controls" id="m01-csv-options"><summary>파일 · 세션 설정</summary><div class="csv-controls"><label>CSV 파일<select id="csv-dataset"><option value="">업로드한 CSV 없음</option></select></label><label>조회 세션<select id="csv-session"><option value="__all__">전체 세션</option></select></label></div><label class="csv-checkbox"><input id="csv-target-mapping" type="checkbox"> 개발용 필드 대응 사용: 비어 있는 target_key를 target_selector로 검사</label><p class="subtitle">개발용 대응은 진단표에만 적용하며 최종 점수는 원본 필드로 계산합니다. 입력값·API 본문은 표시하지 않습니다.</p></details><div id="csv-diagnostics"><p class="empty">CSV를 업로드하면 이벤트 목록과 C2·C3 진단을 표시합니다.</p></div></div></details>
      <details class="m01-input-card" id="m01-prod-card"><summary><h2>PROD 수집 로그 조회</h2></summary><div class="m01-card-content"><p id="prod-status" role="status">조회 설정 확인 중…</p><form id="prod-search"><div class="csv-controls"><label>시작 날짜<input id="prod-from" type="date"></label><label>종료 날짜<input id="prod-to" type="date"></label><label>session_id<input id="prod-session" type="text" autocomplete="off" placeholder="정확히 일치하는 세션"></label><label>event_id<input id="prod-event" type="text" autocomplete="off" placeholder="정확히 일치하는 이벤트"></label></div><div class="run-row"><p>읽기 전용 · 양쪽 날짜를 지정하면 최대 90일, 공백이면 해당 방향의 기간 제한 없이 조회합니다.</p><button id="prod-query" type="submit">조회 / 새로고침</button></div></form><div id="prod-logs"><p class="empty">조회 버튼을 누르면 PROD DB에 적재된 이벤트를 확인합니다.</p></div></div></details>
    </div></details><p id="comparison-status" role="status"></p>
    <section class="result-panel" id="m01-result-panel"><div id="comparison-result">${m01EmptyResult()}</div></section>`;
  document.querySelector('#m01-open-upload').addEventListener('click',openM01Upload);
  document.querySelector('#prod-search').addEventListener('submit',event=>{event.preventDefault();loadM01Prod(1);});
  document.querySelector('#csv-file').addEventListener('change',()=>{
    if(document.querySelector('#csv-file').files?.length) return uploadM01Csv();
  });
  document.querySelector('#csv-dataset').addEventListener('change',()=>{
    document.querySelector('#csv-session').innerHTML='<option value="__all__">전체 세션</option>';
    invalidateM01Comparison();
    loadM01Csv(0);
  });
  document.querySelector('#csv-session').addEventListener('change',()=>{
    invalidateM01Comparison();
    loadM01Csv(0);
  });
  document.querySelector('#csv-target-mapping').addEventListener('change',()=>{
    invalidateM01Comparison();
    if(document.querySelector('#csv-dataset').value) loadM01Csv(0);
  });
  document.querySelector('#truth-dataset').addEventListener('change',()=>{
    invalidateM01Comparison();
    return loadM01TruthDetail();
  });
  document.querySelector('#compare-events').addEventListener('click',compareM01Events);
  Promise.all([loadM01Datasets(),loadM01Truths()]).then(()=>{
    if(requestedComparisonId) restoreM01Comparison(requestedComparisonId);
  });
  loadM01ProdStatus();
}
async function loadM01ProdStatus() {
  try {
    const result=await csvJson('/api/development/m01/prod/status');
    document.querySelector('#prod-status').textContent=result.configured?'PROD 조회 설정 준비됨 · 실제 연결은 조회 시 확인합니다.':(result.message||'PROD 조회 설정이 필요합니다. CSV 업로드는 독립적으로 사용할 수 있습니다.');
  } catch(error) {document.querySelector('#prod-status').textContent=error.message;}
}
async function loadM01Prod(page=1) {
  const requestNumber=++prodRequestNumber;
  const button=document.querySelector('#prod-query');
  const status=document.querySelector('#prod-status');
  const query=new URLSearchParams({page:String(page),limit:'100'});
  for(const [key,id] of [['from','prod-from'],['to','prod-to'],['session_id','prod-session'],['event_id','prod-event']]) {
    const value=document.querySelector('#'+id).value.trim();
    if(value) query.set(key,value);
  }
  button.disabled=true;status.textContent='PROD 이벤트 조회 중…';
  try {
    const result=await csvJson('/api/development/m01/prod/events?'+query.toString());
    if(requestNumber!==prodRequestNumber) return;
    prodReport=result;
    status.textContent='PROD DB 조회 성공 · 읽기 전용 · 수집기 전송 성공 여부는 해당 event_id로 확인하세요.';
    document.querySelector('#prod-logs').innerHTML=`<p class="subtitle">PROD_DB · ${result.page}페이지 · ${result.rows.length}건 · 시간 기준: ${esc(result.source.time_basis)} ${esc(result.source.event_time_offset||'')}</p>${result.source.missing_columns?.length?`<p class="notice">PROD 테이블에 없는 열: ${esc(result.source.missing_columns.join(', '))}. 해당 값은 공백으로 표시합니다.</p>`:''}${result.notice?`<p class="notice">${esc(result.notice)}</p>`:''}${result.rows.length?table(result.rows):'<p class="empty">현재 조건으로 적재된 이벤트가 없습니다.</p>'}<div class="csv-pagination"><button id="prod-prev" ${result.page<=1?'disabled':''}>이전 100건</button><button id="prod-next" ${result.has_more?'':'disabled'}>다음 100건</button></div>`;
    document.querySelector('#prod-prev').addEventListener('click',()=>loadM01Prod(Math.max(1,prodReport.page-1)));
    document.querySelector('#prod-next').addEventListener('click',()=>loadM01Prod(prodReport.page+1));
  } catch(error) {
    if(requestNumber!==prodRequestNumber) return;
    status.textContent=error.message+' · CSV 업로드는 계속 사용할 수 있습니다.';
    document.querySelector('#prod-logs').innerHTML='<p class="empty">이번 PROD 조회에 실패했습니다. 연결 설정과 백엔드 상태를 확인하세요.</p>';
  } finally {if(requestNumber===prodRequestNumber) button.disabled=false;}
}
async function csvJson(url, options) {
  const response=await fetch(url,options);
  const result=await response.json();
  if(!response.ok) throw new Error(result.error||'CSV 처리 실패');
  return result;
}
async function loadM01Datasets(selectedId) {
  const requestNumber=++csvDatasetListRequestNumber;
  try {
    const result=await csvJson('/api/development/m01/csv');
    if(requestNumber!==csvDatasetListRequestNumber) return;
    const datasets=result.datasets||[];
    const previousId=document.querySelector('#csv-dataset').value;
    document.querySelector('#csv-dataset').innerHTML=datasets.length?datasets.map(d=>`<option value="${esc(d.dataset_id)}">${esc(d.filename)} · ${d.summary.event_count}건 · ${esc(d.uploaded_at)}</option>`).join(''):'<option value="">업로드한 CSV 없음</option>';
    const nextId=selectedId||previousId;
    if(datasets.some(d=>d.dataset_id===nextId)) document.querySelector('#csv-dataset').value=nextId;
    if(previousId!==document.querySelector('#csv-dataset').value) invalidateM01Comparison();
    else updateM01CompareButton();
    if(datasets.length) await loadM01Csv(0);
  } catch(error) {if(requestNumber===csvDatasetListRequestNumber) document.querySelector('#csv-status').textContent=error.message;}
}
async function uploadM01Csv() {
  const file=document.querySelector('#csv-file').files?.[0];
  const button=document.querySelector('#m01-open-upload');
  const status=document.querySelector('#csv-status');
  if(!file) return;
  invalidateM01Comparison('수집 CSV 업로드 후 정답과 비교하세요.');
  if(file.size>10*1024*1024) {status.textContent='CSV 파일은 최대 10 MiB입니다.';return;}
  button.disabled=true;status.textContent='CSV 업로드 · 입력 검증 및 근거 저장 중…';
  try {
    const bytes=new Uint8Array(await file.arrayBuffer());
    let binary='';
    for(let offset=0;offset<bytes.length;offset+=32768) binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
    const result=await csvJson('/api/development/m01/csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,csv_base64:btoa(binary),map_target_selector:document.querySelector('#csv-target-mapping').checked})});
    document.querySelector('#csv-session').innerHTML='<option value="__all__">전체 세션</option>';
    await loadM01Datasets(result.dataset.dataset_id);
    status.textContent='업로드 완료 · 원본 CSV와 입력 해시를 DEVELOPMENT에 보관했습니다.';
  } catch(error) {status.textContent=error.message;}
  finally {button.disabled=false;}
}
async function loadM01Truths(selectedId) {
  const requestNumber=++truthListRequestNumber;
  try {
    const result=await csvJson('/api/development/m01/ground-truths');
    if(requestNumber!==truthListRequestNumber) return;
    const truths=result.truths||[];
    const select=document.querySelector('#truth-dataset');
    const previousId=select.value;
    const options=items=>items.map(t=>`<option value="${esc(t.truth_id)}">${esc(t.scenario_name||t.filename)} · ${esc(t.scenario_version||'legacy')} · 정답 ${esc(t.event_count)}건</option>`).join('');
    const stored=truths.filter(t=>!t.legacy_csv && t.source==='stored_scenario');
    const legacy=truths.filter(t=>!stored.includes(t));
    select.innerHTML='<option value="">'+(truths.length?'시험 시나리오를 선택하세요':'저장된 시험 시나리오 없음')+'</option>'+options(stored)+(legacy.length?`<optgroup label="이전 등록 정답">${options(legacy)}</optgroup>`:'');
    const nextId=selectedId||previousId;
    if(truths.some(t=>t.truth_id===nextId)) select.value=nextId;
    if(previousId!==select.value) invalidateM01Comparison();
    else updateM01CompareButton();
    if(select.value) await loadM01TruthDetail();
  } catch(error) {if(requestNumber===truthListRequestNumber) document.querySelector('#truth-status').textContent=error.message;}
}
async function loadM01TruthDetail() {
  const id=document.querySelector('#truth-dataset').value;
  const requestNumber=++truthDetailRequestNumber;
  const status=document.querySelector('#truth-status');
  const isCurrent=()=>requestNumber===truthDetailRequestNumber && document.querySelector('#truth-dataset').value===id;
  m01TruthReport=null;
  truthDetailBusy=!!id;
  document.querySelector('#truth-dataset').dataset.loadedTruthId='';
  document.querySelector('#truth-events').innerHTML='';
  status.textContent=id?'저장된 정답을 불러오는 중…':'상단에서 시험 시나리오를 선택하세요.';
  updateM01CompareButton();
  if(!id) return;
  try {
    const result=await csvJson(`/api/development/m01/ground-truths/${encodeURIComponent(id)}`);
    if(!isCurrent()) return;
    if(result.truth?.truth_id!==id || !Array.isArray(result.expected)) throw new Error('저장된 시나리오의 정답 정보를 확인할 수 없습니다.');
    m01TruthReport=result;
    const truth=result.truth;
    status.textContent=`${truth.scenario_name||truth.filename} · 버전 ${truth.scenario_version||'legacy'} · 정답 ${truth.event_count}건`;
    document.querySelector('#truth-events').innerHTML=table(result.expected.map(item=>({sequence:item.sequence,expected_event_id:item.expected_event_id,event_type:item.event_type,interaction_type:item.interaction_type,page_url:item.page_url,target:item.data_testid||item.target_selector,api_method:item.api_method,api_path:item.api_path})));
    document.querySelector('#truth-dataset').dataset.loadedTruthId=id;
  } catch(error) {
    if(isCurrent()) status.textContent=error.message;
  } finally {
    if(isCurrent()) {truthDetailBusy=false;updateM01CompareButton();}
  }
}
async function compareM01Events() {
  const selected=m01ComparisonSelection();
  invalidateM01Comparison('');
  const status=document.querySelector('#comparison-status');
  if(!selected.dataset_id || !selected.truth_id) {status.textContent='수집 CSV와 시험 시나리오를 모두 선택하세요.';return;}
  if(truthDetailBusy || m01TruthReport?.truth?.truth_id!==selected.truth_id) {status.textContent='선택한 시나리오의 정답을 불러온 후 평가하세요.';return;}
  const requestNumber=++comparisonRequestNumber;
  const selectionKey=JSON.stringify(selected);
  const isCurrent=()=>requestNumber===comparisonRequestNumber && selectionKey===JSON.stringify(m01ComparisonSelection());
  comparisonBusy=true;updateM01CompareButton();
  status.textContent='정답 이벤트와 수집 이벤트를 비교하고 근거를 저장하는 중…';
  try {
    const payload={dataset_id:selected.dataset_id,truth_id:selected.truth_id};
    if(selected.session_id!=='__all__') payload.session_id=selected.session_id;
    const result=await csvJson('/api/development/m01/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!isCurrent()) return;
    renderM01ComparisonResult(result,selected);
    m01ComparisonUrl(result.comparison_id);
    status.textContent='비교 완료 · 정답별 실제 이벤트 ID와 판정 사유를 확인하세요.';
    document.querySelector('#m01-result-panel').scrollIntoView?.({block:'start'});
  } catch(error) {
    if(!isCurrent()) return;
    document.querySelector('#comparison-result').innerHTML=m01EmptyResult('이번 비교에 실패했습니다. 입력을 확인하고 다시 비교하세요.');
    status.textContent=error.message;
    document.querySelector('#m01-result-panel').scrollIntoView?.({block:'start'});
  } finally {
    if(isCurrent()) {comparisonBusy=false;updateM01CompareButton();}
  }
}
function renderM01ComparisonResult(result,selected) {
  comparisonVerificationRequestNumber++;
  const summary=result.summary;
  const measurement=result.measurement;
  const truth=m01TruthReport?.truth;
  const scenarioName=result.scenario_name||truth?.scenario_name||truth?.filename||'이전 등록 정답';
  const scenarioVersion=result.scenario_version||truth?.scenario_version||'legacy';
  const pct=value=>value==null||!Number.isFinite(Number(value))?'확인 불가':`${Number(value).toFixed(2)}%`;
  const rows=result.rows.map(row=>({sequence:row.sequence,expected_event_id:row.expected_event_id,matched_event_id:row.matched_event_id,status:row.status,reason:row.reason}));
  const evidence=`/api/development/m01/comparisons/${encodeURIComponent(result.comparison_id)}/evidence.csv`;
  const grid=measurement
    ?`<div class="result-grid"><div><label>최종 수집정확도</label><strong class="large-score" id="collection-accuracy">${esc(pct(measurement.collection_accuracy))}</strong></div><div><label>C1 필수 이벤트 수집률</label><strong id="comparison-match-rate">${esc(pct(measurement.c1))}</strong></div><div><label>C2 필수 필드 누락률</label><strong id="comparison-field-missing">${esc(pct(measurement.c2))}</strong></div><div><label>C3 유형 커버리지</label><strong id="comparison-type-coverage">${esc(pct(measurement.c3))}</strong></div></div>`
    :`<div class="result-grid"><div><label>정답 이벤트 일치율</label><strong class="large-score" id="comparison-match-rate">${esc(pct(summary.match_rate))}</strong></div><div><label>일치 / 기대 이벤트</label><strong>${esc(summary.matched_count)} / ${esc(summary.expected_count)}</strong></div><div><label>누락 이벤트</label><strong>${esc(summary.missing_count)}</strong></div><div><label>실행 상태</label><span class="badge neutral">이전 비교 결과</span></div></div>`;
  const threshold=measurement
    ?`<span class="badge ${measurement.threshold_met===true?'pass':measurement.threshold_met===false?'fail':'neutral'}">${measurement.threshold_met===true?'기준 충족 (개발)':measurement.threshold_met===false?'기준 미달 (개발)':'판정 확인 필요'} · 목표 ${esc(pct(measurement.target))}</span>`
    :'';
  const formula=measurement?`<p>${esc(measurement.formula)} · C2는 원본 필수 필드 기준이며 중복·보조 로그도 선택 범위의 전체 수집 이벤트에 포함합니다.</p>`:'<p>이전 결과에는 최종 수집정확도가 저장되어 있지 않습니다. 같은 입력으로 평가를 다시 실행하면 새 산식 결과를 별도로 보관합니다.</p>';
  const notice=measurement?'개발 데이터에 시험 산식을 적용한 결과이며 공식 시험 판정은 아닙니다.':'개발용 정답 이벤트 일치율입니다. 공식 수집정확도 점수와 판정은 별도 기준으로 산출합니다.';
  const counts=measurement?.counts;
  const countDetails=counts?`<p>필수 이벤트 ${esc(counts.collected_required_event_count)} / ${esc(counts.defined_required_event_count)} · 누락 필드 ${esc(counts.missing_required_field_count)} / (${esc(counts.total_collected_events)} × ${esc(counts.required_field_count)}) · 수집 유형 ${esc(counts.collected_event_type_count)} / ${esc(counts.defined_event_type_count)}</p>`:'';
  document.querySelector('#comparison-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2><a class="download" href="${esc(evidence)}" download>${measurement?'통합 근거 CSV':'CSV 다운로드'} ↓</a></div>${grid}<div class="m01-measurement-summary"><p class="subtitle">일치 ${esc(summary.matched_count)} / ${esc(summary.expected_count)} · 누락 ${esc(summary.missing_count)} · 추가 ${esc(summary.extra_event_count)} · 중복 ${esc(summary.duplicate_event_rows)}</p>${threshold}</div><p class="run-meta">시험 시나리오: ${esc(scenarioName)} · 정답 버전: ${esc(scenarioVersion)}</p><p class="subtitle m01-result-note">${notice}</p><details><summary>계산·매칭 근거</summary>${formula}${countDetails}${measurement?'<p id="comparison-verification" role="status">근거 CSV를 독립 검산하는 중…</p>':''}<p class="run-meta">비교 ID: ${esc(result.comparison_id)} · 수집 CSV: ${esc(selected.dataset_id)} · 정답: ${esc(selected.truth_id)} · 세션: ${esc(selected.session_id==='__all__'?'전체 세션':selected.session_id||'(session_id 공백)')}</p>${table(rows)}</details>`;
  if(measurement) loadM01Verification(result.comparison_id);
}
async function loadM01Verification(comparisonId) {
  const requestNumber=++comparisonVerificationRequestNumber;
  try {
    const report=await csvJson(`/api/development/m01/comparisons/${encodeURIComponent(comparisonId)}/verification`);
    if(requestNumber!==comparisonVerificationRequestNumber) return;
    if(report.verified!==true || report.status!=='VERIFIED' || !Number.isFinite(report.recalculated?.collection_accuracy)) throw new Error(report.notice||'근거 CSV의 검산 결과를 확인할 수 없습니다.');
    document.querySelector('#comparison-verification').textContent=`근거 CSV 독립 검산 일치 · 최종 수집정확도 ${Number(report.recalculated.collection_accuracy).toFixed(2)}%`;
  } catch(error) {
    if(requestNumber===comparisonVerificationRequestNumber) document.querySelector('#comparison-verification').textContent='검산 확인 실패: '+error.message;
  }
}
async function restoreM01Comparison(comparisonId) {
  const status=document.querySelector('#comparison-status');
  if(!/^[a-f0-9]{32}$/.test(comparisonId)) {
    invalidateM01Comparison('비교 ID 형식이 올바르지 않습니다.');return;
  }
  const requestNumber=++comparisonRequestNumber;
  comparisonBusy=true;updateM01CompareButton();
  status.textContent='저장한 정답 비교 결과를 불러오는 중…';
  try {
    const result=await csvJson(`/api/development/m01/comparisons/${encodeURIComponent(comparisonId)}`);
    if(requestNumber!==comparisonRequestNumber) return;
    document.querySelector('#csv-dataset').value=result.dataset_id;
    document.querySelector('#truth-dataset').value=result.truth_id;
    if(document.querySelector('#csv-dataset').value!==result.dataset_id || document.querySelector('#truth-dataset').value!==result.truth_id) throw new Error('저장 결과에 연결된 수집 CSV 또는 정답 CSV를 찾을 수 없습니다.');
    await loadM01TruthDetail();
    if(requestNumber!==comparisonRequestNumber) return;
    if(m01TruthReport?.truth?.truth_id!==result.truth_id) throw new Error('저장 결과에 사용한 정답을 불러오지 못했습니다.');
    document.querySelector('#csv-session').innerHTML='<option value="__all__">전체 세션</option>';
    await loadM01Csv(0);
    if(requestNumber!==comparisonRequestNumber) return;
    const session=result.session_id==null?'__all__':result.session_id;
    document.querySelector('#csv-session').value=session;
    if(document.querySelector('#csv-session').value!==session) throw new Error('저장 결과에 연결된 세션을 찾을 수 없습니다.');
    if(session!=='__all__') await loadM01Csv(0);
    if(requestNumber!==comparisonRequestNumber) return;
    renderM01ComparisonResult(result,m01ComparisonSelection());
    m01ComparisonUrl(result.comparison_id);
    status.textContent='저장한 비교 결과를 복원했습니다. 정답별 실제 이벤트 ID와 판정 사유를 확인하세요.';
    document.querySelector('#comparison-result').scrollIntoView?.({block:'start'});
  } catch(error) {
    if(requestNumber!==comparisonRequestNumber) return;
    document.querySelector('#comparison-result').innerHTML=m01EmptyResult('저장한 비교 결과를 불러오지 못했습니다.');
    status.textContent=error.message;m01ComparisonUrl(null);
  } finally {
    if(requestNumber===comparisonRequestNumber) {comparisonBusy=false;updateM01CompareButton();}
  }
}
function m01CsvQuery(offset=0) {
  const query=new URLSearchParams({offset:String(offset),limit:'100',map_target_selector:String(document.querySelector('#csv-target-mapping').checked)});
  const session=document.querySelector('#csv-session').value;
  if(session!=='__all__') query.set('session_id',session);
  return query.toString();
}
async function loadM01Csv(offset=0) {
  const requestNumber=++csvRequestNumber;
  const id=document.querySelector('#csv-dataset').value;
  if(!id) return;
  try {
    const result=await csvJson(`/api/development/m01/csv/${encodeURIComponent(id)}?${m01CsvQuery(offset)}`);
    // Ignore a response from a file selection that has since changed.
    if(requestNumber!==csvRequestNumber || document.querySelector('#csv-dataset').value!==id) return;
    csvReport=result;
    const session=document.querySelector('#csv-session').value;
    document.querySelector('#csv-session').innerHTML='<option value="__all__">전체 세션</option>'+result.summary.sessions.map(s=>`<option value="${esc(s.session_id)}">${esc(s.session_id||'(session_id 공백)')} · ${s.event_count}건</option>`).join('');
    document.querySelector('#csv-session').value=session;
    const s=result.summary;
    const pct=value=>`${Number(value).toFixed(2)}%`;
    const fieldRows=s.required_fields.map(field=>({field,raw_missing:s.raw_missing_fields[field]||0,applied_missing:s.missing_fields[field]||0}));
    document.querySelector('#csv-diagnostics').innerHTML=`<p class="run-meta">${esc(result.dataset.filename)} · ${esc(id)}<br>SHA-256: ${esc(result.dataset.sha256)}</p><div class="detail-stats"><div><label>현재 범위 / 전체 이벤트</label><strong>${s.event_count} / ${s.source_event_count}</strong></div><div><label>C2 필드 누락률${s.target_selector_mapping?' (개발용 대응 적용)':''}</label><strong>${pct(s.c2)}</strong></div><div><label>C3 유형 커버리지</label><strong>${pct(s.c3)}</strong></div></div><p class="subtitle">선택 범위의 필드·유형 진단입니다. 정답을 선택하고 평가를 실행하면 C1과 최종 수집정확도가 Result에 표시됩니다.</p><p class="subtitle">원본 C2 ${pct(s.raw_c2)} · 필드 누락 ${s.missing_field_count}/${s.required_field_slots} · 중복 event_id 추가 행 ${s.duplicate_event_id_rows}건 · event_id 공백 ${s.missing_event_id_rows}건 · 미분류 유형 ${s.unclassified_event_count}건</p><p class="subtitle">이벤트 시간(UTC): ${esc(s.event_time_min_utc||'확인 불가')} ~ ${esc(s.event_time_max_utc||'확인 불가')} · 시간 형식/시간대 확인 필요 ${s.invalid_or_timezone_missing_event_times}건</p><details><summary>필드·유형별 진단 및 대응 규칙</summary><p>원본에 없는 필수 열: ${esc(s.missing_header_fields.join(', ')||'없음')}</p>${table(fieldRows)}${table(Object.entries(s.type_counts).map(([type,count])=>({type,count})))}<p>${esc(s.mapping_version)} · 미분류 이벤트와 중복 행도 전체 이벤트 수에 포함합니다.</p></details><div class="panel-heading csv-log-heading"><h2>수집 이벤트 로그</h2><a class="download" href="/api/development/m01/csv/${esc(id)}/evidence.csv?${esc(m01CsvQuery(0))}" download>현재 범위 검증 근거 CSV ↓</a></div><p class="subtitle">${result.offset+1}–${Math.min(result.offset+result.limit,s.event_count)} / ${s.event_count}건 · URL query/fragment와 입력값·API 본문은 표시하지 않습니다.</p>${table(result.rows)}<div class="csv-pagination"><button id="csv-prev" ${result.offset===0?'disabled':''}>이전 100건</button><button id="csv-next" ${result.has_more?'':'disabled'}>다음 100건</button></div>`;
    document.querySelector('#csv-prev').addEventListener('click',()=>loadM01Csv(Math.max(0,csvReport.offset-100)));
    document.querySelector('#csv-next').addEventListener('click',()=>loadM01Csv(csvReport.offset+100));
    updateM01CompareButton();
  } catch(error) {document.querySelector('#csv-status').textContent=error.message;}
}
async function run(id) {
  const button=document.querySelector('#run'); button.disabled=true;
  document.querySelector('#run-status').textContent='RUNNING · 입력 검증 및 실행 근거 저장 중…';
  try {
    const response=await fetch(`/api/evaluations/${id.toLowerCase()}/run?mode=${mode}`,{method:'POST'});
    const result=await response.json();
    if (!result.run_id) throw new Error(result.error||'실행 요청 실패');
    await load();
  } catch(error) {document.querySelector('#run-status').textContent=error.message; button.disabled=false;}
}
async function load() {
  try {
    const response=await fetch(`/api/evaluations?mode=${mode}`);
    catalog=await response.json();
    if (!response.ok) throw new Error(catalog.error||'평가 정보 조회 실패');
    render();
  } catch(error) { app.innerHTML=`<p class="notice">${esc(error.message)}</p><button id="retry">다시 시도</button>`; document.querySelector('#retry').addEventListener('click',load); }
}
load();
