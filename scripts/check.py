"""
check.py — 내 문서 ↔ 규정 정합성 점검표 (pgvector 의미검색판)

목적:
  보고서·입찰제안서 초안의 각 '항목(주장/문장)'을 지식베이스(Supabase medreg.chunks)에
  대조해, 근거 조항이 있는지 / 인용한 조 번호가 실제로 현행인지 / 시행예정 개정이 걸리는지를
  표로 출력한다. → 건별 HITL 검토의 체계적 토대.

⚠️ 한계(정직):
  '근거 유무·인용 정확성·버전·의미적 근접도'까지 본다. 문장이 규정과 **의미적으로 모순**
  되는지(예: 주체가 틀림)의 최종 판정은 **사람(HITL) 또는 LLM** 단계의 몫이다.
  의미검색이라도 인접 주제(예: 의료기기 책임보험 ↔ 건강보험)는 중간 유사도가 나올 수 있어,
  저신뢰 구간을 별도 표시한다.

판정 종류:
  ✅ 근거있음       : 의미검색 유사도 충분(≥SIM_OK)
  📌 인용확인(현행)  : 문서가 명시한 조(제N조)가 KB에 있고 현행
  ⚠️ 시행예정       : 문서가 명시한 조가 미래 시행본 → 현행 인용으로 부적절할 수 있음
  ⚠️ 저신뢰         : 유사도 중간(범위 밖/인접주제 의심) → 적합성 신중 확인
  ⚠️ 근거없음       : 명시 조가 KB에 없음(오인용/미적재) 또는 유사도 낮음

사전: .env(SUPABASE_DB_URL + GEMINI_API_KEY), embed.py로 medreg.chunks 적재됨.

사용법:
  python scripts/check.py path/to/문서.md
  python scripts/check.py 문서.md --current-only --out 점검표.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever  # noqa: E402

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

SIM_OK = 0.65   # 이상이면 근거있음
SIM_LOW = 0.55  # 이 값~SIM_OK 는 저신뢰, 미만은 근거없음


def split_claims(text: str) -> list[str]:
    """문서를 점검 단위로 분해(빈 줄/헤더 제외, 한 줄=한 항목)."""
    claims = []
    for line in text.splitlines():
        s = line.strip().lstrip("-*0123456789. ").strip()
        if len(s) < 8 or s.startswith("#"):
            continue
        claims.append(s)
    return claims


def detect_law(claim: str, laws: list[str]) -> str | None:
    """문서 문장이 명시한 법령명을 추정(가장 구체적/긴 이름 우선)."""
    for law in sorted(laws, key=len, reverse=True):
        if law in claim:
            return law
    return None


def assess(claim: str, laws: list[str], current_only: bool) -> dict:
    """한 항목을 점검해 판정/근거를 만든다."""
    q_articles = retriever.RE_ARTICLE.findall(claim)
    named_law = detect_law(claim, laws)

    # (1) 특정 조를 명시 인용 → 인용 정확성·버전 검증
    if q_articles:
        for qa in q_articles:
            hit = retriever.find_article(qa, named_law)
            if hit is None:
                where = f"{named_law} " if named_law else ""
                return {"verdict": "⚠️ 근거없음",
                        "basis": f"{where}{qa} — KB에 없음(오인용/미적재 가능)"}
            m = hit["metadata"]
            if not m.get("is_current", True):
                return {"verdict": "⚠️ 시행예정",
                        "basis": f"{m['law_name']} {qa} {m.get('status')}(시행 {m['effective_date']})"}
            return {"verdict": "📌 인용확인(현행)",
                    "basis": f"{m['law_name']} {qa} 현행(시행 {m['effective_date']})"}

    # (2) 명시 인용 없음 → 의미검색
    res = retriever.hybrid_search(claim, top_k=1, current_only=current_only)
    if not res or res[0]["sim"] < SIM_LOW:
        sim = res[0]["sim"] if res else 0.0
        return {"verdict": "⚠️ 근거없음", "basis": f"유사도 {sim:.2f} 낮음 → 확인 필요"}

    top = res[0]
    m = top["metadata"]
    sim = top["sim"]
    base = f"{m['law_name']} {m['article']} (시행 {m['effective_date']}, 유사도 {sim:.2f})"
    if not m.get("is_current", True):
        return {"verdict": "⚠️ 시행예정", "basis": base}
    if sim < SIM_OK:
        return {"verdict": "⚠️ 저신뢰", "basis": base + " — 범위 밖/인접주제 의심"}
    return {"verdict": "✅ 근거있음", "basis": base}


def main() -> None:
    parser = argparse.ArgumentParser(description="내 문서 ↔ 규정 정합성 점검표(pgvector)")
    parser.add_argument("doc", help="점검할 문서 (md/txt)")
    parser.add_argument("--current-only", action="store_true", help="현행만 근거로")
    parser.add_argument("--out", help="점검표 저장 경로(.md). 미지정 시 화면 출력만")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        sys.exit(f"[오류] 문서 없음: {doc_path}")

    claims = split_claims(doc_path.read_text(encoding="utf-8"))
    if not claims:
        sys.exit("[오류] 점검할 항목이 없습니다(문서가 비었거나 제목만 있음).")

    laws = retriever.all_law_names()
    rows = [assess(c, laws, args.current_only) for c in claims]

    lines = [
        f"# 규정 정합성 점검표 — {doc_path.name}",
        "",
        f"> 기준선(KB, Supabase pgvector): {', '.join(sorted(laws))}",
        "> ⚠️ 의미적 충돌 최종판정은 HITL(사람) 또는 LLM 단계. 본 표는 근거·인용·버전·근접도 점검.",
        "",
        "| # | 항목 | 판정 | 근거 |",
        "| - | ---- | ---- | ---- |",
    ]
    for i, (claim, r) in enumerate(zip(claims, rows), start=1):
        c_short = claim[:48].replace("|", "\\|") + ("…" if len(claim) > 48 else "")
        basis = r["basis"].replace("|", "\\|")
        lines.append(f"| {i} | {c_short} | {r['verdict']} | {basis} |")

    from collections import Counter
    cnt = Counter(r["verdict"] for r in rows)
    lines += ["", "## 요약", ""]
    for v, n in cnt.most_common():
        lines.append(f"- {v}: {n}건")
    flags = sum(n for v, n in cnt.items() if v.startswith("⚠️"))
    lines += ["", f"**확인 필요(⚠️) {flags}건 — 담당자 검토 권장.**"]

    report = "\n".join(lines)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\n[저장] {args.out}")


if __name__ == "__main__":
    main()
