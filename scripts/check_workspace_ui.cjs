// Browser regression checks with mock API responses; no application/backend mutation.
// Start the frontend, then set RAILFLOW_CHROMIUM and optionally RAILFLOW_UI_BASE / RAILFLOW_UI_OUTPUT.
// Uses Chromium's DevTools pipe directly; no additional npm dependency required.

const {spawn} = require('node:child_process');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const exe = process.env.RAILFLOW_CHROMIUM;
if (!exe) throw new Error('Set RAILFLOW_CHROMIUM to a Chromium headless shell executable.');
const baseUrl = process.env.RAILFLOW_UI_BASE || 'http://127.0.0.1:3000';
const output = process.env.RAILFLOW_UI_OUTPUT || fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'railflow-workspace-'));
fs.mkdirSync(output, { recursive: true });
const child = spawn(exe, ['--remote-debugging-pipe','--no-sandbox','--disable-gpu'], {stdio:['ignore','ignore','pipe','pipe','pipe'], windowsHide:true});
const pending = new Map(); let id=0, buffer='', session, mode='completed', posts=0, gets=0, revision=1, failPost=false;
const errors=[]; const requests=[]; const jobs=new Map(); let batchMode='running', batchCount=360, replanMode='running';
child.stderr.on('data',()=>{});
function send(method,params={},sid=session) { return new Promise((resolve,reject)=>{ const n=++id; pending.set(n,{resolve,reject}); child.stdio[3].write(JSON.stringify({id:n,method,params,...(sid?{sessionId:sid}:{})})+'\0'); }); }
const scores={completion_percent:100,overrun_days_total:7,excess_access_nights_total:3,eclo_nights_total:5,objective_score:42};
function run(s) {return {status: mode, progress:mode==='completed'?100:35, message:mode==='failed'?'No feasible solution under this policy.':mode==='cancelled'?'Search cancelled.':'Searching the operating policy.',feasible: mode==='completed'||(mode==='running'&&s==='A'),phase:mode==='running'?'improving':'done',termination_reason:mode==='completed'?'optimal':mode==='failed'?'infeasible':mode==='cancelled'?'cancelled':'',solution_revision:revision,objective_score:42,diagnostics:{status:mode==='failed'?'no_solution_within_budget':'optimal_for_policy',strategy:'integrated',config:s==='B'?undefined:{workers:s==='C'?'auto':4,strategy:'integrated',time_limit_seconds:15,seed:42},trajectory:[{seconds:1,objective:42}]},solver_stats:{},scores};}
function job(){return {job_id:'qa-job-'+posts,status:mode,algorithm:'legacy',solver_config:{},source:'public',expires_at:'2026-12-31T12:00:00Z',instance:{activities:200,total_accesses:12000,horizon_weeks:60},scenarios:Object.fromEntries(['A','B','C'].map(s=>[s,run(s)]))};}
const activities=Array.from({length:200},(_,i)=>({activity_id:'ACT-'+String(i).padStart(3,'0'),contract_number:'CONTRACT-'+(i%10),line:'Line '+i%3,access_type:'Standard',required_workload:60,delivered_workload:60,completion_date:'2027-01-01',planned_start_date:'2026-01-01',planned_completion_date:'2026-12-01',overrun_days:i%4,delay_cost:7,predecessor:null,predecessor_finish_week:null,co_workers:['ACT-001'],accesses:Array.from({length:60},(_,j)=>({week:j+1,eclo:j%2,access_night:1})),protection:{buffer_locations:['LOCATION-'+('long-'.repeat(20))]},possessions:Array.from({length:60},(_,j)=>({week:j+1,location_id:'LOCATION-001',co_share_group:'G1'})),evidence_note:'Detailed validation evidence. '.repeat(50)}));
const usage=Array.from({length:120},(_,i)=>({location_id:'LOCATION-'+String(i).padStart(3,'0')+(i===0?'-long'.repeat(20):''),week:i%60+1,used:4,capacity:3,work_possessions:4,protection_possessions:1,activities:['ACT-000','ACT-001'],groups:{G1:['ACT-000','ACT-001']},protection_groups:[]}));
function detail(s){return {scenario:s,status:'completed',solution_revision:revision,solver_stats:{optimal:true},score_breakdown:{delay:7,excess_supply:3,eclo:5},locations:usage.map(u=>({location_id:u.location_id,capacity:u.capacity})),activity_details:activities,validation:{feasible:true,hard_violations:[],soft_scores:scores,detail:{capacity_hotspots:usage,location_usage:usage,nights_scheduled:60,eclo_nights:5}},explanations:['Long result explanation. '.repeat(100)],results:activities.map((a,i)=>({contract_number:'CONTRACT-'+i,simulated_completion_date:a.completion_date,overrun_days:i%4})),accesses:activities.flatMap(a=>a.accesses.map(x=>({...x,activity_id:a.activity_id})))};}

