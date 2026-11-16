/* Display-only presentation layer. All measurements and verdicts come from the server. */
const labels = {M01:'수집 정확도',M02:'프로세스맵 정확도 및 완전성',M03:'테스트 시나리오 자동생성률',M04:'자동 실행 성공률',M05:'AI 데이터 정제 F1 Score',M06:'워크플로우 클러스터링 품질',M07:'LLM 생성 코드 유효성 및 정확도'};
const app = document.querySelector('#app');
let catalog;
let running = false;
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const score = (value,id) => value == null ? '—' : `${Number(value).toFixed(['M05','M06'].includes(id)?4:2)}${['M05','M06'].includes(id)?'':'%'}`;
const number = value => value == null ? '—' : typeof value==='number'&&!Number.isInteger(value)?value.toFixed(4):String(value);
function badge(item) {
  if(item?.status==='COMPLETED' && typeof item.threshold_met==='boolean') return `<span class="badge ${item.threshold_met?'pass':'fail'}">${item.threshold_met?'PASS':'FAIL'}</span>`;
  return `<span class="badge neutral">${item?.status==='READY'?'측정 가능':item?.status==='COMPLETED'?'측정 완료':'준비'}</span>`;
}
function stats(items) { return `<div class="detail-stats">${items.map(([label,value])=>`<div><label>${esc(label)}</label><strong>${esc(value)}</strong></div>`).join('')}</div>`; }
function metricFields(id,d={}) {
  const fields={M02:[['Accuracy (%)','accuracy'],['Completeness (%)','completeness'],['평가 대상 GT 수','ground_truth_count'],['전체 생성 업무 절차','evaluated_procedures'],['직접 매핑 절차','correctly_mapped'],['충족 GT 절차','included_required'],['필수 GT 절차','defined_required']],M03:[['Total scenarios','total_scenarios'],['Success','success'],['Failure','failure']],M05:[['TP','tp'],['FP','fp'],['FN','fn'],['TN','tn'],['Precision','precision'],['Recall','recall']],M06:[['Workflow count','workflow_count'],['Cluster count','cluster_count'],['Embedding dimension','dimensions']]};
  return (fields[id]||[]).filter(([,key])=>d[key]!=null).map(([label,key])=>[label,number(d[key])]);
}
function render() {
  const metrics=catalog.metrics;
  const id=location.pathname.match(/^\/metrics\/(m0[1-7])\/?$/i)?.[1].toUpperCase();
  document.querySelector('#navigation').innerHTML=metrics.map(m=>`<a href="/metrics/${m.metric_id.toLowerCase()}" ${id===m.metric_id?'aria-current="page"':''}><span>${m.metric_id}</span>${labels[m.metric_id]}</a>`).join('');
  document.querySelector('.overview-link').href='/';
  document.querySelector('.brand').href='/';
  document.querySelector('.overview-link').classList.toggle('active',!id);
  document.querySelector('#breadcrumb').textContent=id?`전체 평가 / ${id} · ${labels[id]}`:'성능평가 대시보드';
  if(id) return renderMetric(metrics.find(m=>m.metric_id===id));
  document.title='KTL 성능평가 · Rainbow';
  app.innerHTML=`<section class="page-heading"><div><p class="eyebrow">KTL PERFORMANCE EVALUATION</p><h1>성능평가 대시보드</h1><p class="subtitle">현재 연결된 입력과 모듈로 측정하고 결과 및 근거를 확인합니다.</p></div></section><section class="cards">${metrics.map(m=>`<a class="metric-card" href="/metrics/${m.metric_id.toLowerCase()}"><div class="card-top"><span class="metric-id">${m.metric_id}</span>${badge(m.latest?.score!=null?m.latest:m)}</div><h3>${labels[m.metric_id]}</h3><p class="english">${esc(m.metric_name)}</p><p class="description">${m.dataset?'입력 데이터 연결됨':'입력 데이터 대기'}</p><div class="card-bottom"><strong>${score(m.latest?.score,m.metric_id)}</strong><span>${m.latest?.score!=null?'저장된 최근 측정':'미측정'} ↗</span></div></a>`).join('')}</section>`;
}
function renderMetric(m) {
  const r=m.latest; const d=m.details||{}; const result=r?.details||{};
  document.title=`${m.metric_id} · ${labels[m.metric_id]} · Rainbow`;
  const input=[['Dataset',m.dataset||'입력 데이터 대기'],['측정 기준',`${m.operator} ${score(m.target,m.metric_id)}`]];
  if(m.metric_id==='M05') input.push(['전체 입력 event 수',number(d.full_event_count??result.full_event_count)],['평가 target 수',number(d.target_event_count??m.expected_sample_count)]);
  else input.push(...metricFields(m.metric_id,d));
  if(d.model_version||result.model_version) input.push(['Module / version',d.model_version||result.model_version]);
  if(d.config_path) input.push(['Config',d.config_path.split('/').slice(-2).join('/')]);
  if(d.config_sha256) input.push(['Config SHA-256',d.config_sha256]);
  const resultName={M02:'Final Score',M03:'Success Rate',M05:'F1 Score',M06:'DBI'}[m.metric_id]||'Score';
  app.innerHTML=`<a class="back" href="/">← 전체 평가</a><section class="page-heading"><div><p class="eyebrow">${m.metric_id}</p><h1>${labels[m.metric_id]}</h1><p class="subtitle">${esc(m.metric_name)}</p></div>${badge(r?.score!=null?r:m)}</section><section class="evaluation-panel"><h2>입력 및 측정 조건</h2>${stats(input)}${m.presentation_note?`<p class="notice">${esc(m.presentation_note)}</p>`:''}${m.metric_id==='M05'?'<p class="subtitle">전체 sequence를 처리하고 평가 target만 점수에 포함합니다. Context event는 점수 분모에서 제외합니다.</p>':''}<div class="run-row"><p>${m.execution_available?'측정 준비 완료. 현재 연결된 evaluator를 실행합니다.':r?.score!=null?'저장된 결과 조회입니다. 이 화면의 실행 연결은 준비 중입니다.':'측정 실행 연결 준비 중입니다.'}</p>${m.execution_available?`<button id="run" ${running?'disabled':''}>${m.metric_id} 측정 실행</button>`:''}</div><p id="run-status" role="status"></p></section><section class="result-panel"><div class="panel-heading"><h2>측정 결과</h2>${r?.evidence_file?`<a class="download" href="${esc(r.evidence_file)}" download>Evidence CSV 다운로드</a>`:''}</div>${r?.score!=null?`<p class="subtitle">저장된 최근 측정 결과</p>${stats([[resultName,score(r.score,m.metric_id)],['Target',`${r.operator} ${score(r.target,m.metric_id)}`],...metricFields(m.metric_id,result)])}${badge(r)}<p class="run-meta">마지막 측정: ${esc(r.completed_at||'시각 기록 없음')}</p><p>Dataset: <code>${esc(r.dataset_id||m.dataset)}</code></p>${r.manifest_file?`<a class="download" href="${esc(r.manifest_file)}" download>실행 근거 다운로드</a>`:''}`:'<p class="empty">아직 측정 결과가 없습니다.</p>'}</section>`;
  document.querySelector('#run')?.addEventListener('click',()=>run(m));
}
async function run(m) {
  if(running || !m.execution_available) return;
  running=true;
  const button=document.querySelector('#run'); button.disabled=true;
  document.querySelector('#run-status').textContent='측정 중: 입력 검증 및 실행 근거 저장 중…';
  try {
    const response=await fetch(m.execution_url,{method:'POST'}); const result=await response.json();
    if(!response.ok || !result.run_id) throw new Error('실행에 실패했습니다. 입력 및 모듈 연결을 확인해주세요.');
    running=false; await load();
  } catch(error) {running=false; document.querySelector('#run-status').textContent='실행에 실패했습니다. 입력 및 모듈 연결을 확인해주세요.';button.disabled=false;}
}
async function load() {
  try {
    const response=await fetch('/api/measurement'); catalog=await response.json();
    if(!response.ok) throw new Error('조회 실패');
    render();
  } catch(error) {app.innerHTML='<p class="notice">평가 정보를 불러오지 못했습니다.</p><button id="retry">다시 시도</button>';document.querySelector('#retry').addEventListener('click',load);}
}
load();
