// Sandbox interaction checks: real page script, isolated DOM/HTTP/clipboard fixtures.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {randomUUID}=require('node:crypto');
const catalog=JSON.parse(fs.readFileSync('frontend/integration-samples.json','utf8'));
const source=fs.readFileSync('frontend/integration-sandbox.js','utf8');
const elements=new Map();
function element(key) {
  if(!elements.has(key)) elements.set(key,{innerHTML:'',textContent:'',value:'',dataset:{},disabled:false,listeners:{},children:[],setAttribute(){},focus(){},select(){},appendChild(v){this.children.push(v);},addEventListener(name,callback){this.listeners[name]=callback;}});
  return elements.get(key);
}
let copied='',requests=[],responseStatus=201;
const context=vm.createContext({URLSearchParams,crypto:{randomUUID},location:{port:'8123'},navigator:{clipboard:{writeText:async text=>{copied=text;}}},document:{querySelector:element,createElement:()=>element('fallback')},fetch:async(path,options)=>{
  if(!options) return {ok:true,json:async()=>catalog};
  requests.push({path,options});return {ok:responseStatus===201,status:responseStatus,statusText:responseStatus===201?'Created':'Unprocessable Entity',text:async()=>JSON.stringify(responseStatus===201?{score:90,official_pass:null}:{status:'ERROR',error:'Invalid count: total_execution_count'})};
}});
vm.runInContext(source,context);
const click=(action,metric)=>element(`#${action}-${metric}`).listeners.click();
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  const html=element('#sandbox').innerHTML;
  for(const sample of catalog.samples) {
    assert.ok(html.includes(sample.endpoint));assert.ok(html.includes(sample.metric_name));
    assert.ok(html.includes(`request-${sample.metric_id}`));
    element(`#request-${sample.metric_id}`).value=JSON.stringify(sample.request);
  }
  assert.ok(html.includes('실제 Response Status'));assert.ok(html.includes('Sample Response JSON'));
  const seen=new Set();
  for(const sample of catalog.samples) {
    const metric=sample.metric_id;
    for(let i=0;i<2;i++) {
      await click('send',metric);
      const r=requests.at(-1);const p=JSON.parse(r.options.body);
      assert.equal(r.path,sample.endpoint);assert.equal(r.options.method,'POST');assert.equal(p.run_mode,'REFERENCE');assert.equal(p.dataset_id,'mock-dataset-01');
      assert.ok(!seen.has(p.external_run_id));seen.add(p.external_run_id);
      assert.equal(p.score,undefined);assert.ok(element(`#status-${metric}`).textContent.includes('201'));
    }
    await click('json',metric);const json=JSON.parse(copied);
    assert.equal(json.run_mode,'REFERENCE');assert.ok(json.external_run_id.startsWith(metric+'-MOCK-'));assert.ok(!seen.has(json.external_run_id));seen.add(json.external_run_id);
    await click('curl',metric);assert.ok(copied.includes(`http://127.0.0.1:8123${sample.endpoint}`));assert.ok(copied.includes("'Content-Type: application/json'"));assert.ok(copied.includes('REFERENCE'));
    click('invalid',metric);responseStatus=422;await click('send',metric);
    assert.equal(JSON.parse(requests.at(-1).options.body).counts[sample.invalid_count_field],0);
    assert.ok(element(`#status-${metric}`).textContent.includes('422'));assert.ok(element(`#response-${metric}`).textContent.includes('Invalid count'));
    assert.equal(element(`#status-${metric}`).dataset.state,'error');responseStatus=201;
    click('reset',metric);
    const editor=element(`#request-${metric}`),p=JSON.parse(editor.value);p.run_mode='OFFICIAL';editor.value=JSON.stringify(p);
    const before=requests.length;await click('send',metric);assert.equal(requests.length,before);assert.ok(element(`#status-${metric}`).textContent.includes('REFERENCE'));
    editor.value='{invalid';await click('send',metric);assert.equal(requests.length,before);assert.equal(element(`#send-${metric}`).disabled,false);
    click('reset',metric);
  }
  assert.equal(vm.runInContext('shellQuote("a\'b")',context),"'a'\"'\"'b'");
  context.navigator.clipboard.writeText=async()=>{throw new Error('blocked');};await click('json','M01');
  assert.ok(element('#feedback-M01').textContent.includes('클립보드'));assert.ok(element('fallback').value.includes('M01-MOCK-'));
  console.log('Sandbox: 3 cards, unique IDs, actual response/error rendering, JSON/curl copy, clipboard fallback and OFFICIAL blocking passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
