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


def judge_fulfillment(req: str, basis: str, company: str) -> dict:
    """회사 프로필과 대조해 요구사항 충족 여부 판정(LLM). 프로필에 없으면 확인필요."""
    prompt = (
        "아래 [회사 프로필]만 근거로 [입찰 요구사항] 충족 여부를 판정하라.\n"
        "프로필에 명시되지 않은 내용은 추측 금지(없으면 '확인필요').\n"
        f"[입찰 요구사항] {req}\n[참고 규정] {basis}\n[회사 프로필]\n{company[:3000]}\n"
        '출력 JSON: {"status":"충족|미충족|확인필요","reason":"한 문장"}'
    )
    try:
        r = retriever._client_().models.generate_content(
            model="gemini-2.5-flash", contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        d = json.loads(r.text)
        st = d.get("status", "확인필요")
        return {"status": st if st in ("충족", "미충족", "확인필요") else "확인필요",
                "reason": (d.get("reason") or "").strip()}
    except Exception as e:
        return {"status": "확인필요", "reason": f"판정 실패: {str(e)[:40]}"}


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
    ap.add_argument("--company", help="회사 역량 프로필(md/txt) — 주면 충족 여부 자동 판정")
    ap.add_argument("--no-llm", action="store_true", help="유형 분류(LLM) 끄기")
    ap.add_argument("--out", help="저장 경로(.md)")
    args = ap.parse_args()

    p = Path(args.doc)
    if not p.exists():
        sys.exit(f"[오류] 문서 없음: {p}")
    reqs = split_reqs(p.read_text(encoding="utf-8"))
    if not reqs:
        sys.exit("[오류] 요구사항을 찾지 못했습니다.")

    company = ""
    if args.company:
        cp = Path(args.company)
        if not cp.exists():
            sys.exit(f"[오류] 회사 프로필 없음: {cp}")
        company = cp.read_text(encoding="utf-8")

    use_llm = not args.no_llm
    print(f"분석 중… 요구사항 {len(reqs)}개 / 유형분류 {'ON' if use_llm else 'OFF'}"
          f" / 충족판정 {'ON' if company else 'OFF'}", file=sys.stderr)

    STATUS_ICON = {"충족": "✅ 충족", "미충족": "❌ 미충족", "확인필요": "⚠️ 확인필요"}
    rows = []
    for req in reqs:
        rtype = classify(req) if use_llm else "-"
        hits = retriever.hybrid_search(req, top_k=1)
        sim = hits[0]["sim"] if hits else 0.0
        ref = ""  # judge에 넘길 깔끔한 근거(유사도 숫자 제외)
        if sim >= SIM_OK:
            m = hits[0]["metadata"]
            ref = f"{m['law_name']} {m['article']}"
            basis = f"{ref} (유사도 {sim:.2f})"
        elif sim >= SIM_WEAK:
            m = hits[0]["metadata"]
            ref = f"{m['law_name']} {m['article']}"
            basis = f"참고(저신뢰): {ref} ({sim:.2f}) — 확인필요"
        else:
            basis = "규정 외(조달·계약/실적 요건 — KB 미적재, 회사·공고 근거)"
        if company:
            fj = judge_fulfillment(req, ref or "(해당 규정 미확인)", company)
            fulfil = f"{STATUS_ICON.get(fj['status'], fj['status'])} — {fj['reason']}"
        else:
            fulfil = "⬜ 대조필요"
        rows.append((req, rtype, basis, fulfil))

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
    for i, (req, rtype, basis, fulfil) in enumerate(rows, 1):
        rq = req[:40].replace("|", "\\|") + ("…" if len(req) > 40 else "")
        b = basis.replace("|", "\\|")
        f = fulfil.replace("|", "\\|")
        lines.append(f"| {i} | {rq} | {rtype} | {b} | {f} |")
    mapped = sum(1 for r in rows if not r[2].startswith("규정 외") and not r[2].startswith("참고"))
    weak = sum(1 for r in rows if r[2].startswith("참고"))
    out_n = sum(1 for r in rows if r[2].startswith("규정 외"))
    lines += ["", f"> 규정 근거 확실 {mapped}건 / 저신뢰 {weak}건 / 규정 외 {out_n}건"]
    if company:
        from collections import Counter
        sc = Counter(r[3].split(" —")[0] for r in rows)
        lines.append("> 충족: " + " / ".join(f"{k} {v}건" for k, v in sc.items()))
        lines.append("> ⚠️ 충족 판정은 회사 프로필 텍스트 기반 1차 판단 — 최종 증빙은 HITL 확인.")
    else:
        lines.append("> 충족 여부는 --company 프로필 제공 시 자동 판정.")

    out = "\n".join(lines)
    print(out)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"\n[저장] {args.out}")


if __name__ == "__main__":
    main()