function batchPayload(){return {id:'batch-qa',status:batchMode,method:'all',seconds:15,seed:42,error:null,rows:Array.from({length:batchCount},(_,i)=>({method:['legacy','integrated','alns','random_lns'][Math.floor(i/90)],scenario:'ABC'[i%3],case_id:'case-'+Math.floor((i%90)/3),status:'completed',score:i,elapsed_seconds:2})),summary:Array.from({length:12},(_,i)=>({method:['legacy','integrated','alns','random_lns'][Math.floor(i/3)],scenario:'ABC'[i%3],total:30,finished:30,valid:29,mean_score:5,worst_score:10}))};}
async function event(m) {
 if(m.method==='Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text);
 if(m.method!=='Fetch.requestPaused')return;
 const {requestId,request}=m.params;requests.push({url:request.url,method:request.method,body:request.postData});
 const url=new URL(request.url),path=url.pathname;let payload,status=200;
 if(path.includes('expired')){status=404;payload={detail:'Not found'};}
 else if(path.includes('/benchmark/runs')){
  if(request.method==='POST'){batchMode='running';batchCount=url.searchParams.get('method')==='all'?360:90;}
  if(request.method==='DELETE')batchMode='cancelled';
  payload=batchPayload();
 } else if(path.endsWith('/assistant/query')){payload={answer:'A detailed scheduling answer. '.repeat(150),mode:'deterministic',intent:'capacity_status',evidence:['test evidence']};}
 else if(path.includes('/replans')){
  payload={replan_id:'replan-A',status:replanMode,message:'Replanning',diff:replanMode==='completed'?{summary:{moved_activities:100,preserved_percent:75,contracts_impacted:4,score_delta:2},activity_changes:activities.map(a=>({activity_id:a.activity_id,before:[{week:1}],after:[{week:2}],reason:'disruption'}))}:{},disruption_audit:{feasible:true}};
 } else if(request.method==='POST'){
  posts++;payload=job();jobs.set(payload.job_id,payload);
  assert.ok(['legacy','strategies'].includes(url.searchParams.get('algorithm')));if(!url.searchParams.has('seed'))assert.equal(url.searchParams.get('algorithm'),'legacy');
 } else if(request.method==='DELETE'){payload=jobs.get(path.split('/')[4]);payload.status='cancelled';for(const r of Object.values(payload.scenarios)){r.status='cancelled';r.message='Search cancelled.';r.phase='done';}}
 else if(/\/scenarios\/[ABC]$/.test(path)){payload=detail(path.slice(-1));}
 else {gets++;payload=jobs.get(path.split('/')[4])||job();}
 await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(payload)).toString('base64')},m.sessionId);
}
child.stdio[4].on('data',data=>{buffer+=data.toString();let at;while((at=buffer.indexOf('\0'))>=0){const raw=buffer.slice(0,at);buffer=buffer.slice(at+1);if(!raw)continue;const m=JSON.parse(raw);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(m.error)p.reject(Error(JSON.stringify(m.error)));else p.resolve(m.result);}else event(m).catch(e=>{
 // Navigation can discard a paused request before the fixture response arrives.
 if (!e.message.includes('"code":-32602,"message":"Invalid InterceptionId."')) errors.push(e.message);
});}});
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(expr){for(let i=0;i<100;i++){if(await evaluate('Boolean('+expr+')'))return;await pause(50);}throw Error('Timed out: '+expr);}
async function click(text){await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==="+JSON.stringify(text)+").click()");await pause(100);}
async function tab(name){await click(name);}
async function viewport(w,h){await send('Emulation.setDeviceMetricsOverride',{width:w,height:h,deviceScaleFactor:1,mobile:false});await pause(100);}
async function fits(label){const r=await evaluate("({w:innerWidth,h:innerHeight,sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight,tab:document.querySelector('[role=tabpanel]:not([hidden])')?.getBoundingClientRect().toJSON()})");assert.ok(r.sw<=r.w&&r.sh<=r.h,label+JSON.stringify(r));assert.ok(r.tab.height>60,label+' panel too small: '+JSON.stringify(r));console.log('PASS viewport '+label);}
async function screenshot(name){const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));}

