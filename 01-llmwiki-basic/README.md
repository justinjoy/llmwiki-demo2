# 01. LLM Wiki 기초 실습

흩어진 문서를 LLM이 읽고, 연결된 Markdown 위키로 정리하고, 새 자료가 들어올 때 기존 지식을 갱신하는 실습입니다. 질문할 때마다 원문을 다시 조합하는 대신 검토 가능한 지식을 파일로 축적합니다.

[Andrej Karpathy의 LLM Wiki 아이디어](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)를 바탕으로 만든 자체 교육 예제입니다. 원문은 특정 제품 구현이 아닌 운영 패턴을 설명합니다. 아래 자료와 운영 규칙은 이 실습을 위해 작성했습니다.

## 준비

로컬 파일을 읽고 수정할 수 있는 LLM 에이전트와 Markdown 편집기를 준비합니다. 별도 패키지, API 키, 검색 서버는 필요하지 않습니다. Obsidian은 선택 사항입니다. 이 저장소를 에이전트에서 연 뒤 아래 프롬프트를 순서대로 전달하세요. 프롬프트의 경로는 저장소 루트 기준입니다. 자동 지침 로딩 여부와 관계없이 첫 프롬프트에서 운영 규약을 직접 읽게 합니다.

**모든 프로젝트명·인물·일정·수치는 가상입니다. 실제 회사의 정책이나 결정이 아닙니다.**

## Python 스크립트로 실행

Python **3.9 이상**과 사용할 CLI 하나를 설치하고 해당 계정으로 먼저 로그인합니다. 실행기와 테스트는 표준 라이브러리만 사용합니다. [requirements.txt](requirements.txt)에 별도 Python 패키지가 없음을 명시했습니다. 실행에는 각 서비스의 사용 권한이 필요하며 사용량에 따라 비용이 발생할 수 있습니다. 설치·로그인은 스크립트가 대신 수행하지 않습니다.

저장소 루트에서 실행합니다. 인자 없이 실행하면 터미널에서 도구를 선택합니다.

```console
python3 -m pip install -r 01-llmwiki-basic/requirements.txt
python3 01-llmwiki-basic/build_wiki.py
```

첫 줄은 공통 준비 명령이며 추가 설치할 패키지가 없어 생략해도 됩니다. [build_wiki.py](build_wiki.py)는 어느 디렉터리에서 호출해도 자신의 위치를 기준으로 저장소 루트에서 CLI를 실행합니다. 다른 위치에서는 스크립트의 절대 경로를 지정하세요.

```console
python3 01-llmwiki-basic/build_wiki.py --agent agy
python3 01-llmwiki-basic/build_wiki.py --agent codex
python3 01-llmwiki-basic/build_wiki.py --agent claude
python3 01-llmwiki-basic/build_wiki.py --agent cursor
python3 01-llmwiki-basic/build_wiki.py --agent copilot
```

위 명령 중 **하나만 선택**하면 됩니다. 기본 `--step all`은 `ingest-01` → `ingest-02` → `query` → `lint`를 별도 CLI 호출로 순서대로 실행합니다. 대화 세션을 공유하지 않고 파일로 지식을 이어갑니다. [prompts/](prompts/)의 공통 프롬프트를 사용하며 생성 위치는 `01-llmwiki-basic/wiki/`입니다. 실제로 선택된 모델과 인증 설정은 각 CLI의 기존 설정을 사용합니다.

