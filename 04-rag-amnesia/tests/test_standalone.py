"""Standalone selection shares adapters and preserves dry-run semantics."""
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import rag_amnesia as demo
import cli_backends


class StandaloneTests(unittest.TestCase):
    def test_each_backend_dry_run_never_calls_or_writes_and_accepts_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'criteria.md'
            path.write_text('previous memory', encoding='utf-8')
            for backend in cli_backends.BACKENDS:
                with self.subTest(backend=backend), patch.object(sys, 'argv', ['rag_amnesia.py', '--backend', backend, '--dry-run']), patch.object(demo, 'MEMORY_FILE', path), patch.object(demo, 'HERE', path.parent), patch.object(demo, 'generate', side_effect=AssertionError('called')), patch.object(cli_backends.shutil, 'which', side_effect=AssertionError('lookup')), patch('sys.stdout', new_callable=io.StringIO):
                    demo.main()
                    self.assertEqual(path.read_text(), 'previous memory')

    def test_backend_selection_and_model_default_reach_scenario(self):
        for backend in cli_backends.BACKENDS:
            with self.subTest(backend=backend), patch.object(sys, 'argv', ['rag_amnesia.py', '--agent', backend, '--mode', 'naive']), patch.object(demo, 'scenario_naive', return_value='answer') as run, patch('sys.stdout', new_callable=io.StringIO):
                demo.main()
                self.assertEqual(run.call_args.args[-1], backend)
                self.assertEqual(run.call_args.args[1], demo.DEFAULT_MODEL if backend == 'claude' else None)

    def test_fixed_mode_overwrites_old_memory_and_rereads_current_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / 'criteria.md'
            path.write_text('STALE', encoding='utf-8')
            with patch.object(demo, 'MEMORY_DIR', directory), patch.object(demo, 'MEMORY_FILE', path), patch.object(demo, 'HERE', directory), patch.object(demo, 'run_turn', side_effect=[('FRESH', []), ('ANSWER', [])]) as run, patch('sys.stdout', new_callable=io.StringIO):
                demo.scenario_fixed(None, None, False, 'codex')
                self.assertEqual(path.read_text(), 'FRESH')
                self.assertEqual(run.call_args.kwargs['memory'], 'FRESH')
                self.assertEqual(run.call_args.kwargs['backend'], 'codex')


if __name__ == '__main__':
    unittest.main()
