'use strict';
const sandbox = document.querySelector('#sandbox');
const sandboxDataset = 'mock-dataset-01';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => JSON.stringify(value, null, 2);
let requestSequence = 0;

function nextMockId(metric) {
  requestSequence += 1;
  return `${metric}-MOCK-${new Date().toISOString().replace(/[-:.]/g, '')}-${requestSequence}-${crypto.randomUUID()}`;
}

function prepareRequest(sample, editor) {
  const payload = JSON.parse(editor.value);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('요청은 JSON 객체여야 합니다.');
  if (payload.run_mode !== 'REFERENCE' || payload.dataset_id !== sandboxDataset) {
    throw new Error('Sandbox는 mock-dataset-01의 REFERENCE 요청만 전송·복사할 수 있습니다.');
  }
  payload.external_run_id = nextMockId(sample.metric_id);
  payload.submitted_at = new Date().toISOString();
  editor.value = pretty(payload);
  return payload;
}

function shellQuote(text) {
  return "'" + text.replace(/'/g, "'\"'\"'") + "'";
}

function curlCommand(sample, payload) {
  const port = location.port || '8000';
  const url = `http://127.0.0.1:${port}${sample.endpoint}`;
  return `curl -i -X POST ${shellQuote(url)} \\\n  -H 'Content-Type: application/json' \\\n  --data-raw ${shellQuote(pretty(payload))}`;
}

async function copyText(text, feedback) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(text);
    feedback.textContent = '복사했습니다. 고유 mock ID가 포함돼 있습니다.';
  } catch (_) {
    feedback.textContent = '클립보드 접근이 제한되었습니다. 아래 텍스트를 선택해 복사하세요.';
    const fallback = document.createElement('textarea');
    fallback.readOnly = true;
    fallback.value = text;
    fallback.setAttribute('aria-label', '수동 복사할 내용');
    feedback.appendChild(fallback);
    fallback.focus();
    fallback.select();
  }
}

