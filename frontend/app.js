const labels = {M01:'수집 정확도',M02:'프로세스맵 정확도 및 완전성',M03:'테스트 시나리오 자동생성률',M04:'자동 실행 성공률',M05:'AI 데이터 정제 F1 Score',M06:'워크플로우 클러스터링 품질',M07:'LLM 생성 코드 유효성 및 정확도'};
const descriptions = {M01:'5개 시나리오 · 2회 실행 · 필수 이벤트 100건',M02:'TD-03 업무 20종 · Ground Truth 5종 사후 비교',M03:'업무 10종 · 업무당 생성 요청 1회',M04:'시험 전 고정한 Selenium/Python 10건 · 각 1회 실행',M05:'학습·개발 미사용 held-out · KEEP 100건 / REMOVE 100건',M06:'OFFICIAL: 승인 V6.2 563×128 embedding · 12개 군집 DBI',M07:'구문·실행 모두 PASS / 실제 생성 코드 수 × 100'};
const app = document.querySelector('#app');
const requestedMode = new URLSearchParams(location.search).get('mode');
const mode = ['OFFICIAL','DEVELOPMENT'].includes(requestedMode) ? requestedMode : 'REFERENCE';
const dev = mode === 'DEVELOPMENT';
const nonofficial = mode !== 'OFFICIAL';
const ref = mode === 'REFERENCE';
let catalog;
let catalogRequestNumber=0;
let serverSessionReloading=false;
function ktlServerSessionId() {return typeof catalog?.server_session_id==='string'?catalog.server_session_id:null;}
function ktlDropQuery(keys) {
  if(typeof history==='undefined'||typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);
  for(const key of keys) query.delete(key);
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
function ktlCheckServerSession(response,data,requestedSession) {
  const current=ktlServerSessionId();
  if(!current) return;
  const received=response?.headers?.get?.('X-KTL-Server-Session');
  const expired=new Error('서버 세션이 변경되어 현재 상태를 다시 불러옵니다.');expired.status='SESSION_EXPIRED';
  // 이미 새 catalog를 받은 뒤 도착한 이전 요청 응답은 다시 reload하지 않는다.
  if(requestedSession&&requestedSession!==current) throw expired;
  if(!serverSessionReloading&&!(received&&received!==current)&&data?.status!=='SESSION_EXPIRED') return;
  if(!serverSessionReloading) {
    serverSessionReloading=true;
    ++m03RequestNumber;m03View=null;
    if(typeof m04RequestNumber!=='undefined') {++m04RequestNumber;clearTimeout(m04PollTimer);m04View=null;}
    ++csvRequestNumber;++prodRequestNumber;++csvDatasetListRequestNumber;++m01UploadRequestNumber;
    ++m01AutoRequestNumber;++m01SelectionRequestNumber;++comparisonRequestNumber;++comparisonVerificationRequestNumber;
    csvReport=null;prodReport=null;m01TruthReport=null;truthDetailBusy=false;comparisonBusy=false;
    ktlDropQuery(['run_id','m03_run_id','scenario_id','generation_id','execution_id','comparison_id']);
    app.innerHTML='<p class="loading">평가 정보를 불러오는 중…</p>';
    Promise.resolve().then(load).finally(()=>{serverSessionReloading=false;});
  }
  throw expired;
}
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
  if (dev && m.metric_id === 'M03') return renderM03(m);
  if (dev && m.metric_id === 'M04') return renderM04(m);
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
let truthDetailBusy = false;
let m01TruthReport = null;
let m01UploadRequestNumber = 0;
let m01AutoRequestNumber = 0;
let m01SelectionRequestNumber = 0;
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
function m01EmptyResult(message='CSV를 업로드하면 결과가 자동으로 표시됩니다.') {
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
    truth_id:m01TruthReport?.truth?.truth_id||'',
    session_id:document.querySelector('#csv-session').value,
  };
}
function updateM01CompareButton() {
  const selected=m01ComparisonSelection();
  const truthReady=!truthDetailBusy && m01TruthReport?.truth?.truth_id===selected.truth_id;
  document.querySelector('#comparison-selection').textContent=selected.dataset_id
    ?`수집 CSV: ${selected.dataset_id} · 세션: ${selected.session_id==='__all__'?'전체 세션':selected.session_id||'(session_id 공백)'}`
    :'위에서 수집 CSV를 업로드하거나 선택하세요.';
  const report=csvReport?.dataset?.dataset_id===selected.dataset_id?csvReport:null;
  document.querySelector('#m01-dataset-name').textContent=report?.dataset.filename||(selected.dataset_id?'CSV 불러오는 중…':'CSV 업로드 대기');
  document.querySelector('#m01-event-count').textContent=report?String(report.summary.event_count):'—';
  document.querySelector('#m01-ready-status').textContent=truthDetailBusy?'CSV 평가를 준비하고 있습니다.':comparisonBusy?'CSV를 평가하고 있습니다.':!selected.dataset_id?'CSV를 업로드하면 결과가 자동으로 표시됩니다.':truthReady?'업로드한 CSV의 평가 결과를 확인하세요.':'CSV를 업로드하면 자동으로 평가합니다.';
}
function invalidateM01Comparison(message='CSV를 평가합니다.') {
  m01AutoRequestNumber++;
  comparisonRequestNumber++;
  comparisonVerificationRequestNumber++;
  comparisonBusy=false;
  document.querySelector('#comparison-status').textContent=message;
  document.querySelector('#comparison-result').innerHTML=m01EmptyResult('CSV를 업로드하면 결과가 자동으로 표시됩니다.');
  m01ComparisonUrl(null);
  updateM01CompareButton();
}
function renderM01Csv(m) {
  const requestedComparisonId=new URLSearchParams(location.search).get('comparison_id');
  document.title='DEVELOPMENT · M01 · Rainbow';
  app.innerHTML=`${banner('수집 CSV · 정답 이벤트 비교')}<a class="back" href="${link('/')}">← 전체 평가</a>
    <section class="page-heading"><div><p class="eyebrow">M01 / DEVELOPMENT</p><h1>${labels.M01}</h1><p class="subtitle">${esc(m.metric_name)}</p></div>${badge(m)}</section>
    <section class="evaluation-panel" id="m01-input-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2></div>
      <p class="subtitle">확정 시나리오 · ${esc(M01_BU14_PRESET.scenario_name)} · v${esc(M01_BU14_PRESET.scenario_version)}</p>
      <div class="dataset-grid"><div><label>테스트 데이터셋</label><code id="m01-dataset-name">CSV 업로드 대기</code></div><div><label>개발 데이터 입력 수</label><strong id="m01-event-count">—</strong></div><div><label>M01 목표값</label><strong>${m.target==null?'미설정':esc(m.operator||'>=')+' '+score(m.target,'M01')}</strong></div></div>
      <div class="run-row"><p id="m01-ready-status">CSV를 업로드하면 결과가 자동으로 표시됩니다.</p><button id="m01-open-upload" type="button" class="m01-upload-button">CSV 업로드</button></div>
      <input id="csv-file" type="file" accept=".csv,text/csv" aria-label="수집 이벤트 CSV" hidden><p id="csv-status" role="status"></p>
    </section>
    <details class="m01-detail-tools" id="m01-input-cards"><summary>상세 보기</summary><div class="m01-detail-tools-content">
      <p id="comparison-selection" class="subtitle"></p>
      <details class="m01-input-card" id="m01-diagnostics-card"><summary><h2>CSV 진단 및 수집 이벤트 로그</h2></summary><div class="m01-card-content"><details class="m01-advanced-controls" id="m01-csv-options"><summary>파일 · 세션 설정</summary><div class="csv-controls"><label>CSV 파일<select id="csv-dataset"><option value="">업로드한 CSV 없음</option></select></label><label>조회 세션<select id="csv-session"><option value="__all__">전체 세션</option></select></label></div><label class="csv-checkbox"><input id="csv-target-mapping" type="checkbox"> 개발용 필드 대응 사용: 비어 있는 target_key를 target_selector로 검사</label><p class="subtitle">개발용 대응은 진단표에만 적용하며 최종 점수는 원본 필드로 계산합니다. 입력값·API 본문은 표시하지 않습니다.</p></details><div id="csv-diagnostics"><p class="empty">CSV를 업로드하면 이벤트 목록과 C2·C3 진단을 표시합니다.</p></div></div></details>
      <details class="m01-input-card" id="m01-prod-card"><summary><h2>PROD 수집 로그 조회</h2></summary><div class="m01-card-content"><p id="prod-status" role="status">조회 설정 확인 중…</p><form id="prod-search"><div class="csv-controls"><label>시작 날짜<input id="prod-from" type="date"></label><label>종료 날짜<input id="prod-to" type="date"></label><label>session_id<input id="prod-session" type="text" autocomplete="off" placeholder="정확히 일치하는 세션"></label><label>event_id<input id="prod-event" type="text" autocomplete="off" placeholder="정확히 일치하는 이벤트"></label></div><div class="run-row"><p>읽기 전용 · 양쪽 날짜를 지정하면 최대 90일, 공백이면 해당 방향의 기간 제한 없이 조회합니다.</p><button id="prod-query" type="submit">조회 / 새로고침</button></div></form><div id="prod-logs"><p class="empty">조회 버튼을 누르면 PROD DB에 적재된 이벤트를 확인합니다.</p></div></div></details>
    </div></details><p id="comparison-status" role="status"></p>
    <section class="result-panel" id="m01-result-panel"><div id="comparison-result">${m01EmptyResult()}</div></section>`;
  document.querySelector('#m01-open-upload').addEventListener('click',openM01Upload);
  document.querySelector('#prod-search').addEventListener('submit',event=>{event.preventDefault();loadM01Prod(1);});
  document.querySelector('#csv-file').addEventListener('change',()=>{
    if(document.querySelector('#csv-file').files?.length) return uploadM01Csv();
  });
  document.querySelector('#csv-dataset').addEventListener('change',async()=>{
    const requestNumber=++m01SelectionRequestNumber;
    document.querySelector('#csv-session').innerHTML='<option value="__all__">전체 세션</option>';
    invalidateM01Comparison();
    await loadM01Csv(0);
    if(requestNumber!==m01SelectionRequestNumber) return;
    if(document.querySelector('#csv-dataset').value) await evaluateM01Csv();
  });
  document.querySelector('#csv-session').addEventListener('change',async()=>{
    const requestNumber=++m01SelectionRequestNumber;
    invalidateM01Comparison();
    await loadM01Csv(0);
    if(requestNumber!==m01SelectionRequestNumber) return;
    await evaluateM01Csv();
  });
  document.querySelector('#csv-target-mapping').addEventListener('change',()=>{
    if(document.querySelector('#csv-dataset').value) loadM01Csv(0);
  });
  loadM01Datasets().then(()=>{
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
  const session=ktlServerSessionId();
  const response=await fetch(url,options);
  const result=await response.json();
  ktlCheckServerSession(response,result,session);
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
    document.querySelector('#csv-dataset').innerHTML='<option value="">CSV 업로드 대기</option>'+datasets.map(d=>`<option value="${esc(d.dataset_id)}">${esc(d.filename)} · ${d.summary.event_count}건 · ${esc(d.uploaded_at)}</option>`).join('');
    const nextId=selectedId||previousId;
    if(datasets.some(d=>d.dataset_id===nextId)) document.querySelector('#csv-dataset').value=nextId;
    if(previousId!==document.querySelector('#csv-dataset').value) invalidateM01Comparison();
    else updateM01CompareButton();
    if(document.querySelector('#csv-dataset').value) await loadM01Csv(0);
  } catch(error) {if(requestNumber===csvDatasetListRequestNumber) document.querySelector('#csv-status').textContent=error.message;}
}
async function uploadM01Csv() {
  const file=document.querySelector('#csv-file').files?.[0];
  const button=document.querySelector('#m01-open-upload');
  const status=document.querySelector('#csv-status');
  if(!file) return;
  const requestNumber=++m01UploadRequestNumber;
  const selectionRequest=++m01SelectionRequestNumber;
  const isCurrent=()=>requestNumber===m01UploadRequestNumber && selectionRequest===m01SelectionRequestNumber;
  invalidateM01Comparison('');
  if(file.size>10*1024*1024) {status.textContent='CSV 파일은 최대 10 MiB입니다.';return;}
  button.disabled=true;status.textContent='CSV 업로드 · 입력 검증 및 근거 저장 중…';
  try {
    const bytes=new Uint8Array(await file.arrayBuffer());
    if(!isCurrent()) return;
    let binary='';
    for(let offset=0;offset<bytes.length;offset+=32768) binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
    const result=await csvJson('/api/development/m01/csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,csv_base64:btoa(binary),map_target_selector:document.querySelector('#csv-target-mapping').checked})});
    if(!isCurrent()) return;
    document.querySelector('#csv-session').innerHTML='<option value="__all__">전체 세션</option>';
    await loadM01Datasets(result.dataset.dataset_id);
    if(!isCurrent() || document.querySelector('#csv-dataset').value!==result.dataset.dataset_id) return;
    status.textContent='업로드 완료 · 자동 평가 중…';
    const evaluated=await evaluateM01Csv();
    if(isCurrent()) status.textContent=evaluated?'업로드 및 평가 완료 · 결과를 확인하세요.':'업로드 완료 · 평가 오류를 확인하세요.';
  } catch(error) {if(isCurrent()) status.textContent=error.message;}
  finally {if(requestNumber===m01UploadRequestNumber) button.disabled=false;}
}
const M01_BU14_PRESET = {
  "business_unit_id": "BU14",
  "confirmation_status": "CONFIRMED",
  "confirmed_on": "2026-10-27",
  "scenario_name": "BU14 명함 목록 조회",
  "scenario_version": "2",
  "search_keyword": "테스트",
  "instructions": [
    "시험 계정으로 로그인하고 명함 관리 화면(/mypage/cards)을 엽니다. 로그인은 수집 구간에서 제외합니다.",
    "검색 구분을 기본값인 '구분'으로 두고 검색어를 비운 상태에서 수집기의 CSV 기록을 시작합니다.",
    "명함 관리 화면을 새로고침하고 목록 조회가 끝날 때까지 기다립니다.",
    "검색어 입력란을 클릭해 '테스트'를 입력하고 검색 버튼을 누른 뒤 검색 결과를 확인합니다.",
    "검색어 입력란을 다시 클릭해 내용을 모두 지우고 검색 버튼을 누른 뒤 전체 목록을 확인합니다.",
    "조회와 화면 변경이 끝난 다음 CSV 기록을 종료하고 events.csv를 내려받아 이 페이지에 업로드합니다."
  ],
  "expected_events": [
    {"expected_event_id":"BU14-E01","sequence":1,"event_type":"navigation","interaction_type":"","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E02","sequence":2,"event_type":"network","interaction_type":"","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"","api_path":"/api/business-cards","api_method":"GET"},
    {"expected_event_id":"BU14-E03","sequence":3,"event_type":"click","interaction_type":"click","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"section.mypage-content > div.work-report-page.business-card-page > div.business-card-toolbar:nth-of-type(1) > div.work-report-toolbar__search-panel > div.business-card-toolbar__actions:nth-of-type(2) > input","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E04","sequence":4,"event_type":"input","interaction_type":"change","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"section.mypage-content > div.work-report-page.business-card-page > div.business-card-toolbar:nth-of-type(1) > div.work-report-toolbar__search-panel > div.business-card-toolbar__actions:nth-of-type(2) > input","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E05","sequence":5,"event_type":"click","interaction_type":"click","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"section.mypage-content > div.work-report-page.business-card-page > div.business-card-toolbar:nth-of-type(1) > div.work-report-toolbar__search-panel > div.business-card-toolbar__actions:nth-of-type(2) > button","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E06","sequence":6,"event_type":"network","interaction_type":"","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"","api_path":"/api/business-cards","api_method":"GET"},
    {"expected_event_id":"BU14-E07","sequence":7,"event_type":"click","interaction_type":"click","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"section.mypage-content > div.work-report-page.business-card-page > div.business-card-toolbar:nth-of-type(1) > div.work-report-toolbar__search-panel > div.business-card-toolbar__actions:nth-of-type(2) > input","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E08","sequence":8,"event_type":"input","interaction_type":"change","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"section.mypage-content > div.work-report-page.business-card-page > div.business-card-toolbar:nth-of-type(1) > div.work-report-toolbar__search-panel > div.business-card-toolbar__actions:nth-of-type(2) > input","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E09","sequence":9,"event_type":"click","interaction_type":"click","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"section.mypage-content > div.work-report-page.business-card-page > div.business-card-toolbar:nth-of-type(1) > div.work-report-toolbar__search-panel > div.business-card-toolbar__actions:nth-of-type(2) > button","api_path":"","api_method":""},
    {"expected_event_id":"BU14-E10","sequence":10,"event_type":"network","interaction_type":"","page_url":"https://rainbowlab.ai.kr/mypage/cards","data_testid":"","target_selector":"","api_path":"/api/business-cards","api_method":"GET"}
  ]
};
async function getM01Bu14Preset() {
  return M01_BU14_PRESET;
}
async function evaluateM01Csv() {
  invalidateM01Comparison('');
  const requestNumber=++m01AutoRequestNumber;
  const selection=()=>JSON.stringify([document.querySelector('#csv-dataset').value,document.querySelector('#csv-session').value]);
  const selected=selection();
  const isCurrent=()=>requestNumber===m01AutoRequestNumber && selection()===selected;
  const status=document.querySelector('#comparison-status');
  if(!document.querySelector('#csv-dataset').value) return false;
  m01TruthReport=null;
  truthDetailBusy=true;updateM01CompareButton();
  status.textContent='CSV를 자동으로 평가하고 있습니다…';
  try {
    const preset=await getM01Bu14Preset();
    if(!isCurrent()) return false;
    const payload={scenario_name:preset.scenario_name,scenario_version:preset.scenario_version,expected_events:preset.expected_events};
    const result=await csvJson('/api/development/m01/ground-truths',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),
    });
    if(!isCurrent()) return false;
    if(!result.truth?.truth_id || result.truth.scenario_name!==preset.scenario_name
      || result.truth.scenario_version!==preset.scenario_version || !Array.isArray(result.expected)) {
      throw new Error('평가 기준을 불러오지 못했습니다.');
    }
    m01TruthReport=result;
    truthDetailBusy=false;
    return await compareM01Events();
  } catch(error) {
    if(isCurrent()) {
      status.textContent=error.message;
      document.querySelector('#comparison-result').innerHTML=m01EmptyResult('평가하지 못했습니다. CSV를 다시 업로드하세요.');
    }
    return false;
  } finally {
    if(requestNumber===m01AutoRequestNumber) {truthDetailBusy=false;updateM01CompareButton();}
  }
}
async function compareM01Events() {
  const selected=m01ComparisonSelection();
  invalidateM01Comparison('');
  const status=document.querySelector('#comparison-status');
  if(!selected.dataset_id || !selected.truth_id || truthDetailBusy) {status.textContent='CSV를 다시 업로드하세요.';return false;}
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
    return true;
  } catch(error) {
    if(!isCurrent()) return;
    document.querySelector('#comparison-result').innerHTML=m01EmptyResult('이번 비교에 실패했습니다. 입력을 확인하고 다시 비교하세요.');
    status.textContent=error.message;
    document.querySelector('#m01-result-panel').scrollIntoView?.({block:'start'});
    return false;
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
  const scope=result.capture_scope;
  const scopeNotice=scope?.notice||'수집 run·탭 근거가 없는 이전 결과입니다. 수행 범위는 확인되지 않았습니다.';
  const notice=measurement?`${scopeNotice} 개발 데이터에 시험 산식을 적용한 결과이며 공식 시험 판정은 아닙니다.`:'개발용 정답 이벤트 일치율입니다. 공식 수집정확도 점수와 판정은 별도 기준으로 산출합니다.';
  const counts=measurement?.counts;
  const countDetails=counts?`<p>필수 이벤트 ${esc(counts.collected_required_event_count)} / ${esc(counts.defined_required_event_count)} · 누락 필드 ${esc(counts.missing_required_field_count)} / (${esc(counts.total_collected_events)} × ${esc(counts.required_field_count)}) · 수집 유형 ${esc(counts.collected_event_type_count)} / ${esc(counts.defined_event_type_count)}</p>`:'';
  document.querySelector('#comparison-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2><a class="download" href="${esc(evidence)}" download>${measurement?'통합 근거 CSV':'CSV 다운로드'} ↓</a></div>${grid}<div class="m01-measurement-summary"><p class="subtitle">일치 ${esc(summary.matched_count)} / ${esc(summary.expected_count)} · 누락 ${esc(summary.missing_count)} · 추가 ${esc(summary.extra_event_count)} · 중복 ${esc(summary.duplicate_event_rows)}</p>${threshold}</div><p class="run-meta">시험 시나리오: ${esc(scenarioName)} · 정답 버전: ${esc(scenarioVersion)}</p><p class="subtitle m01-result-note">${esc(notice)}</p><details><summary>계산·매칭 근거</summary>${formula}${countDetails}${measurement?'<p id="comparison-verification" role="status">근거 CSV를 독립 검산하는 중…</p>':''}<p class="run-meta">비교 ID: ${esc(result.comparison_id)} · 수집 CSV: ${esc(selected.dataset_id)} · 정답: ${esc(selected.truth_id)} · 세션: ${esc(selected.session_id==='__all__'?'전체 세션':selected.session_id||'(session_id 공백)')}</p>${table(rows)}</details>`;
  if(measurement) {
    document.querySelector('#comparison-result details')?.insertAdjacentHTML?.('beforeend',`<a class="download" href="/api/development/m01/comparisons/${encodeURIComponent(result.comparison_id)}/event-results.csv" download>이벤트별 비교 결과 CSV ↓</a>`);
    loadM01Verification(result.comparison_id);
  }
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
    if(document.querySelector('#csv-dataset').value!==result.dataset_id) throw new Error('저장 결과에 연결된 수집 CSV를 찾을 수 없습니다.');
    const truth=await csvJson(`/api/development/m01/ground-truths/${encodeURIComponent(result.truth_id)}`);
    if(requestNumber!==comparisonRequestNumber) return;
    if(truth.truth?.truth_id!==result.truth_id) throw new Error('저장 결과에 사용한 정답을 불러오지 못했습니다.');
    m01TruthReport=truth;
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
    document.querySelector('#csv-diagnostics').innerHTML=`<p class="run-meta">${esc(result.dataset.filename)} · ${esc(id)}<br>SHA-256: ${esc(result.dataset.sha256)}</p><div class="detail-stats"><div><label>현재 범위 / 전체 이벤트</label><strong>${s.event_count} / ${s.source_event_count}</strong></div><div><label>C2 필드 누락률${s.target_selector_mapping?' (개발용 대응 적용)':''}</label><strong>${pct(s.c2)}</strong></div><div><label>C3 유형 커버리지</label><strong>${pct(s.c3)}</strong></div></div><p class="subtitle">선택 범위의 필드·유형 진단입니다. CSV 업로드 시 C1과 최종 수집정확도를 자동으로 계산합니다.</p><p class="subtitle">원본 C2 ${pct(s.raw_c2)} · 필드 누락 ${s.missing_field_count}/${s.required_field_slots} · 중복 event_id 추가 행 ${s.duplicate_event_id_rows}건 · event_id 공백 ${s.missing_event_id_rows}건 · 미분류 유형 ${s.unclassified_event_count}건</p><p class="subtitle">이벤트 시간(UTC): ${esc(s.event_time_min_utc||'확인 불가')} ~ ${esc(s.event_time_max_utc||'확인 불가')} · 시간 형식/시간대 확인 필요 ${s.invalid_or_timezone_missing_event_times}건</p><details><summary>필드·유형별 진단 및 대응 규칙</summary><p>원본에 없는 필수 열: ${esc(s.missing_header_fields.join(', ')||'없음')}</p>${table(fieldRows)}${table(Object.entries(s.type_counts).map(([type,count])=>({type,count})))}<p>${esc(s.mapping_version)} · 미분류 이벤트와 중복 행도 전체 이벤트 수에 포함합니다.</p></details><div class="panel-heading csv-log-heading"><h2>수집 이벤트 로그</h2><a class="download" href="/api/development/m01/csv/${esc(id)}/evidence.csv?${esc(m01CsvQuery(0))}" download>현재 범위 검증 근거 CSV ↓</a></div><p class="subtitle">${result.offset+1}–${Math.min(result.offset+result.limit,s.event_count)} / ${s.event_count}건 · URL query/fragment와 입력값·API 본문은 표시하지 않습니다.</p>${table(result.rows)}<div class="csv-pagination"><button id="csv-prev" ${result.offset===0?'disabled':''}>이전 100건</button><button id="csv-next" ${result.has_more?'':'disabled'}>다음 100건</button></div>`;
    document.querySelector('#csv-prev').addEventListener('click',()=>loadM01Csv(Math.max(0,csvReport.offset-100)));
    document.querySelector('#csv-next').addEventListener('click',()=>loadM01Csv(csvReport.offset+100));
    updateM01CompareButton();
  } catch(error) {document.querySelector('#csv-status').textContent=error.message;}
}
// M03 생성 결과 표시
let m03RequestNumber=0;
let m03View=null;
function m03ResultPath(runId, filename='result.json') {
  return /^(DEV|REF)-M03-\d{8}T\d{6}-[0-9a-f]{12}$/.test(runId||'')
    ?`/api/evaluations/m03/runs/${runId}/${filename}`:null;
}
async function m03Json(url, payload) {
  const session=ktlServerSessionId();
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),130000);
  try {
    const response=await fetch(url,{signal:controller.signal,...(payload===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})});
    const result=await response.json();
    ktlCheckServerSession(response,result,session);
    if(!response.ok) throw new Error(result?.error||`요청 오류 (${response.status})`);
    if(!result || typeof result!=='object' || Array.isArray(result)) throw new Error('API 응답 형식을 확인하세요.');
    return result;
  } catch(error) {if(error.name==='AbortError') throw new Error('API 응답 대기 시간을 초과했습니다.');throw error;}
  finally {clearTimeout(timer);}
}
function m03Remember(runId) {
  if(typeof history==='undefined' || typeof history.replaceState!=='function') return;
  const query=new URLSearchParams(location.search);
  if(m03ResultPath(runId)) query.set('run_id',runId); else query.delete('run_id');
  history.replaceState(null,'',`${location.pathname}?${query}`);
}
function renderM03(m) {
  const token=++m03RequestNumber;
  m03View={scenarios:[],attempts:[],result:null,sample:false,busy:false,savedRuns:[],executions:[],deletedCount:0,managementReady:false};
  document.title='DEVELOPMENT · M03 · Rainbow';
  app.innerHTML=`${banner('시나리오 생성 API 연동')}<a class="back" href="${link('/')}">← 전체 평가</a>
    <section class="page-heading"><div><p class="eyebrow">M03 / DEVELOPMENT</p><h1>${labels.M03}</h1><p class="subtitle">Test Scenario Generation</p></div><span class="badge neutral">API 결과 조회</span></section>
    <section class="evaluation-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2></div>
      <div class="dataset-grid"><div><label>입력 데이터셋</label><code id="m03-dataset">생성 결과 대기</code></div><div><label>평가 업무 수</label><strong id="m03-total">—</strong></div><div><label>M03 목표값</label><strong>≥ ${score(m.target,'M03')}</strong></div></div>
      <p id="m03-business-name" class="subtitle"></p><p id="m03-business-status" class="run-meta"></p>
      <div class="run-row"><p>업무별 생성 시나리오와 평가 결과를 확인합니다.</p><div class="m03-actions"><button id="m03-refresh" class="m03-secondary" type="button">결과 새로고침</button><button id="m03-generate" type="button">샘플 시나리오 생성</button></div></div>
      <p id="m03-status" role="status">저장된 생성 결과를 확인하고 있습니다…</p><progress id="m03-progress" max="10" value="0" hidden aria-label="시나리오 생성 진행률"></progress>
    </section><p id="m03-source" class="notice" hidden></p>
    <details class="m03-history"><summary>실제 생성기 연결 설정</summary>
      <p class="subtitle">외부 생성기 URL, 프로젝트 내부 분석 입력 manifest와 업무 정의를 입력하세요. 인증값은 입력하지 않고 서버 환경변수 이름만 지정합니다. 저장 버튼을 누를 때만 설정이 적용됩니다.</p>
      <p id="m03-connection-status" role="status">연결 설정 확인 중…</p>
      <textarea id="m03-connection-json" rows="16" aria-label="M03 연결 설정 JSON" spellcheck="false" style="width:100%;box-sizing:border-box"></textarea>
      <div class="m03-actions"><button id="m03-connection-template" class="m03-secondary" type="button">HTTP 연결 양식</button><button id="m03-connection-save" type="button">연결 설정 저장</button></div>
    </details>
    <section class="result-panel" id="m03-result"></section>
    <details class="m03-history"><summary>저장된 시나리오</summary><div id="m03-history"></div></details>
    <section class="result-panel m03-flow-panel"><div class="panel-heading"><div><h2>시나리오 흐름</h2><p class="subtitle">업무를 선택하고 노드를 누르면 단계별 내용을 볼 수 있습니다.</p></div><div class="m03-actions"><a id="m03-m04-handoff" class="outlined" hidden>M04에서 실행 준비 →</a><button id="m03-download" class="m03-secondary" type="button" disabled>시나리오 JSON ↓</button><button id="m03-delete" class="m03-secondary" type="button" disabled>선택 시나리오 삭제</button></div></div>
      <p id="m03-deletion-note" class="run-meta" hidden></p>
      <div class="m03-workspace"><aside class="m03-scenario-sidebar"><p class="m03-list-heading">생성된 업무</p><div id="m03-scenarios"></div></aside>
      <div class="m03-map-panel"><div class="m03-map-heading"><div><h3 id="m03-graph-title">시나리오 선택</h3><p id="m03-graph-meta"></p></div><div class="m03-zoom-controls"><button id="m03-zoom-out" type="button" aria-label="흐름도 축소">−</button><button id="m03-zoom-fit" type="button" aria-label="흐름도 화면에 맞춤">맞춤</button><span id="m03-zoom-value"></span><button id="m03-zoom-in" type="button" aria-label="흐름도 확대">＋</button></div></div>
        <div id="m03-graph-viewport" class="m03-graph-viewport" aria-label="생성된 시나리오의 단계 순서"></div>
        <p class="m03-graph-note">화살표는 API가 반환한 단계 배열의 순서입니다. 노드를 선택하면 원본 내용을 확인할 수 있습니다.</p>
        <div id="m03-step-detail" class="m03-step-detail" aria-live="polite"></div>
        <div id="m03-execution-results" class="m03-execution-results"></div>
        <details class="m03-raw"><summary>선택한 시나리오 원본 JSON</summary><pre id="m03-raw-json"></pre></details>
      </div></div></section>`;
  document.querySelector('#m03-generate').addEventListener('click',generateM03Sample);
  document.querySelector('#m03-refresh').addEventListener('click',refreshM03);
  document.querySelector('#m03-download').addEventListener('click',downloadM03);
  document.querySelector('#m03-delete').addEventListener('click',deleteM03Scenario);
  document.querySelector('#m03-connection-template').addEventListener('click',m03ConnectionTemplate);
  document.querySelector('#m03-connection-save').addEventListener('click',saveM03Connection);
  document.querySelector('#m03-history').addEventListener('click',event=>{
    const item=event.target.closest('[data-m03-run]');
    if(item&&!m03View.busy) openM03Saved(item.dataset.m03Run);
  });
  document.querySelector('#m03-scenarios').addEventListener('click',event=>{
    const item=event.target.closest('[data-scenario-index]');
    if(item) selectM03Scenario(Number(item.dataset.scenarioIndex));
  });
  const viewport=document.querySelector('#m03-graph-viewport');
  viewport.addEventListener('click',event=>{
    const node=event.target.closest('[data-step-index]');
    if(node) selectM03Step(Number(node.dataset.stepIndex));
  });
  viewport.addEventListener('keydown',event=>{
    const node=event.target.closest('[data-step-index]');
    if(node && ['Enter',' '].includes(event.key)) {event.preventDefault();selectM03Step(Number(node.dataset.stepIndex));}
  });
  let drag=null;
  viewport.addEventListener('pointerdown',event=>{
    if(event.pointerType==='touch'||event.button!==0||event.target.closest('[data-step-index]')) return;
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};
    viewport.setPointerCapture?.(event.pointerId);viewport.classList.toggle('dragging',true);
  });
  viewport.addEventListener('pointermove',event=>{
    if(!drag||drag.id!==event.pointerId) return;
    viewport.scrollLeft=drag.left+drag.x-event.clientX;viewport.scrollTop=drag.top+drag.y-event.clientY;
  });
  const endDrag=()=>{drag=null;viewport.classList.toggle('dragging',false);};
  viewport.addEventListener('pointerup',endDrag);viewport.addEventListener('pointercancel',endDrag);viewport.addEventListener('lostpointercapture',endDrag);
  document.querySelector('#m03-zoom-out').addEventListener('click',()=>zoomM03(-1));
  document.querySelector('#m03-zoom-fit').addEventListener('click',()=>zoomM03(0));
  document.querySelector('#m03-zoom-in').addEventListener('click',()=>zoomM03(1));
  paintM03();
  const requestedId=new URLSearchParams(location.search).get('run_id');
  if(requestedId && !m03ResultPath(requestedId)) {
    document.querySelector('#m03-status').textContent='결과 주소의 실행 ID를 확인하세요.';
    return;
  }
  prepareM03(m.latest,token,requestedId).catch(error=>{if(token===m03RequestNumber) document.querySelector('#m03-status').textContent=error.message;});
}
// M03 확정 업무 입력
function validateM03Context(template) {
  const units=template.business_units;
  const mock=template.generator_mode==='MOCK',real=template.generator_mode==='REAL';
  if(template.run_mode!=='DEVELOPMENT'||(!mock&&!real)||template.synthetic!==mock||!(mock?/^m03-mock-development-[0-9a-f]{12}$/:/^m03-real-development-[0-9a-f]{12}$/).test(template.dataset_id)||!/^[0-9a-f]{64}$/.test(template.dataset_manifest_sha256)) throw new Error('DEVELOPMENT 생성기 설정을 확인하세요.');
  if(!Array.isArray(units)||!units.length||units.length>10||units.some(row=>!row?.business_unit_id||!row?.workflow_id)||new Set(units.map(row=>row.business_unit_id)).size!==units.length) throw new Error('생성할 업무 목록을 확인하세요.');
  if(real&&(!template.real_generator_configured||!template.verified_input?.manifest_sha256||!template.source_module||!template.source_version)) throw new Error('실제 생성기의 분석 입력·버전 설정을 확인하세요.');
}
async function prepareM03(latest,token,runId) {
  const contextTask=(async()=>{
    const template=await m03Json('/api/development/m03/context');
    if(token!==m03RequestNumber) return;
    validateM03Context(template);m03View.context=template;paintM03();
  })();
  const scoped=!!ktlServerSessionId();
  const savedTask=(async()=>{
    if(scoped) {await loadM03History(token);if(token!==m03RequestNumber) return;}
    await readM03Result(latest,token,runId);
  })();
  const [contextResult,savedResult]=await Promise.allSettled([contextTask,savedTask,...(scoped?[]:[loadM03History(token)]),loadM03Connection(token)]);
  if(token!==m03RequestNumber) return;
  if(savedResult.status==='rejected') throw savedResult.reason;
  if(contextResult.status==='rejected'&&!m03View.result) document.querySelector('#m03-status').textContent=contextResult.reason.message;
}
function paintM03() {
  const state=m03View,r=state.result,d=r?.details||{};
  const definition=d.external_details?.business_definition||state.context?.business_definition;
  const historical=!!r&&!!state.context&&r.dataset_id!==state.context.dataset_id;
  document.querySelector('#m03-business-name').textContent=historical&&!d.external_details?.business_definition?'이전 업무 정의 · 원본 시나리오 참조':definition?`${definition.business_unit_id} ${definition.business_name}${definition.definition_version?' · 업무 정의 v'+definition.definition_version:''}`:state.context?.business_definitions?.length?`${state.context.business_definitions.length}개 업무 정의`:'';
  document.querySelector('#m03-business-status').textContent=historical?'이전 입력으로 생성한 보관 결과입니다. 새 생성에는 현재 확정 업무를 사용합니다.':state.context?.generator_mode==='REAL'?`실제 분석 입력 · ${state.context.verified_input.dataset_id} · ${state.context.source_module} ${state.context.source_version}`:definition?`${definition.business_unit_id} · ${definition.confirmed_on} 사용자 확정 · 개발용 워크플로 ID 사용 · 실제 분석 결과 연결 대기`:'';
  document.querySelector('#m03-dataset').textContent=r?.dataset_id||state.context?.dataset_id||(state.sample?'DEVELOPMENT 샘플 준비 중':'생성 결과 대기');
  document.querySelector('#m03-total').textContent=String(d.total_scenario_count??(state.scenarios.length||state.context?.business_units.length||'—'));
  document.querySelector('#m03-generate').disabled=state.busy||state.connectionBusy||(state.connection?.current_mode==='REAL'&&!state.connection.configured);
  document.querySelector('#m03-generate').textContent=state.context?.generator_mode==='REAL'?'시나리오 생성':'샘플 시나리오 생성';
  document.querySelector('#m03-download').disabled=!state.scenarios.length;
  const selected=state.scenarios[state.selectedScenario||0];
  document.querySelector('#m03-delete').disabled=state.busy||!state.managementReady||!selected?.scenario_id||!r;
  const deletionNote=document.querySelector('#m03-deletion-note');
  deletionNote.hidden=!state.deletedCount;
  deletionNote.textContent=`삭제한 시나리오 ${state.deletedCount}건 · 평가 원본과 기존 실행 결과는 보존되며 생성률은 변경되지 않습니다.`;
  paintM03History();
  const source=document.querySelector('#m03-source');source.hidden=!state.sample;
  const placeholder=state.scenarios.length&&state.scenarios.every(row=>row.steps?.length===2&&row.steps[0]?.target==='mock workflow screen'&&row.steps[1]?.target==='mock action control');
  source.textContent=placeholder?'현재 Mock API는 모든 업무에 동일한 2단계 예시를 반환합니다. 실제 업무명과 절차는 생성기 연결 후 표시됩니다.':'샘플 API 연동 결과입니다. 실제 수집 CSV를 분석한 시나리오나 공식 시험 결과가 아닙니다.';
  const threshold=r?.threshold_met==null?'—':r.threshold_met?'목표 충족':'목표 미충족';
  document.querySelector('#m03-result').innerHTML=`<div class="panel-heading"><h2>Development Result</h2>${r&&m03ResultPath(r.run_id)?`<a class="download" href="${m03ResultPath(r.run_id,'evidence.csv')}" download>검증 근거 CSV ↓</a>`:''}</div><div class="result-grid"><div><label>자동생성 성공률${state.sample?' · 샘플':''}</label><strong class="large-score">${score(r?.score,'M03')}</strong></div><div><label>생성 성공 업무</label><strong>${esc(d.successful_scenario_count??'—')}</strong></div><div><label>전체 평가 업무</label><strong>${esc(d.total_scenario_count??'—')}</strong></div><div><label>목표 대비 결과</label><strong>${threshold}</strong></div></div><p class="subtitle">성공 업무 수 / 전체 평가 업무 수 × 100 · 필수항목, 단계 순서, action/target 검증</p>${r?`<p class="run-meta">${esc(r.run_id)} · ${esc(r.completed_at)} · ${esc(r.run_mode)}</p>`:'<p class="empty">평가 API의 결과가 도착하면 성공률을 표시합니다.</p>'}`;
  const validations=new Map((Array.isArray(d.rows)?d.rows:[]).map(row=>[row.business_unit_id,row]));
  if(!Number.isInteger(state.selectedScenario)||!state.scenarios[state.selectedScenario]) state.selectedScenario=0;
  const current=state.scenarios[state.selectedScenario];
  for(const metric of ['m04']) {
    const handoff=document.querySelector(`#m03-${metric}-handoff`);
    handoff.hidden=!(state.managementReady&&r?.run_mode==='DEVELOPMENT'&&m03ResultPath(r.run_id)&&typeof current?.scenario_id==='string'&&current.scenario_id.trim()&&current.status!=='FAILED');
    if(!handoff.hidden) handoff.href=`/metrics/${metric}?${new URLSearchParams({mode:'DEVELOPMENT',m03_run_id:r.run_id,scenario_id:current.scenario_id})}`;
    else handoff.removeAttribute('href');
  }
  document.querySelector('#m03-scenarios').innerHTML=state.scenarios.length?state.scenarios.map((row,index)=>{
    const validation=validations.get(row.business_unit_id);
    const steps=Array.isArray(row.steps)?row.steps:[];
    const label=validation?(validation.success?'생성 성공':'생성 실패'):row.status==='FAILED'?'요청 실패':'평가 대기';
    return `<button type="button" class="m03-scenario ${index===state.selectedScenario?'selected':''}" data-scenario-index="${index}" aria-pressed="${index===state.selectedScenario}"><span class="m03-scenario-name"><strong>${esc(row.scenario_name||row.business_unit_id)}</strong><small>${esc(row.workflow_id||'워크플로 ID 없음')} · ${steps.length}단계</small></span><span class="badge ${validation?.success?'pass':validation||row.status==='FAILED'?'warning':'neutral'}">${label}</span></button>`;
  }).join(''):'<p class="empty">생성 API에서 받은 시나리오가 여기에 표시됩니다.</p>';
  paintM03Graph();
  paintM03Executions();
  paintM03Connection();
}

