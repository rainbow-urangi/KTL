// Synthetic DOM + monotonic fake clock only. Never invokes browser or evaluator.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/app.js','utf8');
const flush=()=>new Promise(r=>setImmediate(r));
async function mount(id='M02',override,behavior='success') {
 let now=0,next=1,release;
 const timers=new Map(),elements=new Map(),listeners={},requests=[];
 const element=k=>{if(!elements.has(k))elements.set(k,{innerHTML:'',textContent:'',classList:{toggle(){}},addEventListener(n,f){this[n]=f;}});return elements.get(k);};
 const metrics=['M01','M02','M03','M04','M05','M06','M07'].map(metric_id=>({metric_id,metric_name:metric_id,dataset:'synthetic',target:.79,operator:'>=',execution_available:true,execution_url:'/synthetic/'+metric_id,latest:{score:99,status:'COMPLETED',threshold_met:true}}));
 const ctx=vm.createContext({Number,performance:{now:()=>now},location:{pathname:'/metrics/'+id.toLowerCase()},window:{...(override===undefined?{}:{M02_RESULT_MIN_DISPLAY_DELAY_MS:override}),addEventListener(n,f){listeners[n]=f;}},document:{querySelector:element},setTimeout(f,ms){const id=next++;timers.set(id,{f,at:now+ms});return id;},clearTimeout(id){timers.delete(id);},fetch:async(url,options)=>{
 requests.push({url,options});if(!options)return {ok:true,json:async()=>({metrics})};
 if(behavior==='deferred')await new Promise(r=>release=r);
 if(behavior==='network')throw Error('synthetic');
 return {ok:behavior!=='http',json:async()=>behavior==='malformed'?{}:{metric_id:url.split('/').pop(),status:'COMPLETED',run_id:'synthetic',score:id==='M02'?77.2898:.823529,threshold_met:true,target:.79,operator:'>=',details:{},evidence_file:'/synthetic.csv'}};
 }});
 vm.runInContext(source,ctx);await flush();
 return {ctx,element,listeners,requests,timers,release:()=>release(),html:()=>element('#app').innerHTML,click:()=>element('#run').click(),async advance(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.f();}await flush();}};
}
const idle=a=>{assert.ok(!a.html().includes('>PASS<'));assert.ok(!a.html().includes('Evidence CSV 다운로드'));assert.ok(!a.html().includes('이전 측정 기록'));};
const pending=a=>{idle(a);assert.ok(a.html().includes('id="run" disabled'));assert.ok(a.html().includes('측정 결과 확인 중...'));assert.ok(a.html().includes('measurement-spinner'));};
const done=a=>{assert.ok(a.html().includes('>PASS<'));assert.ok(a.html().includes('Evidence CSV 다운로드'));assert.ok(!a.html().includes('id="run" disabled'));};
(async()=>{
 const a=await mount();idle(a);assert.equal(a.requests.length,1);
 const promise=a.click();assert.equal(a.requests.length,2); // POST dispatched immediately, not after 30 seconds
 await flush();pending(a);await a.click();assert.equal(a.requests.length,2);
 await a.advance(29999);pending(a);await a.advance(1);await promise;done(a);assert.ok(a.html().includes('77.29%'));
 a.listeners.pagehide();idle(a);assert.equal(a.timers.size,0);idle(await mount());
 for(const id of ['M05','M06']){const b=await mount(id);await b.click();done(b);assert.equal(b.timers.size,0);}
 for(const behavior of ['network','http','malformed']){const b=await mount('M02',undefined,behavior);await b.click();idle(b);assert.ok(b.element('#run-status').textContent.includes('실패'));assert.equal(b.timers.size,0);}
 // Slow response > minimum: reveal on completion without another 30 seconds.
 const slow=await mount('M02',undefined,'deferred');const slowRun=slow.click();await slow.advance(35000);pending(slow);slow.release();await slowRun;done(slow);assert.equal(slow.timers.size,0);
 // Response at 10 seconds: only the remaining 20 seconds are held.
 const medium=await mount('M02',undefined,'deferred');const mediumRun=medium.click();await medium.advance(10000);medium.release();await flush();await medium.advance(19999);pending(medium);await medium.advance(1);await mediumRun;done(medium);
 // Route exit/reentry during display wait must discard the response and timer.
 const nav=await mount();const old=nav.click();await flush();pending(nav);nav.ctx.location.pathname='/metrics/m05';nav.listeners.popstate();nav.ctx.location.pathname='/metrics/m02';nav.listeners.popstate();await old;idle(nav);assert.equal(nav.timers.size,0);await nav.advance(30000);idle(nav);
 const fresh=nav.click();await flush();await nav.advance(30000);await fresh;done(nav);
 // BFCache/pagehide reset and late API responses cannot restore stale results.
 const cache=await mount();const cached=cache.click();await flush();cache.listeners.pagehide();cache.listeners.pageshow({persisted:true});await cached;idle(cache);assert.equal(cache.timers.size,0);
 const late=await mount('M02',undefined,'deferred');const lateRun=late.click();late.listeners.pagehide();late.listeners.pageshow({persisted:true});late.release();await lateRun;idle(late);assert.equal(late.timers.size,0);
 for(const override of [0,100]){const b=await mount('M02',override);const p=b.click();await flush();if(override){pending(b);await b.advance(override);}await p;done(b);}
 for(const override of [-1,'0',NaN,Infinity]){const b=await mount('M02',override);const p=b.click();await flush();pending(b);await b.advance(30000);await p;done(b);}
 assert.ok(!source.includes('모델 추론 중'));assert.ok(!source.includes('AI 모델 실행 중'));
 console.log('PASS: M02 30s monotonic minimum, immediate POST, duplicate guard, evidence reveal, slow/fast API, error immediate, M05/M06 no delay, route/BFCache/reset/stale race, configuration 0/custom/invalid; synthetic only');
})().catch(e=>{console.error(e);process.exit(1)});
