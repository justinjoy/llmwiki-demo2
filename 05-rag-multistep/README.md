# 05 · 다단계 RAG와 절차의 구조

웹에서 같은 질문을 **검색한 조각만 제공한 RAG**와 **같은 조각에 정적 절차 카드를 추가한 RAG**로 비교합니다. 별도 버튼으로 실제 PyreWire 엔진을 실행해 선행 관계와 단계별 입출력을 확인합니다.

## 실행

Python 3.11 이상과 해당 플랫폼의 PyreWire wheel이 필요합니다. 이 저장소에서는 macOS arm64 / Python 3.11 / PyreWire 1.1.3로 검증했습니다.

```bash
python3.11 -m venv 05-rag-multistep/.venv
05-rag-multistep/.venv/bin/python -m pip install -r 05-rag-multistep/requirements.txt
05-rag-multistep/.venv/bin/python 05-rag-multistep/server.py
```

브라우저에서 <http://localhost:8005/05-rag-multistep/>를 엽니다. Windows에서는 `.venv/Scripts/python.exe`를 사용합니다. 포트 충돌 시 `--port 8006`을 지정합니다. 서버는 `127.0.0.1`에만 바인딩됩니다. 정적 파일 서버만으로는 CLI와 추론을 실행할 수 없습니다.

CLI 다섯 가지 중 설치·로그인한 것을 화면에서 선택합니다. `claude`, `cursor-agent`, `copilot`, `agy`, `codex` 실행 파일을 PATH에서 찾습니다. API 키를 웹에 입력하지 않고 각 CLI의 기존 인증을 사용하며, 구독·사용량 정책은 해당 도구를 따릅니다. 실행 파일 발견은 인증 성공을 뜻하지 않습니다.

```bash
05-rag-multistep/.venv/bin/python 05-rag-multistep/server.py --agent codex --timeout 180
# 기본 agent에만 특정 모델 적용 (나머지는 해당 CLI 기본 모델)
05-rag-multistep/.venv/bin/python 05-rag-multistep/server.py --agent claude --model sonnet
```

모델을 생략하면 각 CLI 기본 설정을 사용합니다. 응답에서 실제 모델 정보가 제공되면 실행 JSON에 함께 보존합니다. CLI 별 읽기 전용 모드·도구 제한은 적용하지만 사용자 설정/MCP를 모두 동일하게 격리하는 실험은 아닙니다. 화면에 선택한 CLI의 격리 범위를 표시합니다. 임시 작업 디렉토리에서 매번 새 호출을 만들며, 결과를 예시 답변으로 대체하지 않습니다.

PyreWire가 다른 Python에 설치되어 있다면 서버 시작 시 `--logic-python /절대경로/python`을 지정할 수 있습니다. HTTP 요청으로 실행 파일·논리 프로그램·문서 경로를 지정할 수 없습니다. PyreWire가 없으면 RAG는 사용할 수 있고 온톨로지 관계 추론 버튼에 설치 오류를 표시합니다. CLI가 없어도 온톨로지 관계 추론은 실행할 수 있습니다. 실제 추론은 별도 프로세스에서 수행하며, 실패·시간 초과 시 Python 대체 추론으로 성공을 가장하지 않습니다.

## 화면에서 확인할 내용

1. Top K를 1~6에서 선택합니다. 문자 bigram 코사인 검색이며 TF-IDF나 외부 벡터 DB가 아닙니다. 선택한 조각과 전체 검색 순위를 펼쳐 볼 수 있습니다.
2. 답변 비교는 같은 CLI·모델·질문·검색 결과로 두 번 독립 호출합니다. B에는 사람이 작성한 `PROCEDURE_CARD`만 추가합니다. 질문 자체에 네 단계 이름이 포함되어 있어 단계 이름을 언급하는 것만으로 검색 성공을 입증할 수 없습니다.
3. **결과물 키워드 언급 수**는 `claude 명령`, `운영 규칙`, `facts 파일`, `검증 로그`가 포함되었는지만 셉니다. 백틱과 일반 공백을 제거한 부분 문자열 검사이며, 부정 문장도 포함될 수 있습니다. 순서·의존·근거·정확도를 평가하지 않습니다. 특정 2/4·4/4 결과를 보장하지 않습니다.
4. Top K=6이면 모든 조각을 제공하지만, 조각에는 전체 선행 관계가 명시되어 있지 않습니다. 절차 카드는 추가 근거이므로 두 조건의 정보량도 다릅니다. 이 예제로 모든 일반 RAG의 실패를 주장하지 않습니다.
5. 온톨로지 관계 추론 버튼은 입력 `dep` 3개, `produces` 4개와 Datalog 규칙을 엔진에 넣습니다. 실제 결과는 `before` 6쌍, `input_of` 3개, 4단계 순서입니다. 입력 facts의 진위는 사람이 확인해야 합니다. 이 예제의 유일한 4단계 chain을 검증하며, 임의 DAG를 지원하지 않습니다.
6. Wirelog 결과는 RAG 프롬프트에 자동 주입되지 않습니다. 정적 절차 카드 비교와 규칙 기반 추론을 분리해 관찰하는 데모입니다.