async function loadM03Connection(token) {
  try {
    const value=await m03Json('/api/development/m03/connection');
    if(token!==m03RequestNumber) return;
    if(!value.m03||typeof value.configured!=='boolean') throw new Error('M03 연결 설정 응답을 확인하세요.');
    m03View.connection=value;m03View.connectionError='';
    document.querySelector('#m03-connection-json').value=JSON.stringify(value.m03,null,2);
    paintM03();
  } catch(error) {
    if(token===m03RequestNumber) {m03View.connectionError=error.message;paintM03Connection();}
  }
}
function paintM03Connection() {
  const state=m03View,value=state.connection;
  document.querySelector('#m03-connection-status').textContent=state.connectionError||(!value?'연결 설정 확인 중…':`${value.current_mode} · ${value.transport} · ${value.configured?'설정 준비 완료':'실제 연결 준비 필요'} · ${value.message}${value.missing?.length?' · 필요한 항목: '+value.missing.join(', '):''}`);
  for(const id of ['#m03-connection-json','#m03-connection-template','#m03-connection-save']) document.querySelector(id).disabled=!!(state.busy||state.connectionBusy);
}
function m03ConnectionTemplate() {
  if(m03View.busy||m03View.connectionBusy) return;
  document.querySelector('#m03-connection-json').value=JSON.stringify({generator_mode:'REAL',transport:'HTTP',http:{url:'',timeout_seconds:120,max_response_bytes:4194304,auth_env:'',auth_header:'Authorization',auth_prefix:'Bearer '},input_manifest:'',source_module:'',source_version:'',business_units:[]},null,2);
  document.querySelector('#m03-connection-status').textContent='실제 제공받은 URL·분석 입력·업무 정의를 채운 뒤 저장하세요. 아직 적용되지 않았습니다.';
}
async function saveM03Connection() {
  const state=m03View;if(state.busy||state.connectionBusy) return;
  const token=m03RequestNumber;
  try {
    let settings;
    try {settings=JSON.parse(document.querySelector('#m03-connection-json').value);}
    catch {throw new Error('연결 설정 JSON 구문을 확인하세요. 인증값은 입력하지 않습니다.');}
    if(!settings||typeof settings!=='object'||Array.isArray(settings)) throw new Error('연결 설정은 JSON 객체여야 합니다.');
    state.connectionBusy=true;paintM03();
    const value=await m03Json('/api/development/m03/connection',{m03:settings});
    if(token!==m03RequestNumber) return;
    state.connection=value;state.connectionError='';
    await refreshM03();
  } catch(error) {
    if(token===m03RequestNumber) {state.connectionError=error.message;paintM03Connection();}
  } finally {if(token===m03RequestNumber) {state.connectionBusy=false;paintM03();}}
}

