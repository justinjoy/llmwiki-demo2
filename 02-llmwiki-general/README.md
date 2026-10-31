# 02. 범용 LLM Wiki

[01-llmwiki-basic](../01-llmwiki-basic/)의 원본 → 요약 → 주제 종합 → query/lint 흐름을 사용자의 문서로 실행합니다. 교육 프로젝트나 두 개의 고정 파일에 종속되지 않습니다. `raw/`에 DOCX·PDF·HWPX 중 하나 또는 여러 형식을 섞어 넣으면 Python이 텍스트를 추출하고, 선택한 LLM CLI가 내용을 연결된 Markdown 위키로 작성합니다. UTF-8 Markdown·TXT도 지원합니다.

## 설치와 실행

Python 3.9 이상과 다섯 CLI 중 **하나**가 필요합니다. 저장소 루트에서:

```console
python3 -m venv 02-llmwiki-general/.venv
```

macOS/Linux에서는 `source 02-llmwiki-general/.venv/bin/activate`, Windows PowerShell에서는 `02-llmwiki-general/.venv/Scripts/Activate.ps1`로 활성화한 다음 실행합니다.

```console
python -m pip install -r 02-llmwiki-general/requirements.txt
python 02-llmwiki-general/build_wiki.py
```

실행 전에 `02-llmwiki-general/raw/`에 자신의 문서를 넣으세요. 하위 디렉터리도 재귀적으로 읽고 확장자의 대소문자를 구분하지 않습니다. 숨김 파일·숨김 디렉터리는 무시합니다. 심볼릭 링크와 지원하지 않는 파일은 명시적으로 거절합니다. `.hwp`는 한글에서 `.hwpx`로 저장해야 합니다.

터미널에서 도구를 선택하거나 다음 중 하나를 사용합니다. 비대화형 환경에서는 `--agent`가 필수입니다.

```console
python 02-llmwiki-general/build_wiki.py --agent agy
python 02-llmwiki-general/build_wiki.py --agent codex
python 02-llmwiki-general/build_wiki.py --agent claude
python 02-llmwiki-general/build_wiki.py --agent cursor
python 02-llmwiki-general/build_wiki.py --agent copilot
```

| 선택 | 실행 파일과 호출 옵션 |
| --- | --- |
| agy | `agy --mode accept-edits -p PROMPT` |
| codex | `codex exec --sandbox workspace-write PROMPT` |
| claude | `claude --permission-mode acceptEdits -p PROMPT` |
| cursor | `cursor-agent --force -p PROMPT` |
| copilot | `copilot --allow-tool=read --allow-tool=write --assisted-approval -p PROMPT` |

Windows에서는 PATH의 `copilot.exe`를 직접 호출합니다. npm의 `copilot.cmd` 래퍼는 여러 줄 `-p` 프롬프트를 유실할 수 있으므로 사용하지 않습니다. `copilot.exe`가 없으면 Windows용 네이티브 Copilot CLI를 설치하고 PATH에 추가하세요.

