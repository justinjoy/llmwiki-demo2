const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
function setup(){
 class Element{constructor(){this.value='2';this.children=[];this.classList={add(){}};}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}addEventListener(){}}
 const elements={};const document={getElementById(id){return elements[id]??=new Element();},createElement(){return new Element();}};
 const context=vm.createContext({document,fetch:()=>new Promise(()=>{}),setTimeout(){}});vm.runInContext(source,context);return {context,elements};
}
test('answer and errors are rendered as text, and score describes mentions',()=>{
 const {context,elements}=setup();vm.runInContext(`render({id:'x',kind:'rag',backend:'codex',model:null,top_k:2,status:'completed',calls:[{mode:'naive',status:'completed',answer:'<img src=x onerror=alert(1)>',prompt:'<script>x</script>',mentions:{a:true,b:false,c:false,d:true}}]})`,context);
 assert.equal(elements.naive.children[1].textContent,'<img src=x onerror=alert(1)>');assert.equal(elements.naive.children[2].textContent,'결과물 키워드 언급 수 2/4');assert.match(elements['rag-meta'].textContent,/Top K 2/);
});
test('single active operation locks settings and both actions',()=>{
 const {context,elements}=setup();vm.runInContext(`state.config={backends:[{id:'codex',available:true,label:'Codex'}],logic:{available:true}};$('backend').value='codex';state.active='id';controls()`,context);
 for(const id of ['backend','top-k','rag','logic'])assert.equal(elements[id].disabled,true);assert.equal(elements.cancel.disabled,false);
});
test('stale polling response cannot replace results',async()=>{
 const {context,elements}=setup();vm.runInContext(`api=async()=>({kind:'rag',id:'old'});state.epoch=2`,context);await vm.runInContext(`poll('old',1)`,context);assert.equal(elements.naive,undefined);
});
test('logic view labels actual engine relations and artifact flow',()=>{
 const {context,elements}=setup();vm.runInContext(`render({id:'w',kind:'logic',status:'completed',result:{engine:'PyreWire',version:'1.1.3',before:[[1,2]],input_of:{b:'a'},flow:[{title:'설치',input:null,artifact:'명령'}]}})`,context);assert.match(elements['logic-output'].children[0].textContent,/PyreWire 1\.1\.3/);assert.equal(elements['logic-output'].children[1].children[2].textContent,'결과물: 명령');
});
