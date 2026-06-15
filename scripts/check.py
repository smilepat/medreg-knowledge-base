"""
check.py — 내 문서 ↔ 규정 정합성 점검표 (로컬판)

목적:
  보고서·입찰제안서 초안의 각 '항목(주장/문장)'을 지식베이스(samples/*.json)에 대조해,
  근거 조항이 있는지 / 인용한 조 번호가 실제로 현행인지 / 시행예정 개정이 걸리는지를
  표로 출력한다. → 건별 HITL 검토의 체계적 토대.

⚠️ 한계(정직):
  로컬판은 '근거 유무 · 인용 정확성 · 버전'까지만 본다. 문장이 규정과 **의미적으로 모순**
  되는지(예: "시·도지사에게 허가"처럼 주체가 틀림)의 최종 판정은 **사람(HITL) 또는 LLM(Gemini)**
  단계의 몫이다. check.py는 그 판단에 필요한 '근거 조항'을 정확히 끌어다 줄 뿐 지어내지 않는다.

판정 종류:
  ✅ 근거있음      : 충분한 근거 조항 검색됨(인용 첨부)
  📌 인용확인(현행) : 문서가 명시한 조(제N조)가 KB에 있고 현행
  ⚠️ 시행예정      : 문서가 명시한 조가 미래 시행본 → 현행 인용으로 부적절할 수 있음
  ⚠️ 근거없음      : 명시한 조가 KB에 없음(오인용/미적재) 또는 검색 근거 부족 → 확인 필요

사용법:
  python scripts/check.py path/to/문서.md
  python scripts/check.py 문서.md --current-only --out 점검표.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search import RE_ARTICLE, bigrams, load_chunks, score_chunk, tokenize  # noqa: E402

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

MIN_SCORE = 3.0  # 검색 근거 충분 임계


def split_claims(text: str) -> list[str]:
    """문서를 점검 단위로 분해(빈 줄/헤더 제외, 한 줄=한 항목)."""
    claims = []
    for line in text.splitlines():
        s = line.strip().lstrip("-*0123456789. ").strip()
        if len(s) < 8 or s.startswith("#"):  # 너무 짧거나 제목 줄은 제외
            continue
        claims.append(s)
    return claims


def find_article(chunks: list[dict], law: str | None, article: str) -> dict | None:
    """KB에서 (법령, 조) 에 해당하는 청크를 찾는다. law=None이면 조 번호만으로."""
    for c in chunks:
        m = c["metadata"]
        if m["article"] == article and (law is None or m["law_name"] == law):
            return c
    return None


def detect_law(claim: str, laws: list[str]) -> str | None:
    """문서 문장이 명시한 법령명을 추정(가장 구체적/긴 이름 우선)."""
    for law in sorted(laws, key=len, reverse=True):
        if law in claim:
            return law
    return None


def assess(claim: str, chunks: list[dict], laws: list[str]) -> dict:
    """한 항목을 점검해 판정/근거를 만든다."""
    tokens = tokenize(claim)
    q_articles = RE_ARTICLE.findall(claim)
    named_law = detect_law(claim, laws)  # 문서가 명시한 법령(있으면 그 법으로 한정)

    # (1) 문서가 특정 조를 명시 인용한 경우 → 인용 정확성·버전 검증
    if q_articles:
        for qa in q_articles:
            hit = find_article(chunks, named_law, qa)
            if hit is None:
                where = f"{named_law} " if named_law else ""
                return {"verdict": "⚠️ 근거없음",
                        "basis": f"{where}{qa} — KB에 없음(오인용/미적재 가능)",
                        "cite": ""}
            m = hit["metadata"]
            if not m.get("is_current", True):
                return {"verdict": "⚠️ 시행예정",
                        "basis": f"{m['law_name']} {qa} 은(는) {m.get('status')}(시행 {m['effective_date']})",
                        "cite": hit["context_header"]}
            return {"verdict": "📌 인용확인(현행)",
                    "basis": f"{m['law_name']} {qa} 현행(시행 {m['effective_date']})",
                    "cite": hit["context_header"]}

    # (2) 명시 인용이 없으면 의미 검색으로 근거 후보 탐색
    scored = []
    for c in chunks:
        s, _ = score_chunk(claim, tokens, [], c)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored or scored[0][0] < MIN_SCORE:
        return {"verdict": "⚠️ 근거없음", "basis": "검색 근거 부족 → 확인 필요", "cite": ""}

    top = scored[0][1]
    m = top["metadata"]
    tag = "✅ 근거있음" if m.get("is_current", True) else "⚠️ 시행예정"
    return {"verdict": tag,
            "basis": f"{m['law_name']} {m['article']} (시행 {m['effective_date']})",
            "cite": top["context_header"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="내 문서 ↔ 규정 정합성 점검표")
    parser.add_argument("doc", help="점검할 문서 (md/txt)")
    parser.add_argument("--samples-dir", default="samples")
    parser.add_argument("--current-only", action="store_true", help="현행만 근거로")
    parser.add_argument("--out", help="점검표 저장 경로(.md). 미지정 시 화면 출력만")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        sys.exit(f"[오류] 문서 없음: {doc_path}")

    chunks = load_chunks(Path(args.samples_dir))
    if args.current_only:
        chunks = [c for c in chunks if c["metadata"].get("is_current")]

    claims = split_claims(doc_path.read_text(encoding="utf-8"))
    if not claims:
        sys.exit("[오류] 점검할 항목이 없습니다(문서가 비었거나 제목만 있음).")

    laws = sorted({c["metadata"]["law_name"] for c in chunks})
    rows = [assess(c, chunks, laws) for c in claims]

    # 점검표(Markdown)
    lines = [
        f"# 규정 정합성 점검표 — {doc_path.name}",
        "",
        f"> 기준선(KB): {', '.join(laws)} / 청크 {len(chunks)}개",
        "> ⚠️ 의미적 충돌 최종판정은 HITL(사람) 또는 LLM 단계. 본 표는 근거·인용·버전 점검.",
        "",
        "| # | 항목 | 판정 | 근거 |",
        "| - | ---- | ---- | ---- |",
    ]
    for i, (claim, r) in enumerate(zip(claims, rows), start=1):
        c_short = claim[:48].replace("|", "\\|") + ("…" if len(claim) > 48 else "")
        basis = r["basis"].replace("|", "\\|")
        lines.append(f"| {i} | {c_short} | {r['verdict']} | {basis} |")

    # 요약
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
