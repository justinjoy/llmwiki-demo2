#!/usr/bin/env python3
"""Local multi-step RAG and genuine Wirelog demonstration."""
import argparse
import copy
import json
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4
from cli_backends import BACKENDS, Cancelled, available_backends, executable_name, generate, validate_backend, validate_model
from logic_runner import run_logic
from multistep_rag import DOCS, QUESTION, SYSTEM_PROMPT, PROCEDURE_CARD, STEP_DELIVERABLES, retrieve, build_prompt, score_steps
from wirelog_reasoning import DEPS, PRODUCES, WIRELOG_PROGRAM

HERE = Path(__file__).resolve().parent


class RunManager:
    def __init__(self, backend='claude', model=None, timeout=180, logic_python=sys.executable,
                 root=None, generator=generate, logic=run_logic):
        self.default_backend = validate_backend(backend)
        self.models = {key: None for key in BACKENDS}
        self.models[backend] = validate_model(model)
        self.timeout, self.logic_python = timeout, logic_python
        self.root = Path(root) if root else HERE/'runs'
        self.generator, self.logic = generator, logic
        self.lock = threading.RLock()
        self.runs, self.latest = {}, {}
        self.active = self.worker = None
        self.cancel_event = threading.Event()
        try:
            logic(threading.Event(), python=logic_python, timeout=5, probe=True)
            self.logic_status = {'available': True, 'detail': 'PyreWire 가져오기 성공 · 실행 시 실제 추론 검증'}
        except Exception as error:
            self.logic_status = {'available': False, 'detail': str(error)}

    def snapshot(self, ident):
        with self.lock:
            return copy.deepcopy(self.runs[ident])

    def status(self):
        with self.lock:
            return {'latest': dict(self.latest), 'active': self.active}

    def start(self, kind, top_k=2, backend=None):
        if kind not in ('rag', 'logic'):
            raise ValueError('kind는 rag 또는 logic이어야 합니다.')
        backend = validate_backend(backend or self.default_backend)
        if type(top_k) is not int or not 1 <= top_k <= len(DOCS):
            raise ValueError('Top K는 1부터 6 사이의 정수여야 합니다.')
        with self.lock:
            if self.active:
                raise RuntimeError('이미 실행 중입니다.')
            ident = uuid4().hex
            retrieved = retrieve(QUESTION, top_k)
            self.runs[ident] = {'id': ident, 'kind': kind, 'status': 'running', 'phase': '준비',
                'backend': backend, 'model': self.models[backend], 'top_k': top_k,
                'question': QUESTION, 'system_prompt': SYSTEM_PROMPT,
                'retrieved': retrieved, 'procedure_card': PROCEDURE_CARD,
                'facts': {'dep': DEPS, 'produces': PRODUCES}, 'rules': WIRELOG_PROGRAM,
                'calls': [], 'result': None, 'error': None, 'started_at': time.time(), 'finished_at': None}
            self.latest[kind] = self.active = ident
            self.cancel_event = threading.Event()
            self.worker = threading.Thread(target=self.execute, args=(ident, self.cancel_event), daemon=True)
            self.worker.start()
            return ident

    def cancel(self, ident):
        with self.lock:
            if self.active == ident:
                self.cancel_event.set()

    def execute(self, ident, cancel):
        run = self.snapshot(ident)
        try:
            if run['kind'] == 'rag':
                for mode, card in [('naive', None), ('fixed', run['procedure_card'])]:
                    if cancel.is_set():
                        raise Cancelled()
                    prompt = build_prompt(run['retrieved'], card)
                    with self.lock:
                        self.runs[ident]['phase'] = mode
                        self.runs[ident]['calls'].append({'mode': mode, 'prompt': prompt, 'status': 'running'})
                    started = time.monotonic()
                    result = self.generator(prompt, run['model'], cancel, self.timeout,
                                            backend=run['backend'], system_prompt=run['system_prompt'])
                    with self.lock:
                        self.runs[ident]['calls'][-1].update(result, status='completed',
                            seconds=round(time.monotonic()-started, 2), mentions=score_steps(result['answer']))
            else:
                with self.lock:
                    self.runs[ident]['phase'] = 'Wirelog 추론'
                result = self.logic(cancel, python=self.logic_python, timeout=min(self.timeout, 30))
                with self.lock:
                    self.runs[ident]['result'] = result
            if cancel.is_set():
                raise Cancelled()
            with self.lock:
                self.runs[ident]['status'] = 'completed'
        except Cancelled:
            with self.lock:
                self.runs[ident]['status'] = 'cancelled'
        except Exception as error:
            with self.lock:
                self.runs[ident].update(status='failed', error=str(error))
        finally:
            with self.lock:
                saved = self.runs[ident]
                saved['finished_at'] = time.time()
                for call in saved['calls']:
                    if call['status'] == 'running':
                        call['status'] = saved['status']
                try:
                    directory = self.root/ident
                    directory.mkdir(parents=True, exist_ok=True)
                    temporary = directory/'result.tmp'
                    temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
                    temporary.replace(directory/'result.json')
                except OSError as error:
                    saved['error'] = (saved['error'] or '')+' 결과 저장 실패: '+str(error)
                    saved['status'] = 'failed'
                self.active = None