## 저장·취소·재접속

한 번에 하나의 작업만 실행하며 실행 중 선택 메뉴를 잠급니다. 취소하면 현재 CLI/추론 프로세스를 종료합니다. 성공·실패·취소 결과는 `runs/<실행 ID>/result.json`에 저장하고 Git에서 제외합니다. 실제 프롬프트, 선택한 문서, 답변, CLI 메타데이터, 소요 시간, 키워드 검사 또는 추론 결과를 포함합니다. 두 번째 호출이 실패해도 첫 번째 답변을 보존합니다.

새로고침하면 현재 서버 메모리에 있는 각 실험의 최근 결과를 복원합니다. 서버 재시작 후 과거 파일을 자동 복원하지 않습니다. 웹 JSON 링크는 현재 서버가 보유한 실행만 제공합니다. 외부 사이트 요청을 막는 Host/Origin/실행 토큰 검사와 정적 파일 허용 목록을 사용합니다.

## 기존 터미널 실행

```bash
05-rag-multistep/.venv/bin/python 05-rag-multistep/multistep_rag.py --mode both --agent codex --top-k 2
05-rag-multistep/.venv/bin/python 05-rag-multistep/multistep_rag.py --dry-run --top-k 6
05-rag-multistep/.venv/bin/python 05-rag-multistep/wirelog_reasoning.py
```

## 검증

```bash
05-rag-multistep/.venv/bin/python -m unittest discover -s 05-rag-multistep/tests -v
node --test 05-rag-multistep/tests/ui.test.cjs
```

Python 테스트는 CLI 프로토콜·오류·취소의 실행 파일 대역과 실제 PyreWire 추론을 포함합니다. 웹 E2E 검증과 실제 모델 호출 결과는 작업 보고서에서 따로 구분합니다. 서버/프론트엔드는 Python 표준 라이브러리와 기본 브라우저 API만 사용합니다.

## 온톨로지 관계 추론 시각화

이 영역은 단계·결과물·선행 조건을 연결한 관계 지도를 보여 줍니다. 입력 사실(선행 조건 3개, 결과물 4개), 연결 규칙 3개, 실제 실행 결과를 순서대로 읽을 수 있습니다. 실행 전에는 입력 미리보기만 표시하며 결과를 미리 만들어 표시하지 않습니다.

실행 후에는 네 단계의 받는 것·만드는 것과, 실제 엔진이 반환한 순서 관계 6개·다음 단계 입력 관계 3개를 표시합니다. 관계 버튼을 클릭하거나 키보드로 선택하면 사용한 사실과 규칙을 강조하고 도출 근거를 설명합니다. 직접 순서와 여러 조건을 연결한 간접 순서를 구분합니다.

근거 설명은 해당 실행에 저장된 사실과 실제 반환된 관계를 대조해 만든 화면 설명이며 엔진 내부 추적 로그가 아닙니다. 설명을 연결할 수 없으면 근거를 만들어내지 않습니다. 원본 facts·규칙·추론 결과는 개발자용 상세와 실행 JSON에서 확인할 수 있습니다.

추론 실행 옆의 **초기화** 버튼은 표시 중인 관계·근거 강조·JSON 링크와 서버의 최근 추론 표시를 지웁니다. 새로고침해도 다시 나타나지 않습니다. 입력 사실·규칙, RAG 비교 결과, 저장된 실행 JSON은 유지합니다. 작업 실행 중에는 초기화가 잠기며, 완료 또는 취소 후 사용할 수 있습니다.
