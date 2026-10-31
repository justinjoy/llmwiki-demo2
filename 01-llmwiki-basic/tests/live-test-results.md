# 실제 CLI 검증 기록

검증일: **2026-10-31**. macOS에서 설치된 실제 CLI와 로그인된 계정으로 모델을 호출했다. 모의 테스트나 dry-run만의 결과가 아니다. 기준 커밋 `de64c51`에서 아래 결함을 수정한 버전을 검증했다.

## 최종 결과

| CLI 선택 | 확인한 CLI 버전 | ingest-01 | ingest-02 | query | lint | 최종 위키 상대 링크·앵커 |
| --- | --- | --- | --- | --- | --- | --- |
| agy | 버전 문자열 미확인, 로컬 Antigravity CLI | PASS | PASS | PASS | PASS | 93개 PASS |
| codex | 0.166.0 | PASS | PASS | PASS | PASS | 44개 PASS |
| claude | 2.1.311 | PASS | PASS | PASS | PASS | 74개 PASS |
| cursor | 2026.10.14-0f9edde (`cursor-agent`) | PASS | PASS | PASS | PASS | 45개 PASS |
| copilot | 1.0.104 | PASS | PASS | PASS | PASS | 49개 PASS |

Codex의 실제 출력에서 모델 `gpt-6.1-sol`을 확인했다. 나머지 도구의 실제 모델 식별자는 출력에서 확인하지 못했으며 추정하지 않는다. 실행에는 각 CLI의 기존 계정·모델 설정을 사용했다.

## 재현 방식과 검증 범위

CLI별 독립 임시 Git clone을 사용했다. 원래 저장소의 raw와 시작용 wiki는 수정하지 않았다. 실행 명령은 다음 형태다.

```console
python3 01-llmwiki-basic/build_wiki.py --agent <선택값> --step ingest-01
python3 01-llmwiki-basic/build_wiki.py --agent <선택값> --step ingest-02
python3 01-llmwiki-basic/build_wiki.py --agent <선택값> --step query
python3 01-llmwiki-basic/build_wiki.py --agent <선택값> --step lint
```

첫 실행에서 발견한 결함을 수정한 후 다섯 도구로 첫 ingest를 실제 수행했다. 추가 입력·질의 프롬프트 보완 후에는 agy/codex/claude/cursor의 **검증된 첫 ingest snapshot을 새 clone에 복사**하여 변경된 ingest-02 → query → lint를 다시 실행했다. 네 도구를 수정 후 단일 `all` 호출로 처음부터 다시 실행했다고 주장하지 않는다. 이후 Copilot 명령에만 `--assisted-approval`을 추가했으며 나머지 네 도구의 명령·공통 검사 코드는 변경하지 않았다.

Copilot 최종 재검증은 초기 위키의 새 clone에서 `--agent copilot --step all`로 네 단계를 연속 실행했다(약 142초). 단계 전환 시 snapshot을 보존했으며, 개별 단계의 정확한 경계 검사는 앞선 단계별 실행 기록과 함께 대조했다. 초기 결함 재현용·중간 실행은 수정본으로 대체할 때 해당 테스트 process group만 종료했다. 최종 표는 종료된 중간 실행을 성공으로 집계한 것이 아니다.

각 단계의 산출물과 로그를 대조하여 다음을 확인했다.

- 첫 ingest에는 30명·11월 20일·대면 4시간이 반영되고 60명·11월 27일·온라인 2시간은 섞이지 않았다.
- 추가 ingest 후 승인된 11월 27일 일정과 이전 값·변경 근거가 보존됐다. 인원 30/60명과 대면/온라인 방식은 초기 승인안·미승인 제안·확인 질문으로 구분됐다.
- 지식 페이지 3개가 index에 등록되고 페이지 간 참조가 있었다. 최종 Markdown 5개(index/log 포함)의 상대 링크·앵커 총 305개가 유효했다.
- 단계별 log가 이전 내용을 보존하며 추가됐다. query는 답변 파일을 만들지 않고 지식 Markdown 중 log만 변경했으며, 답변에서 위키와 원본 파일 근거를 제공했다.
- raw의 파일 목록·내용 바이트가 원본과 같았다. 최종 Copilot 위키에는 문제를 재현했던 `.new`·`.tmp_unused` 파일이 없었다.

주요 사실과 충돌 처리는 원문과 수동 대조했다. 링크가 열리고 구조 검사를 통과한다고 자유 형식 답변의 모든 문장·인용 범위가 자동으로 정확해지는 것은 아니다. 다른 모델·계정·CLI 버전에서도 같은 결과를 보장하지 않는다.

## 발견한 문제와 수정

1. **Copilot의 부모 폴더 생성 실패:** 파일 생성 도구가 없는 부모 폴더를 만들지 못하고 셸 `mkdir`은 거부됐다. 실행기가 ingest 전에 `wiki/sources/`, `wiki/topics/`를 Python으로 준비하도록 수정했다.
2. **종료 코드 0의 거짓 성공:** 페이지를 만들지 못해도 다음 단계로 넘어갔다. 선행 페이지 검사와 단계별 필수 페이지·새 작업 기록·기존 log 보존 검사를 추가했다. 검사 실패는 코드 1로 중단한다.
3. **터미널 답변의 잘못된 상대 경로:** 위키 내부의 `../../raw/...`를 답변에 복사했다. query 프롬프트와 수동 안내에 저장소 루트 기준 `01-llmwiki-basic/...` 링크를 명시했다.
4. **Copilot의 임시 파일 잔존:** 직접 편집하도록 프롬프트를 보완했지만 임시 파일 생성·정리 권한 문제를 다시 관측했다. 읽기·쓰기 허용에 공식 `--assisted-approval`을 추가하여 추가 작업을 심사하도록 했다. 최종 전체 실행에서 임시 파일 없이 완료됐다. 일부 셸 로그 추가 요청은 심사에서 거절됐지만 편집 도구로 완료했으며, 이를 모든 셸 요청이 허용된 것으로 해석하지 않는다.

이 환경의 Claude Code는 설치된 OMC 플러그인 관련 `.omc` 메타데이터를 생성했다(위키 안의 상태 JSON 포함). 이를 지식 페이지와 구분해 별도 메타데이터로 기록했으며, 전역 플러그인·인증·권한 설정을 수정하거나 해당 상태를 임의로 지우지 않았다. 모든 CLI에 동일한 파일 접근 격리를 보장하는 실행기는 아니다.

## 자동 회귀 검사

```console
python3 -m unittest discover -s 01-llmwiki-basic/tests -v
```

**16개 PASS.** 부모 폴더 준비, 산출물 없는 exit 0의 중단, 선행 페이지 누락, 새 log 기록과 과거 log 보존을 포함한다. 추가로 컴파일, 다섯 dry-run, 문서 링크, 원래 raw/wiki/AGENTS/requirements 보존, `git diff --check`를 확인했다. Python 외부 패키지는 추가하지 않았다.

최종 실행기와 네 프롬프트의 경로·내용 결합 SHA-256: `d29d5618a489baa00d943860530494895aad32ce9c61005c456431f7751855d9`.
