#!/usr/bin/env python3
"""선택한 로컬 CLI로 일반 RAG와 파일 메모리의 두 턴을 비교한다.

이 예제의 일반 모드는 이전 답변을 다음 요청에 전달하지 않는다.
검색은 문자 bigram 기반 TF-IDF이며 외부 Python 의존성이 없다.
fixed 모드는 실제 1턴 응답을 파일로 저장하고 2턴에 다시 읽는다.
키워드 언급 수는 판단 정확도나 생활 기준의 실제 준수율이 아니다.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

# --------------------------------------------------------------------------
# 설정
# --------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
CORPUS_DIR = HERE / "corpus"
MEMORY_DIR = HERE / "memory"          # fixed 모드에서 기준을 남기는 곳
MEMORY_FILE = MEMORY_DIR / "criteria.md"

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
TOP_K = int(os.environ.get("RAG_TOP_K", "1"))

# 1턴: 어제 일기에서 내일 체크할 기준을 정리 / 2턴: 오늘 일기에 그 기준 적용
TURN1_QUERY = "2026-07-01 일기에서 내일도 지켜야 할 생활 체크 기준을 정리해줘."
TURN2_QUERY = "제품 회고 회의와 편의점 생수가 나온 2026-07-02 일기를 보고 오늘 하루를 평가해줘."

SYSTEM_PROMPT = (
    "너는 개인 일기 회고 어시스턴트다. "
    "반드시 아래 '제공된 컨텍스트'에 있는 정보만 사용해서 답한다. "
    "컨텍스트에 없는 날짜의 일기나 생활 기준은 스스로 지어내지 말고, "
    "주어진 자료 범위 안에서만 구체적으로 안내한다. 답변은 한국어로 한다."
)

# 우리가 추적할 '생활 체크 기준' 세 가지와, 답변에서 그 기준을 찾기 위한 키워드
CRITERIA = {
    "30분 걷기": ["30분 걷", "걷기"],
    "커피 지출 5천원 이하": ["커피", "5천원", "지출"],
    "야식 금지": ["야식"],
}


# --------------------------------------------------------------------------
# 로컬 임베딩 + 검색기 (외부 의존성 없는 TF-IDF, 문자 bigram 기반)
#   - 한국어 형태소 분석 없이도 동작하도록 문자 bigram을 토큰으로 사용
# --------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    text = text.lower()
    words = re.findall(r"[a-z0-9]+", text)              # 영문/숫자 단어
    compact = re.sub(r"\s+", "", text)                  # 공백 제거 후
    bigrams = [compact[i : i + 2] for i in range(len(compact) - 1)]  # 문자 bigram
    return words + bigrams


class TfidfRetriever:
    """아주 작은 TF-IDF 코사인 유사도 검색기."""

    def __init__(self, docs: list[dict]):
        self.docs = docs
        tokenized = [tokenize(d["text"]) for d in docs]

        # 문서 빈도(df) -> idf
        df: Counter = Counter()
        for toks in tokenized:
            for t in set(toks):
                df[t] += 1
        n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

        # 각 문서의 정규화된 tf-idf 벡터
        self.doc_vecs = [self._vectorize(toks) for toks in tokenized]

    def _vectorize(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        vec = {t: (c / len(toks)) * self.idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        # 더 작은 쪽을 순회
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(t, 0.0) for t, v in a.items())

    def search(self, query: str, top_k: int) -> list[tuple[dict, float]]:
        qvec = self._vectorize(tokenize(query))
        scored = [
            (doc, self._cosine(qvec, dvec))
            for doc, dvec in zip(self.docs, self.doc_vecs)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


# --------------------------------------------------------------------------
# 코퍼스 로딩 / 평가 유틸
# --------------------------------------------------------------------------
def load_corpus() -> list[dict]:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.lstrip().splitlines()[0].lstrip("# ").strip()
        docs.append({"id": path.name, "title": title, "text": text})
    if not docs:
        sys.exit(f"코퍼스가 비어 있습니다: {CORPUS_DIR}")
    return docs


def score_criteria(answer: str) -> dict[str, bool]:
    """답변이 각 판단 기준을 언급했는지 검사."""
    return {
        name: any(kw in answer for kw in kws) for name, kws in CRITERIA.items()
    }


def fmt_criteria(result: dict[str, bool]) -> str:
    kept = sum(result.values())
    marks = "  ".join(f"{'✅' if v else '❌'} {k}" for k, v in result.items())
    return f"기준 언급 수 {kept}/{len(result)}   |   {marks}"


# --------------------------------------------------------------------------
# 생성 — 선택한 로컬 CLI
#   공통 어댑터가 각 CLI의 기존 인증과 설정을 사용한다.
# --------------------------------------------------------------------------
def generate(prompt: str, model: str | None, backend: str = "claude") -> str:
    from cli_backends import generate as call_cli, GenerationError
    import threading
    try:
        return call_cli(prompt, model, threading.Event(), 180,
                        backend=backend, system_prompt=SYSTEM_PROMPT)["answer"]
    except GenerationError as error:
        sys.exit(str(error))


def build_prompt(query: str, retrieved: list[tuple[dict, float]], memory: str | None) -> str:
    parts = []
    if memory:
        # fixed 모드에서만 들어오는, 이전에 확정한 생활 체크 기준
        parts.append("[이전에 확정한 생활 체크 기준 — 반드시 적용할 것]\n" + memory.strip())
    parts.append("[제공된 컨텍스트]")
    for doc, score in retrieved:
        parts.append(f"\n## {doc['title']} (유사도 {score:.3f})\n{doc['text'].strip()}")
    parts.append("\n[질문]\n" + query)
    return "\n".join(parts)


# --------------------------------------------------------------------------
# 한 턴 실행
# --------------------------------------------------------------------------
def run_turn(label, query, retriever, model, memory=None, dry_run=False, backend="claude"):
    retrieved = retriever.search(query, TOP_K)
    titles = ", ".join(f"{d['title']}({s:.2f})" for d, s in retrieved)

    print(f"\n{'─' * 78}")
    print(f"[{label}]")
    print(f"  질문   : {query}")
    print(f"  검색됨 : {titles}")
    if memory:
        print(f"  메모리 : criteria.md 주입됨 ({len(memory)}자)")

    if dry_run:
        print("  (dry-run: 생성 생략)")
        return None, retrieved

    answer = generate(build_prompt(query, retrieved, memory), model, backend)
    print(f"\n  답변:\n{indent(answer)}")
    print(f"\n  → {fmt_criteria(score_criteria(answer))}")
    return answer, retrieved


def indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


# --------------------------------------------------------------------------
# 시나리오
# --------------------------------------------------------------------------
def scenario_naive(retriever, model, dry_run, backend="claude"):
    """순수 RAG: 턴 사이에 아무것도 보존하지 않는다."""
    print("\n" + "=" * 78)
    print("  모드 A — naive RAG (상태 없음): 단기 기억 상실 재현")
    print("=" * 78)
    run_turn("1턴 · 어제 일기에서 기준 정리", TURN1_QUERY, retriever, model, dry_run=dry_run, backend=backend)
    a2, _ = run_turn("2턴 · 오늘 일기에 기준 적용", TURN2_QUERY, retriever, model, dry_run=dry_run, backend=backend)
    return a2


def scenario_fixed(retriever, model, dry_run, backend="claude"):
    """슬라이드 15 모드 B: 1턴 기준을 파일로 남기고 2턴에 다시 읽힌다."""
    print("\n" + "=" * 78)
    print("  모드 B — fixed (기준을 파일로 외부화): 단기 기억 상실 완화")
    print("=" * 78)
    a1, _ = run_turn("1턴 · 어제 일기에서 기준 정리", TURN1_QUERY, retriever, model, dry_run=dry_run, backend=backend)

    if dry_run:
        # dry-run은 생성을 건너뛰므로 저장할 기준이 없다. 메모리 파일을 건드리지 않는다.
        print(f"\n  (dry-run: {MEMORY_FILE.relative_to(HERE)} 저장 생략)")
        run_turn("2턴 · 오늘 일기에 기준 적용", TURN2_QUERY, retriever, model, dry_run=dry_run, backend=backend)
        return None

    # 1턴의 답변(= 확정된 생활 체크 기준)을 파일로 남긴다.
    MEMORY_DIR.mkdir(exist_ok=True)
    MEMORY_FILE.write_text(a1, encoding="utf-8")
    print(f"\n  💾 1턴 기준을 {MEMORY_FILE.relative_to(HERE)} 에 저장")

    # 2턴: 검색 결과 + 저장해 둔 기준을 함께 주입한다.
    saved = MEMORY_FILE.read_text(encoding="utf-8")
    a2, _ = run_turn("2턴 · 오늘 일기에 기준 적용", TURN2_QUERY, retriever, model, memory=saved, dry_run=dry_run, backend=backend)
    return a2


def main():
    ap = argparse.ArgumentParser(description="일반 RAG의 단기 기억 상실 재현 데모")
    from cli_backends import BACKENDS, validate_model
    ap.add_argument("--agent", "--backend", dest="backend", choices=BACKENDS, default="claude")
    ap.add_argument("--model", help="선택한 CLI에 전달할 모델, 생략 시 CLI 기본값 (Claude는 기존 기본 모델)")
    ap.add_argument("--mode", choices=["naive", "fixed", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true", help="CLI 호출·설치 검사·메모리 저장 없이 검색 결과만 확인")
    args = ap.parse_args()
    if args.model is None and args.backend == "claude":
        args.model = DEFAULT_MODEL
    try:
        validate_model(args.model)
    except ValueError as error:
        ap.error(str(error))

    docs = load_corpus()
    retriever = TfidfRetriever(docs)

    head = f"코퍼스 {len(docs)}개 문서 로드 · top_k={TOP_K} · model={args.model or 'CLI 기본 설정'}"
    print(head + ("  [dry-run]" if args.dry_run else f" · backend={args.backend}"))

    naive_a2 = fixed_a2 = None
    if args.mode in ("naive", "both"):
        naive_a2 = scenario_naive(retriever, args.model, args.dry_run, args.backend)
    if args.mode in ("fixed", "both"):
        fixed_a2 = scenario_fixed(retriever, args.model, args.dry_run, args.backend)

    # 핵심 대비 요약
    if args.mode == "both" and not args.dry_run:
        print("\n" + "=" * 78)
        print("  결론: 동일한 2턴 질문, 2턴 답변의 기준 언급 수 비교")
        print("=" * 78)
        print(f"  naive RAG : {fmt_criteria(score_criteria(naive_a2 or ''))}")
        print(f"  fixed     : {fmt_criteria(score_criteria(fixed_a2 or ''))}")
        print("\n  이 실험의 naive RAG에는 이전 답변을 전달하지 않습니다.")
        print("  fixed는 실제 저장한 응답을 다시 읽습니다. 키워드 언급 수는 정확도나 준수율이 아닙니다.")


if __name__ == "__main__":
    main()
