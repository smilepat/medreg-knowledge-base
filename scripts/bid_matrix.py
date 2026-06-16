"""
bid_matrix.py — 입찰 공고문 → 요구사항 매트릭스 (M3, 컴플라이언스 매칭 1단계)

입찰 공고문의 각 '요구사항'을 ①유형 분류 ②규정 근거 매핑 ③충족여부 칸으로 구조화한다.
→ 입찰제안서 준비 시 "무엇을, 어느 규정 근거로, 우리가 충족하는지" 점검 토대.

⚠️ 한계(정직): '충족 여부'는 **회사 제품·실적 자료와 대조**해야 확정된다(여기엔 그 자료가 없음).
  따라서 충족 칸은 '⬜ 회사자료 대조 필요'로 두고, 규정 근거가 있는 항목만 근거를 채운다.
  규정 외 요건(실적·가격 등)은 '규정 외(행정 요건)'으로 표시한다.

사전: .env(SUPABASE_DB_URL + GEMINI_API_KEY), embed.py 적재됨.

사용법:
  python scripts/bid_matrix.py examples/sample-bid-notice.md --out 매트릭스.md
  python scripts/bid_matrix.py 공고문.md --no-llm   # 유형분류 끄기
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever  # noqa: E402
from google.genai import types  # noqa: E402

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

SIM_OK = 0.68    # 이상이면 규정 근거 확실
SIM_WEAK = 0.60  # 이 값~SIM_OK 는 저신뢰(참고), 미만은 규정 외
TYPES = ["자격요건", "품질·인증", "규격·성능", "실적·납품", "가격·계약", "서류제출", "기타"]


def split_reqs(text: str) -> list[str]:
    reqs = []
    for line in text.splitlines():
        s = line.strip().lstrip("-*0123456789. )").strip()
        if len(s) < 8 or s.startswith("#"):
            continue
        reqs.append(s)
    return reqs


def classify(req: str) -> str:
    """요구사항 유형 분류(LLM). 실패 시 '기타'."""
    prompt = (
        "다음 입찰 요구사항의 유형을 아래 중 하나로만 분류해 JSON으로 답하라.\n"
        f"유형: {', '.join(TYPES)}\n요구사항: {req}\n"
        '출력: {"type":"<유형>"}'
    )
    try:
        r = retriever._client_().models.generate_content(
            model="gemini-2.5-flash", contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        t = json.loads(r.text).get("type", "기타")
        return t if t in TYPES else "기타"
    except Exception:
        return "기타"


def main() -> None:
    ap = argparse.ArgumentParser(description="입찰 공고문 → 요구사항 매트릭스")
    ap.add_argument("doc")
    ap.add_argument("--no-llm", action="store_true", help="유형 분류(LLM) 끄기")
    ap.add_argument("--out", help="저장 경로(.md)")
    args = ap.parse_args()

    p = Path(args.doc)
    if not p.exists():
        sys.exit(f"[오류] 문서 없음: {p}")
    reqs = split_reqs(p.read_text(encoding="utf-8"))
    if not reqs:
        sys.exit("[오류] 요구사항을 찾지 못했습니다.")

    use_llm = not args.no_llm
    print(f"분석 중… 요구사항 {len(reqs)}개 / 유형분류 {'ON' if use_llm else 'OFF'}", file=sys.stderr)

    rows = []
    for req in reqs:
        rtype = classify(req) if use_llm else "-"
        hits = retriever.hybrid_search(req, top_k=1)
        sim = hits[0]["sim"] if hits else 0.0
        if sim >= SIM_OK:
            m = hits[0]["metadata"]
            basis = f"{m['law_name']} {m['article']} (유사도 {sim:.2f})"
        elif sim >= SIM_WEAK:
            m = hits[0]["metadata"]
            basis = f"참고(저신뢰): {m['law_name']} {m['article']} ({sim:.2f}) — 확인필요"
        else:
            basis = "규정 외(조달·계약/실적 요건 — KB 미적재, 회사·공고 근거)"
        rows.append((req, rtype, basis))

    laws = ", ".join(sorted(retriever.all_law_names()))
    lines = [
        f"# 입찰 요구사항 매트릭스 — {p.name}",
        "",
        f"> 규정 기준선(KB): {laws}",
        "> ⚠️ 충족 여부는 회사 제품·실적 자료 대조 필요(HITL). 본 표는 요구사항↔규정 매핑.",
        "",
        "| # | 요구사항 | 유형 | 규정 근거 | 충족 |",
        "| - | -------- | ---- | --------- | ---- |",
    ]
    for i, (req, rtype, basis) in enumerate(rows, 1):
        rq = req[:42].replace("|", "\\|") + ("…" if len(req) > 42 else "")
        b = basis.replace("|", "\\|")
        lines.append(f"| {i} | {rq} | {rtype} | {b} | ⬜ 대조필요 |")
    mapped = sum(1 for _, _, b in rows if not b.startswith("규정 외") and not b.startswith("참고"))
    weak = sum(1 for _, _, b in rows if b.startswith("참고"))
    out_n = sum(1 for _, _, b in rows if b.startswith("규정 외"))
    lines += ["", f"> 규정 근거 확실 {mapped}건 / 저신뢰 {weak}건 / 규정 외 {out_n}건",
              "> 규정 외=조달·계약 규정(나라장터/국가계약법) KB 미적재 → Tier4 적재 시 개선."]

    out = "\n".join(lines)
    print(out)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"\n[저장] {args.out}")


if __name__ == "__main__":
    main()
