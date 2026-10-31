const {test}=require('node:test');const assert=require('node:assert/strict');const viz=require('../logic-viz.js');
const facts={dep:[['rules','install'],['facts','rules'],['check','facts']],produces:[['install','command'],['rules','rulesDoc'],['facts','factsFile'],['check','log']]};
const labels={steps:{install:'CLI 설치',rules:'운영 규칙 작성',facts:'사실 추출',check:'정합성 점검'},artifacts:{command:'사용 가능한 명령',rulesDoc:'운영 규칙 문서',factsFile:'출처가 달린 사실 파일',log:'검증 로그'}};
const result={engine:'PyreWire',version:'1.1.3',before:[['install','rules'],['install','facts'],['install','check'],['rules','facts'],['rules','check'],['facts','check']],input_of:{rules:'command',facts:'rulesDoc',check:'factsFile'},flow:[{step:'install',title:'CLI 설치',input:null,artifact:'사용 가능한 명령'}]};
function setup(){
 const ids={};const elements=[];
 class Element{
  constructor(tag){this.tag=tag;this.textContent='';this.children=[];this.attrs={};this.listeners={};this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x)};elements.push(this);}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,fn){this.listeners[k]=fn;}
  set id(value){ids[value]=this;}
 }
 const document={createElement:tag=>new Element(tag),getElementById:id=>ids[id],querySelectorAll:()=>elements};
 const inputs=new Element('div'),output=new Element('div');for(const id of ['rule-direct','rule-chain','rule-handoff']){const e=new Element('li');e.id=id;}
 const text=e=>e.textContent+e.children.map(text).join('\n');
 return {document,inputs,output,ids,text,elements};
}
test('seven human supplied facts render before any derived result',()=>{
 const d=setup();viz.renderInputs(d.inputs,facts,labels,d.document);const t=d.text(d.inputs);
 assert.match(t,/선행 조건 3개/);assert.match(t,/운영 규칙 작성 전에 CLI 설치/);assert.match(t,/만드는 것 → 출처가 달린 사실 파일/);assert.equal(Object.keys(d.ids).filter(k=>k.startsWith('dep-')||k.startsWith('produce-')).length,7);assert.doesNotMatch(t,/실제 실행 완료/);
});
test('direct and transitive explanations cite recorded facts and actual returned relations',()=>{
 const proofs=viz.proofsFor(facts,result,labels);assert.equal(proofs.length,9);
 const direct=proofs.find(p=>p.from==='install'&&p.to==='rules');assert.deepEqual(direct.facts,['dep-0']);assert.equal(direct.indirect,false);
 const transitive=proofs.find(p=>p.from==='install'&&p.to==='check');assert.deepEqual(transitive.facts,['dep-0','dep-1','dep-2']);assert.equal(transitive.supported,true);assert.deepEqual(transitive.rules,['rule-direct','rule-chain']);assert.match(transitive.lines.join(' '),/규칙 2 적용/);
 const input=proofs.find(p=>p.kind==='input'&&p.label.includes('정합성 점검'));assert.deepEqual(input.facts,['dep-2','produce-2']);assert.deepEqual(input.rules,['rule-handoff']);assert.match(input.lines.join(' '),/출처가 달린 사실 파일/);
});
test('missing support, mismatched outputs, cycles, and missing intermediate output never fabricate proof',()=>{
 const wrong={...result,before:[...result.before,['check','install']],input_of:{check:'log'}};
 const proofs=viz.proofsFor(facts,wrong,labels);assert.equal(proofs.find(p=>p.from==='check').supported,false);assert.equal(proofs.find(p=>p.kind==='input').supported,false);
 const incomplete={...result,before:result.before.filter(p=>!(p[0]==='install'&&p[1]==='rules'))};assert.equal(viz.proofsFor(facts,incomplete,labels).find(p=>p.from==='install'&&p.to==='check').supported,false);
 assert.equal(viz.pathBetween({dep:[['a','b'],['b','a']]},'a','z'),null);
});
test('selection highlights exact supporting facts/rule and actual output counts',()=>{
 const d=setup();viz.renderInputs(d.inputs,facts,labels,d.document);viz.renderResult(d.output,{id:'r',status:'completed',facts,logic_labels:labels,result},d.document);
 assert.match(d.text(d.output),/순서 관계 6개 · 다음 단계의 입력 관계 3개/);assert.match(d.text(d.output),/엔진 내부의 실행 순서나 추적 로그는 아닙니다/);
 assert.ok(d.ids['dep-0'].classes.has('evidence-active'));
 const button=d.elements.find(e=>e.tag==='button'&&e.textContent.includes('결과물 전달')&&e.textContent.includes('정합성 점검'));
 button.listeners.click();assert.equal(button.attrs['aria-pressed'],'true');assert.ok(d.ids['dep-2'].classes.has('evidence-active'));assert.ok(d.ids['produce-2'].classes.has('evidence-active'));assert.ok(d.ids['rule-handoff'].classes.has('evidence-active'));assert.equal(d.ids['dep-0'].classes.has('evidence-active'),false);
});
test('running failed and cancelled never show success or retain old proof',()=>{
 for(const status of ['running','failed','cancelled']){const d=setup();viz.renderInputs(d.inputs,facts,labels,d.document);viz.renderResult(d.output,{id:'x',status,result,error:status==='failed'?'<img onerror=x>':null},d.document);const t=d.text(d.output);assert.doesNotMatch(t,/실제 실행 완료|순서 관계 6개/);assert.match(t,/완료된 추론 결과가 없습니다/);}
});
test('restored snapshot labels stay independent of current data and safe as text',()=>{
 const d=setup(), old=JSON.parse(JSON.stringify(labels));old.steps.install='<img onerror=x> 옛 설치';viz.renderInputs(d.inputs,facts,old,d.document);viz.renderResult(d.output,{id:'old',status:'completed',facts,logic_labels:old,result},d.document);assert.match(d.text(d.inputs),/<img onerror=x> 옛 설치/);assert.match(d.text(d.output),/<img onerror=x> 옛 설치/);assert.equal(d.elements.some(e=>e.tag==='img'),false);
});
