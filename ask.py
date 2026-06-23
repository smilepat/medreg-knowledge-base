"""
ask.py — 의료기기 규정 지식베이스 대화형 검색 (키 불필요, 로컬)

질문을 입력하면 관련 조항을 출처·시행일과 함께 보여준다.
scripts/search.py 의 검색 로직을 그대로 재사용한다.

실행:
  python ask.py                 # 대화형(질문 반복 입력)
  python ask.py "의료기기 제조업 허가"   # 한 번만 검색
"""

from __future__ import annotations

import sys
from pathlib import Path

# 콘솔 UTF-8 강제 (Windows 한글 깨짐 방지)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

import search  # scripts/search.py  # noqa: E402

SAMPLES = ROOT / "samples"
TOP = 3
CURRENT_ONLY = True   # 기본: 현행 규정만


def run_query(chunks: list[dict], query: str) -> None:
    pool = [c for c in chunks if c["metadata"].get("is_current")] if CURRENT_ONLY else chunks
    tokens = search.tokenize(query)
    q_articles = search.RE_ARTICLE.findall(query)

    scored = []
    for c in pool:
        s, why = search.score_chunk(query, tokens, q_articles, c)
        if s > 0:
            scored.append((s, why, c))
    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"\n질의: {query!r}  | 후보 {len(pool)}개 중 매칭 {len(scored)}개\n")
    if not scored:
        print("  (매칭 없음 — 검색어에 법령 용어를 넣어보세요. 예: '제조업 허가', '등급분류')\n")
        return

    for rank, (s, why, c) in enumerate(scored[:TOP], start=1):
        m = c["metadata"]
        snippet = c["text"].split("\n", 1)[-1][:140].replace("\n", " ")
        print(f"  #{rank} [{s:.1f}]  {c['context_header']}")
        print(f"      시행 {m['effective_date']} / {m['reg_type']}")
        print(f"      출처: {m['source_url']}")
        print(f"      발췌: {snippet}…\n")

    print("  ※ 초안입니다 — 중요한 판단은 출처 원문을 직접 확인하세요(HITL).\n")


def main() -> None:
    chunks = search.load_chunks(SAMPLES)
    print(f"[지식베이스 로드 완료: 조항 {len(chunks)}개 · 현행만={CURRENT_ONLY}]")

    # 인자가 있으면 한 번만 검색하고 종료
    if len(sys.argv) > 1:
        run_query(chunks, " ".join(sys.argv[1:]))
        return

    # 대화형 모드
    print("질문을 입력하세요. (그냥 Enter 누르면 종료)\n")
    while True:
        try:
            q = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        run_query(chunks, q)
    print("종료합니다.")


if __name__ == "__main__":
    main()
