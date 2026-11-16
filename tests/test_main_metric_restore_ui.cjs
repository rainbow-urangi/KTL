'use strict';
// Local git + synthetic VM/DOM only. No server, model, browser, or external API.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const referenceCommit='32aa412c34a3355e4e9e2d236b6bd5fd707127b5';
const source=fs.readFileSync(path.join(root,'frontend/app.js'),'utf8');
const reference=execFileSync('git',['show',referenceCommit+':frontend/app.js'],{cwd:root,encoding:'utf8'});
const clone=value=>JSON.parse(JSON.stringify(value));
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
let groups=0;
async function test(name,run){await run();groups++;console.log('PASS '+name);}

function declaration(text,name){
  const start=new RegExp('^(?:async )?function '+name+'\\(', 'm').exec(text);
  assert.ok(start,'Missing declaration: '+name);
  const rest=text.slice(start.index+start[0].length);
  const next=/^(?:async )?function \w+\(/m.exec(rest);
  return text.slice(start.index,next?start.index+start[0].length+next.index:undefined).trim().replace(/\r\n/g,'\n');
}

function fixtureMetric(id){
  return {metric_id:id,metric_name:'SYNTHETIC '+id,dataset:'synthetic-fixed-'+id,
    target:id==='M05'?.79:id==='M06'?1:id==='M03'?80:75,operator:id==='M06'?'<=':'>=',
    expected_sample_count:id==='M05'?20:10,execution_available:true,execution_url:'/synthetic-run/'+id,
    details:{total_scenarios:10,ground_truth_count:5,full_event_count:417,target_event_count:20,
      workflow_count:22,cluster_count:21,dimensions:1152,model_version:'SYNTHETIC-fixed',
      config_path:'synthetic/config.json',config_sha256:'a'.repeat(64),
      business_units:[{business_unit_id:'SYNTHETIC-BU',name:'SYNTHETIC fixed business'}]},
    latest:{status:'COMPLETED',score:99.999,threshold_met:true,evidence_file:'/synthetic-history.csv'}};
}

function fixtureResult(id){
  const values={M02:71.23456,M03:90,M05:.823529,M06:.3182056481321068};
  return {metric_id:id,run_id:'SYNTHETIC-'+id,status:'COMPLETED',score:values[id],
    threshold_met:id!=='M06',target:fixtureMetric(id).target,operator:fixtureMetric(id).operator,
    completed_at:'SYNTHETIC-current-time',dataset_id:'synthetic-fixed-'+id,
    evidence_file:'/synthetic-current-'+id+'.csv',manifest_file:'/synthetic-current-'+id+'.json',
    details:{accuracy:61,completeness:89,ground_truth_count:5,evaluated_procedures:31,
      correctly_mapped:20,included_required:25,defined_required:27,total_scenarios:10,success:9,failure:1,
      tp:10,fp:1,fn:2,tn:7,precision:.9,recall:.8,workflow_count:22,cluster_count:21,dimensions:1152,
      per_business_unit:[{business_unit_id:'SYNTHETIC-BU',name:'SYNTHETIC fixed business',success:false,
        failure_reason:'SYNTHETIC reason',steps:[{order:1,action:'click',target:'SYNTHETIC target'}]}]}};
}

async function mount(id='M03',query='',script=source){
  const elements=new Map(),requests=[],listeners={},delegations=[];
  const state={defer:false,release:null,reply:fixtureResult(id),available:true};
  const element=selector=>{
    if(!elements.has(selector))elements.set(selector,{innerHTML:'',textContent:'',disabled:false,
      classList:{toggle(){}},addEventListener(name,handler){this[name]=handler;}});
    return elements.get(selector);
  };
  const ctx=vm.createContext({Number,URLSearchParams,location:{pathname:'/metrics/'+id.toLowerCase(),search:query},
    performance:{now:()=>0},setTimeout,clearTimeout,
    window:{M02_RESULT_MIN_DISPLAY_DELAY_MS:0,addEventListener(name,handler){listeners[name]=handler;}},
    document:{querySelector:element},
    fetch:async(url,options)=>{
      requests.push({url,options});
      if(options?.method==='POST'){
        if(state.defer)await new Promise(resolve=>{state.release=resolve;});
        return {ok:true,json:async()=>clone(state.reply)};
      }
      return {ok:true,json:async()=>({metrics:['M01','M02','M03','M04','M05','M06','M07'].map(fixtureMetric)})};
    }});
  vm.runInContext(script.replace(/\bload\(\);\s*$/,''),ctx);
  for(const metric of ['M01','M04','M07'])ctx['render'+(metric==='M01'?'M01Csv':metric)]=()=>{
    delegations.push(metric);element('#app').innerHTML='<p>SYNTHETIC dedicated '+metric+'</p>';
  };
  await vm.runInContext('load()',ctx);await settle();
  return {ctx,state,element,requests,listeners,delegations,html:()=>element('#app').innerHTML,
    click:()=>element('#run').click(),posts:()=>requests.filter(row=>row.options?.method==='POST')};
}

(async()=>{
  await test('main render declarations equal reference after explicit name aliases only',()=>{
    const expected=declaration(reference,'renderMetric').replace('function renderMetric(', 'function renderMainMetric(')
      .replace(/\bbadge\(/g,'measurementBadge(').replace(/\bscenarioDetails\(/g,'mainScenarioDetails(')
      .replace(/\brun\(m\)/g,'runMeasurement(m)');
    assert.equal(declaration(source,'renderMainMetric'),expected);
    assert.equal(declaration(source,'mainScenarioDetails'),declaration(reference,'scenarioDetails')
      .replace('function scenarioDetails(', 'function mainScenarioDetails('));
  });
  await test('four restored routes always use main catalog including former M03 auxiliary queries',async()=>{
    for(const id of ['M02','M03','M05','M06'])for(const query of ['', '?mode=DEVELOPMENT',
      '?mode=OFFICIAL','?mode=DEVELOPMENT&view=api','?run_id=DEV-M03-synthetic']){
      const item=await mount(id,query);
      assert.equal(item.requests.length,1);
      assert.equal(item.requests[0].url,'/api/measurement');
      assert.deepEqual(item.delegations,[]);
      assert.ok(item.html().includes('id="run"'));
      assert.ok(!item.html().includes('type="file"'));
      assert.ok(!item.html().includes('id="m03-generate"'));
      assert.equal(item.posts().length,0);
      assert.ok(!item.html().includes('99.999'));
      assert.ok(!item.html().includes('synthetic-history.csv'));
    }
  });
  for(const id of ['M02','M03','M05','M06'])await test(id+' original input/result markup, single POST and original server values',async()=>{
    const actual=await mount(id),original=await mount(id,'',reference);
    assert.equal(actual.html(),original.html());
    await actual.click();await original.click();
    assert.equal(actual.html(),original.html());
    assert.equal(actual.posts().length,1);
    assert.equal(actual.posts()[0].url,'/synthetic-run/'+id);
    assert.deepEqual(clone(actual.posts()[0].options),{method:'POST'});
    assert.ok(actual.html().includes('/synthetic-current-'+id+'.csv'));
    assert.ok(actual.html().includes('/synthetic-current-'+id+'.json'));
    const displayed={M02:'71.23%',M03:'90.00%',M05:'0.8235',M06:'0.3182'}[id];
    assert.ok(actual.html().includes(displayed));
    assert.ok(actual.html().includes(id==='M06'?'>FAIL<':'>PASS<'));
    if(id==='M03')for(const text of ['고정 평가 업무','SYNTHETIC reason','SYNTHETIC target','Failure reason:'])
      assert.ok(actual.html().includes(text));
  });
  await test('M01 M04 M07 dedicated routes preserved without model or execution requests',async()=>{
    for(const id of ['M01','M04','M07']){
      const item=await mount(id,'?mode=DEVELOPMENT');
      assert.deepEqual(item.delegations,[id]);
      assert.equal(item.requests[0].url,'/api/evaluations?mode=DEVELOPMENT');
      assert.equal(item.posts().length,0);
    }
  });
  await test('missing readiness keeps original absent run button and cannot POST',async()=>{
    const item=await mount('M03');
    vm.runInContext("catalog.metrics.find(m=>m.metric_id==='M03').execution_available=false;render();",item.ctx);
    assert.ok(!item.html().includes('id="run"'));
    await vm.runInContext("runMeasurement(catalog.metrics.find(m=>m.metric_id==='M03'))",item.ctx);
    assert.equal(item.posts().length,0);
  });
  await test('null M03 score is rejected rather than restored as zero or successful current result',async()=>{
    const item=await mount('M03');
    item.state.reply={...item.state.reply,score:null,details:{evaluation_status:'NOT_READY'}};
    await item.click();
    assert.ok(item.element('#run-status').textContent.includes('실패'));
    assert.ok(!item.html().includes('synthetic-current-M03.csv'));
    assert.ok(!item.html().includes('>PASS<'));
    assert.ok(!item.html().includes('<strong>0.00%</strong>'));
  });
  await test('duplicate pending click and route exit cannot publish stale results',async()=>{
    const item=await mount('M03');item.state.defer=true;
    const pending=item.click();await settle();await item.click();assert.equal(item.posts().length,1);
    item.ctx.location.pathname='/metrics/m06';item.listeners.popstate();
    item.ctx.location.pathname='/metrics/m03';item.listeners.popstate();
    item.state.release();await pending;
    assert.ok(!item.html().includes('synthetic-current-M03.csv'));
    assert.ok(!item.html().includes('>PASS<'));
  });
  console.log('PASS '+groups+' main restore groups; synthetic VM only; external/model/browser calls 0');
})().catch(error=>{console.error(error);process.exitCode=1;});
