// DOM rendering checks with real catalog responses. No browser dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const catalogs = JSON.parse(execFileSync('python3', ['-B', '-c', 'import json; from backend.server import Service; s=Service(); print(json.dumps({m:s.catalog(m) for m in ["REFERENCE","OFFICIAL","DEVELOPMENT"]}))'], {encoding:'utf8'}));
const source = fs.readFileSync('frontend/app.js','utf8');
async function check(mode, path) {
  const elements = new Map();
  const element = key => {
    if (!elements.has(key)) elements.set(key,{innerHTML:'',textContent:'',classList:{toggle(){}},addEventListener(){}});
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
  if(mode==='DEVELOPMENT') { assert.ok(html.includes('DEVELOPMENT DATASET')); assert.ok(html.includes('공식 시험성적 아님')); assert.ok(!/>PASS<|>FAIL</.test(html)); }
  assert.ok(element('#navigation').innerHTML.includes('?mode='+mode));
}
(async()=>{
  for(const mode of ['REFERENCE','OFFICIAL','DEVELOPMENT']) {
    await check(mode,'/');
    for(let i=1;i<=7;i++) await check(mode,`/metrics/m0${i}`);
  }
  console.log('24 mode/page DOM rendering checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
