"""합성 실제 문서 추출과 모의 CLI 경계를 검증한다. 모델 품질 검증은 아니다."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("general_launcher", SOURCE / "build_wiki.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def make_pdf(path, pages=("First page", "Second page"), encrypted=False):
    # Minimal real PDF, with no fixture-only dependency such as reportlab.
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    ref = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(width=595, height=842)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): ref})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 40 700 Td ({text}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('secret')
    with path.open('wb') as f:
        writer.write(f)


def make_hwpx(path, order=(10, 2), bad_ref=False, entity=False, root_href=False):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/hwp+zip')
        items = ''.join(f'<opf:item id="s{i}" href="{"Contents/" if root_href else ""}section{i}.xml"/>' for i in order)
        refs = ''.join(f'<opf:itemref idref="s{i}"/>' for i in order)
        if bad_ref:
            refs += '<opf:itemref idref="missing"/>'
        z.writestr('Contents/content.hpf', f'<opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>{items}</opf:manifest><opf:spine>{refs}</opf:spine></opf:package>')
        for i in order:
            body = f'<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>구역 {i}</hp:t><hp:t><hp:tab/>끝</hp:t></hp:run></hp:p><hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>표 셀</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hp:sec>'
            if entity:
                body = '<!DOCTYPE a [<!ENTITY x "bad">]>' + body
            z.writestr(f'Contents/section{i}.xml', body)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'raw').mkdir()

    def parse(self, name):
        path = self.root / 'raw' / name
        return app.extract(path, path.read_bytes())[0]

    def test_docx_paragraph_table_order_and_nested_cells(self):
        from docx import Document
        doc = Document()
        doc.add_paragraph('처음')
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = '중간 A'
        table.cell(0, 1).text = '중간 B'
        table.cell(0, 0).add_table(rows=1, cols=1).cell(0, 0).text = '내부 표'
        doc.add_paragraph('마지막')
        doc.save(self.root / 'raw/회의.DOCX')
        text = self.parse('회의.DOCX')
        self.assertLess(text.index('처음'), text.index('중간 A'))
        self.assertLess(text.index('중간 B'), text.index('마지막'))
        self.assertIn('내부 표', text)
        self.assertIn('Block 2', text)

    def test_pdf_page_order(self):
        make_pdf(self.root / 'raw/a.pdf')
        text = self.parse('a.pdf')
        self.assertLess(text.index('First page'), text.index('Second page'))
        self.assertIn('Page 2', text)

    def test_pdf_empty_page_and_encryption_fail(self):
        for pages, encrypted, needle in [(('Good', ''), False, 'OCR'), (('Good',), True, '암호')]:
            with self.subTest(needle=needle):
                make_pdf(self.root / 'raw/a.pdf', pages, encrypted)
                with self.assertRaisesRegex(app.WikiError, needle):
                    self.parse('a.pdf')

    def test_hwpx_spine_order_table_and_mixed_text(self):
        make_hwpx(self.root / 'raw/a.hwpx')
        text = self.parse('a.hwpx')
        self.assertLess(text.index('구역 10'), text.index('구역 2'))
        self.assertEqual(text.count('표 셀'), 2)
        self.assertIn('끝', text)
        self.assertIn('Section 2', text)

    def test_hwpx_bad_reference_and_entity_rejected(self):
        for kwargs in ({'bad_ref': True}, {'entity': True}):
            with self.subTest(kwargs=kwargs):
                make_hwpx(self.root / 'raw/a.hwpx', **kwargs)
                with self.assertRaises(app.WikiError):
                    self.parse('a.hwpx')

    def test_malformed_and_empty_inputs(self):
        for name, body in [('a.docx', b'bad zip'), ('a.hwpx', b'bad zip'), ('a.pdf', b'bad pdf'), ('a.txt', b''), ('a.md', b'\xff')]:
            with self.subTest(name=name):
                (self.root / 'raw' / name).write_bytes(body)
                with self.assertRaises(app.WikiError):
                    self.parse(name)

    def test_hwpx_package_root_href(self):
        make_hwpx(self.root / 'raw/a.hwpx', root_href=True)
        self.assertIn('구역 10', self.parse('a.hwpx'))

    def test_missing_library_actionable(self):
        real_import = __import__
        def missing(name, *args, **kwargs):
            if name == 'pypdf':
                raise ImportError('pypdf')
            return real_import(name, *args, **kwargs)
        with patch('builtins.__import__', missing):
            with self.assertRaisesRegex(app.WikiError, 'pip install'):
                app.extract(Path('x.pdf'), b'pdf')

    def test_limits_symlinks_unknown_and_empty_inventory(self):
        with self.assertRaises(app.WikiError):
            app.inventory(self.root)
        path = self.root / 'raw/a.txt'
        path.write_text('large')
        with patch.object(app, 'MAX_FILE', 1):
            with self.assertRaises(app.WikiError):
                app.inventory(self.root)
        path.unlink()
        (self.root / 'raw/x.hwp').write_text('old')
        with self.assertRaisesRegex(app.WikiError, 'hwpx'):
            app.inventory(self.root)
        (self.root / 'raw/x.hwp').unlink()
        try:
            path.symlink_to(self.root / 'outside')
        except OSError:
            return
        with self.assertRaisesRegex(app.WikiError, '심볼릭'):
            app.inventory(self.root)

    def test_zip_size_and_duplicate_limits(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('a', b'123')
        with patch.object(app, 'MAX_PART', 2):
            with self.assertRaises(app.WikiError):
                app.bounded_zip(data.getvalue())

    def test_manifest_ids_hash_and_atomic_failed_preparation(self):
        (self.root / 'raw/a').mkdir()
        (self.root / 'raw/b').mkdir()
        for name in ('a/한글.txt', 'b/한글.txt'):
            (self.root / 'raw' / name).write_text('내용', encoding='utf-8')
        records = app.prepare(self.root, app.inventory(self.root))
        self.assertNotEqual(records[0]['id'], records[1]['id'])
        self.assertEqual(records[0]['id'], app.source_id('a/한글.txt'))
        self.assertEqual(records[0]['policy'], app.POLICY)
        manifest = (self.root / '.prepared/manifest.json').read_bytes()
        (self.root / 'raw/z.pdf').write_bytes(b'broken')
        with self.assertRaises(app.WikiError):
            app.prepare(self.root, app.inventory(self.root))
        self.assertEqual(manifest, (self.root / '.prepared/manifest.json').read_bytes())

    def test_atomic_replace_failure_preserves_state(self):
        path = self.root / 'state.json'
        path.write_text('old')
        with patch.object(app.os, 'replace', side_effect=OSError('fail')):
            with self.assertRaises(OSError):
                app.atomic_write(path, 'new')
        self.assertEqual(path.read_text(), 'old')
        self.assertEqual(list(self.root.glob('.writing-*')), [])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'repo 공백 $literal' / '02-llmwiki-general'
        shutil.copytree(SOURCE, self.root, ignore=shutil.ignore_patterns('.venv', '__pycache__', '.prepared', '.llmwiki.lock'))
        self.raw = self.root / 'raw'
        (self.raw / '한글 $(`x`).txt').write_text('확정 내용', encoding='utf-8')
        self.calls = []
        self.original = self.root / 'build_wiki.py'

    def mock_run(self, argv, cwd, shell):
        self.assertFalse(shell)
        self.assertEqual(cwd, self.root)
        payload = json.loads(argv[-1].split('작업 데이터 JSON:\n')[1])
        self.calls.append((argv, payload))
        if getattr(self, 'fail_code', False):
            return subprocess.CompletedProcess(argv, self.fail_code)
        if getattr(self, 'no_output', False):
            return subprocess.CompletedProcess(argv, 0)
        wiki = cwd / 'wiki'
        (wiki / 'topics/topic.md').write_text('# 주제\n')
        record = payload['document']
        if record:
            (cwd / record['source']).write_text('# 원본 요약\n')
            with (wiki / 'index.md').open('a') as stream:
                stream.write(f"\n[원본](sources/{record['id']}.md)\n[주제](topics/topic.md)\n")
        with (wiki / 'log.md').open('a') as stream:
            stream.write(f"\n## [{payload['today']}] {payload['operation']} | test\n")
        return subprocess.CompletedProcess(argv, 0)

    def run_app(self, *args):
        with patch.object(app, '__file__', str(self.original)), patch.object(app.shutil, 'which', lambda name: '/mock/' + name), patch.object(app.subprocess, 'run', self.mock_run), patch('sys.stdout', new_callable=io.StringIO), patch('sys.stderr', new_callable=io.StringIO) as errors:
            result = app.main(list(args))
            self.error = errors.getvalue()
            return result

    def test_all_five_agents_and_cwd_argv(self):
        for agent, expected in app.COMMANDS.items():
            with self.subTest(agent=agent):
                self.assertEqual(self.run_app('--agent', agent, '--step', 'ingest', '--force'), 0)
                argv, data = self.calls[-1]
                self.assertEqual(argv[:-1], ['/mock/' + expected[0], *expected[1:]])
                self.assertIn('$(`x`)', data['document']['original'])

    def test_all_order_optional_question_raw_preserved_and_incremental(self):
        before = {p.name: p.read_bytes() for p in self.raw.iterdir()}
        self.assertEqual(self.run_app('--agent', 'codex', '--question', '무엇인가?'), 0)
        self.assertEqual([p['operation'] for _, p in self.calls], ['ingest', 'query', 'lint'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.raw.iterdir()})
        self.calls.clear()
        self.assertEqual(self.run_app('--agent', 'claude'), 0)
        self.assertEqual([p['operation'] for _, p in self.calls], ['lint'])
        (self.raw / '한글 $(`x`).txt').write_text('변경')
        self.calls.clear()
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'ingest'), 0)
        self.assertEqual(len(self.calls), 1)

    def test_missing_summary_reprocessed(self):
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'ingest'), 0)
        next((self.root / 'wiki/sources').glob('*.md')).unlink()
        self.calls.clear()
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'ingest'), 0)
        self.assertEqual(len(self.calls), 1)

    def test_cli_fail_and_zero_without_outputs_do_not_mark_success(self):
        for mode in ('fail', 'no_output'):
            with self.subTest(mode=mode):
                self.fail_code = 23 if mode == 'fail' else False
                self.no_output = mode == 'no_output'
                self.assertEqual(self.run_app('--agent', 'codex'), 23 if self.fail_code else 1)
                self.assertFalse((self.root / '.prepared/ingested.json').exists())
                self.assertFalse((self.root / '.llmwiki.lock').exists())
        self.no_output = False
        self.assertEqual(self.run_app('--agent', 'codex'), 0)

    def test_signal_mapping(self):
        self.fail_code = -15
        self.assertEqual(self.run_app('--agent', 'codex'), 143)

    def test_dry_run_zero_writes_calls_for_all_agents(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        for agent in app.COMMANDS:
            self.assertEqual(self.run_app('--agent', agent, '--dry-run'), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))

    def test_extract_without_agent_and_query_lint_prerequisites(self):
        self.assertEqual(self.run_app('--step', 'extract'), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'query', '--question', '질문'), 1)
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'lint'), 1)
        self.assertEqual(self.calls, [])

    def test_lock_blocks_concurrent_run(self):
        (self.root / '.llmwiki.lock').write_text('1234')
        self.assertEqual(self.run_app('--agent', 'codex'), 1)
        self.assertEqual(self.calls, [])
        self.assertTrue((self.root / '.llmwiki.lock').exists())

    def test_log_rewrite_fails(self):
        original = self.mock_run
        def bad(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.root / 'wiki/log.md').write_text('rewritten')
            return result
        self.mock_run = bad
        self.assertEqual(self.run_app('--agent', 'codex'), 1)
        self.assertFalse((self.root / '.prepared/ingested.json').exists())

    def test_missing_executable_and_os_launch_error(self):
        with patch.object(app.shutil, 'which', return_value=None):
            prompt = app.render_prompt(self.root, 'ingest')
            self.assertEqual(app.run_agent(self.root, 'codex', 'ingest', prompt), 127)
        with patch.object(app.shutil, 'which', return_value='/bad'), patch.object(app.subprocess, 'run', side_effect=OSError('bad')):
            self.assertEqual(app.run_agent(self.root, 'codex', 'ingest', prompt), 126)

    def test_real_child_processes_for_all_cli_adapters(self):
        fake = self.root / 'fake_cli.py'
        fake.write_text(r"""import json, pathlib, sys
