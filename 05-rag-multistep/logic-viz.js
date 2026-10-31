/* Explanations of returned relations, reconstructed from recorded facts.
   This is a presentation layer, never a substitute inference engine. */
(function(root) {
  'use strict';
  const same = (a,b) => a[0]===b[0] && a[1]===b[1];
  const has = (rows,pair) => rows.some(row=>same(row,pair));
  const title = (labels,id) => labels.steps?.[id] || id;
  const artifact = (labels,id) => labels.artifacts?.[id] || id;
  function pathBetween(facts,from,to) {
    const queue=[[from]], seen=new Set([from]);
    while(queue.length) {
      const path=queue.shift(), last=path[path.length-1];
      for(const [step,needs] of facts.dep) {
        if(needs!==last || seen.has(step))continue;
        const next=[...path,step];if(step===to)return next;
        seen.add(step);queue.push(next);
      }
    }
    return null;
  }
  function proofsFor(facts,result,labels) {
    const proofs=[];
    for(const [from,to] of result.before) {
      const path=pathBetween(facts,from,to), ids=[], lines=[];
      let supported=!!path;
      if(path) {
        for(let i=0;i<path.length-1;i++) {
          const a=path[i],b=path[i+1];
          ids.push('dep-'+facts.dep.findIndex(pair=>same(pair,[b,a])));
          lines.push(`입력 사실: ‘${title(labels,b)}’에는 ‘${title(labels,a)}’가 필요합니다.`);
          if(!has(result.before,[a,b]))supported=false;
        }
        if(path.length===2)lines.push(`규칙 1 적용: 선행 조건이므로 ‘${title(labels,from)}’가 ‘${title(labels,to)}’보다 먼저입니다.`);
        else {
          lines.push('규칙 1 적용: 각 선행 조건을 “먼저 한다”는 순서로 바꿉니다.');
          for(let i=2;i<path.length;i++) {
            if(!has(result.before,[from,path[i]]))supported=false;
            lines.push(`규칙 2 적용: ‘${title(labels,from)} → ${title(labels,path[i-1])}’와 ‘${title(labels,path[i-1])} → ${title(labels,path[i])}’를 연결하면 ‘${title(labels,from)} → ${title(labels,path[i])}’가 됩니다.`);
          }
        }
      }
      proofs.push({kind:'order',from,to,label:`${title(labels,from)} → ${title(labels,to)}`,
        indirect:!!path && path.length>2, supported, facts:ids,
        rules:path?.length>2?['rule-direct','rule-chain']:['rule-direct'], lines,
        conclusion:`‘${title(labels,from)}’를 ‘${title(labels,to)}’보다 먼저 해야 합니다.`});
    }
    for(const [step,output] of Object.entries(result.input_of)) {
      const supports=[];
      facts.dep.forEach(([current,needs],i)=>{
        if(current!==step)return;
        facts.produces.forEach(([producer,value],j)=>{
          if(producer===needs && value===output)supports.push({needs,i,j});
        });
      });
      const support=supports.length===1?supports[0]:null;
      proofs.push({kind:'input',label:`${artifact(labels,output)} → ${title(labels,step)}`,
        supported:!!support, facts:support?['dep-'+support.i,'produce-'+support.j]:[], rules:['rule-handoff'],
        lines:support?[
          `입력 사실: ‘${title(labels,step)}’에는 ‘${title(labels,support.needs)}’가 필요합니다.`,
          `입력 사실: ‘${title(labels,support.needs)}’는 ‘${artifact(labels,output)}’을 만듭니다.`,
          '규칙 3 적용: 필요한 앞 단계가 만든 결과물을 다음 단계의 입력으로 연결합니다.'
        ]:[], conclusion:`‘${artifact(labels,output)}’을 ‘${title(labels,step)}’의 입력으로 넘깁니다.`});
    }
    return proofs;
  }
  function maker(document) {
    return (tag,text='',className='')=>{const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;};
  }
  function renderInputs(container,facts,labels,document) {
    const el=maker(document);container.replaceChildren();
    container.append(el('h4',`선행 조건 ${facts.dep.length}개`));
    facts.dep.forEach(([step,needs],i)=>{
      const row=el('div','','fact-row');row.id='dep-'+i;
      row.append(el('span',`조건 ${i+1}`,'fact-tag'),el('p',`${title(labels,step)} 전에 ${title(labels,needs)}가 필요합니다.`));container.append(row);
    });
    container.append(el('h4',`각 단계가 만드는 결과물 ${facts.produces.length}개`));
    facts.produces.forEach(([step,output],i)=>{
      const row=el('div','','fact-row');row.id='produce-'+i;
      row.append(el('span',title(labels,step),'fact-tag'),el('p',`만드는 것 → ${artifact(labels,output)}`));container.append(row);
    });
  }
  function clearHighlights(document) {
    for(const item of document.querySelectorAll('.fact-row, .rule-list li'))item.classList.remove('evidence-active');
  }
  function renderResult(container,run,document) {
    const el=maker(document);container.replaceChildren();clearHighlights(document);
    const statuses={running:'추론 중',failed:'실패',cancelled:'취소됨',completed:'완료'};
    if(run.status!=='completed' || !run.result) {
      container.append(el('p',`${statuses[run.status]||'실행 전'}${run.error?' · '+run.error:''}`,'empty-result'),
        el('p','완료된 추론 결과가 없습니다. 입력 사실과 규칙은 위에서 확인할 수 있습니다.','muted'));return;
    }
    const r=run.result, labels=run.logic_labels||{steps:{},artifacts:{}}, facts=run.facts;
    container.append(el('p',`실제 실행 완료 · 순서 관계 ${r.before.length}개 · 다음 단계의 입력 관계 ${Object.keys(r.input_of).length}개`,'score'),
      el('p',`실행 ${run.id} · 실제 엔진 ${r.engine} ${r.version}`,'muted'));
    const flow=el('div','','ontology-flow');
    r.flow.forEach((step,i)=>{
      const card=el('div','','stage-card');
      card.append(el('span',`단계 ${i+1}`,'badge'),el('h4',step.title),el('p',`받는 것: ${step.input||'없음 · 시작 단계'}`),el('p',`만드는 것: ${step.artifact}`));flow.append(card);
      if(i<r.flow.length-1)flow.append(el('span','→','flow-arrow'));
    });container.append(flow);
    if(!facts || !run.logic_labels) {
      container.append(el('p','이 실행에는 설명용 입력 정보가 없습니다. 다시 실행하면 근거를 함께 확인할 수 있습니다.','note'));return;
    }
    const proofs=proofsFor(facts,r,labels), orders=proofs.filter(p=>p.kind==='order'), inputs=proofs.filter(p=>p.kind==='input');
    const selector=el('div','','proof-selector'), orderGroup=el('div'), inputGroup=el('div');
    orderGroup.append(el('h4',`어떤 일이 먼저인가요? · ${orders.length}개`),el('p','선행 조건을 바꾼 직접 순서와, 여러 조건을 연결한 간접 순서를 구분합니다.','muted'));
    inputGroup.append(el('h4',`무엇을 다음 단계에 넘기나요? · ${inputs.length}개`));
    const explanation=el('div','','proof-explanation');explanation.id='proof-explanation';explanation.setAttribute('aria-live','polite');
    const buttons=[];
    function select(proof) {
      clearHighlights(document);buttons.forEach(([button,p])=>button.setAttribute('aria-pressed',String(p===proof)));
      explanation.replaceChildren(el('span','선택한 결과의 근거','eyebrow'),el('h4',proof.label));
      if(!proof.supported){explanation.append(el('p','저장된 입력 사실과 이 결과의 근거를 연결할 수 없습니다. 설명을 만들어내지 않고 실제 결과만 표시합니다.','note'));return;}
      for(const id of [...proof.facts,...proof.rules])document.getElementById(id)?.classList.add('evidence-active');
      const list=el('ol');proof.lines.forEach(line=>list.append(el('li',line)));explanation.append(list,el('p',`따라서 ${proof.conclusion}`,'proof-conclusion'),
        el('p','입력 사실과 실제 반환된 결과를 대조해 풀어쓴 설명입니다. 엔진 내부의 실행 순서나 추적 로그는 아닙니다.','muted'));
    }
    proofs.forEach(proof=>{
      const button=el('button',`${proof.kind==='order'?(proof.indirect?'간접 순서':'직접 순서'):'결과물 전달'} · ${proof.label}`,'relation-button');
      button.type='button';button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>select(proof));buttons.push([button,proof]);
      (proof.kind==='order'?orderGroup:inputGroup).append(button);
    });
    selector.append(orderGroup,inputGroup);container.append(el('p','아래 관계를 선택하면, 사용한 입력 사실과 규칙이 강조됩니다.','note'),selector,explanation);
    const initial=orders.filter(p=>p.indirect).sort((a,b)=>b.facts.length-a.facts.length)[0]||proofs[0];if(initial)select(initial);
    const details=el('details');details.append(el('summary','개발자용 · 실제 도출한 관계 원본'),el('pre',JSON.stringify({before:r.before,input_of:r.input_of},null,2)));container.append(details);
  }
  const api={pathBetween,proofsFor,renderInputs,renderResult};
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  else root.WirelogViz=api;
})(globalThis);
