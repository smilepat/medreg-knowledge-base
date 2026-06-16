"""
report.py — 파이프라인 5단계(로컬판): 질문 → 검색 → 근거 인용 답변 초안

3대 안전장치를 코드로 구현한다:
  1) 환각 방지: 검색 점수가 임계값 미만이면 답을 만들지 않고 "확인 불가" 출력.
                모든 근거에 [법령명 조항 (시행일)] 인용을 의무화.
  2) 버전 관리: 인용에 시행일을 함께 표기(폐지 조항 인용 방지).
  3) HITL: 출력 말미에 '담당자 인용 확인 필요' 고지 + 출처 링크 노출.

설계 메모:
  - 로컬판은 LLM 호출 없이 '근거(조항) 제시'까지만 한다 → 환각 0(있는 원문만 보여줌).
  - LLM 초안 생성(자연어 요약)은 Gemini 키 도입 시 이 자리에서 검색결과를 근거로
    추가하면 된다. 그래도 인용·확인불가·HITL 규칙은 동일하게 유지한다.

사용법:
  python scripts/report.py "의료기기 제조업 허가는 누구에게 받나?"
  python scripts/report.py "치과 임플란트 보험 수가 기준?"   # 근거 없으면 확인 불가
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 콘솔 인코딩 안전장치: cp949 등에서 못 찍는 문자가 있어도 crash 대신 대체
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

# 공용 검색 모듈(pgvector 의미검색) 재사용
sys.path.insert(0, str(Path(__file__).resolve().parent))
import retriever  # noqa: E402

MIN_SIM = 0.50   # 코사인 유사도 이 값 미만이면 근거 불충분 → "확인 불가"
LOW_CONF = 0.65  # 이 값 미만이면 표시하되 '저신뢰(범위 밖 의심)' 경고
TOP_K = 3        # 답변 근거로 제시할 최대 조항 수


def citation(meta: dict) -> str:
    """의무 인용 형식: [법령명 조항 (시행 YYYY-MM-DD)]."""
    return f"[{meta['law_name']} {meta['article']} (시행 {meta['effective_date']})]"


def main() -> None:
    parser = argparse.ArgumentParser(description="질문 → 근거 인용 답변 초안(환각 방지)")
    parser.add_argument("question", help="질문")
    parser.add_argument("--current-only", action="store_true", help="현행만 근거로")
    args = parser.parse_args()

    results = retriever.hybrid_search(args.question, top_k=TOP_K, current_only=args.current_only)

    print(f"질문: {args.question}\n" + "=" * 60)

    # 안전장치 1: 근거 불충분(의미적으로 멂) → 확인 불가
    if not results or results[0]["sim"] < MIN_SIM:
        print("\n⚠️ 확인 불가 — 보유한 규정에서 충분한 근거를 찾지 못했습니다.")
        print("   (관련 규정이 아직 적재되지 않았거나, 질문 범위 밖일 수 있습니다.)")
        if results:
            top = results[0]
            print(f"   참고로 가장 가까운 후보: {citation(top['metadata'])} "
                  f"(유사도 {top['sim']:.2f}, 임계 {MIN_SIM})")
        return

    # 저신뢰 경고: 최상위 유사도가 애매하면(범위 밖 의심) 신중 검토 안내
    if results[0]["sim"] < LOW_CONF:
        print(f"\n⚠️ 주의: 최상위 유사도 {results[0]['sim']:.2f}(<{LOW_CONF})로 낮습니다.")
        print("   질문이 보유 규정의 범위 밖이거나 인접 주제일 수 있으니 적합성을 특히 신중히 확인하세요.")

    # 근거 제시(인용 의무)
    print("\n■ 관련 규정 (근거, 의미검색 유사도순):\n")
    for rank, c in enumerate(results, start=1):
        m = c["metadata"]
        body = c["text"].split("\n", 1)[-1].strip()
        print(f"{rank}. {citation(m)}  「{c['context_header']}」  (유사도 {c['sim']:.2f})")
        print(f"   {body[:220]}{'…' if len(body) > 220 else ''}")
        if m.get("cross_refs"):
            print(f"   ↳ 함께 볼 참조: {', '.join(m['cross_refs'][:5])}")
        print(f"   출처: {m['source_url']}\n")

    # 안전장치 2·3: 버전 고지 + HITL
    print("-" * 60)
    print("※ 위 인용은 시행일 기준 현행 조문입니다. 개정 여부를 최종 확인하세요.")
    print("※ 본 결과는 '초안'입니다 — 담당자가 출처(법령명·조항)를 직접 확인해야 합니다(HITL).")
    print("※ (로컬 PoC: LLM 자연어 요약 미적용 — 근거 원문만 제시. Gemini 도입 시 요약 추가)")


if __name__ == "__main__":
    main()
