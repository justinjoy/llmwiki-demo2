#!/usr/bin/env python3
"""공급한 dep/produces 사실과 규칙으로 실제 PyreWire 추론을 실행한다.

이 예제는 알려진 네 단계 chain만 지원한다. 모델 성능이나 사실의 진위는 평가하지 않는다.
"""
from __future__ import annotations

import sys

# --------------------------------------------------------------------------
# 1) 논리 프로그램 — 관계(스키마)와 추론 규칙 (Soufflé 스타일 Datalog)
# --------------------------------------------------------------------------
WIRELOG_PROGRAM = """
.decl dep(step: symbol, needs: symbol)          // step 은 needs 를 선행으로 요구
.decl produces(step: symbol, artifact: symbol)  // step 의 결과물은 artifact

.decl before(a: symbol, b: symbol)              // a 는 b 보다 먼저 (전이 폐쇄)
.decl input_of(artifact: symbol, step: symbol)  // artifact 가 step 의 입력

// 직접 의존 -> 순서. 그리고 순서는 전이적으로 누적된다.
before(N, S) :- dep(S, N).
before(A, C) :- before(A, B), before(B, C).

// 앞 단계(N)의 결과물(A)은 그 단계를 필요로 하는 step 의 입력이 된다.
input_of(A, S) :- dep(S, N), produces(N, A).
"""

# --------------------------------------------------------------------------
# 2) 사실(facts) — 페이지 28의 'depends on / produces' 관계를 그대로 입력
#    (이 관계들은 사람이 확정하는 '논리 계층'. RAG의 검색 대상이 아니다.)
# --------------------------------------------------------------------------
DEPS = [
    ("claude_md", "install"),     # CLAUDE.md 작성은 CLI 설치 뒤
    ("facts", "claude_md"),       # facts 추출은 CLAUDE.md 작성 뒤
    ("bookkeeping", "facts"),     # 점검은 facts 추출 뒤
]
PRODUCES = [
    ("install", "claude_cmd"),
    ("claude_md", "rules_doc"),
    ("facts", "facts_file"),
    ("bookkeeping", "verify_log"),
]

# 사람이 읽는 이름
STEP_KO = {
    "install": "Claude Code CLI 설치",
    "claude_md": "CLAUDE.md 작성",
    "facts": "facts 추출",
    "bookkeeping": "Bookkeeping 점검",
}
ART_KO = {
    "claude_cmd": "사용 가능한 claude 명령",
    "rules_doc": "운영 규칙 문서",
    "facts_file": "출처가 달린 facts 파일",
    "verify_log": "검증 로그와 수정 목록",
}


def reason():
    """Return genuine engine relations; never substitute a Python inference engine."""
    try:
        from pyrewire import EasySession
    except (ImportError, OSError) as error:
        raise RuntimeError("PyreWire가 필요합니다. Python 3.11+ 환경에서 pip install -r 05-rag-multistep/requirements.txt를 실행하세요: " + str(error)) from error
    if len(set(DEPS)) != len(DEPS) or len(set(PRODUCES)) != len(PRODUCES):
        raise ValueError("중복 입력 facts는 지원하지 않습니다.")
    session = EasySession(WIRELOG_PROGRAM)
    before_pairs, input_of = [], {}
    try:
        for step, needs in DEPS:
            session.insert("dep", (step, needs))
        for step, artifact in PRODUCES:
            session.insert("produces", (step, artifact))
        for relation, row, diff in session.step():
            if diff <= 0:
                continue
            if relation == "before":
                pair = tuple(row)
                if pair in before_pairs:
                    raise ValueError("중복 before 관계")
                before_pairs.append(pair)
            elif relation == "input_of":
                if row[1] in input_of:
                    raise ValueError("단계의 입력 관계가 유일하지 않습니다.")
                input_of[row[1]] = row[0]
    finally:
        session.close()
    return sorted(before_pairs), input_of


def linearize(before_pairs) -> list[str]:
    """Validate a complete unique four-stage chain from actual derived pairs."""
    pairs = set(map(tuple, before_pairs))
    steps = set(STEP_KO)
    if len(pairs) != len(before_pairs) or any(a not in steps or b not in steps or a == b for a, b in pairs):
        raise ValueError("중복·알 수 없는 단계·순환 관계가 있습니다.")
    order = []
    while len(order) < len(steps):
        ready = [s for s in steps-set(order) if all(a in order for a, b in pairs if b == s)]
        if len(ready) != 1:
            raise ValueError("순환하거나 유일한 순서를 도출할 정보가 부족합니다.")
        order.append(ready[0])
    expected = {(order[i], order[j]) for i in range(len(order)) for j in range(i+1, len(order))}
    if pairs != expected or any(order.index(needs) >= order.index(step) for step, needs in DEPS):
        raise ValueError("완전한 전이 관계 또는 입력 의존 관계가 일치하지 않습니다.")
    return order


def build_result():
    before, inputs = reason()
    order = linearize(before)
    artifacts = dict(PRODUCES)
    expected_inputs = {step: artifacts[needs] for step, needs in DEPS}
    if inputs != expected_inputs or set(artifacts) != set(STEP_KO):
        raise ValueError("엔진의 input_of 결과가 입력 facts와 일치하지 않습니다.")
    from importlib.metadata import version
    return {"engine": "PyreWire", "version": version("pyrewire"), "before": before,
            "input_of": inputs, "order": order,
            "flow": [{"step": step, "title": STEP_KO[step], "artifact": ART_KO[artifacts[step]],
                      "input": ART_KO[inputs[step]] if step in inputs else None} for step in order]}


def main():
    print("=" * 70)
    print("  wirelog 논리 엔진으로 다단계 추론 (입력 facts와 규칙으로 도출)")
    print("=" * 70)
    print(f"  입력 관계: dep {len(DEPS)}개 · produces {len(PRODUCES)}개")
    print("  규칙     : before(전이 폐쇄) · input_of(결과물→다음 입력)\n")

    try:
        result = build_result()
    except (RuntimeError, ValueError) as error:
        sys.exit(str(error))
    before_pairs, input_of, order = result["before"], result["input_of"], result["order"]

    print(f"[도출된 절차]  단계 {len(order)}/{len(STEP_KO)} · 순서·의존 모두 규칙으로 도출")
    for i, step in enumerate(order, 1):
        deliverable = ART_KO[dict(PRODUCES)[step]]
        feed = input_of.get(step)
        feed_txt = f"   (입력: {ART_KO[feed]})" if feed else "   (입력: 없음)"
        print(f"  {i}. {STEP_KO[step]:<22} → 결과물: {deliverable}{feed_txt}")

    print(f"\n  도출된 순서 관계(before) {len(before_pairs)}쌍 — 전이 폐쇄로 완전한 순서 확보")
    print("\n  위 결과는 공급한 facts와 규칙으로 도출했습니다. 모델 답변의 정확성 점수는 아닙니다.")


if __name__ == "__main__":
    main()