class Handler(BaseHTTPRequestHandler):
    def send_data(self, code, value, mime='application/json; charset=utf-8'):
        data = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
        self.send_response(code)
        for key, val in {'Content-Type': mime, 'Content-Length': str(len(data)), 'Cache-Control': 'no-store',
                         'X-Content-Type-Options': 'nosniff',
                         'Content-Security-Policy': "default-src 'self'; frame-ancestors 'none'; base-uri 'none'"}.items():
            self.send_header(key, val)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get('Host') in {f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host():
            return self.send_data(403, {'error': '로컬 주소로 접속하세요.'})
        path = urlsplit(self.path).path
        manager = self.server.manager
        if path == '/api/status':
            return self.send_data(200, {**manager.status(), 'service': 'rag-multistep',
                'token': self.server.token, 'default_backend': manager.default_backend,
                'backends': available_backends(manager.models), 'logic': manager.logic_status,
                'question': QUESTION, 'ranked': retrieve(QUESTION, len(DOCS)),
                'procedure_card': PROCEDURE_CARD, 'system_prompt': SYSTEM_PROMPT,
                'deliverables': STEP_DELIVERABLES, 'facts': {'dep': DEPS, 'produces': PRODUCES}, 'rules': WIRELOG_PROGRAM})
        if path.startswith('/api/runs/'):
            try:
                return self.send_data(200, manager.snapshot(path.removeprefix('/api/runs/')))
            except KeyError:
                return self.send_data(404, {'error': '이 서버에 해당 실행이 없습니다.'})
        static = {'/': 'index.html', '/05-rag-multistep/': 'index.html', '/05-rag-multistep': 'index.html',
                  '/app.js': 'app.js', '/styles.css': 'styles.css',
                  '/05-rag-multistep/app.js': 'app.js', '/05-rag-multistep/styles.css': 'styles.css'}
        if path in static:
            name = static[path]
            mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
            return self.send_data(200, (HERE/name).read_bytes(), mime+'; charset=utf-8')
        self.send_data(404, {'error': '찾을 수 없는 경로입니다.'})

    def do_POST(self):
        if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Run-Token', ''), self.server.token):
            return self.send_data(403, {'error': '페이지를 새로고침하세요.'})
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}'}:
            return self.send_data(403, {'error': '다른 사이트의 실행 요청입니다.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                raise ValueError('요청 크기가 올바르지 않습니다.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('JSON 객체가 필요합니다.')
            manager, path = self.server.manager, urlsplit(self.path).path
            if path == '/api/runs':
                kind = body.get('kind')
                backend = validate_backend(body.get('backend', manager.default_backend))
                if kind == 'rag' and not shutil.which(executable_name(backend)):
                    return self.send_data(503, {'error': '선택한 CLI를 설치하고 로그인하세요.'})
                if kind == 'logic' and not manager.logic_status['available']:
                    return self.send_data(503, {'error': manager.logic_status['detail']})
                ident = manager.start(kind, body.get('top_k', 2), backend)
                return self.send_data(202, {'id': ident})
            parts = path.split('/')
            if len(parts) == 5 and parts[1:3] == ['api', 'runs'] and parts[4] == 'cancel':
                manager.snapshot(parts[3])
                manager.cancel(parts[3])
                return self.send_data(200, {'cancel_requested': True})
            return self.send_data(404, {'error': '찾을 수 없는 경로입니다.'})
        except (ValueError, UnicodeDecodeError) as error:
            self.send_data(400, {'error': str(error)})
        except KeyError:
            self.send_data(404, {'error': '실행을 찾을 수 없습니다.'})
        except RuntimeError as error:
            self.send_data(409, {'error': str(error)})


def make_server(port=8005, manager=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.manager = manager or RunManager()
    server.token = secrets.token_urlsafe(32)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8005)
    parser.add_argument('--agent', '--backend', dest='backend', choices=BACKENDS, default='claude')
    parser.add_argument('--model', help='기본 agent에만 적용; 생략하면 CLI 기본 모델')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--logic-python', default=sys.executable, help='PyreWire가 설치된 Python 실행 파일')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout은 양수여야 합니다.')
    try:
        manager = RunManager(args.backend, args.model, args.timeout, args.logic_python)
        server = make_server(args.port, manager)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error)+'\n')
    print(f'Local: http://localhost:{server.server_port}/05-rag-multistep/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if manager.active:
            manager.cancel(manager.active)
        if manager.worker:
            manager.worker.join(timeout=6)
        server.server_close()


if __name__ == '__main__':
    main()
