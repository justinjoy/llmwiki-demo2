# RAG Amnesia Lab — 선택한 CLI로 실행하는 메모리 비교

## 1. 준비

Python 3.10 이상과 다음 CLI 중 하나를 설치하고 먼저 로그인합니다.
서버용 Python 패키지는 추가 설치하지 않습니다. 선택한 서비스의 실제 모델
사용량이 발생하며, 계정의 권한·한도·모델 설정을 따릅니다.

| 선택값 | 실행 파일 | 설치·인증 참고 |
| --- | --- | --- |
| `claude` | `claude` | [공식 문서](https://code.claude.com/docs/en/cli-reference) |
| `cursor` | `cursor-agent` | [공식 문서](https://cursor.com/docs/cli/overview) |
| `copilot` | `copilot` | [공식 문서](https://docs.github.com/en/copilot/how-tos/copilot-cli) |
| `agy` | `agy` | [공식 문서](https://antigravity.google/docs/cli/headless/) |
| `codex` | `codex` | [공식 문서](https://developers.openai.com/codex/cli/reference/) |

Windows의 Copilot은 copilot.exe를 PATH에 등록해야 합니다. CMD 래퍼 대신
네이티브 실행 파일을 사용합니다. 나머지 도구도 네이티브 설치를 권장합니다.
실행 파일 발견은 로그인·모델 접근 성공을 보장하지 않습니다.

## 2. 웹 실행

저장소 루트에서:

```bash
python3 04-rag-amnesia/server.py --port 8003
```

브라우저:

<http://localhost:8003/02-rag-amnesia/>

현재 HTTP 경로는 폴더명 04와 달리 /02-rag-amnesia/입니다.
정적 http.server나 파일 직접 열기로는 실제 CLI를 실행할 수 없습니다.
서버는 127.0.0.1에만 바인딩되며 외부 공개 호스팅용이 아닙니다.

화면 위쪽 '실행할 CLI' 메뉴에서 도구를 선택한 뒤 실행 버튼을 누릅니다.
설치되지 않은 도구는 '(미설치)'로 표시하며 선택·실행할 수 없습니다.
설치 후 새로고침하면 다시 탐지합니다. 로그인 실패는 실제 실행 오류로 표시합니다.
실행 중에는 CLI와 Top K 선택을 잠급니다. 도구나 Top K를 바꾸면 화면의 이전
비교 결과를 초기화하며, 새 조건을 보려면 실행 버튼을 다시 눌러야 합니다.
새로고침은 같은 서버의 마지막 실행과 당시 CLI·Top K를 복원하며 추가 호출하지 않습니다.

처음 선택할 CLI와 그 CLI의 모델을 지정할 수도 있습니다.

```bash
python3 04-rag-amnesia/server.py --port 8003 --agent codex
python3 04-rag-amnesia/server.py --port 8003 --agent cursor --model auto
python3 04-rag-amnesia/server.py --port 8003 --agent claude --model sonnet
```

--backend는 --agent의 별칭입니다. --model은 --agent로 지정한 기본 CLI에만
적용합니다. 웹에서 다른 CLI를 선택하면 해당 CLI 자체의 기본 모델을 사용합니다.
Claude만 기존 기본 claude-sonnet-4-6 (ANTHROPIC_MODEL 설정 시 그 값)을 유지합니다.
요청 모델과 CLI가 알려준 실제 모델을 화면에 구분해 표시합니다. 실제 모델 이름을
반환하지 않는 CLI는 임의로 모델 이름을 채우지 않습니다.

각 호출의 기본 제한 시간은 180초이며 --timeout 300처럼 변경할 수 있습니다.
Ctrl+C로 서버를 종료합니다. 실행 취소는 진행 중인 CLI 프로세스를 종료하고,
이미 완료된 응답과 저장 파일은 보존합니다. 서버 재시작은 웹 실행 목록을 초기화하지만
memory/의 과거 실행 파일을 삭제하지 않습니다.

## 3. 한 실행의 네 호출

선택한 CLI와 요청 모델은 실행 시작 시 고정합니다. 네 호출 모두 같은 선택을 사용합니다.

1. 일반 RAG 1턴: 어제 일기 검색 → 기준 정리 답변
2. 메모리 RAG 1턴: 같은 문맥 → 별도로 생성한 실제 응답을 criteria.md에 저장
3. 일반 RAG 2턴: 오늘 일기 검색 → 이전 답변을 전달하지 않고 평가
4. 메모리 RAG 2턴: 오늘 일기 + 저장 파일을 디스크에서 다시 읽어 추가 → 평가

각 호출은 새 프로세스이며 resume/continue를 사용하지 않습니다. 임시 작업 폴더에서
실행하고, Python이 검색한 내용과 공통 지침을 명시적으로 전달합니다. system 인자를
지원하지 않는 도구에는 같은 지침을 요청 본문 앞에 붙입니다. 메모리 파일을 읽는
주체는 Python이며 모델 도구에 저장 경로를 읽도록 맡기지 않습니다.

두 모드의 1턴 응답은 독립 생성이므로 내용이 서로 다를 수 있습니다. 메모리 유무만
엄밀하게 통제한 인과 실험으로 해석하지 마세요. CLI나 모델까지 바꾼 결과를 비교할
때는 해당 조건도 기록하세요.

## 4. CLI별 실행 제한과 응답 형식

```text
Claude: --tools "", --safe-mode, 빈 MCP 설정, --no-session-persistence.
        JSON의 최종 result를 사용합니다.
Cursor: --print --mode ask --trust --output-format json.
        비어 있는 임시 폴더만 신뢰하며 --force를 사용하지 않습니다.
        JSON의 최종 result를 사용합니다.
Copilot: 표준입력 prompt mode, --available-tools=, read/write/shell/url/memory 거부,
         --disable-builtin-mcps, --no-ask-user. JSONL 완료 기록과 assistant.message 사용.
agy: --mode plan --disable-slash-commands --output-format json --print=본문.
     성공 JSON의 response를 사용합니다.
Codex: exec --sandbox read-only --ephemeral --skip-git-repo-check --json.
       JSONL의 최종 agent_message와 turn.completed를 사용합니다.
```

위 옵션은 설치된 CLI의 --help 및 공식 문서에 맞췄습니다. CLI 버전이 오래됐거나
관리 정책이 옵션을 거절하면 오류를 그대로 표시하며 다른 CLI나 예문으로 대체하지 않습니다.
Claude 외 도구는 사용자 설정·MCP·읽기 도구·CLI 자체 기록까지 동일하게 차단한다고
보장하지 않습니다. 새 프로세스·임시 cwd도 모든 사용자 설정을 제거하는 sandbox는
아닙니다. 정책에 따른 외부 도구·자동 지침 차이가 실험에 영향을 줄 수 있습니다.

## 5. 화면과 파일에서 확인할 것

- 실제 호출 상태와 소요 시간, 실행에 고정된 CLI와 요청/응답 모델
- 각 턴에서 검색한 문서와 0~1 코사인 점수
- 메모리 모드 1턴의 실제 응답과 2턴에 실제로 주입한 파일 내용
- 실제 두 번째 답변과 기준 키워드 언급 수
- 전송한 프롬프트, criteria.md 다운로드

검색 문서 수 Top K는 1 또는 2입니다. 2로 바꾸면 일반 모드도 어제 일기를
읽을 수 있으므로 검색 범위 확대와 별도 메모리의 효과를 구분해서 보세요.
'다음 단계'는 화면 보기만 바꾸고 추가 모델 호출을 하지 않습니다.

이 폴더 기준 생성 파일:

```text
memory/runs/<실행 ID>/criteria.md
memory/runs/<실행 ID>/result.json
```

result.json에는 backend, 요청 모델, 검색 점수, 전송 문맥, 실제 답변, 주입한 메모리,
기준 검사, 호출 시간과 CLI가 제공한 사용량 정보가 들어갑니다. 새 실행은 새 폴더를
사용합니다. 일반 모드 응답도 실행 기록에 남지만 다음 요청에는 전달하지 않습니다.
메모리와 결과는 .gitignore로 제외합니다. 조직 자료로 바꿀 때는 선택한 모델 제공자에
내용이 전달된다는 점을 고려하세요.

## 6. 터미널 실행

같은 실행 어댑터를 사용하는 standalone 예제입니다.

```bash
python3 04-rag-amnesia/rag_amnesia.py --agent claude
python3 04-rag-amnesia/rag_amnesia.py --agent cursor
python3 04-rag-amnesia/rag_amnesia.py --agent copilot
python3 04-rag-amnesia/rag_amnesia.py --agent agy
python3 04-rag-amnesia/rag_amnesia.py --agent codex
python3 04-rag-amnesia/rag_amnesia.py --agent codex --dry-run
```

--mode naive/fixed/both를 선택할 수 있으며 기본 both입니다. --model은 선택한 CLI의
모델 이름을 지정합니다. dry-run은 CLI 설치 검사·호출·메모리 쓰기 없이 검색만 봅니다.
standalone의 기준 파일은 memory/criteria.md이며 웹의 실행별 폴더와 다릅니다.
fixed는 이번 1턴 응답을 저장한 후 읽으며, 1턴 실패 시 과거 파일을 대신 쓰지 않습니다.

## 7. 계산과 평가의 범위

검색과 코퍼스·질문은 rag_amnesia.py의 기존 TF-IDF 구현을 공유합니다.
브라우저 검색 미리보기는 같은 계산을 JavaScript로 구현합니다.
기준 언급 수는 부분 문자열 검사입니다. 키워드 중 하나만 포함해도 해당 기준을
언급한 횟수에 추가하며, 부정문·확인 질문도 포함될 수 있습니다. 생활 기준의
달성률이나 답변 정확도는 아닙니다. 오늘 일기에는 걷기 시간과 커피 지출액이 없어
해당 기준 준수 여부를 단정할 수 없습니다. 모든 RAG가 대화 이력을 잊는다는
뜻이 아니라, 이 실험의 일반 모드가 이전 답변을 전달하지 않는다는 뜻입니다.

## 8. 개발 검증

저장소 루트에서:

```bash
python3 -B -m unittest discover -s 04-rag-amnesia/tests -p 'test_*.py' -v
node --test 04-rag-amnesia/tests/*.cjs
```

Python 테스트는 모의 실행 파일로 다섯 어댑터의 argv, 실제 자식 프로세스 경계,
응답 파싱·오류·timeout·취소와 웹/standalone 계약을 검사합니다. Node.js 18 이상
테스트는 검색 수치 일치와 DOM 대역을 사용한 선택·잠금·결과 복원·escaping을 검사합니다.
이 테스트들은 모델 과금이 없으며 실제 서비스 인증을 보증하지 않습니다.
실제 CLI 호출 검증 기록은 tests/live-test-results.md에 별도로 남깁니다.

구현 참고:
<https://cursor.com/docs/cli/reference/output-format>
<https://antigravity.google/docs/cli/headless/>
<https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference>
