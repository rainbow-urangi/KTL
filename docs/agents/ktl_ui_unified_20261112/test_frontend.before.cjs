// DOM rendering checks with real catalog responses. No browser dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const catalogs = JSON.parse(execFileSync('python3', ['-B', '-c', 'import json; from backend.server import Service; s=Service(); print(json.dumps({m:s.catalog(m) for m in ["REFERENCE","OFFICIAL","DEVELOPMENT"]}))'], {encoding:'utf8',maxBuffer:16*1024*1024}));
const source = fs.readFileSync('frontend/app.js','utf8');
async function check(mode, path) {
  const elements = new Map();
  const element = key => {
    if (!elements.has(key)) elements.set(key,{innerHTML:'',textContent:'',classList:{toggle(){}},addEventListener(name,fn){this[name]=fn;}});
    return elements.get(key);
  };
  const context = vm.createContext({URLSearchParams,location:{pathname:path,search:'?mode='+mode},document:{querySelector:element},fetch:async()=>({ok:true,json:async()=>catalogs[mode]})});
  vm.runInContext(source,context);
  await new Promise(resolve=>setImmediate(resolve));
  const html=element('#app').innerHTML;
  assert.ok(html.includes('REFERENCE') && html.includes('OFFICIAL'));
  assert.ok(!html.includes('undefined'));
  assert.ok(!html.includes('junior'));
  if(mode==='REFERENCE') {
    assert.ok(html.includes('공식 시험성적이 아닙니다'));
    assert.ok(!/>PASS<|>FAIL</.test(html));
    if(path==='/metrics/m02') assert.ok(html.includes('공식 KTL Ground Truth 아님'));
    if(path==='/metrics/m06') assert.ok(html.includes('563')&&html.includes('consensus'));
  }
  if(mode==='DEVELOPMENT') { assert.ok(html.includes('DEVELOPMENT DATASET')); assert.ok(html.includes('공식 시험성적 아님')); if(path!=='/metrics/m05') assert.ok(!/>PASS<|>FAIL</.test(html)); }
  assert.ok(element('#navigation').innerHTML.includes('?mode='+mode));
  if(mode==='DEVELOPMENT' && path==='/') {
    const card=html.match(/<a class="metric-card" href="[^"]*\/metrics\/m05[^"]*"[\s\S]*?<\/a>/)?.[0];
    const m=catalogs.DEVELOPMENT.metrics.find(m=>m.metric_id==='M05');
    assert.ok(card, 'M05 overview card is present');
    assert.ok(card.includes(m.dataset+' · 개발 평가'), 'Overview uses actual M05 dataset');
    assert.ok(!card.includes('current_site_dev_01'), 'No stale M05 overview dataset');
  }
  if(mode==='DEVELOPMENT' && path==='/metrics/m05') {
    assert.ok(html.includes('M05 측정 실행'));
    assert.ok(html.includes('Target &gt;= 0.7900'));
    assert.ok(html.includes('raw01_raw02_raw03_target20_20261111'));
    const m=catalogs.DEVELOPMENT.metrics.find(m=>m.metric_id==='M05');
    if(m.latest) {
      assert.ok(html.includes(m.latest.evidence_file));
      assert.ok(html.includes('F1 '+Number(m.latest.score).toFixed(4)));
      assert.ok(html.includes(m.latest.completed_at));
    }
  }
  if(mode==='DEVELOPMENT' && path==='/metrics/m06') {
    assert.ok(html.includes('v1_2_1_unseen_m06_development'));
    assert.ok(html.includes('Frozen embedding M06 측정'));
    assert.ok(html.includes('Embedding dimension'));
    assert.ok(html.includes('입력 artifact / SHA-256'));
    const input=catalogs[mode].metrics.find(m=>m.metric_id==='M06');
    assert.ok(html.includes(input.details.input_sha256[Object.keys(input.details.input_sha256)[0]]));
  }
  if(mode==='DEVELOPMENT' && path==='/metrics/m02') {
    const input=catalogs[mode].metrics.find(m=>m.metric_id==='M02');
    if(input.input_options?.length) {
      const legacy=input.input_options.find(o=>o.id==='');
      const candidate=input.input_options.find(o=>o.id!=='');
      element('#input-dataset').change({target:{value:''}});
      let changed=element('#app').innerHTML;
      assert.ok(changed.includes('<code>'+legacy.readiness.dataset+'</code>'));
      assert.ok(!changed.includes('DIRECT_PROCEDURE_MAPPING_REQUIRED'));
      if(candidate.ready!==false) {
        element('#input-dataset').change({target:{value:candidate.id}});
        changed=element('#app').innerHTML;
        assert.ok(changed.includes('<code>'+candidate.readiness.dataset+'</code>'));
        if(candidate.id==='m02_recovery_data_01' && candidate.readiness.status!=='READY') assert.ok(/id="run" disabled/.test(changed));
        if(candidate.readiness.details.serializer_hash) {
          assert.ok(changed.includes(candidate.readiness.details.serializer_hash));
          assert.ok(changed.includes(candidate.readiness.details.serializer_version));
          if(candidate.readiness.details.evaluation_contract_hash) {
            assert.ok(changed.includes(candidate.readiness.details.evaluation_contract_hash));
            assert.ok(changed.includes('Evaluation contract SHA-256'));
            assert.ok(changed.includes(candidate.readiness.details.comparison_contract));
            assert.notEqual(candidate.readiness.details.evaluation_contract_hash,candidate.readiness.details.serializer_snapshot_hash);
          }
          assert.ok(changed.includes('GT 5종 측정 결과'));
          assert.ok(changed.includes('UNASSIGNED'));
        } else if(candidate.readiness.status==='ERROR' || candidate.readiness.status==='BLOCKED') {
          assert.ok(changed.includes(candidate.readiness.status==='ERROR'?'오류':'실행 조건 미충족'));
        } else if(candidate.id==='m02_recovery_data_01') {
          assert.ok(changed.includes('모델 추론은 다시 실행하지 않습니다'));
        } else {
          assert.ok(changed.includes('DIRECT_PROCEDURE_MAPPING_REQUIRED'));
        }
      }
    }
  }
}
(async()=>{
  for(const mode of ['REFERENCE','OFFICIAL','DEVELOPMENT']) {
    await check(mode,'/');
    for(let i=1;i<=7;i++) await check(mode,`/metrics/m0${i}`);
  }
  console.log('24 mode/page DOM rendering checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