async function ready(){await until("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Load public dataset'&&!b.disabled)");}
async function go(path){await send('Page.navigate',{url:baseUrl+path});await pause(400);}
async function setInput(selector,value){await evaluate("(()=>{const e=document.querySelector("+JSON.stringify(selector)+");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"+JSON.stringify(value)+");e.dispatchEvent(new Event('input',{bubbles:true}));})()");await pause(80);}
(async()=>{
 try {
 const target=await send('Target.createTarget',{url:'about:blank'},null);session=(await send('Target.attachToTarget',{targetId:target.targetId,flatten:true},null)).sessionId;
 await send('Page.enable');await send('Runtime.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*/api/ps1/*'}]});
 await viewport(1366,768);await go('/');await ready();
 assert.equal(await evaluate("document.querySelector('.algorithm-picker')===null"),true);
 assert.equal(requests.filter(r=>r.url.includes('/benchmark/')).length,0);
 await click('Load public dataset');await until("document.querySelector('.validation-badge')");assert.ok(await evaluate("localStorage.getItem('railflow-planner-job-id')"));
 for(const [w,h] of [[1366,768],[1920,1080]]){await viewport(w,h);for(const name of ['Overview','Activities','Location & capacity','Contract results','Operations']){await tab(name);await fits(w+'x'+h+' '+name);}}
 await viewport(1366,768);await tab('Operations');
 const visible='.operations-policy:not([hidden]) ';
 await setInput(visible+'input[placeholder]', 'What is the capacity?');
 await evaluate("document.querySelector('.operations-policy:not([hidden]) .assistant-form button').click()");
 await until("document.querySelector('.operations-policy:not([hidden]) .assistant-answer')");await fits('long assistant answer');
 await evaluate("document.querySelector('.operations-policy:not([hidden]) .disruption-form button').click()");
 await until("document.querySelector('.operations-policy:not([hidden]) .replan-panel .subheading span').textContent==='running'");
 await click('BStrict schedule');await tab('Overview');replanMode='completed';await pause(1700);await click('AStrict supply');await tab('Operations');
 assert.equal(await evaluate("document.querySelector('.operations-policy:not([hidden]) .assistant-form input').value"),'What is the capacity?');
 await until("document.querySelector('.operations-policy:not([hidden]) .replan-panel .subheading span').textContent==='completed'");
 await fits('completed replan with long changes');await screenshot('split-operations');
 await click('Result details');await until("document.querySelector('dialog').open");assert.equal(await evaluate("document.querySelector('.execution-config > div:nth-child(2) dd').textContent"),'4');await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await pause(100);assert.equal(await evaluate("document.activeElement.textContent"),'Result details');
 for(const [policy,expected] of [['BStrict schedule','Not reported'],['CBalanced','Auto']]){await click(policy);await click('Result details');assert.ok((await evaluate("document.querySelector('.execution-config > div:nth-child(2) dd').textContent")).includes(expected));await evaluate("document.querySelector('dialog').close()");}await click('AStrict supply');
 console.log('PASS resolved, auto and older worker diagnostics');
 await tab('Overview');await evaluate("document.getElementById('tab-overview').focus()");await send('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End',windowsVirtualKeyCode:35});await pause(100);assert.equal(await evaluate("document.activeElement.id"),'tab-operations');
 await tab('Activities');await setInput('input[placeholder="Search activity ID"]','ACT-001');await tab('Overview');await tab('Activities');assert.equal(await evaluate("document.querySelectorAll('.activity-list button').length"),1);
 await go('/lab');await ready();assert.equal(await evaluate("document.querySelector('.solver-options select').options.length"),4);
 await evaluate("(()=>{const e=document.querySelector('.solver-options select');e.value='integrated';e.dispatchEvent(new Event('change',{bubbles:true}));})()");await pause(80);
 await click('Load public dataset');await until("document.querySelector('.validation-badge')");await fits('lab single input');
 assert.notEqual(await evaluate("localStorage.getItem('railflow-planner-job-id')"),await evaluate("localStorage.getItem('railflow-lab-job-id')"));
 await click('Dataset suite');await click('Compare all 4 methods · 360 runs');await until("document.querySelector('.batch-detail tbody tr')");
 assert.equal(await evaluate("document.querySelectorAll('.batch-detail tbody tr').length"),360);
 for(const [w,h] of [[1366,768],[1920,1080]]){await viewport(w,h);const box=await evaluate("({h:innerHeight,w:innerWidth,sh:document.documentElement.scrollHeight,sw:document.documentElement.scrollWidth,b:document.querySelector('.dataset-panel > a').getBoundingClientRect().bottom})");assert.ok(box.sh<=box.h&&box.sw<=box.w&&box.b<=box.h,JSON.stringify(box));}
 await viewport(1366,768);await screenshot('split-lab-suite');
 await click('Single input');assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Change data').disabled"),true);
 await go('/');await until("document.querySelector('.validation-badge')");assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Change data').disabled"),false);
 await go('/lab');await until("document.querySelector('.dataset-panel:not([hidden]) .batch-detail')");
 await click('Stop comparison');await until("document.querySelector('.dataset-panel h3').textContent.includes('cancelled')");
 assert.ok(requests.filter(r=>r.method==='DELETE').every(r=>r.url.includes('/benchmark/')));
 await click('Run selected method · 90 runs');await until("document.querySelectorAll('.batch-detail tbody tr').length===90");await click('Stop comparison');await until("document.querySelector('.dataset-panel h3').textContent.includes('cancelled')");
 await click('Single input');await until("document.querySelector('.validation-badge')");await tab('Overview');await fits('restored lab result');
 await viewport(390,844);for(const name of ['Overview','Activities','Location & capacity','Contract results','Operations']){await tab(name);assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth"));}
 await click('Dataset suite');assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth"));await screenshot('split-lab-mobile');
 await viewport(1366,768);await go('/');await until("document.querySelector('.validation-badge')");
 await evaluate("localStorage.setItem('railflow-planner-job-id','expired');");await go('/');await until("document.querySelector('[role=alert]')");assert.equal(await evaluate("localStorage.getItem('railflow-planner-job-id')"),null);await ready();
 await evaluate("localStorage.setItem('railflow-lab-job-id','expired');localStorage.setItem('railflow-benchmark-id','expired');");await go('/lab');await ready();await click('Dataset suite');await until("document.querySelector('.dataset-panel [role=alert]')");assert.equal(await evaluate("localStorage.getItem('railflow-benchmark-id')"),null);
 await click('Single input');await ready();mode='failed';await click('Load public dataset');await until("document.querySelector('.empty-result')");await click('Result details');await until("document.querySelector('dialog').open");assert.ok(await evaluate("document.querySelector('dialog').textContent.includes('Search diagnostics')"));await evaluate("document.querySelector('dialog').close()");
 assert.equal(errors.length,0,errors.join('; '));
 console.log('Screenshots: '+output);
 console.log('PASS isolated API calls, legacy defaults, separate restoration, operations persistence, long content, 360 runs, cancellation target, expired IDs, keyboard, mobile, runtime errors');
 } finally {child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