async function sendRequest(sample, editor, status, output, button) {
  button.disabled = true;
  output.textContent = '';
  document.querySelector(`#summary-${sample.metric_id}`).textContent='평가 결과 없음';
  status.dataset.state = 'pending';
  status.textContent = '전송 중…';
  try {
    const payload = prepareRequest(sample, editor);
    const response = await fetch(sample.endpoint, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const text = await response.text();
    let body;
    try { body = JSON.parse(text); } catch (_) { body = null; }
    output.textContent = body === null ? text : pretty(body);
    const counts=body?.details?.raw_counts || {};
    const summary=document.querySelector(`#summary-${sample.metric_id}`);
    if (response.ok && body && summary) {
      const successes=body.details?.successful_scenario_count ?? body.details?.calculated_both_pass_count ?? counts.successful_execution_count ?? counts.both_pass_count;
      summary.textContent=`성공 ${successes ?? '—'} / 전체 ${body.sample_count ?? '—'} · 비율 ${body.score ?? '—'}% · 목표 ${body.target ?? '—'}% · ${body.run_mode ?? ''}`;
    } else if(summary) summary.textContent='평가 결과 없음';
    status.dataset.state = response.ok ? 'success' : 'error';
    status.textContent = `HTTP ${response.status}${response.statusText ? ' '+response.statusText : ''} · ${response.ok ? '응답 수신 완료' : '요청 오류'}`;
  } catch (error) {
    status.dataset.state = 'error';
    status.textContent = `요청을 완료하지 못했습니다: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

async function generateMock(sample) {
  const output=document.querySelector('#generation-response-M03');
  const button=document.querySelector('#generate-M03');
  button.disabled=true;
  try {
    const request=JSON.parse(document.querySelector('#generation-request-M03').value);
    if(request.run_mode!=='REFERENCE' || request.generator_mode!=='MOCK') throw new Error('Sandbox 생성은 REFERENCE / MOCK만 허용합니다.');
    const response=await fetch(sample.generation_endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:pretty(request)});
    const body=await response.json();
    output.textContent=`HTTP ${response.status}\n${pretty(body)}`;
    if(response.ok && body.status==='SUCCESS') {
      const editor=document.querySelector('#request-M03');const evaluation=JSON.parse(editor.value);
      const index=evaluation.scenarios.findIndex(s=>s.business_unit_id===body.business_unit_id);
      if(index>=0) evaluation.scenarios[index]=body;
      else if(evaluation.scenarios.length<10) evaluation.scenarios.push(body);
      editor.value=pretty(evaluation);
    }
  } catch(error) { output.textContent=error.message; }
  finally {button.disabled=false;}
}

function renderSandbox(catalog) {
  sandbox.innerHTML = catalog.samples.map(sample => `
    <section class="api-card" id="card-${sample.metric_id}" aria-labelledby="title-${sample.metric_id}">
      <div class="metric-title"><span class="metric-id">${sample.metric_id}</span><h2 id="title-${sample.metric_id}">${esc(sample.metric_name)}</h2></div>
      <p class="endpoint"><span class="method">POST</span><code>${esc(sample.endpoint)}</code></p>
      <p>${esc(sample.purpose)}</p>
      <p class="notice">${esc(sample.criteria)} · REFERENCE / DEVELOPMENT 연동용</p>
      ${sample.generation_endpoint ? `<div class="generation">
        <h3>Scenario Generation · POST ${esc(sample.generation_endpoint)}</h3>
        <label for="generation-request-M03">Generation Request JSON</label>
        <textarea id="generation-request-M03">${esc(pretty(sample.generation_request))}</textarea>
        <h3>Generation Response Sample · HTTP 200</h3><pre>${esc(pretty(sample.generation_response_example))}</pre>
        <button id="generate-M03" type="button">Generate Mock</button>
        <pre id="generation-response-M03">미생성</pre>
        <p>생성 결과는 같은 업무 ID의 평가 요청 항목에 반영됩니다. 점수는 Submit Evaluation Result로 확인하세요.</p>
      </div>` : ''}
      <details><summary>Required fields</summary>
        <p class="fields">${catalog.common_required.map(esc).join(' · ')}</p>
        <p class="fields"><strong>${sample.metric_id==='M03'?'scenario results':'counts'}:</strong> ${(sample.required_fields || sample.required_counts).map(esc).join(' · ')}</p>
        <p class="hint">모든 count는 0 이상의 정수입니다. 분모는 양수여야 합니다. 자세한 오류는 서버 응답에서 확인하세요.</p>
      </details>
      <div class="columns"><div>
        <label for="request-${sample.metric_id}">Sample Request JSON · 편집 가능</label>
        <textarea id="request-${sample.metric_id}" spellcheck="false">${esc(pretty(sample.request))}</textarea>
      </div><div>
        <h3>Sample Response JSON · HTTP ${catalog.success_http_status}</h3>
        <p class="hint">핵심 필드 예시입니다. 실제 전송 결과가 아닙니다.</p>
        <pre>${esc(pretty(sample.response_example))}</pre>
        <p class="hint">서버는 실제 응답에 run_id, provenance, 입력 해시, evidence_file 등을 추가합니다.</p>
      </div></div>
      <div class="buttons">
        <button type="button" class="primary" id="send-${sample.metric_id}">${sample.metric_id==='M03'?'Submit Evaluation Result':'Send Test Request'}</button>
        <button type="button" id="json-${sample.metric_id}">Copy Request JSON</button>
        <button type="button" id="curl-${sample.metric_id}">Copy curl</button>
        <button type="button" id="reset-${sample.metric_id}">정상 예시 불러오기</button>
        <button type="button" id="invalid-${sample.metric_id}">오류 예시 불러오기</button>
      </div>
      <div class="feedback" id="feedback-${sample.metric_id}" role="status"></div>
      <div class="actual"><p id="summary-${sample.metric_id}" role="status">평가 결과 없음</p><h3>실제 Response Status</h3>
        <p class="status" id="status-${sample.metric_id}" role="status">미전송</p>
        <h3>실제 Response JSON</h3><pre id="response-${sample.metric_id}">Send Test Request를 누르면 표시됩니다.</pre>
      </div>
    </section>`).join('');
  for (const sample of catalog.samples) {
    const find = prefix => document.querySelector(`#${prefix}-${sample.metric_id}`);
    const editor=find('request'), feedback=find('feedback'), send=find('send');
    if(sample.generation_endpoint) find('generate').addEventListener('click',()=>generateMock(sample));
    send.addEventListener('click', () => sendRequest(sample,editor,find('status'),find('response'),send));
    for (const action of ['json','curl']) {
      find(action).addEventListener('click', async () => {
        try {
          const payload=prepareRequest(sample,editor);
          await copyText(action==='json' ? pretty(payload) : curlCommand(sample,payload),feedback);
        } catch (error) { feedback.textContent=error.message; }
      });
    }
    find('reset').addEventListener('click', () => {
      editor.value=pretty(sample.request);feedback.textContent='정상 예시를 불러왔습니다.';
    });
    find('invalid').addEventListener('click', () => {
      const payload=JSON.parse(JSON.stringify(sample.request));
      if(sample.metric_id==='M03') payload.scenarios=[];
      else payload.counts[sample.invalid_count_field]=0;
      editor.value=pretty(payload);
      feedback.textContent='빈 시나리오 배열 또는 분모 0 예시입니다. 전송하여 실제 HTTP 422 오류를 확인하세요.';
    });
  }
  sandbox.setAttribute('aria-busy','false');
}

async function loadSandbox() {
  try {
    const response=await fetch('/integration-samples.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderSandbox(await response.json());
  } catch (error) {
    sandbox.textContent=`예시를 불러오지 못했습니다: ${error.message}. 페이지를 새로고침하세요.`;
    sandbox.setAttribute('aria-busy','false');
  }
}
loadSandbox();
