'use strict';
const $ = id => document.getElementById(id);
const state = {token:null, config:null, active:null, epoch:0, runs:{}, polling:false};
function node(tag, text, className) { const el=document.createElement(tag); el.textContent=text; if(className)el.className=className; return el; }
async function api(path, body) {
  const response=await fetch(path, body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Run-Token':state.token},body:JSON.stringify(body)});
  const data=await response.json(); if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`); return data;
}
function controls() {
  const busy=!!state.active, config=state.config;
  $('backend').disabled=$('top-k').disabled=busy||!config;
  const backend=config?.backends.find(b=>b.id===$('backend').value);
  $('rag').disabled=busy||!backend?.available;
  $('logic').disabled=busy||!config?.logic.available;
  $('cancel').disabled=!busy;
  $('backend-info').textContent=backend?`${backend.label} · ${backend.available?'실행 파일 발견 (인증 상태는 호출 시 확인)':'CLI 설치 필요'} · 모델: ${backend.model||'CLI 기본 설정'} · ${backend.isolation}`:'';
}
function sources() {
  const k=Number($('top-k').value);
  $('sources').replaceChildren(...state.config.ranked.map(([score,name,text],i)=>{
    const el=node('div',`${i+1}. ${name} · 유사도 ${score.toFixed(3)}${i<k?' · 선택됨':''}\n${text}`,'source'); if(i<k)el.classList.add('selected');return el;
  }));
}
function render(run) {
  state.runs[run.kind]=run;
  const link=$(run.kind+'-download'); link.href='/api/runs/'+run.id;link.hidden=false;link.target='_blank';link.rel='noopener';
  if(run.kind==='rag') {
    for(const mode of ['naive','fixed']) {
      const area=$(mode), call=run.calls.find(c=>c.mode===mode); area.replaceChildren();
      if(!call){area.append(node('p',run.status==='running'?'호출 대기':'호출되지 않음'));continue;}
      area.append(node('p',`${call.status}${call.seconds!==undefined?` · ${call.seconds}초`:''}`,'muted'));
      if(call.answer)area.append(node('div',call.answer,'answer'));
      if(call.mentions) {
        area.append(node('p',`결과물 키워드 언급 수 ${Object.values(call.mentions).filter(Boolean).length}/4`,'score'));
        for(const [step,mentioned]of Object.entries(call.mentions))area.append(node('div',`${mentioned?'✓':'—'} ${step}`));
      }
      const details=node('details',''), summary=node('summary','실제 제공한 프롬프트');details.append(summary,node('pre',call.prompt));area.append(details);
    }
    $('rag-meta').textContent=`실행 ${run.id} · CLI ${run.backend} · 모델 ${run.model||'CLI 기본 설정'} · Top K ${run.top_k} · ${run.status}${run.error?' · '+run.error:''}`;
  } else {
    const area=$('logic-output');area.replaceChildren();
    if(run.result){
      const r=run.result;area.append(node('p',`${r.engine} ${r.version} · before ${r.before.length}쌍 · input_of ${Object.keys(r.input_of).length}개`,'score'));
      r.flow.forEach((step,i)=>{const flow=node('div','','flow');flow.append(node('strong',`${i+1}. ${step.title}`),node('div',`입력: ${step.input||'없음'}`),node('div',`결과물: ${step.artifact}`));area.append(flow);});
      const details=node('details','');details.append(node('summary','실제 도출한 관계'),node('pre',JSON.stringify({before:r.before,input_of:r.input_of},null,2)));area.append(details);
    }else area.append(node('p',run.error||run.status));
  }
}
async function poll(id, epoch) {
  try {
    const run=await api('/api/runs/'+id);
    if(epoch!==state.epoch)return;
    render(run);$('status').textContent=`${run.kind==='rag'?'RAG 비교':'Wirelog'} · ${run.status} · ${run.phase}${run.error?' · '+run.error:''}`;
    if(run.status==='running'){setTimeout(()=>poll(id,epoch),600);return;}
    // Persisting the result finishes just after status changes; status API is authoritative for the lock.
    const current=await api('/api/status');if(epoch!==state.epoch)return;
    state.active=current.active;controls();
    if(state.active)setTimeout(()=>poll(state.active,epoch),300);
  }catch(error){if(epoch===state.epoch){$('status').textContent=error.message+' · 새로고침하여 다시 연결하세요.';}}
}
async function start(kind) {
  if(state.active)return;
  state.active='pending';controls();const epoch=++state.epoch;
  try {
    const run=await api('/api/runs',{kind,backend:$('backend').value,top_k:Number($('top-k').value)});
    state.active=run.id;poll(run.id,epoch);
  }catch(error){state.active=null;controls();$('status').textContent=error.message;}
}
async function init() {
  controls();
  try {
    const config=await api('/api/status');state.config=config;state.token=config.token;
    $('backend').replaceChildren(...config.backends.map(b=>{const o=node('option',b.label+(b.available?'':' · 미설치'));o.value=b.id;return o;}));
    $('backend').value=config.default_backend;
    $('question').textContent=config.question;$('card').textContent=config.procedure_card;$('system').textContent=config.system_prompt;
    $('facts').textContent=JSON.stringify(config.facts,null,2);$('rules').textContent=config.rules;
    $('logic-info').textContent=config.logic.detail;
    const epoch=++state.epoch;
    for(const [kind,id] of Object.entries(config.latest)){
      const run=await api('/api/runs/'+id);render(run);
      if(kind==='rag'){$('backend').value=run.backend;$('top-k').value=String(run.top_k);}
    }
    state.active=config.active;sources();controls();$('status').textContent='연결됨 · 버튼을 누르면 실제 실행합니다.';
    if(state.active)poll(state.active,epoch);
  }catch(error){$('status').textContent=error.message;}
}
$('rag').addEventListener('click',()=>start('rag'));$('logic').addEventListener('click',()=>start('logic'));
$('cancel').addEventListener('click',async()=>{if(!state.active||state.active==='pending')return;try{await api('/api/runs/'+state.active+'/cancel',{});$('status').textContent='취소 요청 중…';}catch(error){$('status').textContent=error.message;}});
for(const id of ['backend','top-k'])$(id).addEventListener('change',()=>{if(state.active)return;state.epoch++;sources();controls();$('status').textContent='설정 변경됨 · 이전 결과에는 실행 당시 설정을 표시합니다.';});
init();
