import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import multistep_rag as rag
import wirelog_reasoning as wire
from logic_runner import run_logic
from cli_backends import Cancelled, GenerationError


class RetrievalTests(unittest.TestCase):
    def test_same_retrieval_only_card_changes(self):
        rows = rag.retrieve(rag.QUESTION, 2)
        a, b = rag.build_prompt(rows, None), rag.build_prompt(rows, rag.PROCEDURE_CARD)
        self.assertNotIn(rag.PROCEDURE_CARD, a)
        self.assertIn(rag.PROCEDURE_CARD, b)
        for _, name, text in rows:
            self.assertIn(text, a)
            self.assertIn(text, b)
        self.assertEqual(len(rag.retrieve(rag.QUESTION, 6)), 6)
        self.assertEqual(rag.cosine(rag.embed(''), rag.embed('x')), 0)

    def test_mentions_are_not_accuracy(self):
        self.assertTrue(rag.score_steps('운영 규칙은 자료 없음')['2. CLAUDE.md'])
        self.assertTrue(rag.score_steps('`claude` 명령')['1. CLI 설치'])


class LogicTests(unittest.TestCase):
    def test_real_engine(self):
        result = run_logic(threading.Event())
        self.assertEqual(result['engine'], 'PyreWire')
        self.assertEqual(result['order'], ['install', 'claude_md', 'facts', 'bookkeeping'])
        self.assertEqual(len(result['before']), 6)
        self.assertEqual(len(result['input_of']), 3)
        self.assertEqual(result['flow'][2]['input'], '운영 규칙 문서')

    def test_reject_invalid_chain(self):
        good = [('install','claude_md'), ('install','facts'), ('install','bookkeeping'),
                ('claude_md','facts'), ('claude_md','bookkeeping'), ('facts','bookkeeping')]
        self.assertEqual(wire.linearize(good)[0], 'install')
        for pairs in [[], good[:-1], good+[good[0]], good+[('facts','install')], [('x','y')]]:
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                wire.linearize(pairs)

    def test_session_closed_on_failure(self):
        class Session:
            closed = False
            def __init__(self, program): pass
            def insert(self, *args): raise RuntimeError('native error')
            def close(self): Session.closed = True
        import types
        with patch.dict(sys.modules, {'pyrewire': types.SimpleNamespace(EasySession=Session)}):
            with self.assertRaises(RuntimeError): wire.reason()
        self.assertTrue(Session.closed)

    def test_missing_engine_no_fallback(self):
        with patch.dict(sys.modules, {'pyrewire': None}):
            with self.assertRaisesRegex(RuntimeError, 'PyreWire'): wire.reason()

    def test_cancel_timeout_and_bad_worker(self):
        event = threading.Event(); event.set()
        with self.assertRaises(Cancelled): run_logic(event)
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory)/'worker.py'
            worker.write_text('import time; time.sleep(5)')
            with patch('logic_runner.WORKER', worker), self.assertRaises(GenerationError):
                run_logic(threading.Event(), timeout=.1)
            worker.write_text('print("bad output")')
            with patch('logic_runner.WORKER', worker), self.assertRaises(GenerationError):
                run_logic(threading.Event())


if __name__ == '__main__': unittest.main()
