#!/usr/bin/env python3
"""선택한 로컬 에이전트 CLI로 LLM Wiki 실습을 실행한다 (Python 3.9+)."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


COMMANDS = {
    "agy": ["agy", "--mode", "accept-edits", "-p"],
    "codex": ["codex", "exec", "--sandbox", "workspace-write"],
    "claude": ["claude", "--permission-mode", "acceptEdits", "-p"],
    "cursor": ["cursor-agent", "--force", "-p"],
    "copilot": ["copilot", "--allow-tool=read", "--allow-tool=write", "--assisted-approval", "-p"],
}
STEPS = ("ingest-01", "ingest-02", "query", "lint")
FIRST_PAGES = ("sources/project-brief.md", "topics/training-project.md")
ALL_PAGES = (*FIRST_PAGES, "sources/meeting-notes.md")


def require_pages(wiki, pages):
    for name in pages:
        path = wiki / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise ValueError(f"필수 위키 파일이 없거나 비어 있습니다: {path}")


def check_stage_result(wiki, step, previous_log):
    pages = FIRST_PAGES if step == "ingest-01" else ALL_PAGES
    require_pages(wiki, (*pages, "index.md", "log.md"))
    log = (wiki / "log.md").read_text(encoding="utf-8")
    operation = "ingest" if step.startswith("ingest-") else step
    heading = rf"^## \[\d{{4}}-\d{{2}}-\d{{2}}\] {operation} \|"
    if not log.startswith(previous_log):
        raise ValueError("기존 wiki/log.md 내용이 변경되었습니다. 과거 기록을 보존해야 합니다.")
    if not re.search(heading, log[len(previous_log):], re.MULTILINE):
        raise ValueError(f"wiki/log.md에 새 {operation} 수행 기록이 없습니다.")


def select_agent(parser):
    if not sys.stdin.isatty():
        parser.error("비대화형 실행에는 --agent가 필요합니다.")
    names = list(COMMANDS)
    print("사용할 CLI를 선택하세요.")
    for number, name in enumerate(names, 1):
        print(f"{number}) {name}")
    try:
        choice = input("선택 [1-5 또는 이름]: ").strip()
    except EOFError:
        parser.error("선택이 취소되었습니다.")
    if choice in names:
        return choice
    if choice in {str(number) for number in range(1, len(names) + 1)}:
        return names[int(choice) - 1]
    parser.error(f"잘못된 선택: {choice}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="선택한 CLI로 원본 입력 → 추가 자료 반영 → 질의 → lint를 실행합니다."
    )
    parser.add_argument("--agent", choices=COMMANDS, help="생략하면 터미널에서 선택")
    parser.add_argument("--step", choices=(*STEPS, "all"), default="all",
                        help="기본 all: 각 단계를 순서대로 별도 CLI 호출")
    parser.add_argument("--dry-run", action="store_true",
                        help="CLI 실행·설치 검사 없이 cwd, argv, 전체 프롬프트 출력")
    args = parser.parse_args(argv)
    agent = args.agent or select_agent(parser)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    steps = STEPS if args.step == "all" else (args.step,)

    # 중간 단계의 누락으로 앞 단계만 호출되는 일을 피한다.
    prompts = []
    for step in steps:
        path = script_dir / "prompts" / f"{step}.txt"
        try:
            prompt = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            parser.error(f"프롬프트를 읽을 수 없습니다: {path}: {exc}")
        if not prompt.strip():
            parser.error(f"프롬프트가 비어 있습니다: {path}")
        prompts.append((step, prompt))

    command = COMMANDS[agent]
    executable = command[0]
    if not args.dry_run:
        executable = shutil.which(executable)
        if executable is None:
            print(f"오류: {command[0]} CLI가 PATH에 없습니다. README의 설치 안내를 확인하세요.",
                  file=sys.stderr)
            return 127

    print(f"작업 위치: {repo_root}\n선택한 CLI: {agent}", flush=True)
    for step, prompt in prompts:
        argv = [executable, *command[1:], prompt]
        print(f"\n단계: {step}", flush=True)
        if args.dry_run:
            print("명령 argv (JSON): " + json.dumps(argv, ensure_ascii=False))
            print("프롬프트:\n" + prompt)
            continue
        wiki = script_dir / "wiki"
        try:
            if step != "ingest-01":
                required = FIRST_PAGES if step == "ingest-02" else ALL_PAGES
                require_pages(wiki, required)
            # Copilot의 파일 도구는 부모 폴더를 만들지 않는다. 셸 권한 없이 준비한다.
            if step.startswith("ingest-"):
                for folder in ("sources", "topics"):
                    (wiki / folder).mkdir(parents=True, exist_ok=True)
            log_path = wiki / "log.md"
            previous_log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"오류: {step} 준비 실패: {exc}", file=sys.stderr)
            return 1
        try:
            # 셸을 거치지 않아 공백·개행·셸 메타문자가 단일 프롬프트 인자로 유지된다.
            result = subprocess.run(argv, cwd=repo_root, shell=False)
        except OSError as exc:
            print(f"오류: {command[0]} 실행 실패: {exc}", file=sys.stderr)
            return 126
        if result.returncode:
            code = result.returncode if result.returncode > 0 else 128 - result.returncode
            print(f"오류: {step} 단계의 CLI가 종료 코드 {code}로 실패했습니다. "
                  "이후 단계는 실행하지 않습니다. 이미 반영된 파일은 남습니다.", file=sys.stderr)
            return code
        try:
            check_stage_result(wiki, step, previous_log)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"오류: {step} 산출물 검사 실패: {exc} "
                  "CLI 종료 코드는 0이지만 이후 단계를 실행하지 않습니다. "
                  "CLI 출력과 위키를 확인하세요. 이미 반영된 파일은 남습니다.", file=sys.stderr)
            return 1
        print(f"CLI 호출 종료: {step}", flush=True)

    if args.dry_run:
        print("\n미리보기 완료. CLI를 실행하지 않았습니다.")
    else:
        print("\nCLI 호출을 마쳤습니다. README의 완료 기준으로 생성 파일과 내용, raw 보존 여부를 확인하세요.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다. 이미 반영된 파일은 남습니다.", file=sys.stderr)
        sys.exit(130)
