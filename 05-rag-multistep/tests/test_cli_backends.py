"""Backend adapters use explicit executable doubles, never paid model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cli_backends as cli


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


def response(backend, answer='실제 테스트 응답'):
    if backend in ('claude', 'cursor'):
        return encoded({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': answer})
    if backend == 'agy':
        return encoded({'status': 'SUCCESS', 'response': answer, 'conversation_id': 'agy-session'})
    if backend == 'codex':
        return '\n'.join(map(encoded, [{'type': 'thread.started', 'thread_id': 'codex-session'},
                          {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}},
                          {'type': 'turn.completed', 'usage': {'input_tokens': 5}}]))
    return '\n'.join(map(encoded, [{'type': 'assistant.message_delta', 'data': {'deltaContent': 'ignore delta'}},
                       {'type': 'tool.execution_complete', 'data': {'content': 'ignore tool'}},
                       {'type': 'assistant.message', 'data': {'content': answer, 'model': 'actual-model', 'toolRequests': []}},
                       {'type': 'result', 'exitCode': 0, 'sessionId': 'copilot-session'}]))


class AdapterTests(unittest.TestCase):
    def test_commands_have_no_resume_and_no_unsafe_write_approval(self):
        for backend in cli.BACKENDS:
            with self.subTest(backend=backend):
                args = cli.build_command(backend, 'CLI', None, 'SYSTEM', 'MULTI\nLINE')
                self.assertEqual(args[0], 'CLI')
                for bad in ('--resume', '--continue', '--force', '--allow-all', '--dangerously-skip-permissions', '--model'):
                    self.assertNotIn(bad, args)
                if backend == 'agy':
                    self.assertIn('--print=SYSTEM\n\nMULTI\nLINE', args)
                if backend == 'codex':
                    self.assertIn('read-only', args)
                    self.assertIn('--ephemeral', args)
                if backend == 'cursor':
                    self.assertIn('ask', args)
                if backend == 'copilot':
                    self.assertIn('--available-tools=', args)

    def test_explicit_model_only_when_specified(self):
        for backend in cli.BACKENDS:
            args = cli.build_command(backend, 'CLI', 'provider-specific-model', 's')
            self.assertEqual(args[-2:], ['--model', 'provider-specific-model'])

    def test_backend_and_model_validation(self):
        for value in (None, 'unknown', [], {}, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cli.validate_backend(value)
        for value in ('', '--unsafe', 'x\nflag', 9, 'x' * 201):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cli.validate_model(value)
        self.assertIsNone(cli.validate_model(None))

    def test_windows_copilot_uses_native_executable(self):
        with patch.object(cli.sys, 'platform', 'win32'):
            self.assertEqual(cli.executable_name('copilot'), 'copilot.exe')

    def test_success_shapes_and_last_final_only(self):
        for backend in cli.BACKENDS:
            with self.subTest(backend=backend):
                self.assertEqual(cli.parse_output(backend, response(backend))['answer'], '실제 테스트 응답')
        copilot = cli.parse_output('copilot', response('copilot'))
        self.assertEqual(copilot['models'], ['actual-model'])
        self.assertEqual(copilot['session_id'], 'copilot-session')
        codex = '\n'.join(map(encoded, [{'type': 'item.completed', 'item': {'type': 'agent_message', 'phase': 'commentary', 'text': 'progress'}},
                  {'type': 'item.completed', 'item': {'type': 'command_execution', 'text': 'tool output'}},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'phase': 'final_answer', 'text': 'final'}},
                  {'type': 'turn.completed'}]))
        self.assertEqual(cli.parse_output('codex', codex)['answer'], 'final')

    def test_invalid_empty_or_partial_output_is_never_success(self):
        for backend in cli.BACKENDS:
            for bad in ('', 'not json', '[]', '{}', response(backend, '  ')):
                with self.subTest(backend=backend, bad=bad), self.assertRaises(cli.GenerationError):
                    cli.parse_output(backend, bad)
        for backend, bad in [('claude', encoded({'is_error': True, 'result': 'failure'})),
                             ('cursor', encoded({'subtype': 'error', 'result': 'failure'})),
                             ('agy', encoded({'status': 'ERROR', 'response': 'partial'})),
                             ('codex', encoded({'type': 'turn.failed', 'error': {'message': 'failure'}})),
                             ('codex', encoded({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'partial'}})),
                             ('copilot', encoded({'type': 'assistant.message', 'data': {'content': 'partial'}})),
                             ('copilot', response('copilot') + '\n' + encoded({'type': 'session.error', 'data': {'message': 'failure'}})),
                             ('copilot', response('copilot') + '\n' + encoded({'type': 'result', 'exitCode': 1}))]:
            with self.subTest(backend=backend, bad=bad), self.assertRaises(cli.GenerationError):
                cli.parse_output(backend, bad)

    def test_real_child_process_argv_context_and_temporary_cwd_for_all_backends(self):
        real_popen = subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mock CLI.py'
            capture = Path(tmp) / 'capture.json'
            for backend in cli.BACKENDS:
                with self.subTest(backend=backend):
                    path.write_text('import os,sys,json,pathlib\n'
                        + 'data={"argv":sys.argv[1:],"stdin":sys.stdin.read(),"cwd":os.getcwd()}\n'
                        + f'pathlib.Path({str(capture)!r}).write_text(json.dumps(data))\n'
                        + f'print({response(backend)!r})\n', encoding='utf-8')
                    def native_python(argv, **kwargs):
                        self.assertFalse(kwargs['shell'])
                        return real_popen([sys.executable, str(path), *argv[1:]], **kwargs)
                    with patch.object(cli.shutil, 'which', return_value=str(path)), patch.object(cli.subprocess, 'Popen', native_python):
                        result = cli.generate('다중\n줄 $(`literal`)', None, threading.Event(), 5,
                                              backend=backend, system_prompt='COMMON SYSTEM')
                    self.assertEqual(result['answer'], '실제 테스트 응답')
                    received = json.loads(capture.read_text())
                    self.assertNotIn('claude-sonnet', str(received))
                    self.assertFalse(Path(received['cwd']).exists())
                    if backend == 'agy':
                        self.assertIn('--print=COMMON SYSTEM\n\n다중\n줄 $(`literal`)', received['argv'])
                    elif backend == 'claude':
                        self.assertEqual(received['stdin'], '다중\n줄 $(`literal`)')
                        self.assertIn('COMMON SYSTEM', received['argv'])
                    else:
                        self.assertEqual(received['stdin'], 'COMMON SYSTEM\n\n다중\n줄 $(`literal`)')

    def test_missing_executable_and_launch_failure(self):
        for backend in cli.BACKENDS:
            with self.subTest(backend=backend), patch.object(cli.shutil, 'which', return_value=None):
                with self.assertRaisesRegex(cli.GenerationError, 'PATH'):
                    cli.generate('p', None, threading.Event(), backend=backend)
        with patch.object(cli.shutil, 'which', return_value='missing'), patch.object(cli.subprocess, 'Popen', side_effect=OSError('bad')):
            with self.assertRaisesRegex(cli.GenerationError, '실행 실패'):
                cli.generate('p', None, threading.Event())

    def test_timeout_cancel_and_nonzero_for_every_backend(self):
        real_popen = subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'slow.py'
            for body, mode in [('import time;time.sleep(10)', 'timeout'), ('import time;time.sleep(10)', 'cancel'), ('import sys;sys.exit(23)', 'nonzero')]:
                path.write_text(body)
                for backend in cli.BACKENDS:
                    cancel = threading.Event()
                    if mode == 'cancel': cancel.set()
                    def native_python(argv, **kwargs):return real_popen([sys.executable, str(path)], **kwargs)
                    with self.subTest(backend=backend, mode=mode), patch.object(cli.shutil, 'which', return_value=str(path)), patch.object(cli.subprocess, 'Popen', native_python):
                        with self.assertRaises(cli.Cancelled if mode == 'cancel' else cli.GenerationError):
                            cli.generate('p', None, cancel, 0.1 if mode == 'timeout' else 5, backend=backend)

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group contract')
    def test_timeout_kills_child_after_cli_parent_exits(self):
        real_popen = subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'parent.py'
            path.write_text('import subprocess,sys\nsubprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])\n')
            def native_python(argv, **kwargs):return real_popen([sys.executable, str(path)], **kwargs)
            with patch.object(cli.shutil, 'which', return_value=str(path)), patch.object(cli.subprocess, 'Popen', native_python):
                with self.assertRaisesRegex(cli.GenerationError, '초과'):
                    cli.generate('p', None, threading.Event(), 0.1)

    def test_availability_is_discovery_not_authentication(self):
        with patch.object(cli.shutil, 'which', side_effect=lambda name: '/cli' if name == 'codex' else None):
            descriptors = cli.available_backends({'claude': 'claude-only'})
        self.assertEqual(len(descriptors), 5)
        self.assertEqual([x['id'] for x in descriptors if x['available']], ['codex'])
        self.assertEqual(next(x for x in descriptors if x['id'] == 'claude')['model'], 'claude-only')


if __name__ == '__main__':
    unittest.main()