// M03 저장 목록과 실행 결과
function m03ManagementPath(runId, part='scenarios') {
  return m03ResultPath(runId)?`/api/development/m03/runs/${runId}/${part}`:null;
}
async function loadM03History(token) {
  try {
    const data=await m03Json('/api/development/m03/runs');
    if(token!==m03RequestNumber) return;
    if(data.run_mode!=='DEVELOPMENT'||!Array.isArray(data.runs)) throw new Error('저장 목록 형식을 확인하세요.');
    m03View.savedRuns=data.runs.filter(row=>m03ResultPath(row.run_id));m03View.historyError='';paintM03History();
  } catch(error) {if(token===m03RequestNumber) {m03View.historyError=error.message;paintM03History();}}
}
function paintM03History() {
  const state=m03View;
  document.querySelector('#m03-history').innerHTML=state.historyError?`<p class="notice">${esc(state.historyError)}</p>`:state.savedRuns?.length?state.savedRuns.map(row=>`<button class="m03-saved-run ${row.run_id===state.result?.run_id?'selected':''}" type="button" data-m03-run="${esc(row.run_id)}" ${state.busy?'disabled':''}><strong>${esc(row.completed_at||row.run_id)}</strong><span>시나리오 ${esc(row.active_scenario_count)}건${row.deleted_scenario_count?' · 삭제 '+esc(row.deleted_scenario_count)+'건':''} · 생성률 ${score(row.score,'M03')}${row.synthetic?' · 샘플':''}</span><small>${esc(row.run_id)}</small></button>`).join(''):'<p class="empty">저장된 시나리오가 없습니다.</p>';
}
async function openM03Saved(runId) {
  if(m03View.busy||!m03ResultPath(runId)) return;
  const token=++m03RequestNumber;
  m03View.scenarios=[];m03View.executions=[];m03View.selectedScenario=0;m03View.selectedStep=0;m03View.managementReady=false;
  m03View.busy=true;paintM03();
  try {await readM03Result(null,token,runId);}
  catch(error) {if(token===m03RequestNumber) document.querySelector('#m03-status').textContent=error.message;}
  finally {if(token===m03RequestNumber) {m03View.busy=false;paintM03();}}
}
function paintM03Executions() {
  const row=m03View.scenarios[m03View.selectedScenario],target=document.querySelector('#m03-execution-results');
  if(!row) {target.innerHTML='';return;}
  const runs=(m03View.executions||[]).filter(item=>item.scenario_id===row.scenario_id);
  target.innerHTML=`<h3>M04 실행 결과</h3>${m03View.executionError?`<p class="subtitle">${esc(m03View.executionError)}</p>`:runs.length?runs.map(item=>`<a class="m03-execution" href="/metrics/m04?${new URLSearchParams({mode:'DEVELOPMENT',execution_id:item.execution_id})}"><span class="badge ${item.status==='PASS'?'pass':item.status==='FAIL'||item.status==='ERROR'?'warning':'neutral'}">${esc(item.status||item.execution_status)}</span><span>${esc(item.started_at||'실행 시각 없음')}${item.duration_ms!=null?' · '+esc((item.duration_ms/1000).toFixed(2))+'초':''}${item.error?' · '+esc(item.error):''}</span><small>상세 결과 →</small></a>`).join(''):'<p class="subtitle">이 시나리오의 M04 실행 결과가 없습니다.</p>'}`;
}
async function loadM03Management(runId,token) {
  const [state,executions]=await Promise.allSettled([m03Json(m03ManagementPath(runId)),m03Json(m03ManagementPath(runId,'executions'))]);
  if(token!==m03RequestNumber) return;
  if(state.status==='rejected') throw state.reason;
  if(state.value.run_id!==runId||!Array.isArray(state.value.scenarios)||!Array.isArray(state.value.deleted_scenario_ids)) throw new Error('저장 시나리오 관리 응답을 확인하세요.');
  m03View.scenarios=state.value.scenarios;m03View.deletedCount=state.value.deleted_scenario_ids.length;m03View.managementReady=true;
  m03View.executions=executions.status==='fulfilled'&&Array.isArray(executions.value.executions)?executions.value.executions:[];
  m03View.executionError=executions.status==='rejected'?executions.reason.message:'';
}
async function deleteM03Scenario() {
  const state=m03View,row=state.scenarios[state.selectedScenario],runId=state.result?.run_id;
  if(state.busy||!state.managementReady||!row?.scenario_id||!m03ResultPath(runId)) return;
  if(!window.confirm(`“${row.scenario_name||row.scenario_id}” 시나리오를 삭제할까요?\n평가 원본과 기존 실행 기록은 보존됩니다.`)) return;
  state.busy=true;paintM03();const token=m03RequestNumber;
  try {
    const data=await m03Json(m03ManagementPath(runId,'scenarios/delete'),{scenario_id:row.scenario_id});
    if(token!==m03RequestNumber) return;
    if(data.run_id!==runId||!Array.isArray(data.scenarios)||!Array.isArray(data.deleted_scenario_ids)) throw new Error('삭제 결과 형식을 확인하세요.');
    state.scenarios=data.scenarios;state.deletedCount=data.deleted_scenario_ids.length;state.selectedScenario=0;state.selectedStep=0;state.zoom=null;
    await loadM03History(token);
    document.querySelector('#m03-status').textContent='선택한 시나리오를 삭제했습니다. 평가 원본과 기존 실행 결과는 보존됩니다.';
  } catch(error) {if(token===m03RequestNumber) document.querySelector('#m03-status').textContent=error.message;}
  finally {if(token===m03RequestNumber) {state.busy=false;paintM03();}}
}
// M03 단계 흐름도
const m03ActionNames={open:'화면 열기',navigate:'화면 이동',click:'클릭',input:'입력',type:'입력',clear:'입력 지우기',select:'선택',change:'변경',submit:'제출',save:'저장',verify:'결과 확인',assert:'기대 결과 확인',wait:'대기',network:'API 요청'};
function m03ActionName(action) {
  return Object.prototype.hasOwnProperty.call(m03ActionNames,action)?m03ActionNames[action]:String(action||'단계 정보 확인 필요');
}
function selectM03Scenario(index) {
  if(!Number.isInteger(index)||!m03View?.scenarios[index]) return;
  m03View.selectedScenario=index;m03View.selectedStep=0;m03View.zoom=null;paintM03();
  document.querySelector(`[data-scenario-index="${index}"]`)?.focus?.();
}
function selectM03Step(index) {
  const row=m03View?.scenarios[m03View.selectedScenario];
  if(!Number.isInteger(index)||!Array.isArray(row?.steps)||index<0||index>=row.steps.length) return;
  m03View.selectedStep=index;paintM03Graph();
  document.querySelector(`[data-step-index="${index}"]`)?.focus?.();
}
function zoomM03(direction) {
  if(!m03View) return;
  m03View.zoom=direction===0?null:Math.max(.35,Math.min(1.75,(m03View.zoom||1)+direction*.15));
  paintM03Graph();
}
function paintM03Graph() {
  const state=m03View,row=state.scenarios[state.selectedScenario];
  const viewport=document.querySelector('#m03-graph-viewport');
  const detail=document.querySelector('#m03-step-detail');
  document.querySelector('#m03-raw-json').textContent=row?JSON.stringify(row,null,2):'시나리오 대기 중';
  document.querySelector('#m03-graph-title').textContent=row?.scenario_name||row?.business_unit_id||'시나리오 선택';
  const steps=Array.isArray(row?.steps)?row.steps:[];
  const validation=state.result?.details?.rows?.find(item=>item.business_unit_id===row?.business_unit_id);
  const reasons=validation?Object.entries({schema_valid:'필수항목·형식',step_order_valid:'단계 순서',action_present:'action',target_present:'target'}).filter(([key])=>!validation[key]).map(([,name])=>name+' 확인 필요'):[];
  if(row?.status==='FAILED') reasons.push(row.error||'생성 요청 실패');
  document.querySelector('#m03-graph-meta').textContent=row?`${steps.length}개 단계 · ${row.scenario_id||'시나리오 ID 없음'}${reasons.length?' · '+reasons.join(' · '):''}`:'생성 결과를 기다리고 있습니다.';
  for(const id of ['#m03-zoom-in','#m03-zoom-out','#m03-zoom-fit']) document.querySelector(id).disabled=!steps.length;
  if(!steps.length) {viewport.innerHTML='<p class="empty">표시할 시나리오 단계가 없습니다.</p>';detail.innerHTML='';document.querySelector('#m03-zoom-value').textContent='—';return;}
  if(!Number.isInteger(state.selectedStep)||state.selectedStep<0||state.selectedStep>=steps.length) state.selectedStep=0;
  const columns=Math.min(3,steps.length),width=columns*260+60,height=Math.ceil(steps.length/3)*150+60;
  const positions=steps.map((_,index)=>{const line=Math.floor(index/3),col=index%3;return {x:30+(line%2?2-col:col)*260,y:30+line*150};});
  const fit=Math.max(.35,Math.min(1,((viewport.clientWidth||840)-40)/width));
  const zoom=state.zoom??fit;state.zoom=zoom;
  document.querySelector('#m03-zoom-value').textContent=Math.round(zoom*100)+'%';
  const edges=positions.slice(1).map((to,index)=>{
    const from=positions[index];let path;
    if(from.y===to.y) {
      const forward=to.x>from.x,start=forward?from.x+220:from.x,end=forward?to.x:to.x+220;
      path=`M ${start} ${from.y+49} H ${end}`;
    } else path=`M ${from.x+110} ${from.y+98} V ${to.y}`;
    return `<path class="m03-edge" d="${path}" marker-end="url(#m03-arrow)"/>`;
  }).join('');
  const wrap=value=>{const chars=Array.from(String(value??''));return [chars.slice(0,22).join(''),chars.slice(22,43).join('')+(chars.length>43?'…':'')];};
  const nodes=steps.map((step,index)=>{
    const {x,y}=positions[index],action=String(step?.action||'action 없음'),target=String(step?.target||'target 없음'),lines=wrap(target);
    return `<g class="m03-node ${index===state.selectedStep?'selected':''}" data-step-index="${index}" tabindex="0" role="button" aria-label="단계 ${esc(step?.order??'없음')} · ${esc(action)} · ${esc(target)}" aria-pressed="${index===state.selectedStep}" transform="translate(${x} ${y})"><title>${esc(action+' · '+target)}</title><rect width="220" height="98" rx="10"/><circle cx="24" cy="24" r="13"/><text class="m03-node-order" x="24" y="28" text-anchor="middle">${esc(step?.order??'—')}</text><text class="m03-node-label" x="46" y="28">${esc(Array.from(m03ActionName(action)).slice(0,18).join(''))}</text><text class="m03-node-target" x="15" y="55">${esc(lines[0])}</text><text class="m03-node-target" x="15" y="74">${esc(lines[1])}</text><text class="m03-node-action" x="15" y="90">${esc(Array.from(action).slice(0,30).join(''))}</text></g>`;
  }).join('');
  viewport.innerHTML=`<svg id="m03-graph" width="${Math.round(width*zoom)}" height="${Math.round(height*zoom)}" viewBox="0 0 ${width} ${height}" aria-label="${steps.length}개 생성 단계"><defs><marker id="m03-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>${edges}${nodes}</svg>`;
  const step=steps[state.selectedStep];
  detail.innerHTML=`<div class="m03-detail-heading"><span class="metric-id">STEP ${esc(step?.order??'—')}</span><h3>${esc(m03ActionName(step?.action))}</h3></div><dl><div><dt>원본 action</dt><dd>${esc(step?.action||'제공되지 않음')}</dd></div><div><dt>대상</dt><dd>${esc(step?.target||'제공되지 않음')}</dd></div>${step?.expected_result?`<div><dt>기대 결과</dt><dd>${esc(step.expected_result)}</dd></div>`:''}${step?.page_url||step?.url?`<div><dt>화면 URL</dt><dd>${esc(step.page_url||step.url)}</dd></div>`:''}</dl><details><summary>선택한 단계 원본 JSON</summary><pre>${esc(JSON.stringify(step,null,2))}</pre></details>`;
}
async function readM03Result(latest,token,runId) {
  const candidate=runId||latest?.run_id;
  if(ktlServerSessionId()&&candidate&&!m03View.savedRuns.some(row=>row.run_id===candidate)) {
    m03View.result=null;m03View.scenarios=[];m03View.executions=[];m03View.managementReady=false;
    m03Remember(null);paintM03();return;
  }
  const r=runId?await m03Json(m03ResultPath(runId)):latest;
  if(token!==m03RequestNumber) return;
  if(!r) {document.querySelector('#m03-status').textContent='저장된 생성 결과가 없습니다. 샘플 시나리오 생성으로 확인하세요.';return;}
  if(r.metric_id!=='M03' || r.run_mode!=='DEVELOPMENT' || !m03ResultPath(r.run_id)) throw new Error('M03 DEVELOPMENT 결과 형식을 확인하세요.');
  const raw=await m03Json(m03ResultPath(r.run_id,'received_payload.json'));
  if(token!==m03RequestNumber) return;
  if(!Array.isArray(raw.scenarios)||raw.scenarios.some(row=>!row||typeof row!=='object'||Array.isArray(row))) throw new Error('저장 결과에 원본 시나리오가 없습니다.');
  await loadM03Management(r.run_id,token);
  if(token!==m03RequestNumber) return;
  m03View.result=r;
  m03View.sample=r.run_mode==='REFERENCE'||r.details?.external_details?.synthetic===true||raw.scenarios.some(row=>row.synthetic===true||row.generator_mode==='MOCK');
  paintM03();m03Remember(r.run_id);
  document.querySelector('#m03-status').textContent='저장된 생성 시나리오와 평가 결과를 불러왔습니다.';
}
async function refreshM03() {
  const token=++m03RequestNumber;
  if(m03View) m03View.busy=false;
  document.querySelector('#m03-progress').hidden=true;
  document.querySelector('#m03-generate').disabled=false;
  document.querySelector('#m03-status').textContent='실제 생성 결과를 확인하고 있습니다…';
  try {
    const data=await m03Json('/api/evaluations?mode=DEVELOPMENT');
    if(token!==m03RequestNumber) return;
    const metric=data.metrics?.find(row=>row.metric_id==='M03');
    if(!metric) throw new Error('M03 평가 정보를 찾을 수 없습니다.');
    m03Remember(null);renderM03(metric);
  } catch(error) {if(token===m03RequestNumber) document.querySelector('#m03-status').textContent=error.message;}
}
async function generateM03Sample() {
  if(m03View.busy) return;
  const token=++m03RequestNumber;
  const context=m03View.context;
  m03View={scenarios:[],attempts:[],result:null,sample:context?.synthetic??true,busy:true,context,savedRuns:m03View.savedRuns||[],executions:[],deletedCount:0,managementReady:false,connection:m03View.connection};m03Remember(null);paintM03();
  const current=()=>token===m03RequestNumber;
  const status=document.querySelector('#m03-status'),progress=document.querySelector('#m03-progress');
  progress.value=0;progress.hidden=false;status.textContent='생성 API를 호출하고 있습니다…';
  try {
    const template=await m03Json('/api/development/m03/context');
    if(!current()) return;
    validateM03Context(template);
    const units=template.business_units;
    m03View.context=template;m03View.sample=template.synthetic;paintM03();
    progress.max=units.length;
    for(const unit of units) {
      if(!current()) return;
      status.textContent=`${template.synthetic?'샘플 ':''}생성 중 · ${m03View.scenarios.length+1}/${units.length} · ${unit.business_unit_id}`;
      let scenario;
      const attempt={business_unit_id:unit.business_unit_id};
      m03View.attempts.push(attempt);
      try {
        scenario=await m03Json('/api/m03/generate',{business_unit_id:unit.business_unit_id,workflow_id:unit.workflow_id,run_mode:'DEVELOPMENT',generator_mode:template.generator_mode});
        if(!current()) return;
        attempt.response=scenario;
        if(scenario.business_unit_id!==unit.business_unit_id||scenario.workflow_id!==unit.workflow_id||scenario.run_mode!=='DEVELOPMENT'||scenario.synthetic!==template.synthetic||scenario.generator_mode!==template.generator_mode||!['SUCCESS','FAILED'].includes(scenario.status)) throw new Error('생성 응답의 업무·워크플로 또는 생성기 구분을 확인하세요.');
      } catch(error) {
        if(!current()) return;
        scenario={business_unit_id:unit.business_unit_id,workflow_id:unit.workflow_id,status:'FAILED',synthetic:template.synthetic,generator_mode:template.generator_mode,error:error.message};
        attempt.error=error.message;
      }
      m03View.scenarios.push(scenario);progress.value=m03View.scenarios.length;paintM03();
    }
    if(!current()) return;
    status.textContent='생성 응답을 평가 API로 보내 검증·저장하고 있습니다…';
    const payload={external_run_id:'M03-UI-'+crypto.randomUUID(),dataset_id:template.dataset_id,run_mode:'DEVELOPMENT',source_module:template.source_module,source_version:template.source_version,submitted_at:new Date().toISOString(),dataset_manifest_sha256:template.dataset_manifest_sha256,details:{synthetic:template.synthetic,generator_mode:template.generator_mode,note:template.synthetic?'DEVELOPMENT 생성 API의 Mock 응답을 순서대로 평가한 화면 연동 검사':'검증된 분석 입력의 실제 생성 응답을 순서대로 평가한 DEVELOPMENT 결과',business_definition:template.business_definition,business_definitions:template.business_definitions,verified_input:template.verified_input,generation_attempts:m03View.attempts},scenarios:m03View.scenarios};
    const result=await m03Json('/api/integrations/m03/result',payload);
    if(!current()) return;
    if(result.metric_id!=='M03'||result.run_mode!=='DEVELOPMENT'||!m03ResultPath(result.run_id)) throw new Error('평가 API의 M03 결과 형식을 확인하세요.');
    m03View.result=result;paintM03();m03Remember(result.run_id);
    await loadM03Management(result.run_id,token);
    if(!current()) return;
    await loadM03History(token);paintM03();
    status.textContent=`${template.synthetic?'샘플 ':''}생성 → 평가 → 저장을 완료했습니다. 업무와 노드를 선택하면 단계별 내용을 볼 수 있습니다.`;
  } catch(error) {if(current()) status.textContent=`평가 완료 전 · ${error.message}`;}
  finally {if(current()) {m03View.busy=false;progress.hidden=true;paintM03();}}
}
function downloadM03() {
  if(!m03View?.scenarios.length) return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(m03View.scenarios,null,2)+'\n'],{type:'application/json;charset=utf-8'}));
  const anchor=document.createElement('a');anchor.href=url;anchor.download='m03-scenarios.json';document.body.append(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
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
  const requestNumber=++catalogRequestNumber;
  try {
    const response=await fetch(`/api/evaluations?mode=${mode}`);
    const data=await response.json();
    if(requestNumber!==catalogRequestNumber) return;
    if (!response.ok) throw new Error(data.error||'평가 정보 조회 실패');
    catalog=data;serverSessionReloading=false;
    render();
  } catch(error) {if(requestNumber===catalogRequestNumber) {app.innerHTML=`<p class="notice">${esc(error.message)}</p><button id="retry">다시 시도</button>`;document.querySelector('#retry').addEventListener('click',load);}}
}
load();
