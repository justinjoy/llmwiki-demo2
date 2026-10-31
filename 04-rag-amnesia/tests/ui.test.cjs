const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const rag = require('../rag.js');
const scenario = require('../data.js');

class Element {
  constructor(id = '') { this.id = id; this.value = ''; this.disabled = false; this.hidden = false; this.textContent = ''; this.innerHTML = ''; this.handlers = {}; this.dataset = {}; this.children = []; this.classList = {toggle() {}}; }
  addEventListener(type, action) { this.handlers[type] = action; }
  replaceChildren(...nodes) { this.children = nodes; }
  append(node) { this.children.push(node); }
  setAttribute() {}
  removeAttribute() {}
  querySelector(selector) { return this.options?.find(option => selector.includes(`"${option.value}"`)); }
}
const names = {claude: 'Claude', cursor: 'Cursor', copilot: 'Copilot', agy: 'Antigravity', codex: 'Codex'};
function runResult(backend, status = 'complete') {
  return {id: 'run-' + backend, backend, model: backend === 'claude' ? 'claude-only' : null,
    status, phase: status === 'complete' ? 'complete' : 'turn1', top_k: 2, message: '실행 상태', memory: null,
    calls: status === 'complete' ? ['naive', 'fixed'].map(mode => ({mode, turn: 2, status: 'complete',
      answer: '<script>safe output</script>', duration_seconds: 1, criteria: {'30분 걷기': true}, models: []})) : []};
}
async function setup({missing, latest} = {}) {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
  get('agent').options = Object.keys(names).map(id => Object.assign(new Element(), {value: id}));
  const buttons = ['0', '1', '2', '3'].map(step => Object.assign(new Element(), {dataset: {step}}));
  const info = {service: 'rag-amnesia-cli', default_backend: 'claude', token: 'test', latest_run: latest ? latest.id : null,
    backends: Object.entries(names).map(([id, label]) => ({id, label, available: id !== missing, model: id === 'claude' ? 'claude-only' : null})),
    docs: scenario.docs, queries: scenario.queries, criteria: scenario.criteria, system_prompt: scenario.systemPrompt};
  let selectedRun = latest, pendingStatus = 'complete';
  const requests = [], timers = new Map(); let serial = 0;
  const fetch = async (url, options = {}) => {
    let data;
    if (url === '/api/status') data = info;
    else if (url === '/api/runs') { const body = JSON.parse(options.body); requests.push(body); selectedRun = runResult(body.backend, pendingStatus); data = {id: selectedRun.id}; }
    else data = selectedRun;
    return {ok: true, headers: {get: () => 'application/json'}, json: async () => structuredClone(data)};
  };
  const context = vm.createContext({AmnesiaRag: rag, SCENARIO: scenario, document: {getElementById: get,
      querySelectorAll: () => buttons, createElement: () => new Element()}, fetch, console,
    setTimeout: callback => {timers.set(++serial, callback); return serial;}, clearTimeout: id => timers.delete(id)});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8'), context);
  for (let i = 0; i < 20; i++) await Promise.resolve();
  return {get, requests, timers, choose: async id => {get('agent').value = id; await get('agent').handlers.change({target: get('agent')});},
    status: value => {pendingStatus = value;}, complete: () => {selectedRun = runResult(selectedRun.backend);}};
}

test('all five UI selections dispatch the selected backend and preserve answer identity', async () => {
  const ui = await setup();
  for (const [id, label] of Object.entries(names)) {
    await ui.choose(id);
    assert.ok(ui.get('play').textContent.includes(label));
    assert.ok(!ui.get('naive-body').innerHTML.includes('safe output'));
    await ui.get('play').handlers.click();
    assert.equal(ui.requests.at(-1).backend, id);
    assert.ok(ui.get('naive-body').innerHTML.includes(`실제 ${label} 응답`));
    assert.ok(ui.get('naive-body').innerHTML.includes('&lt;script&gt;safe output&lt;/script&gt;'));
    assert.equal(ui.get('agent').disabled, false);
    if (id !== 'claude') assert.ok(!ui.get('model-info').textContent.includes('claude-only'));
  }
});

test('active requests lock CLI/Top K and unlock after polling completion', async () => {
  const ui = await setup(); ui.status('running'); await ui.choose('codex');
  await ui.get('play').handlers.click();
  assert.equal(ui.get('agent').disabled, true);
  assert.equal(ui.get('top-k').disabled, true);
  assert.equal(ui.get('play').disabled, true);
  assert.equal(ui.get('cancel').disabled, false);
  ui.complete(); await [...ui.timers.values()][0]();
  assert.equal(ui.get('agent').disabled, false);
  assert.equal(ui.get('top-k').disabled, false);
  assert.ok(ui.get('naive-body').innerHTML.includes('실제 Codex 응답'));
});

test('reconnect restores run backend; unavailable selection does not enable execute', async () => {
  const restored = await setup({latest: runResult('agy')});
  assert.equal(restored.get('agent').value, 'agy');
  assert.ok(restored.get('naive-body').innerHTML.includes('실제 Antigravity 응답'));
  const ui = await setup({missing: 'cursor'});
  assert.equal(ui.get('agent').options.find(option => option.value === 'cursor').disabled, true);
  await ui.choose('cursor');
  assert.equal(ui.get('play').disabled, true);
  assert.ok(ui.get('connection-status').textContent.includes('설치 필요'));
});
