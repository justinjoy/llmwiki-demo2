"""CLI adapters for independent, read-and-answer calls (standard library only)."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time


class GenerationError(Exception):
    pass


class Cancelled(Exception):
    pass


BACKENDS = {
    'claude': {'label': 'Claude', 'executable': 'claude',
               'isolation': '도구·MCP·커스터마이징·CLI 대화 저장 비활성화'},
    'cursor': {'label': 'Cursor', 'executable': 'cursor-agent',
               'isolation': 'ask 읽기 전용 모드. 사용자 설정·MCP의 완전 차단은 보장하지 않음'},
    'copilot': {'label': 'Copilot', 'executable': 'copilot',
                'isolation': '도구 제한·기본 MCP 비활성화. 사용자 설정의 완전 차단은 보장하지 않음'},
    'agy': {'label': 'Antigravity', 'executable': 'agy',
            'isolation': 'plan 모드. 사용자 설정·MCP의 완전 차단은 보장하지 않음'},
    'codex': {'label': 'Codex', 'executable': 'codex',
              'isolation': '읽기 전용 sandbox·ephemeral. 읽기 도구·사용자 설정의 완전 차단은 보장하지 않음'},
}


def validate_backend(backend):
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ValueError('backend는 claude, cursor, copilot, agy, codex 중 하나여야 합니다.')
    return backend


def executable_name(backend):
    validate_backend(backend)
    # Avoid CMD wrappers for the native Windows Copilot installation.
    return 'copilot.exe' if backend == 'copilot' and sys.platform == 'win32' else BACKENDS[backend]['executable']


def available_backends(models=None):
    return [{'id': key, **value, 'available': bool(shutil.which(executable_name(key))),
             'model': (models or {}).get(key)} for key, value in BACKENDS.items()]


def validate_model(model):
    if model is not None and (not isinstance(model, str) or not model.strip() or model.startswith('-')
                              or len(model) > 200 or any(ord(c) < 32 for c in model)):
        raise ValueError('model은 비어 있지 않은 모델 이름이어야 합니다.')
    return model


def build_command(backend, executable, model, system_prompt, prompt=""):
    validate_backend(backend)
    validate_model(model)
    if backend == 'claude':
        args = ['-p', '--system-prompt', system_prompt, '--output-format', 'json', '--tools', '',
                '--safe-mode', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--no-session-persistence']
    elif backend == 'cursor':
        args = ['--print', '--mode', 'ask', '--trust', '--output-format', 'json']
    elif backend == 'copilot':
        # Piped stdin is prompt mode. Keep multiline input out of shell wrappers.
        args = ['--silent', '--output-format', 'json', '--no-ask-user', '--available-tools=',
                '--deny-tool=read', '--deny-tool=write', '--deny-tool=shell', '--deny-tool=url',
                '--deny-tool=memory', '--disable-builtin-mcps']
    elif backend == 'agy':
        args = ['--mode', 'plan', '--output-format', 'json', '--disable-slash-commands',
                '--print=' + system_prompt + '\n\n' + prompt]
    else:
        args = ['exec', '--json', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                '--color', 'never']
    if model is not None:
        args.extend(['--model', model])
    return [executable, *args]


def _object(stdout):
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise GenerationError('CLI가 유효한 JSON 응답을 반환하지 않았습니다. CLI 버전을 확인하세요.') from error
    if not isinstance(value, dict):
        raise GenerationError('CLI 응답이 JSON 객체가 아닙니다.')
    return value


def _events(stdout):
    try:
        rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise GenerationError('CLI가 유효한 JSONL 응답을 반환하지 않았습니다.') from error
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise GenerationError('CLI 이벤트가 없거나 형식이 올바르지 않습니다.')
    return rows


def parse_output(backend, stdout):
    """Return final assistant text only; progress/tool output is never an answer."""
    validate_backend(backend)
    result = {'session_id': None, 'models': [], 'usage': None, 'cost_usd': None}
    answer = None
    if backend in ('claude', 'cursor'):
        payload = _object(stdout)
        if payload.get('type') not in (None, 'result'):
            raise GenerationError('CLI 최종 결과 객체가 아닙니다.')
        if payload.get('is_error') or payload.get('subtype', 'success') != 'success':
            raise GenerationError('CLI 생성 실패: ' + str(payload.get('result') or payload.get('errors') or payload.get('subtype'))[:2000])
        answer = payload.get('result')
        model_usage = payload.get('modelUsage')
        result.update(session_id=payload.get('session_id'),
                      models=list(model_usage) if isinstance(model_usage, dict) else [],
                      usage=payload.get('usage'), cost_usd=payload.get('total_cost_usd'))
        if not result['models'] and isinstance(payload.get('model'), str):
            result['models'] = [payload['model']]
    elif backend == 'agy':
        payload = _object(stdout)
        if payload.get('status') != 'SUCCESS' or payload.get('error'):
            raise GenerationError('Antigravity 생성 실패: ' + str(payload.get('error') or payload.get('status'))[:2000])
        answer = payload.get('response')
        result.update(session_id=payload.get('conversation_id'), usage=payload.get('usage'))
        if isinstance(payload.get('model'), str):
            result['models'] = [payload['model']]
    elif backend == 'codex':
        events = _events(stdout)
        completed = False
        for event in events:
            kind = event.get('type')
            if kind in ('error', 'turn.failed'):
                raise GenerationError('Codex 생성 실패: ' + str(event.get('error') or event.get('message'))[:2000])
            if kind == 'thread.started':
                result['session_id'] = event.get('thread_id')
            if kind == 'item.completed':
                item = event.get('item', {})
                if item.get('type') == 'agent_message' and item.get('phase') in (None, 'final_answer'):
                    answer = item.get('text')
            if kind == 'turn.completed':
                completed = True
                result['usage'] = event.get('usage')
        if not completed:
            raise GenerationError('Codex 완료 이벤트가 없습니다.')
    else:
        events = _events(stdout)
        completed = False
        for event in events:
            kind = event.get('type')
            data = event.get('data') if isinstance(event.get('data'), dict) else {}
            if kind in ('error', 'session.error') or event.get('is_error'):
                raise GenerationError('Copilot 생성 실패: ' + str(data.get('message') or event.get('error') or event.get('message'))[:2000])
            if kind == 'assistant.message' and not data.get('toolRequests'):
                answer = data.get('content')
                if isinstance(data.get('model'), str):
                    result['models'] = [data['model']]
            if kind in ('result', 'assistant.result'):
                completed = True
                if event.get('exitCode', 0) != 0:
                    raise GenerationError('Copilot 생성 실패: ' + str(event.get('exitCode')))
                result.update(session_id=event.get('sessionId') or event.get('session_id'), usage=event.get('usage'))
                if event.get('status') not in (None, 'success', 'completed'):
                    raise GenerationError('Copilot 생성 실패: ' + str(event.get('status')))
                answer = event.get('result') or data.get('content') or answer
            if kind == 'session.start':
                result['session_id'] = data.get('sessionId') or event.get('session_id')
        if not completed:
            raise GenerationError('Copilot 완료 이벤트가 없습니다.')
    if not isinstance(answer, str) or not answer.strip():
        raise GenerationError('CLI가 최종 답변을 반환하지 않았습니다. 예시 답변으로 대체하지 않습니다.')
    result['answer'] = answer.strip()
    return result


def terminate(proc):
    # A CLI may exit while its child still holds stdout/stderr open.
    # Kill the owned POSIX process group even after the parent has exited.
    try:
        if os.name == 'posix':
            os.killpg(proc.pid, signal.SIGKILL)
        elif proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=5)
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        pass
    if proc.poll() is None:
        proc.kill()
    proc.communicate(timeout=5)


def generate(prompt, model, cancel, timeout=180, *, backend='claude', system_prompt=''):
    validate_backend(backend)
    validate_model(model)
    label = BACKENDS[backend]['label']
    name = executable_name(backend)
    executable = shutil.which(name)
    if not executable:
        raise GenerationError(f'{name} CLI가 PATH에 없습니다. 설치·로그인 안내를 확인하세요.')
    command = build_command(backend, executable, model, system_prompt, prompt)
    payload = '' if backend == 'agy' else prompt if backend == 'claude' else system_prompt + '\n\n' + prompt
    started = time.monotonic()
    # Only explicit prompt context lives here; never load this repository's files as cwd.
    with tempfile.TemporaryDirectory(prefix='rag-amnesia-call-') as workspace:
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding='utf-8', cwd=workspace, shell=False,
                                    start_new_session=(os.name == 'posix'))
        except OSError as error:
            raise GenerationError(f'{label} CLI 실행 실패: {error}') from error
        with proc:
            try:
                first = True
                while True:
                    if cancel.is_set():
                        terminate(proc)
                        raise Cancelled()
                    if time.monotonic() - started > timeout:
                        terminate(proc)
                        raise GenerationError(f'{label} 응답 시간이 {timeout}초를 초과했습니다.')
                    try:
                        stdout, stderr = proc.communicate(input=payload if first else None, timeout=0.25)
                        break
                    except subprocess.TimeoutExpired:
                        first = False
                if cancel.is_set():
                    raise Cancelled()
                if proc.returncode != 0:
                    raise GenerationError(f'{label} CLI 실패 (종료 코드 {proc.returncode}): ' + (stderr.strip() or stdout.strip())[:2000])
            except BaseException:
                terminate(proc)
                raise
    result = parse_output(backend, stdout)
    result.update(duration_seconds=round(time.monotonic() - started, 2), backend=backend)
    return result
