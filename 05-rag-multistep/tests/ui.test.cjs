const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
function setup(){
 class Element{constructor(){this.value='2';this.children=[];this.classList={add(){},remove(){}};}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}addEventListener(){}setAttribute(){}removeAttribute(name){delete this[name];}}
 const elements={};const document={querySelectorAll(){return [];},getElementById(id){return elements[id]??=new Element();},createElement(){return new Element();}};
 const context=vm.createContext({document,WirelogViz:require('../logic-viz.js'),fetch:()=>new Promise(()=>{}),setTimeout(){}});vm.runInContext(source,context);return {context,elements};
}
test('answer and errors are rendered as text, and score describes mentions',()=>{
 const {context,elements}=setup();vm.runInContext(`render({id:'x',kind:'rag',backend:'codex',model:null,top_k:2,status:'completed',calls:[{mode:'naive',status:'completed',answer:'<img src=x onerror=alert(1)>',prompt:'<script>x</script>',mentions:{a:true,b:false,c:false,d:true}}]})`,context);
 assert.equal(elements.naive.children[1].textContent,'<img src=x onerror=alert(1)>');assert.equal(elements.naive.children[2].textContent,'결과물 키워드 언급 수 2/4');assert.match(elements['rag-meta'].textContent,/Top K 2/);
});
test('single active operation locks settings and both actions',()=>{
 const {context,elements}=setup();vm.runInContext(`state.config={backends:[{id:'codex',available:true,label:'Codex'}],logic:{available:true}};$('backend').value='codex';state.active='id';controls()`,context);
 for(const id of ['backend','top-k','rag','logic','logic-reset'])assert.equal(elements[id].disabled,true);assert.equal(elements.cancel.disabled,false);
});
test('stale polling response cannot replace results',async()=>{
 const {context,elements}=setup();vm.runInContext(`api=async()=>({kind:'rag',id:'old'});state.epoch=2`,context);await vm.runInContext(`poll('old',1)`,context);assert.equal(elements.naive,undefined);
});
test('logic view displays returned engine version and handles absent historical labels',()=>{
 const {context,elements}=setup();vm.runInContext(`render({id:'w',kind:'logic',status:'completed',result:{engine:'PyreWire',version:'1.1.3',before:[[1,2]],input_of:{b:'a'},flow:[{title:'설치',input:null,artifact:'명령'}]}})`,context);
 assert.match(elements['logic-output'].children[1].textContent,/PyreWire 1\.1\.3/);
 assert.match(elements['logic-output'].children[3].textContent,/설명용 입력 정보가 없습니다/);
});

function prepareReset(context){vm.runInContext(`state.config={backends:[],logic:{available:true},facts:{dep:[],produces:[]},logic_labels:{steps:{},artifacts:{}},latest:{logic:'old',rag:'rag-id'},rules:'original rules'};state.runs={logic:{id:'old'},rag:{id:'rag-id'}};$('logic-download').href='/api/runs/old';$('logic-download').hidden=false;$('logic-output').textContent='previous result'`,context);}
test('reset clears only ontology display and rejects stale results after success',async()=>{
 const {context,elements}=setup();prepareReset(context);
 vm.runInContext(`api=async(path)=>{if(path!=='/api/logic/reset')throw Error('wrong endpoint');return {reset:true}}`,context);
 await vm.runInContext('resetLogic()',context);
 assert.equal(elements['logic-download'].hidden,true);assert.equal(elements['logic-download'].href,undefined);
 assert.match(elements['logic-output'].children[0].textContent,/실행 전/);
 assert.equal(vm.runInContext('state.runs.logic',context),undefined);assert.equal(vm.runInContext('state.config.latest.logic',context),undefined);
 assert.equal(vm.runInContext('state.runs.rag.id',context),'rag-id');assert.equal(vm.runInContext('state.config.latest.rag',context),'rag-id');
 const count=elements['logic-output'].children.length;vm.runInContext(`api=async()=>({id:'old',kind:'logic'});`,context);await vm.runInContext(`poll('old',0)`,context);assert.equal(elements['logic-output'].children.length,count);
});
test('reset failure keeps results and links; active and pending operations cannot reset or run',async()=>{
 const {context,elements}=setup();prepareReset(context);
 vm.runInContext(`api=async()=>{throw Error('server busy')}`,context);await vm.runInContext('resetLogic()',context);
 assert.equal(vm.runInContext('state.runs.logic.id',context),'old');assert.equal(elements['logic-download'].hidden,false);assert.equal(elements['logic-output'].textContent,'previous result');assert.match(elements.status.textContent,/초기화 실패/);
 vm.runInContext(`api=async()=>{throw Error('must not call')};state.active='run'`,context);await vm.runInContext('resetLogic()',context);assert.equal(vm.runInContext('state.runs.logic.id',context),'old');
 vm.runInContext(`state.active=null;state.resetting=true;controls()`,context);assert.equal(elements['logic-reset'].disabled,true);assert.equal(elements.logic.disabled,true);assert.equal(elements.cancel.disabled,true);await vm.runInContext(`start('logic')`,context);assert.equal(vm.runInContext('state.active',context),null);
});