p = json.loads(sys.argv[-1].split('작업 데이터 JSON:\n')[1])
r = pathlib.Path.cwd()
w = r / 'wiki'
assert (w / 'sources').is_dir()
(w / 'topics' / 'real.md').write_text('# Topic', encoding='utf-8')
if p['document']:
    d = p['document']
    (r / d['source']).write_text('# Summary', encoding='utf-8')
    with (w / 'index.md').open('a', encoding='utf-8') as f:
        f.write('\n[s](sources/' + d['id'] + '.md)\n')
with (w / 'log.md').open('a', encoding='utf-8') as f:
    f.write('\n## [' + p['today'] + '] ' + p['operation'] + ' | real child\n')
with (r / 'child-calls.jsonl').open('a', encoding='utf-8') as f:
    f.write(json.dumps({'args': sys.argv[1:], 'cwd': str(r)}) + '\n')
""", encoding='utf-8')
        # Bootstrap maps the executable to Python + the synthetic CLI; subprocess.run itself stays real.
        bootstrap = """import pathlib, runpy, shutil, subprocess, sys
script, fake, agent = sys.argv[1:]
real = subprocess.run
shutil.which = lambda name: str(pathlib.Path(fake))
subprocess.run = lambda argv, **kw: real([sys.executable, *argv], **kw)
sys.argv = [script, '--agent', agent, '--force']
runpy.run_path(script, run_name='__main__')
"""
        for agent in app.COMMANDS:
            with self.subTest(agent=agent):
                result = subprocess.run([sys.executable, '-c', bootstrap, str(self.original), str(fake), agent],
                                        cwd=self.root.parent, text=True, capture_output=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in (self.root / 'child-calls.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records), 10)  # per agent: ingest + lint
        for i, command in enumerate(app.COMMANDS.values()):
            self.assertEqual(records[i * 2]['args'][:-1], command[1:])
            self.assertEqual(Path(records[i * 2]['cwd']), self.root)

    def test_removed_original_is_reported_to_ingest_and_query(self):
        extra = self.raw / 'second.txt'
        extra.write_text('second')
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'ingest'), 0)
        deleted_id = app.source_id('second.txt')
        extra.unlink()
        self.calls.clear()
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'ingest'), 0)
        self.assertIn(deleted_id, self.calls[0][1]['missing_originals'])
        self.assertTrue((self.root / 'wiki/sources' / (deleted_id + '.md')).exists())
        self.calls.clear()
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'ingest'), 0)
        self.assertEqual(self.calls, [])
        self.calls.clear()
        self.assertEqual(self.run_app('--agent', 'codex', '--step', 'query', '--question', '질문'), 0)
        self.assertIn(deleted_id, self.calls[0][1]['missing_originals'])

    def test_raw_modification_detected(self):
        original = self.mock_run
        def bad(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.raw / '한글 $(`x`).txt').write_text('changed')
            return result
        self.mock_run = bad
        self.assertEqual(self.run_app('--agent', 'codex'), 1)
        self.assertIn('원본을 변경', self.error)
        self.assertFalse((self.root / '.prepared/ingested.json').exists())

    def test_noninteractive_choice_and_query_arguments(self):
        for args in [[], ['--step', 'query', '--agent', 'codex'], ['--step', 'extract', '--question', 'x']]:
            with self.subTest(args=args), patch.object(app, '__file__', str(self.original)), patch('sys.stdin.isatty', return_value=False), patch('sys.stderr', new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as cm:
                    app.main(args)
                self.assertEqual(cm.exception.code, 2)

    def test_interactive_choice(self):
        parser = app.argparse.ArgumentParser()
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value='2'):
            self.assertEqual(app.select_agent(parser), 'codex')


if __name__ == '__main__':
    unittest.main()