설치·로그인 안내는 [basic의 CLI 표](../01-llmwiki-basic/README.md#python-스크립트로-실행)를 참고하세요. 모델·계정·인증은 각 CLI의 기존 설정을 사용합니다. 버전에 따른 옵션 변경은 해당 CLI의 `--help`에서 확인하세요. Cursor의 `--force`와 Copilot 자동 승인 옵션의 범위도 basic 안내를 참고하세요. 원본 보존 규약은 모든 CLI에 동일한 OS 수준 접근 격리를 제공하는 기능이 아닙니다.

스크립트는 어느 위치에서 호출해도 자신의 폴더를 기준으로 raw를 찾고, **`02-llmwiki-general/`을 CLI cwd로 사용**합니다. basic의 저장소 루트 cwd와 다릅니다. 다른 디렉터리에서는 스크립트의 절대 경로를 지정하세요.

## 단계별 사용

| `--step` | 수행 내용 |
| --- | --- |
| `extract` | Python으로 모든 문서를 추출. CLI·로그인·agent 선택 불필요 |
| `ingest` | 모든 문서 추출 후 신규·변경·요약 누락 문서마다 CLI를 한 번씩 호출 |
| `query` | 기존 위키에서 `--question`에 답하고 log에 기록. raw 재추출 안 함 |
| `lint` | 기존 위키의 구조·근거·충돌을 검사하고 log에 기록. raw 재추출 안 함 |
| `all` (기본) | ingest → 질문이 있으면 query → lint. 질문 없으면 query 생략 |

```console
python 02-llmwiki-general/build_wiki.py --step extract
python 02-llmwiki-general/build_wiki.py --agent codex --step ingest
python 02-llmwiki-general/build_wiki.py --agent codex --step query --question "자료에서 확정된 결정과 미확정 사항은?"
python 02-llmwiki-general/build_wiki.py --agent claude --step lint
python 02-llmwiki-general/build_wiki.py --agent cursor --question "각 문서가 서로 다르게 설명하는 부분은?"
python 02-llmwiki-general/build_wiki.py --agent codex --step ingest --force
python 02-llmwiki-general/build_wiki.py --agent codex --dry-run
```

`--force`는 변경 없는 문서도 다시 ingest합니다. 추출만으로 위키가 생기지는 않습니다. query/lint는 비어 있지 않은 원본 요약·주제·index·log가 있어야 실행합니다. 질문은 query/all에서만 지정하며, 기본 query는 답변 파일을 저장하지 않습니다.

`--dry-run`은 입력 목록, 예정 산출물 경로, cwd와 프롬프트를 포함한 argv(JSON)를 출력합니다. 의존성 import·실제 추출·디렉터리 생성·CLI 설치 검사·상태 갱신을 하지 않습니다. 손상된 문서의 추출 성공을 검증하는 기능은 아닙니다. 입력 목록과 프롬프트는 점검하므로 raw가 비어 있거나 지원하지 않는 파일이 있으면 실패합니다.

## 입력과 산출물 구분

```text
02-llmwiki-general/
├── build_wiki.py / requirements.txt / AGENTS.md / README.md
├── prompts/                     # ingest, query, lint 공통 지침
├── raw/                         # 사용자가 넣는 원본 (읽기 전용)
│   ├── 회의록.docx
│   ├── 규정.pdf
│   └── 부서/운영안.hwpx
├── .prepared/                   # Python이 생성, 에이전트는 읽기만
│   ├── manifest.json            # 이번 추출 문서 목록·해시·방법·경로
│   ├── text/<id>.md             # 원본별 추출 텍스트와 위치 표식
│   ├── missing-notified.json     # 문서별로 위키에 반영 완료한 원본 부재 목록
│   └── ingested.json            # 검증 완료한 원본 해시 + 추출 정책 버전
└── wiki/                        # LLM이 작성·갱신
    ├── sources/<id>.md          # 원본 하나의 의미 요약
    ├── topics/<slug>.md         # 여러 원본에서 찾은 실제 주제의 종합
    ├── answers/                # 기본 query에서는 생성하지 않음
    ├── index.md                # 제공된 시작 파일 → 지식 페이지 목록 갱신
    └── log.md                  # 제공된 시작 파일 → 실제 수행 기록만 추가
```

위 raw 파일명은 배치 예시이며 저장소에 제공되는 문서가 아닙니다. `raw/.gitkeep`만 제공합니다. `.prepared/`, sources/topics/answers는 실행 후 생성됩니다. source ID는 `raw/` 상대 POSIX 경로의 SHA-256 앞 16자리와 짧은 파일명으로 구성합니다. 같은 이름을 다른 하위 폴더에 넣어도 구별되며, **내용만 변경하면 같은 ID**를 유지합니다. 파일을 옮기거나 이름을 바꾸면 새 문서로 인식합니다. 대소문자와 Unicode 표기가 다른 경로도 구분합니다.

manifest에는 `id`, `original`, `format`, `sha256`, `policy`, `method`, `extracted`, `source`가 들어갑니다. `.prepared/text`는 검색용 변환 텍스트이고 `wiki/sources`는 LLM이 작성하는 요약입니다. 주제 파일은 `training-project.md`로 고정하지 않고 자료에 따라 정합니다.

## 추출 범위와 제한

| 형식 | 추출 | 위치 표식·한계 |
| --- | --- | --- |
| DOCX | 본문 문단과 표, 중첩 표의 셀을 문서 순서로 추출 | `Block N`; 원본 쪽 번호는 아님. 머리말·꼬리말·텍스트 상자·주석·변경 추적·그림·수식·임베디드 파일은 완전 추출하지 않음 |
| PDF | 페이지별 텍스트 레이어 | `Page N`; 다단·표의 읽기 순서와 글자 인코딩은 원본에 따라 달라짐 |
| HWPX | content.hpf의 spine 순서로 section XML 텍스트, 표 셀의 본문 포함 | `Section N (Contents/sectionN.xml)`; 쪽 번호가 아니며 그림·서식·복잡한 객체는 재현하지 않음 |
| MD/TXT | UTF-8 또는 UTF-8 BOM 텍스트 | 원문 제목·절을 근거로 사용 |

스캔 PDF·이미지 속 글자에 대한 **자동 OCR은 포함하지 않습니다**. PDF의 어느 한 페이지라도 텍스트가 비어 있으면 전체 문서 추출을 실패시킵니다. 실제 빈 페이지도 포함되므로 확인 후 제거하거나 OCR 도구로 텍스트 레이어를 만든 사본을 넣으세요. 암호 PDF는 해제한 사본이 필요합니다. 텍스트가 일부 추출된다고 모든 내용이 인식됐다는 뜻은 아니므로 추출본을 원본과 대조하세요. HWPX spine/참조 파일이 없거나 잘못되면 임의로 정렬해 처리하지 않습니다.

파일당 64 MiB, DOCX/HWPX ZIP 내부 최대 2,000항목·전체 128 MiB·항목당 32 MiB를 허용합니다. ZIP을 디스크에 풀지 않으며 HWPX XML의 DTD/외부 엔티티는 거절합니다. 이는 손상된 입력을 일부 방어하는 제한이며 모든 비정상 문서의 처리 시간·메모리를 보장하지는 않습니다.

구현 근거: [python-docx 문단·표 순회](https://python-docx.readthedocs.io/en/latest/api/document.html), [pypdf 텍스트 추출과 OCR 한계](https://pypdf.readthedocs.io/en/latest/user/extract-text.html), [한컴 HWPX 패키지·spine·텍스트 구조](https://tech.hancom.com/hwpxformat/).

## 증분 처리와 실패 복구

원본 바이트 해시와 추출 정책 버전이 이전 ingest 성공 상태와 같고 요약 파일도 있으면 CLI ingest를 생략합니다. 추가·변경·빈 요약/누락 요약은 다시 처리합니다. 새 문서를 처리할 때 기존 주제를 읽어 같은 주제에 통합하고, 명시적 승인 없이 상반된 주장을 덮어쓰지 않도록 규약으로 지시합니다. 삭제된 원본의 성공 이력과 지식은 자동 삭제하지 않으며 경고합니다. 원본 부재 목록이 달라지면 남은 문서를 다시 처리해 부재를 표시하도록 전달하고, 문서별 반영 완료 목록을 저장합니다. 이후 부재 목록과 원본이 같으면 다시 ingest하지 않습니다. query/lint에도 현재 부재 목록을 전달합니다. raw가 전부 비었다면 ingest는 실패하고 기존 위키에 대한 query/lint는 가능합니다.

추출은 전체 입력의 파싱이 끝난 뒤 파일과 manifest를 발행합니다. 각 파일은 임시 파일 후 원자적으로 교체하지만 디렉터리 전체 트랜잭션은 아닙니다. I/O 실패 시 부분 추출 파일이 남을 수 있으므로 extract/ingest를 다시 실행하세요. 추출만 재실행하면 기존 위키가 새 내용으로 갱신되는 것은 아닙니다. 변경 문서를 ingest하기 전에는 요약·주제와 최신 추출본 사이에 차이가 있을 수 있습니다.

CLI는 문서별로 순서대로 호출합니다. 완료 후 필요한 요약·주제·index·오늘의 log 추가 및 과거 log 보존을 확인한 문서만 성공 해시를 원자적으로 저장합니다. 이후 문서나 lint가 실패해도 앞서 완료한 문서의 상태는 남습니다. **이미 생성된 위키를 자동 되돌리거나 삭제하지 않습니다.** 실패를 고친 뒤 같은 명령을 재실행하면 미완료 문서부터 다시 처리합니다. 의미적 재검토나 규약 변경 후 전체 재처리가 필요하면 `--force`를 사용하세요.

실행 중 `.llmwiki.lock`으로 중복 실행을 막습니다. 강제 종료 후 잠금이 남으면 다른 프로세스가 실행 중이지 않은지 확인한 뒤 해당 잠금 파일만 삭제하세요. CLI 호출 전후 raw 파일 목록과 바이트 해시를 비교해 변경을 검출하지만 자동 복구하지 않으므로 원본 백업을 유지하세요.

종료 코드는 인자 오류 2, 추출/구조 검증 오류 1, 실행 파일 없음 127, 실행 실패 126, 중단 130이며 CLI의 비정상 종료 코드도 전파합니다. 실패하면 이후 단계는 실행하지 않습니다. CLI의 성공 코드만으로 사실의 정확성·근거·index 링크·충돌 해결이 검증된 것은 아닙니다. 내용을 직접 검토하세요.

원본과 생성 지식의 내용은 선택한 CLI의 모델 제공자에게 전달될 수 있습니다. 공개 가능한 문서로 시작하고 조직의 사용 정책에 맞는 도구를 선택하세요. `.gitignore`는 원본, 추출·성공 상태, 생성 지식 디렉터리를 기본 제외합니다. 제공된 index/log는 추적되는 시작 파일이므로 실행 후 민감한 링크·내용을 커밋하지 않도록 diff를 확인하세요.

## 개발 검증

```console
python -m unittest discover -s 02-llmwiki-general/tests -v
python -m unittest discover -s 01-llmwiki-basic/tests -v
```

테스트는 임시 디렉터리에서 실제 합성 DOCX/PDF/HWPX를 만들고, 모의 CLI로 다섯 도구의 인자·cwd·순서·실패 전파·증분 상태·원본 보존을 검증합니다. 사용자 문서·실제 계정·유료 모델은 호출하지 않습니다. 따라서 실제 서비스의 로그인 성공이나 모델의 의미적 위키 품질을 보증하지 않습니다.
