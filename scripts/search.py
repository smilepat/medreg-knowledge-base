"""
search.py — 파이프라인 4단계(로컬판): 청크 검색 (임베딩 없이)

목적:
  Supabase pgvector 적재 전, 로컬에서 검색·인용 파이프라인을 끝까지 검증한다.
  여기서는 '키워드 + 글자 유사도'만 쓴다(= 하이브리드 검색의 키워드 측).
  의미검색(임베딩) 측은 Gemini/pgvector 도입 시 embed.py + 이 점수에 합산.

검색 점수(설명 가능):
  - 키워드 일치: 질의 토큰이 본문/맥락헤더/정의어에 등장 (등장 위치별 가중)
  - 조문 부스트: 질의에 '제15조' 같은 조 번호가 있고 청크 article과 일치하면 큰 가점
  - 글자 bigram 유사도: 맥락헤더와의 2글자 겹침(Jaccard) — 한국어 퍼지 매칭

메타데이터 필터(정확도 급상승):
  --current-only : 현행(is_current=true) 만
  --reg-type 법  : 규정유형 한정

사용법:
  python scripts/search.py "의료기기 등급분류 기준"
  python scripts/search.py "제15조" --top 3 --current-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 콘솔 인코딩 안전장치: cp949 등에서 못 찍는 문자가 있어도 crash 대신 대체
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

RE_ARTICLE = re.compile(r"제\d+조(?:의\d+)?")


def load_chunks(samples_dir: Path) -> list[dict]:
    """samples/*_processed.json 의 모든 청크를 로드한다."""
    files = sorted(samples_dir.glob("*_processed.json"))
    if not files:
        sys.exit(f"[오류] 청크 파일 없음: {samples_dir}/*_processed.json (chunk.py 먼저 실행)")
    chunks: list[dict] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        chunks.extend(data.get("chunks", []))
    return chunks


def bigrams(s: str) -> set[str]:
    """문자열의 2글자 집합(공백 제거)."""
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}


def tokenize(q: str) -> list[str]:
    """질의를 토큰으로 분리(2글자 이상만, 조문번호는 보존)."""
    raw = re.split(r"[\s,./]+", q.strip())
    return [t for t in raw if len(t) >= 2]


def score_chunk(query: str, tokens: list[str], q_articles: list[str], chunk: dict) -> tuple[float, str]:
    """청크 점수와 매칭 근거를 반환."""
    text = chunk["text"]
    header = chunk["context_header"]
    meta = chunk["metadata"]
    score = 0.0
    reasons: list[str] = []

    # 1) 키워드 일치
    for tok in tokens:
        if tok in header:
            score += 3.0  # 제목/맥락 일치는 강한 신호
            reasons.append(f"헤더:{tok}")
        elif tok in text:
            score += 1.0
            reasons.append(f"본문:{tok}")
        if tok in meta.get("defined_terms", []):
            score += 2.0
            reasons.append(f"정의어:{tok}")

    # 2) 조문 번호 직격 부스트
    for qa in q_articles:
        if meta["article"] == qa:
            score += 10.0
            reasons.append(f"조문일치:{qa}")

    # 3) 글자 bigram 유사도(맥락헤더 대상)
    qb = bigrams(query)
    hb = bigrams(header)
    if qb and hb:
        jacc = len(qb & hb) / len(qb | hb)
        score += jacc * 2.0

    return score, ", ".join(reasons[:6])


def main() -> None:
    parser = argparse.ArgumentParser(description="청크 로컬 검색(키워드+글자유사도)")
    parser.add_argument("query", help="검색 질의")
    parser.add_argument("--top", type=int, default=5, help="상위 N개 (기본 5)")
    parser.add_argument("--samples-dir", default="samples", help="청크 폴더 (기본 samples)")
    parser.add_argument("--current-only", action="store_true", help="현행만(is_current)")
    parser.add_argument("--reg-type", help="규정유형 한정(예: 법)")
    args = parser.parse_args()

    chunks = load_chunks(Path(args.samples_dir))

    # 메타데이터 필터 먼저 적용(정확도 급상승)
    pool = chunks
    if args.current_only:
        pool = [c for c in pool if c["metadata"].get("is_current")]
    if args.reg_type:
        pool = [c for c in pool if c["metadata"].get("reg_type") == args.reg_type]

    tokens = tokenize(args.query)
    q_articles = RE_ARTICLE.findall(args.query)

    scored = []
    for c in pool:
        s, why = score_chunk(args.query, tokens, q_articles, c)
        if s > 0:
            scored.append((s, why, c))
    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"질의: {args.query!r}  | 후보 {len(pool)}개 중 매칭 {len(scored)}개\n")
    if not scored:
        print("(매칭 없음 — 검색어를 바꾸거나 필터를 완화하세요)")
        return

    for rank, (s, why, c) in enumerate(scored[:args.top], start=1):
        m = c["metadata"]
        snippet = c["text"].split("\n", 1)[-1][:90].replace("\n", " ")
        print(f"#{rank} [{s:.1f}] {c['context_header']}")
        print(f"     시행 {m['effective_date']} / {m['reg_type']} / 근거: {why}")
        print(f"     출처: {m['source_url']}")
        print(f"     발췌: {snippet}…\n")


if __name__ == "__main__":
    main()
