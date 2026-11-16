// Synthetic VM/DOM tests only. No browser or actual evaluator execution.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/app.js','utf8');
// Optional explicit reference comparison; default regression runs remain checkout-portable.
const referenceSource=process.argv[2]?fs.readFileSync(process.argv[2],'utf8'):null;
// Versioned archived result: the same M05 result contract, independent of local runtime history.
const saved=JSON.parse(fs.readFileSync('docs/agents/m05_main_web_20261112/api_result.json','utf8'));
const fixture={metrics:Array.from({length:7},(_,i)=>{const id='M0'+(i+1);return {metric_id:id,metric_name:'Metric '+id,dataset:'synthetic-input',target:id==='M05'?.79:id==='M06'?1:75,operator:id==='M06'?'<=':'>=',expected_sample_count:20,details:{business_units:[{business_unit_id:'SYNTHETIC-M03',name:'synthetic business'}],accuracy:99,completeness:98,success:7,failure:3,total_scenarios:10},execution_available:['M02','M03','M05','M06'].includes(id),execution_url:'/synthetic/'+id,latest:{...saved,metric_id:id}};})};
const tick=()=>new Promise(r=>setImmediate(r));
async function mount(path,query='',behavior='success',script=source) {
 const elements=new Map(),requests=[],listeners={};let release;
 const element=k=>{if(!elements.has(k))elements.set(k,{innerHTML:'',textContent:'',disabled:false,classList:{toggle(){}},addEventListener(n,f){this[n]=f;}});return elements.get(k);};
 const ctx=vm.createContext({Number,URLSearchParams,location:{pathname:path,search:query},performance:{now:()=>0},setTimeout,clearTimeout,window:{M02_RESULT_MIN_DISPLAY_DELAY_MS:0,addEventListener(n,f){listeners[n]=f;}},document:{querySelector:element},fetch:async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){
  if(behavior==='deferred')await new Promise(r=>release=r);
  if(behavior==='reject')throw Error('network');
  return {ok:behavior!=='fail',json:async()=>behavior==='invalid'?{run_id:'invalid'}:{...saved,...(url.endsWith('M02')?{score:77.28981596002805,details:{accuracy:64.516129,completeness:92.592593,per_business_unit:[{business_unit_id:'SYNTHETIC-BU',score:50,generated_count:2,matched_count:1,included_required_count:1,required_count:2,generated_process:[{label:'synthetic step',action_type:'CLICK'}],required_steps:[{ground_truth_step:'synthetic GT',direct_match:'True',required_included:'True'}],missing:['synthetic missing']}]}}:{}),...(url.endsWith('M03')?{score:90,details:{total_scenarios:10,success:9,failure:1,per_business_unit:[{business_unit_id:'SYNTHETIC-M03',name:'synthetic business',success:false,failure_reason:'synthetic order error',steps:[{order:2,action:'click',target:'synthetic control'}]}]}}:{}),run_id:'synthetic-current',metric_id:url.split('/').pop(),evidence_file:'/synthetic-current.csv',completed_at:'synthetic-current-time'}};
 }return {ok:true,json:async()=>JSON.parse(JSON.stringify(fixture))};}});
 ctx.m04Delegations=[];ctx.renderM04=metric=>{ctx.m04Delegations.push(metric.metric_id);element('#app').innerHTML='<p>M04 dedicated script screen</p>';};
 vm.runInContext(script,ctx);await tick();return {element,requests,ctx,listeners,release:()=>release(),html:()=>element('#app').innerHTML};
}
function idle(a){const h=a.html();assert.ok(h.includes('미실행'));assert.ok(!h.includes('0.8235'));assert.ok(!h.includes('>PASS<'));assert.ok(!h.includes('Evidence CSV 다운로드'));assert.ok(!h.includes(saved.evidence_file));}
function routeContext(pathname,search='') {
 const ctx=vm.createContext({URLSearchParams,location:{pathname,search},document:{querySelector(){return {};}}});
 vm.runInContext(source.replace(/\bload\(\);\s*$/,''),ctx);return ctx;
}
(async()=>{
 let routes=0;
 // M04 opens its script screen directly; other metric route boundaries stay intact.
 for(const query of ['', '?mode=REFERENCE','?mode=OFFICIAL','?mode=DEVELOPMENT'])for(const path of ['/','/metrics/m02','/metrics/m03','/metrics/m04','/metrics/m05','/metrics/m06']){
  const a=await mount(path,query);
  if(path==='/metrics/m04'&&['','?mode=DEVELOPMENT'].includes(query)){
   assert.deepEqual(a.ctx.m04Delegations,['M04']);assert.equal(a.requests.length,1);
   assert.equal(a.requests[0].url,'/api/evaluations?mode=DEVELOPMENT');
   assert.equal(a.requests.filter(row=>row.options?.method==='POST').length,0);routes++;continue;
  }
  idle(a);const text=a.html().replace(/<[^>]*>/g,'');assert.ok(!/REFERENCE|OFFICIAL|DEVELOPMENT|undefined|이전 측정 기록/.test(text));assert.equal(a.requests.length,1);assert.equal(a.requests[0].url,'/api/measurement');
  if(path!=='/')assert.ok(a.html().includes('아직 이번 세션에서 측정하지 않았습니다.'));
  if(path==='/metrics/m03')assert.ok(!a.html().includes('API 시나리오 관리'));
  if(path==='/metrics/m04'){
   assert.ok(!a.html().includes('id="run"'));assert.ok(!a.html().includes('id="m04-register"'));
   assert.ok(!a.html().includes('id="m04-start"'));assert.ok(a.html().includes('id="m04-open"'));
   await a.element('#m04-open').click();assert.equal(a.ctx.location.href,'/metrics/m04?mode=DEVELOPMENT&view=execution');
   assert.equal(a.requests.filter(row=>row.options?.method==='POST').length,0);
  }
  routes++;
 }
 const boundary=await mount('/');
 for(const id of ['M01','M07']){
  assert.equal(vm.runInContext(`ktlMetricHref('${id}')`,boundary.ctx),'/metrics/'+id.toLowerCase()+'?mode=DEVELOPMENT');
  boundary.ctx.location.pathname='/metrics/'+id.toLowerCase();assert.equal(vm.runInContext('ktlUseMeasurementRoute()',boundary.ctx),false);
 }
 assert.equal(vm.runInContext("ktlMetricHref('M04')",boundary.ctx),'/metrics/m04');
 for(const [pathname,search,expectedMode,measurement] of [
  ...['m01','m07'].map(id=>['/metrics/'+id,'','DEVELOPMENT',false]),
  ['/metrics/m04','','DEVELOPMENT',false],['/metrics/m04','?mode=DEVELOPMENT','DEVELOPMENT',false],
  ['/metrics/m04','?mode=REFERENCE','REFERENCE',true],['/metrics/m04','?mode=OFFICIAL','OFFICIAL',true],
  ['/metrics/m03','','REFERENCE',true],['/metrics/m03','?view=api','DEVELOPMENT',true],
  ['/metrics/m03','?run_id=DEV-M03-synthetic','DEVELOPMENT',true],['/metrics/m01','?mode=REFERENCE','REFERENCE',false]]){
  const ctx=routeContext(pathname,search);
  assert.equal(vm.runInContext('mode',ctx),expectedMode);assert.equal(vm.runInContext('ktlUseMeasurementRoute()',ctx),measurement);
 }
 let auxiliaryRoutes=0;
 const auxiliary=[...['?view=execution','?m03_run_id=DEV-M03-20261113T000000-aaaaaaaaaaaa','?scenario_id=SYNTHETIC',
   '?execution_id=M04-RUN-'+'a'.repeat(32),'?run_id=DEV-M04-20261113T000000-aaaaaaaaaaaa',
   '?prep_generation_id=M07-GEN-'+'a'.repeat(32)].map(query=>['m04',query])];
 for(const [id,query] of auxiliary)for(const prefix of ['', '?mode=DEVELOPMENT&']){
  const ctx=routeContext('/metrics/'+id,prefix?prefix+query.slice(1):query);
  assert.equal(vm.runInContext('ktlUseMeasurementRoute()',ctx),false);
  assert.equal(vm.runInContext('mode',ctx),'DEVELOPMENT');
  ctx.delegations=[];ctx.renderM03=()=>ctx.delegations.push('M03');ctx.renderM04=()=>ctx.delegations.push('M04');
  vm.runInContext(`renderMetric({metric_id:'${id.toUpperCase()}'});`,ctx);
  assert.deepEqual(ctx.delegations,[id.toUpperCase()]);auxiliaryRoutes++;
 }
 let referenceComparisons=0;
 if(referenceSource)for(const query of ['', '?mode=REFERENCE','?mode=OFFICIAL','?mode=DEVELOPMENT'])for(const id of ['m03','m05','m06']){
  const current=await mount('/metrics/'+id,query),reference=await mount('/metrics/'+id,query,'success',referenceSource);
  for(const marker of ['page-heading','evaluation-panel','result-panel'])assert.ok(current.html().includes(marker)&&reference.html().includes(marker));referenceComparisons++;
  if(id!=='m04'){
   await current.element('#run').click();await reference.element('#run').click();
   assert.ok(current.html().includes('/synthetic-current.csv')&&reference.html().includes('/synthetic-current.csv'));referenceComparisons++;
  }
  assert.equal(current.requests.filter(row=>row.options?.method==='POST').length,id==='m04'?0:1);
 }
 for(const id of ['m02','m03','m05','m06']){
  const a=await mount('/metrics/'+id);await a.element('#run').click();assert.ok(a.html().includes(id==='m02'?'77.29%':id==='m03'?'90.00%':'0.8235'));assert.ok(a.html().includes('>PASS<'));assert.ok(a.html().includes('/synthetic-current.csv'));assert.ok(a.html().includes('synthetic-current-time'));assert.ok(!a.html().includes(saved.evidence_file));assert.equal(a.requests.length,2);if(id==='m03'){assert.ok(a.html().includes('synthetic order error'));assert.ok(a.html().includes('synthetic control'));}if(id==='m02'){assert.ok(a.html().includes('SYNTHETIC-BU'));assert.ok(a.html().includes('synthetic step'));assert.ok(a.html().includes('synthetic missing'));}
  a.listeners.pagehide();idle(a);a.listeners.pageshow({persisted:true});idle(a);
  await a.element('#run').click();a.ctx.location.pathname='/metrics/m02';a.listeners.popstate();idle(a);a.ctx.location.pathname='/metrics/'+id;a.listeners.popstate();idle(a);
  a.ctx.location.pathname='/';a.listeners.popstate();idle(a);a.ctx.location.pathname='/metrics/'+id;a.listeners.popstate();idle(a);
  idle(await mount('/metrics/'+id)); // reload/new page session
 }
 for(const behavior of ['fail','reject','invalid']){const a=await mount('/metrics/m05','',behavior);await a.element('#run').click();idle(a);assert.ok(a.element('#run-status').textContent.includes('실패'));assert.ok(!a.html().includes('id="run" disabled'));}
 const blocked=await mount('/metrics/m05');
 vm.runInContext("Object.assign(catalog.metrics.find(m=>m.metric_id==='M05'),{execution_available:false,details:{missing:['SYNTHETIC missing adapter']}});render();",blocked.ctx);
 assert.ok(!blocked.html().includes('id="run"'));assert.ok(blocked.html().includes('측정 실행 연결 준비 중입니다.'));
 await vm.runInContext("runMeasurement(catalog.metrics.find(m=>m.metric_id==='M05'))",blocked.ctx);
 assert.equal(blocked.requests.filter(row=>row.options?.method==='POST').length,0);
 const pending=await mount('/metrics/m03');
 pending.ctx.fetch=async()=>({ok:true,json:async()=>({metric_id:'M03',run_id:'synthetic-order-pending',status:'COMPLETED',score:null,threshold_met:null,target:80,operator:'>=',evidence_file:'/synthetic-pending.csv',details:{evaluation_status:'NOT_READY',success_policy:'STRUCTURE_AND_REFERENCE_ORDER',rows:[{business_unit_id:'SYNTHETIC-M03',success:null}],external_details:{generation_summary:{attempt_count:10,successful_count:9,failed_count:1},per_business_unit:[{business_unit_id:'SYNTHETIC-M03',name:'synthetic order pending',steps:[{order:1,action:'click',target:'synthetic control'}]}]}}})});
 await pending.element('#run').click();
 assert.ok(pending.element('#run-status').textContent.includes('실패'));
 assert.ok(pending.html().includes('아직 이번 세션에서 측정하지 않았습니다.'));
 assert.ok(!pending.html().includes('/synthetic-pending.csv'));assert.ok(!pending.html().includes('synthetic control'));
 assert.ok(!pending.html().includes('>PASS<'));assert.ok(!pending.html().includes('>FAIL<'));assert.ok(!pending.html().includes('90.00%'));
 const a=await mount('/metrics/m05','','deferred');const first=a.element('#run').click();await a.element('#run').click();assert.equal(a.requests.filter(x=>x.options?.method==='POST').length,1);a.ctx.location.pathname='/metrics/m02';a.listeners.popstate();a.ctx.location.pathname='/metrics/m05';a.listeners.popstate();a.release();await first;idle(a);
 const b=await mount('/metrics/m05','','deferred');const old=b.element('#run').click();b.listeners.pagehide();b.listeners.pageshow({persisted:true});b.release();await old;idle(b);
 const measurementSource=source.slice(source.indexOf('function renderMeasurementMetric(m)'),source.indexOf('function renderMetric(m)'))+source.slice(source.indexOf('async function runMeasurement(m)'),source.indexOf('async function run(id)'));
 assert.ok(!/localStorage|sessionStorage|Math\.sqrt|calculate_binary|2\s*\*\s*precision/.test(measurementSource));
 console.log(`PASS: ${routes} basic routes, ${auxiliaryRoutes} explicit auxiliary routes, ${referenceComparisons} optional reference layout comparisons; M04 visible entry with POST0; M02/M03/M05/M06 explicit POST server result; reload/new-session/history/reentry/BFCache; failure/malformed/network; repeated-submit; stale completion; no real browser/evaluator calls`);
})().catch(e=>{console.error(e);process.exit(1)});
