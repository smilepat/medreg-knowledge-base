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

판정 종류(LLM 판정 ON 기준):
  ✅ 근거있음        : 조항이 주장을 직접 뒷받침(LLM '지지')
  ◐ 부분지지        : 일부/조건부 뒷받침(LLM '부분지지')
  ⚠️ 충돌(모순)     : 조항이 주장과 반대/충돌(LLM '모순')
  ⚠️ 근거없음(무관)  : 조항이 주장과 무관(다른 법 소관 등, LLM '무관')
  ⚠️ 시행예정        : 뒷받침되나 미래 시행본 → 현행 인용으로 부적절
  ⚠️ 확인필요        : 조항만으로 판단 근거 부족(LLM '불충분')
  ⚠️ 근거없음        : 명시 조가 KB에 없음(오인용) 또는 검색 유사도 낮음
  (--no-llm 시: 검색 근접도 기반 ✅근거있음/⚠️저신뢰/⚠️시행예정/⚠️근거없음)

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
import judge  # noqa: E402

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

SIM_OK = 0.65   # 이상이면 근거있음(검색 전용 모드)
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


def assess(claim: str, laws: list[str], current_only: bool, use_llm: bool) -> dict:
    """한 항목을 점검: 후보 조항 확보 → (LLM이면) 지지여부 판정."""
    q_articles = retriever.RE_ARTICLE.findall(claim)
    named_law = detect_law(claim, laws)

    # 1) 후보 조항 확보 (명시 인용 우선, 없으면 의미검색)
    sim = None
    if q_articles:
        prov = retriever.find_article(q_articles[0], named_law)
        if prov is None:
            where = f"{named_law} " if named_law else ""
            return {"verdict": "⚠️ 근거없음",
                    "basis": f"{where}{q_articles[0]} — KB에 없음(오인용/미적재 가능)"}
    else:
        res = retriever.hybrid_search(claim, top_k=1, current_only=current_only)
        if not res or res[0]["sim"] < SIM_LOW:
            sim = res[0]["sim"] if res else 0.0
            return {"verdict": "⚠️ 근거없음", "basis": f"유사도 {sim:.2f} 낮음 → 확인 필요"}
        prov = res[0]
        sim = prov["sim"]

    m = prov["metadata"]
    ver = f"시행 {m['effective_date']}" + (f", 유사도 {sim:.2f}" if sim is not None else "")
    future = not m.get("is_current", True)
    tag = f"{m['law_name']} {m['article']} ({ver})"

    # 2) 검색 전용(LLM 끔)
    if not use_llm:
        if future:
            return {"verdict": "⚠️ 시행예정", "basis": tag}
        if sim is not None and sim < SIM_OK:
            return {"verdict": "⚠️ 저신뢰", "basis": tag + " — 범위밖/인접주제 의심"}
        return {"verdict": "✅ 근거있음", "basis": tag}

    # 3) LLM 판정: 이 조항이 주장을 실제 뒷받침하는가
    j = judge.judge(claim, prov["text"], prov["context_header"])
    v, reason = j["verdict"], j["reason"]
    base = f"{tag} — {reason}"
    if v == "모순":
        return {"verdict": "⚠️ 충돌(모순)", "basis": base}
    if v == "무관":
        return {"verdict": "⚠️ 근거없음(무관)", "basis": base}
    if v == "불충분":
        return {"verdict": "⚠️ 확인필요", "basis": base}
    if future:  # 지지/부분지지지만 미래 시행본
        return {"verdict": "⚠️ 시행예정", "basis": base}
    if v == "부분지지":
        return {"verdict": "◐ 부분지지", "basis": base}
    return {"verdict": "✅ 근거있음", "basis": base}


def main() -> None:
    parser = argparse.ArgumentParser(description="내 문서 ↔ 규정 정합성 점검표(pgvector)")
    parser.add_argument("doc", help="점검할 문서 (md/txt)")
    parser.add_argument("--current-only", action="store_true", help="현행만 근거로")
    parser.add_argument("--no-llm", action="store_true", help="LLM 판정 끄기(검색 전용)")
    parser.add_argument("--out", help="점검표 저장 경로(.md). 미지정 시 화면 출력만")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        sys.exit(f"[오류] 문서 없음: {doc_path}")

    claims = split_claims(doc_path.read_text(encoding="utf-8"))
    if not claims:
        sys.exit("[오류] 점검할 항목이 없습니다(문서가 비었거나 제목만 있음).")

    use_llm = not args.no_llm
    laws = retriever.all_law_names()
    print(f"점검 중… 항목 {len(claims)}개 / LLM 판정 {'ON(gemini-2.5-flash)' if use_llm else 'OFF'}", file=sys.stderr)
    rows = [assess(c, laws, args.current_only, use_llm) for c in claims]

    mode = "LLM 지지여부 판정" if use_llm else "검색 근접도(LLM 끔)"
    lines = [
        f"# 규정 정합성 점검표 — {doc_path.name}",
        "",
        f"> 기준선(KB, Supabase pgvector): {', '.join(sorted(laws))}",
        f"> 판정 방식: {mode}. 조항 텍스트만 근거로 판정(외부지식 금지).",
        "> ⚠️ 최종 책임 판단은 HITL(담당자) 몫. 본 표는 1차 점검.",
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
