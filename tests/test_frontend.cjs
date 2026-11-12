// Synthetic VM/DOM tests only. No browser or actual evaluator execution.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/app.js','utf8');
const saved=JSON.parse(fs.readFileSync('results/development/latest-M05.json','utf8'));
const fixture={metrics:Array.from({length:7},(_,i)=>{const id='M0'+(i+1);return {metric_id:id,metric_name:'Metric '+id,dataset:'synthetic-input',target:id==='M05'?.79:id==='M06'?1:75,operator:id==='M06'?'<=':'>=',expected_sample_count:20,details:{business_units:[{business_unit_id:'SYNTHETIC-M03',name:'synthetic business'}],accuracy:99,completeness:98,success:7,failure:3,total_scenarios:10},execution_available:['M02','M03','M05','M06'].includes(id),execution_url:'/synthetic/'+id,latest:{...saved,metric_id:id}};})};
const tick=()=>new Promise(r=>setImmediate(r));
async function mount(path,query='',behavior='success') {
 const elements=new Map(),requests=[],listeners={};let release;
 const element=k=>{if(!elements.has(k))elements.set(k,{innerHTML:'',textContent:'',disabled:false,classList:{toggle(){}},addEventListener(n,f){this[n]=f;}});return elements.get(k);};
 const ctx=vm.createContext({Number,location:{pathname:path,search:query},performance:{now:()=>0},setTimeout,clearTimeout,window:{M02_RESULT_MIN_DISPLAY_DELAY_MS:0,addEventListener(n,f){listeners[n]=f;}},document:{querySelector:element},fetch:async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){
  if(behavior==='deferred')await new Promise(r=>release=r);
  if(behavior==='reject')throw Error('network');
  return {ok:behavior!=='fail',json:async()=>behavior==='invalid'?{run_id:'invalid'}:{...saved,...(url.endsWith('M02')?{score:77.28981596002805,details:{accuracy:64.516129,completeness:92.592593,per_business_unit:[{business_unit_id:'SYNTHETIC-BU',score:50,generated_count:2,matched_count:1,included_required_count:1,required_count:2,generated_process:[{label:'synthetic step',action_type:'CLICK'}],required_steps:[{ground_truth_step:'synthetic GT',direct_match:'True',required_included:'True'}],missing:['synthetic missing']}]}}:{}),...(url.endsWith('M03')?{score:90,details:{total_scenarios:10,success:9,failure:1,per_business_unit:[{business_unit_id:'SYNTHETIC-M03',name:'synthetic business',success:false,failure_reason:'synthetic order error',steps:[{order:2,action:'click',target:'synthetic control'}]}]}}:{}),run_id:'synthetic-current',metric_id:url.split('/').pop(),evidence_file:'/synthetic-current.csv',completed_at:'synthetic-current-time'}};
 }return {ok:true,json:async()=>fixture};}});
 vm.runInContext(source,ctx);await tick();return {element,requests,ctx,listeners,release:()=>release(),html:()=>element('#app').innerHTML};
}
function idle(a){const h=a.html();assert.ok(h.includes('미실행'));assert.ok(!h.includes('0.8235'));assert.ok(!h.includes('>PASS<'));assert.ok(!h.includes('Evidence CSV 다운로드'));assert.ok(!h.includes(saved.evidence_file));}
(async()=>{
 let routes=0;
 for(const query of ['', '?mode=REFERENCE','?mode=OFFICIAL','?mode=DEVELOPMENT'])for(const path of ['/',...fixture.metrics.map(m=>'/metrics/'+m.metric_id.toLowerCase())]){
  const a=await mount(path,query);idle(a);const text=a.html().replace(/<[^>]*>/g,'');assert.ok(!/REFERENCE|OFFICIAL|DEVELOPMENT|undefined|이전 측정 기록/.test(text));assert.equal(a.requests.length,1);assert.equal(a.requests[0].url,'/api/measurement');
  if(/m0[147]$/.test(path))assert.ok(!a.html().includes('id="run"'));
  if(path!=='/')assert.ok(a.html().includes('아직 이번 세션에서 측정하지 않았습니다.'));
  routes++;
 }
 for(const id of ['m02','m03','m05','m06']){
  const a=await mount('/metrics/'+id);await a.element('#run').click();assert.ok(a.html().includes(id==='m02'?'77.29%':id==='m03'?'90.00%':'0.8235'));assert.ok(a.html().includes('>PASS<'));assert.ok(a.html().includes('/synthetic-current.csv'));assert.ok(a.html().includes('synthetic-current-time'));assert.ok(!a.html().includes(saved.evidence_file));assert.equal(a.requests.length,2);if(id==='m03'){assert.ok(a.html().includes('synthetic order error'));assert.ok(a.html().includes('synthetic control'));}if(id==='m02'){assert.ok(a.html().includes('SYNTHETIC-BU'));assert.ok(a.html().includes('synthetic step'));assert.ok(a.html().includes('synthetic missing'));}
  a.listeners.pagehide();idle(a);a.listeners.pageshow({persisted:true});idle(a);
  await a.element('#run').click();a.ctx.location.pathname='/metrics/m02';a.listeners.popstate();idle(a);a.ctx.location.pathname='/metrics/'+id;a.listeners.popstate();idle(a);
  a.ctx.location.pathname='/';a.listeners.popstate();idle(a);a.ctx.location.pathname='/metrics/'+id;a.listeners.popstate();idle(a);
  idle(await mount('/metrics/'+id)); // reload/new page session
 }
 for(const behavior of ['fail','reject','invalid']){const a=await mount('/metrics/m05','',behavior);await a.element('#run').click();idle(a);assert.ok(a.element('#run-status').textContent.includes('실패'));assert.ok(!a.html().includes('id="run" disabled'));}
 const a=await mount('/metrics/m05','','deferred');const first=a.element('#run').click();await a.element('#run').click();assert.equal(a.requests.filter(x=>x.options?.method==='POST').length,1);a.ctx.location.pathname='/metrics/m02';a.listeners.popstate();a.ctx.location.pathname='/metrics/m05';a.listeners.popstate();a.release();await first;idle(a);
 const b=await mount('/metrics/m05','','deferred');const old=b.element('#run').click();b.listeners.pagehide();b.listeners.pageshow({persisted:true});b.release();await old;idle(b);
 assert.ok(!/localStorage|sessionStorage|Math\.sqrt|calculate_binary|2\s*\*\s*precision/.test(source));
 console.log(`PASS: ${routes} initial/legacy routes; M02/M03/M05/M06 explicit POST server result; reload/new-session/history/reentry/BFCache; failure/malformed/network; repeated-submit; stale completion; no real browser/evaluator calls`);
})().catch(e=>{console.error(e);process.exit(1)});
