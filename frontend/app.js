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
  if (!ref && r.run_mode === 'OFFICIAL' && r.status === 'COMPLETED' && typeof r.official_pass === 'boolean') return `<span class="badge ${r.official_pass ? 'pass':'fail'}">${r.official_pass ? 'PASS':'FAIL'}</span>`;
  return `<span class="badge ${r.status === 'COMPLETED' ? 'neutral':'warning'}">${esc(r.status === 'READY' && dev ? '개발 평가 실행 가능' : statuses[r.status] || r.status)}</span>`;
}
function banner() {
  return `<div class="mode-switch" aria-label="평가 모드"><a class="${ref?'selected':''}" href="${location.pathname}?mode=REFERENCE">REFERENCE</a><a class="${mode==='OFFICIAL'?'selected':''}" href="${location.pathname}?mode=OFFICIAL">OFFICIAL</a><a class="${dev?'selected':''}" href="${location.pathname}?mode=DEVELOPMENT">DEVELOPMENT</a></div><p class="notice">${dev?'DEVELOPMENT DATASET · current_site_dev_01 · 공식 시험성적 아님':ref?'V6.2 Historical Reference를 사용한 평가 프로그램 검증 모드입니다. 공식 시험성적이 아닙니다.':'OFFICIAL · 공식 dataset manifest, 입력 해시 및 필요한 모델/모듈 연결이 있어야 실행할 수 있습니다.'}</p>`;
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
  const r=m.latest;
  document.title=`${mode} · ${m.metric_id} · Rainbow`;
  app.innerHTML=`${banner()}<a class="back" href="${link('/')}">← 전체 평가</a><section class="page-heading"><div><p class="eyebrow">${m.metric_id} / ${mode}</p><h1>${labels[m.metric_id]}</h1><p class="subtitle">${esc(m.metric_name)}</p></div>${badge(m)}</section><section class="evaluation-panel"><div class="panel-heading"><h2>입력 및 현재 준비 상태</h2></div><div class="dataset-grid"><div><label>테스트 데이터셋</label><code>${esc(m.dataset || '공식 평가 데이터 대기 중')}</code></div><div><label>${dev?'개발 데이터 입력 수':ref?'Reference 케이스 / 입력 수':'공식 설계 케이스 수'}</label><strong>${dev?(m.latest?.sample_count??'—'):ref?(m.details.ground_truth_count??m.details.workflow_count??m.details.process_model_count??'—'):(m.expected_sample_count??'실제 생성 코드 수')}</strong></div><div><label>${ref?'Target Reference':'Target'}</label><strong>${m.target==null?'미설정':esc(m.operator)+' '+score(m.target,m.metric_id)}</strong></div></div>${detailView(m.details)}${m.error?`<p class="notice">${esc(m.error)}</p>`:''}<div class="run-row"><p>실행 또는 준비 상태 확인 결과를 근거 파일로 저장합니다.</p><button id="run">${dev && ['M02','M06'].includes(m.metric_id)?'개발 모델 및 M02/M06 실행':['READY','REFERENCE_READY'].includes(m.status)?'평가 실행':'준비 상태 기록'} →</button></div></section><p id="run-status" role="status"></p><section class="result-panel"><div class="panel-heading"><h2>${dev?'DEVELOPMENT RESULT':ref?'Reference Result':'공식 실행 결과'}</h2>${r?`<a class="download" href="${esc(r.evidence_file)}" download>CSV 다운로드 ↓</a>`:''}</div><div class="result-grid"><div><label>${ref?'Reference Score':'Measured Score'}</label><strong class="large-score">${score(r?.score,m.metric_id)}</strong></div><div><label>실행 시 목표값</label><strong>${r?.target==null?'—':esc(r.operator)+' '+score(r.target,m.metric_id)}</strong></div><div><label>${nonofficial?'Threshold Met (비공식)':'공식 판정'}</label><strong>${nonofficial?(r?.threshold_met==null?'—':r.threshold_met?'YES':'NO'):''}</strong>${nonofficial?'':badge(r)}</div><div><label>실행 상태</label>${badge(r)}</div></div>${r?`<p class="run-meta">${esc(r.run_id)} · ${esc(r.completed_at)}</p>${r.error?`<p class="notice">${esc(r.error)}</p>`:''}${detailView(r.details)}<a class="download" href="${esc(r.manifest_file)}">Run manifest</a><details><summary>결과 및 입력 해시</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`:'<p class="empty">아직 이 모드의 실행 기록이 없습니다.</p>'}</section>`;
  document.querySelector('#run').addEventListener('click',()=>run(m.metric_id));
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