| 선택값 | 필요한 실행 파일 | 호출 방식 | 설치·인증 및 옵션 참고 |
| --- | --- | --- | --- |
| `agy` | `agy` (Antigravity CLI) | `agy --mode accept-edits -p PROMPT` | [Antigravity CLI](https://antigravity.google/docs/cli/reference) — 먼저 `agy`를 실행해 로그인 |
| `codex` | `codex` | `codex exec --sandbox workspace-write PROMPT` | [Codex CLI](https://learn.chatgpt.com/docs/non-interactive-mode) — `codex login` |
| `claude` | `claude` (Claude Code) | `claude --permission-mode acceptEdits -p PROMPT` | [Claude Code CLI](https://code.claude.com/docs/en/cli-reference) — 먼저 `claude`를 실행해 로그인 |
| `cursor` | `cursor-agent` | `cursor-agent --force -p PROMPT` | [Cursor CLI](https://cursor.com/docs/cli/reference/parameters) — `cursor-agent login` |
| `copilot` | `copilot` (GitHub Copilot CLI) | `copilot --allow-tool=read --allow-tool=write --assisted-approval -p PROMPT` | [Copilot CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference) — `copilot login` |

`cursor`는 에디터 실행 명령이 아닌 `cursor-agent`를 사용합니다. `copilot`은 기존 `gh copilot` 확장과 다릅니다. CLI 버전에 따라 옵션과 승인 정책이 달라질 수 있으므로 설치된 CLI의 `--help`를 확인하세요. 위 옵션은 파일 편집을 가능하게 하며 Cursor의 `--force`는 명시적으로 거부된 항목 외 명령도 허용합니다. 원본 보존과 `wiki/` 쓰기 범위는 프롬프트 규약이고, 모든 도구에 동일한 파일 접근 격리를 제공하는 것은 아닙니다. 계정·관리 정책에서 작업을 거부하면 CLI 진단을 확인하세요.

Copilot은 명시적으로 읽기·쓰기를 허용하고, 추가 권한 요청에는 `--assisted-approval`의 자동 심사를 사용합니다. 읽기·쓰기 허용만으로는 모델이 만든 임시 파일을 셸 명령으로 정리하지 못하는 사례가 실제 실행에서 발생했습니다. 자동 심사는 모든 요청의 승인을 보장하지 않으며 기존 거부 규칙과 관리 정책을 따릅니다. [Copilot 권한 문서](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools)

실행 전에 명령의 **인자 배열(JSON)**과 전체 프롬프트를 확인할 수 있습니다. 미리보기는 CLI 설치·로그인 없이 사용할 수 있고 파일을 수정하지 않습니다.

```console
python3 01-llmwiki-basic/build_wiki.py --agent codex --dry-run
python3 01-llmwiki-basic/build_wiki.py --agent claude --step ingest-01
python3 01-llmwiki-basic/build_wiki.py --agent claude --step ingest-02
python3 01-llmwiki-basic/build_wiki.py --agent claude --step query
python3 01-llmwiki-basic/build_wiki.py --agent claude --step lint
python3 01-llmwiki-basic/build_wiki.py --help
```

`ingest-02`는 첫 ingest 결과가 필요하고, 이 실행기의 `query`와 `lint`는 두 ingest 결과가 모두 필요합니다. 실행기가 필요한 선행 페이지를 검사하며 누락되거나 비어 있으면 CLI를 호출하지 않습니다. 도구를 바꿔 다음 단계를 실행해도 같은 위키 파일을 읽습니다. 비대화형 환경에서는 `--agent`를 반드시 지정합니다.

ingest 실행 전에 `wiki/sources/`, `wiki/topics/`를 Python으로 준비합니다. 따라서 부모 폴더 생성에 별도 셸 권한이 필요한 CLI도 파일 도구로 페이지를 만들 수 있습니다. CLI 종료 후에는 필수 페이지·index·log가 비어 있지 않은지, 기존 log가 그대로 보존되고 해당 작업의 날짜가 있는 기록이 추가됐는지 검사합니다. 종료 코드 0이어도 이 검사를 통과하지 못하면 코드 1로 중단합니다.

CLI가 실패 코드로 종료하면 이후 호출을 중단하고 해당 코드를 반환합니다. **이미 반영된 파일은 남으며 자동 복구·초기화하지 않습니다.** 위키를 검토한 뒤 실패한 단계만 다시 실행하세요. 위 검사는 구조적인 완료 조건이며 사실의 정확성·출처 링크·index 내용까지 보장하지 않습니다. 아래 완료 기준과 CLI 출력을 확인해야 합니다. 재실행은 기존 위키 갱신 요청이며 시작 상태로 초기화하지 않습니다.

개발 검증은 실제 모델 호출 없이 모의 CLI로 인자·작업 위치·단계 순서·실패 전파·미리보기의 무호출을 검사합니다.

```console
python3 -m unittest discover -s 01-llmwiki-basic/tests -v
```

모의 검증은 각 서비스의 로그인 성공이나 실제 위키 생성 품질을 보장하지 않습니다. 실제 모델 호출 결과와 수정 내역은 [실제 CLI 검증 기록](tests/live-test-results.md)에 따로 기록합니다. 아래 수동 실습 프롬프트도 계속 사용할 수 있습니다.

## 세 계층

| 계층 | 위치 | 역할 |
| --- | --- | --- |
| 원본 | `raw/` | 사람이 고른 자료. 에이전트는 읽기만 합니다. |
| 위키 | `wiki/` | 요약·주제·답변을 연결하고 누적 갱신합니다. |
| 운영 규약 | [AGENTS.md](AGENTS.md) | 구조, 출처, 충돌 처리, 작업 순서를 정합니다. |

```text
01-llmwiki-basic/
├── AGENTS.md
├── README.md
├── build_wiki.py                 # 도구 선택 및 단계별 CLI 실행
├── requirements.txt              # 외부 Python 패키지 없음
├── prompts/                      # CLI에 전달하는 단계별 프롬프트
├── tests/                        # 실제 모델 호출 없는 실행기 검증
├── raw/
│   ├── 01-project-brief.md
│   └── 02-meeting-notes.md
├── wiki/
│   ├── index.md                  # 내용별 탐색, 현재는 시작 안내
│   └── log.md                    # 시간순 작업 이력, 현재는 비어 있음
└── examples/
    └── expected-output.md        # 실습 후 비교할 참고 예시
```

`sources/`, `topics/`, `answers/`는 실습 중 `wiki/` 아래에 생성합니다. 시작부터 완성 위키를 제공하지 않으므로 자료가 추가될 때 무엇이 바뀌는지 볼 수 있습니다.

## 1. 첫 자료로 위키 만들기 — ingest

다음 프롬프트를 전달합니다.

```text
01-llmwiki-basic/AGENTS.md를 읽고 그 규약을 따라라.
이번 단계에서는 raw/01-project-brief.md만 읽어 ingest하라.
raw/02-meeting-notes.md와 examples/는 아직 읽거나 반영하지 마라.
경로는 모두 01-llmwiki-basic 아래를 기준으로 한다.
wiki/sources/project-brief.md에 원본 요약을 만들고,
wiki/topics/training-project.md에 교육 프로젝트의 목표·대상·운영·미확정 사항을 정리하라.
주장마다 원본의 절로 이어지는 상대 Markdown 링크를 달아라.
wiki/index.md에 각 페이지 링크와 한 줄 설명을 추가하고 wiki/log.md에 ingest를 기록하라.
raw/는 수정하지 말고, 마지막에 생성·수정한 파일과 확인이 필요한 사항을 보고하라.
```

`wiki/index.md`에서 요약과 주제 페이지로 이동하고, 각 주장의 링크가 원본 근거로 이어지는지 확인하세요. 첫 단계에서는 **30명, 대면 4시간, 11월 20일**이 나타나야 합니다.

## 2. 새 자료를 반영하기 — incremental ingest

두 번째 자료는 이미 연습용으로 들어 있지만 이 단계에서 처음 처리합니다.

```text
01-llmwiki-basic/AGENTS.md와 wiki/index.md, 기존 위키 페이지를 읽어라.
경로는 모두 01-llmwiki-basic 아래를 기준으로 한다.
이제 raw/02-meeting-notes.md를 ingest하여 wiki/sources/meeting-notes.md를 만들고
기존 wiki/topics/training-project.md를 갱신하라. 같은 주제의 중복 페이지를 만들지 마라.
확정된 일정 변경과 승인되지 않은 인원·교육 방식 제안을 구분하라.
충돌은 두 원본의 링크와 확인 질문을 함께 남기고 최신 날짜만으로 덮어쓰지 마라.
index를 갱신하고 log에는 새 기록만 추가하라. raw/와 과거 log는 변경하지 마라.
마지막에 이전 위키 대비 바뀐 주장, 남은 충돌, 변경 파일을 보고하라.
```

**11월 27일**은 승인된 일정 변경으로 반영되어야 합니다. **30명/60명, 대면 4시간/온라인 2시간**은 결론이 아닌 미해결 충돌로 남아야 합니다. 기존 topic 파일이 갱신되고 새 원본 요약이 추가됐는지 확인하세요.

## 3. 근거를 따라 질문하기 — query

```text
01-llmwiki-basic/AGENTS.md를 읽어라.
01-llmwiki-basic/wiki/index.md부터 관련 위키를 찾아 읽고 다음에 답하라.
“이 교육의 현재 일정과 운영 방식은 무엇이며, 안내문 발송 전에 무엇을 확인해야 하는가?”
확정 사실·제안·미확정 사항을 구분하고 위키 및 원본 근거를 링크하라.
터미널 답변의 링크는 저장소 루트 기준 01-llmwiki-basic/wiki/... 또는
01-llmwiki-basic/raw/... 경로로 표시하라. 위키 내부 상대 링크를 그대로 복사하지 마라.
자료에 없는 담당자나 결정을 만들어내지 마라. 이번에는 답변 파일을 만들지 말고
규약에 따라 query 수행 사실만 wiki/log.md에 추가하라.
```

답변을 재사용하려면 이어서 아래처럼 요청합니다. 저장도 새 위키 지식을 축적하는 작업입니다.

```text
방금 답변을 01-llmwiki-basic/wiki/answers/launch-checklist.md로 저장하라.
관련 주제와 원본 링크를 포함하고 index에 등록한 뒤 log에 저장 사실을 추가하라.
```

## 4. 위키 점검하기 — lint

```text
01-llmwiki-basic/AGENTS.md를 읽고 wiki/만 대상으로 lint하라.
끊어진 상대 링크, index 누락, 고립 페이지, 출처 없는 주장,
날짜가 지난 주장, 누락된 충돌, 중복 주제, 근거가 부족한 부분을 점검하라.
검사 범위와 발견 사항을 파일·절 단위로 보고하라.
명백한 링크/index 오류는 수정하되, 사실 판단이 필요한 사항은 질문으로 남겨라.
새 자료 검색이나 raw 수정은 하지 말고 log에 점검 결과를 추가하라.
```

문법이나 링크 점검만으로 사실의 정확성이 보장되지는 않습니다. 인원과 방식의 충돌이 모두 남아 있는지 원본과 직접 대조하세요.

## 완료 기준

- 원본 요약 2개, 누적 갱신된 주제 1개가 있고 모든 페이지가 index에서 연결됩니다.
- 일정 변경에는 승인 근거가 있고, 인원·방식의 충돌에는 양쪽 근거와 확인 질문이 있습니다.
- 질문 답변은 확정 사실과 미확정 사항을 구분하며 근거로 돌아갈 수 있습니다.
- log에는 실제 수행한 ingest/query/lint가 시간순으로 추가되고 과거 기록은 보존됩니다.
- raw 두 파일이 원래 상태이며, 자료에 없는 사실을 추가하지 않았습니다.

Git을 사용할 경우 저장소 루트에서 `git status --short`와 `git diff -- 01-llmwiki-basic`으로 변경 파일을 확인합니다. 커밋된 시작 상태와 비교할 때 `git diff --exit-code HEAD -- 01-llmwiki-basic/raw`가 성공하면 원본 내용이 같습니다. 새 파일은 `git diff`에 나오지 않으므로 `git status`와 실제 파일 내용도 확인하세요.

마친 뒤 [예상 결과 예시](examples/expected-output.md)와 비교하세요. 다시 연습하려면 이 폴더를 별도로 복사하여 생성된 위키 페이지를 제외하고 `wiki/index.md`, `wiki/log.md`를 시작 상태로 복원하세요. 기존 결과를 보관한 뒤 진행합니다.
