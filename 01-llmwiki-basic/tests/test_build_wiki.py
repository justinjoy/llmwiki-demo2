"""실제 모델 호출 없이 CLI 경계, 실행 순서와 오류 전파를 검증한다."""

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


SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_wiki", SOURCE / "build_wiki.py")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo with spaces $literal"
        self.project = self.root / "01-llmwiki-basic"
        self.project.mkdir(parents=True)
        shutil.copy(SOURCE / "build_wiki.py", self.project)
        shutil.copytree(SOURCE / "prompts", self.project / "prompts")
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.log = Path(self.temp.name) / "calls.jsonl"
        self.env = dict(os.environ, PATH=str(self.bin), MOCK_LOG=str(self.log))
        self.cwd = Path(self.temp.name)

    def mock_cli(self, name):
        # 절대 interpreter 경로를 써서 격리된 PATH에서도 실행한다.
        path = self.bin / name
        path.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, signal, sys\n"
            "log = pathlib.Path(os.environ['MOCK_LOG'])\n"
            "with log.open('a') as stream:\n"
            "    stream.write(json.dumps({'argv': sys.argv, 'cwd': os.getcwd()}) + '\\n')\n"
            "if os.environ.get('MOCK_FAIL_MATCH', '') and os.environ['MOCK_FAIL_MATCH'] in sys.argv[-1]:\n"
            "    sys.exit(23)\n"
            "if os.environ.get('MOCK_SIGNAL'):\n"
            "    os.kill(os.getpid(), signal.SIGTERM)\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_launcher(self, *args):
        return subprocess.run(
            [sys.executable, str(self.project / "build_wiki.py"), *args],
            cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
            text=True, capture_output=True,
        )

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_each_backend_receives_exact_argv_cwd_and_multiline_prompt(self):
        expected = {
            "agy": ["agy", "--mode", "accept-edits", "-p"],
            "codex": ["codex", "exec", "--sandbox", "workspace-write"],
            "claude": ["claude", "--permission-mode", "acceptEdits", "-p"],
            "cursor": ["cursor-agent", "--force", "-p"],
            "copilot": ["copilot", "--allow-tool=read", "--allow-tool=write", "-p"],
        }
        prompt = "한글과 공백\n'quoted' $(touch SHOULD_NOT_EXIST); `echo nope`\n"
        (self.project / "prompts/ingest-01.txt").write_text(prompt, encoding="utf-8")
        for agent, command in expected.items():
            with self.subTest(agent=agent):
                executable = self.mock_cli(command[0])
                result = self.run_launcher("--agent", agent, "--step", "ingest-01")
                self.assertEqual(result.returncode, 0, result.stderr)
                call = self.calls()[-1]
                self.assertEqual(call["argv"], [str(executable), *command[1:], prompt])
                self.assertEqual(Path(call["cwd"]).resolve(), self.root.resolve())
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_all_runs_four_distinct_prompts_in_order(self):
        self.mock_cli("codex")
        result = self.run_launcher("--agent", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = [(self.project / f"prompts/{step}.txt").read_text() for step in launcher.STEPS]
        self.assertEqual([call["argv"][-1] for call in self.calls()], expected)

    def test_individual_steps_make_only_one_call(self):
        self.mock_cli("claude")
        for step in launcher.STEPS:
            with self.subTest(step=step):
                before = len(self.calls())
                result = self.run_launcher("--agent", "claude", "--step", step)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(self.calls()), before + 1)
                self.assertEqual(self.calls()[-1]["argv"][-1],
                                 (self.project / f"prompts/{step}.txt").read_text())

    def test_failure_stops_later_calls_and_preserves_exit_code(self):
        self.mock_cli("copilot")
        self.env["MOCK_FAIL_MATCH"] = "승인되지 않은 인원"
        result = self.run_launcher("--agent", "copilot")
        self.assertEqual(result.returncode, 23)
        self.assertEqual(len(self.calls()), 2)
        self.assertIn("ingest-02", result.stderr)
        self.assertNotIn("CLI 호출을 마쳤습니다", result.stdout)

    @unittest.skipUnless(os.name == "posix", "POSIX signal test")
    def test_signal_exit_is_converted_and_stops(self):
        self.mock_cli("agy")
        self.env["MOCK_SIGNAL"] = "1"
        result = self.run_launcher("--agent", "agy")
        self.assertEqual(result.returncode, 143)
        self.assertEqual(len(self.calls()), 1)

    def test_dry_run_without_installed_cli_and_without_writes(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.run_launcher("--agent", "cursor", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cursor-agent", result.stdout)
        self.assertEqual(result.stdout.count("명령 argv (JSON):"), 4)
        self.assertIn((self.project / "prompts/lint.txt").read_text(), result.stdout)
        self.assertFalse(self.calls())
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_dry_run_does_not_call_an_installed_cli(self):
        self.mock_cli("cursor-agent")
        result = self.run_launcher("--agent", "cursor", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls())

    def test_missing_cli_reports_executable_and_exit_127(self):
        result = self.run_launcher("--agent", "cursor")
        self.assertEqual(result.returncode, 127)
        self.assertIn("cursor-agent CLI가 PATH에 없습니다", result.stderr)

    def test_prompt_preflight_happens_before_any_cli(self):
        self.mock_cli("codex")
        path = self.project / "prompts/lint.txt"
        for content in (None, " \n", b"\xff"):
            with self.subTest(content=content):
                if content is None:
                    path.unlink()
                elif isinstance(content, bytes):
                    path.write_bytes(content)
                else:
                    path.write_text(content)
                result = self.run_launcher("--agent", "codex")
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.calls())

    def test_bad_arguments_and_non_tty_selection_fail_without_calls(self):
        for args in (("--agent",), ("--agent", "unknown"), ("--step", "bad"),
                     ("--unknown",), ("--agent", ""), ()):
            with self.subTest(args=args):
                result = self.run_launcher(*args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.calls())

    def test_help_needs_no_cli_or_selection(self):
        result = self.run_launcher("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--dry-run", result.stdout)
        self.assertFalse(self.calls())

    def test_tty_selection_by_number_and_name(self):
        for choice, expected in (("4", "cursor"), ("agy", "agy")):
            with self.subTest(choice=choice), patch.object(sys.stdin, "isatty", return_value=True), \
                    patch("builtins.input", return_value=choice), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(launcher.select_agent(launcher.argparse.ArgumentParser()), expected)

    def test_tty_invalid_choice_and_eof_are_controlled_errors(self):
        for choice in ("0", "invalid", EOFError):
            with self.subTest(choice=choice), patch.object(sys.stdin, "isatty", return_value=True), \
                    patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
                kwargs = {"side_effect": choice} if choice is EOFError else {"return_value": choice}
                with patch("builtins.input", **kwargs), self.assertRaises(SystemExit) as exc:
                    launcher.select_agent(launcher.argparse.ArgumentParser())
                self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
