#!/usr/bin/env python3
"""두 독립 RAG 요청에 정적 절차 카드가 제공하는 문맥 차이를 비교한다.

검색은 문자 bigram 코사인이다. 키워드 언급 수는 순서나 답변 정확도가 아니다.
절차 카드는 사람이 작성한 추가 자료이며 Wirelog가 만든 결과가 아니다.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter

# --------------------------------------------------------------------------
# 코퍼스: 각 '단계'는 독립 문서로 흩어져 있고, 전체 순서/의존 관계는
#         어느 한 문서에도 들어 있지 않다 (이것이 다단계 질문이 어려운 이유).
# --------------------------------------------------------------------------
DOCS = [
    ("설치", "Claude Code CLI 설치: CLI를 설치하고 로그인한다. "
             "결과물은 사용 가능한 claude 명령이다."),
    ("규칙", "CLAUDE.md 작성: 위키 운영 규칙을 CLAUDE.md에 적는다. "
             "결과물은 에이전트가 따르는 운영 규칙 문서다."),
    ("추출", "facts 추출: 원본 문서에서 사실 후보를 뽑아낸다. "
             "결과물은 출처가 달린 facts 파일이다."),
    ("점검", "Bookkeeping 점검: facts와 페이지의 정합성을 확인한다. "
             "결과물은 검증 로그와 수정 목록이다."),
    ("검색팁", "위키 검색 팁: 제목 검색과 본문 검색을 구분하고 태그로 좁힌다."),
    ("용어집", "용어집: 스페이스는 팀 문서 공간, 템플릿은 반복 양식, 워치는 변경 알림이다."),
]

# fixed 모드가 주입하는 '절차 카드' = 단계 순서와 의존 관계(논리 계층).
PROCEDURE_CARD = (
    "[절차 카드 — 단계 순서와 의존 관계]\n"
    "1) Claude Code CLI 설치  -> 결과물: 사용 가능한 claude 명령   (선행: 없음)\n"
    "2) CLAUDE.md 작성        -> 결과물: 운영 규칙 문서            (선행: 1)\n"
    "3) facts 추출            -> 결과물: 출처가 달린 facts 파일     (선행: 2)\n"
    "4) Bookkeeping 점검      -> 결과물: 검증 로그와 수정 목록      (선행: 3)\n"
    "각 단계는 앞 단계의 결과물을 입력으로 받는다."
)

QUESTION = (
    "Claude Code CLI 설치, CLAUDE.md 작성, facts 추출, Bookkeeping 점검은 "
    "어떤 순서로 진행해야 하며, 각 단계의 결과물은 무엇입니까?"
)

SYSTEM_PROMPT = (
    "너는 사내 위키 어시스턴트다. 반드시 '제공된 컨텍스트'에 명시된 정보만 사용한다. "
    "컨텍스트에 없는 단계의 순서나 결과물은 절대 지어내지 말고 '자료 없음'이라고 표시한다. "
    "답변은 한국어로 한다."
)

# 단계별 '결과물' 핵심 표현 — 답변에 들어있는지로 언급 수만 확인한다.
STEP_DELIVERABLES = {
    "1. CLI 설치": "claude 명령",
    "2. CLAUDE.md": "운영 규칙",
    "3. facts 추출": "facts 파일",
    "4. Bookkeeping": "검증 로그",
}

TOP_K = 2


# --------------------------------------------------------------------------
# 로컬 임베딩 + 검색 (문자 bigram 코사인) — mimic_rag와 동일한 원리
# --------------------------------------------------------------------------
def embed(text: str) -> Counter:
    s = text.replace(" ", "")
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def cosine(a: Counter, b: Counter) -> float:
    na, nb = math.hypot(*a.values()), math.hypot(*b.values())
    return sum(a[t] * b[t] for t in a) / (na * nb) if na and nb else 0.0


INDEX = [(name, text, embed(text)) for name, text in DOCS]


def retrieve(query: str, top_k: int):
    q = embed(query)
    ranked = sorted(
        ((cosine(q, vec), name, text) for name, text, vec in INDEX),
        key=lambda x: x[0],
        reverse=True,
    )
    return ranked[:top_k]


# --------------------------------------------------------------------------
# 생성 (claude CLI = 구독 인증, 키 불필요)
# --------------------------------------------------------------------------
def llm(prompt: str, backend="claude", model=None) -> str:
    import threading
    from cli_backends import generate, GenerationError
    try:
        return generate(prompt, model, threading.Event(), backend=backend,
                        system_prompt=SYSTEM_PROMPT)["answer"]
    except GenerationError as error:
        sys.exit(str(error))


def build_prompt(retrieved, procedure_card: str | None) -> str:
    parts = ["[제공된 컨텍스트]"]
    if procedure_card:
        # 절차 카드도 '컨텍스트의 권위 있는 문서'로 함께 제공한다(fixed 모드).
        parts.append("\n## 절차 카드 (단계 순서·의존·결과물)\n" + procedure_card)
    for score, name, text in retrieved:
        parts.append(f"\n## {name} (유사도 {score:.3f})\n{text}")
    parts.append("\n[질문]\n" + QUESTION)
    return "\n".join(parts)


def _norm(s: str) -> str:
    # 백틱/공백 차이로 매칭이 깨지지 않도록 정규화 (예: `claude` 명령 -> claude명령)
    return s.replace("`", "").replace(" ", "")


def score_steps(answer: str) -> dict[str, bool]:
    a = _norm(answer)
    return {step: _norm(kw) in a for step, kw in STEP_DELIVERABLES.items()}


def fmt_steps(result: dict[str, bool]) -> str:
    kept = sum(result.values())
    marks = "  ".join(f"{'✅' if v else '❌'} {s}" for s, v in result.items())
    return f"결과물 키워드 언급 수 {kept}/{len(result)}   |   {marks}"


# --------------------------------------------------------------------------
# 시나리오
# --------------------------------------------------------------------------
def run(label, procedure_card, dry_run, backend="claude", model=None, top_k=TOP_K):
    retrieved = retrieve(QUESTION, top_k)
    titles = ", ".join(f"{name}({score:.2f})" for score, name, _ in retrieved)
    print(f"\n{'─' * 78}\n[{label}]")
    print(f"  검색됨 : {titles}  (top_k={top_k})")
    if procedure_card:
        print("  주입   : 절차 카드(순서·의존 관계) 함께 제공")
    if dry_run:
        print("  (dry-run: 생성 생략)")
        return None
    answer = llm(build_prompt(retrieved, procedure_card), backend, model)
    print("\n  답변:\n" + "\n".join("    " + ln for ln in answer.splitlines()))
    print(f"\n  → {fmt_steps(score_steps(answer))}")
    return answer


def main():
    from cli_backends import BACKENDS, validate_model
    ap = argparse.ArgumentParser(description="다단계 질문의 검색 문맥과 절차 카드 비교")
    ap.add_argument("--agent", "--backend", dest="backend", choices=BACKENDS, default="claude")
    ap.add_argument("--model", help="선택한 CLI 모델, 생략 시 해당 CLI 기본 설정")
    ap.add_argument("--top-k", type=int, choices=range(1, len(DOCS)+1), default=TOP_K)
    ap.add_argument("--mode", choices=["naive", "fixed", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true", help="생성 없이 검색 결과만 확인")
    args = ap.parse_args()
    try:
        validate_model(args.model)
    except ValueError as error:
        ap.error(str(error))

    print(f"코퍼스 {len(DOCS)}개 문서 · top_k={args.top_k}"
          + ("  [dry-run]" if args.dry_run else ""))
    print("질문:", QUESTION)

    naive = fixed = None
    if args.mode in ("naive", "both"):
        print("\n" + "=" * 78)
        print("  모드 A — naive RAG: top-k 조각만 검색 (검색 문맥 확인)")
        print("=" * 78)
        naive = run("naive · 절차 카드 없음", None, args.dry_run, args.backend, args.model, args.top_k)
    if args.mode in ("fixed", "both"):
        print("\n" + "=" * 78)
        print("  모드 B — fixed: 순서·의존을 담은 '절차 카드'를 함께 주입")
        print("=" * 78)
        fixed = run("fixed · 절차 카드 주입", PROCEDURE_CARD, args.dry_run, args.backend, args.model, args.top_k)

    if args.mode == "both" and not args.dry_run:
        print("\n" + "=" * 78)
        print("  결론: 같은 다단계 질문, 결과물 키워드 언급 수 비교")
        print("=" * 78)
        print(f"  naive : {fmt_steps(score_steps(naive or ''))}")
        print(f"  fixed : {fmt_steps(score_steps(fixed or ''))}")
        print("\n  → 검색은 조각을 찾지만 '절차의 구조(순서·의존)'를 보장하지 않는다.")
        print("    절차 카드는 추가 근거를 제공하며, 답변의 순서·의존·근거는 별도로 확인해야 한다.")


if __name__ == "__main__":
    main()
