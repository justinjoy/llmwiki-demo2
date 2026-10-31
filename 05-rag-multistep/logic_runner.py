"""Keep native engine failures outside the HTTP process."""
import json
from pathlib import Path
import subprocess
import sys
import time
from cli_backends import Cancelled, GenerationError, terminate

WORKER = Path(__file__).with_name('logic_worker.py').resolve()


def run_logic(cancel, python=sys.executable, timeout=20, probe=False):
    command = [python, '-B', str(WORKER)] + (['--probe'] if probe else [])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', start_new_session=sys.platform != 'win32')
    started = time.monotonic()
    try:
        while True:
            if cancel.is_set():
                raise Cancelled()
            if time.monotonic()-started > timeout:
                raise GenerationError('Wirelog 실행 제한 시간을 초과했습니다.')
            try:
                stdout, stderr = process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            payload = json.loads(stdout)
        except (ValueError, TypeError) as error:
            raise GenerationError('Wirelog 작업자가 유효한 결과를 반환하지 않았습니다: '+stderr[-500:]) from error
        if process.returncode or not isinstance(payload, dict) or not payload.get('ok'):
            raise GenerationError(str(payload.get('error', stderr[-500:])) if isinstance(payload, dict) else 'Wirelog 작업 실패')
        result = payload['result']
        if not probe and (result.get('engine') != 'PyreWire' or len(result.get('order', [])) != 4):
            raise GenerationError('Wirelog 결과 형식이 올바르지 않습니다.')
        return result
    finally:
        terminate(process)
