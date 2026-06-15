"""
chunk.py — 파이프라인 3단계: 위계 트리 JSON → 최종 청크 + 메타데이터(지식베이스 형식)

입력:  processed/<법령명>_structured.json   (structure.py 산출)
출력:  samples/<법령명>_processed.json       (★ M1 핵심 검증물 — chunks + definitions)

설계 핵심:
  - 청킹 단위 = '조(條) 1개 = 청크 1개'. (법령 위계가 천연 청킹 경계)
  - contextual chunking: 청크 text 맨 앞에 '[법령명 제N조(제목)] (장)' 맥락 줄을 넣어
    조각만 떼어내도 "어느 법, 어느 장, 몇 조"인지 자기완결로 알 수 있게 한다.
  - 메타데이터 6필수(docs/metadata-schema.md): law_name/article/effective_date/
    reg_type/applies_to/source(+is_current, cross_refs, defined_terms).
  - 정의어(제2조 등 "○○"란 …)는 definitions 사전으로 분리.
  - 교차참조("제20조에 따라", 「약사법」 …)는 cross_refs로 추출.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 같은 법 내부 조문 참조: 제20조, 제15조제2항, 제4조의2
RE_INTERNAL_REF = re.compile(r"제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?")
# 외부 법령 참조: 「약사법」, 「의료법」 제37조
RE_EXTERNAL_REF = re.compile(r"「[^」]{1,30}」(?:\s*제\d+조(?:의\d+)?)?")
# 정의어: "의료기기"란 / "기술문서"란 / "안전관리종합계획"이라 한다
RE_DEFINED = re.compile(r'[""]([^""]{1,40})[""]\s*(?:이?란|(?:이)?라\s*한다)')


def build_body(article: dict) -> str:
    """조문 본문 텍스트를 만든다(항/호 번호는 내용에 이미 포함됨)."""
    if not article["hang"]:
        return article["head"].strip()
    parts: list[str] = []
    for h in article["hang"]:
        parts.append(h["text"].strip())
        for ho in h["ho"]:
            parts.append("  " + ho["text"].strip())  # 호는 들여쓰기로 종속 표시
    return "\n".join(p for p in parts if p.strip())


def extract_cross_refs(text: str, self_article: str) -> list[str]:
    """본문에서 내부/외부 참조를 추출(자기 자신 참조는 제외)."""
    refs: list[str] = []
    for m in RE_INTERNAL_REF.findall(text):
        if m != self_article:  # '제2조' 안에서 '제2조'는 제외
            refs.append(m)
    for m in RE_EXTERNAL_REF.findall(text):
        refs.append(m.strip())
    # 순서 보존 중복 제거
    seen = set()
    uniq = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def extract_definitions(article: dict) -> list[dict]:
    """조문 안의 정의어를 (용어, 정의문, 출처조항) 으로 추출."""
    defs: list[dict] = []
    # 항/호 단위로 스캔해 정의문 본문을 짝지어 보존
    scan_units: list[str] = []
    if article["hang"]:
        for h in article["hang"]:
            scan_units.append(h["text"])
            scan_units.extend(ho["text"] for ho in h["ho"])
    else:
        scan_units.append(article["head"])

    for unit in scan_units:
        for term in RE_DEFINED.findall(unit):
            defs.append({
                "term": term.strip(),
                "article": article["article"],
                "definition": unit.strip(),
            })
    return defs


def make_chunks(data: dict) -> tuple[list[dict], list[dict]]:
    """구조화 데이터 → (청크 리스트, 정의어 사전)."""
    meta = data["meta"]
    law = meta["law_name"]
    chunks: list[dict] = []
    definitions: list[dict] = []

    for a in data["articles"]:
        title = f"({a['title']})" if a["title"] else ""
        chapter = a["chapter"]
        body = build_body(a)

        # contextual 맥락 줄 + 본문
        ctx_line = f"[{law} {a['article']}{title}]" + (f" {chapter}" if chapter else "")
        text = f"{ctx_line}\n{body}"

        context_header = " > ".join(x for x in [law, chapter, f"{a['article']}{title}"] if x)
        cross_refs = extract_cross_refs(body, a["article"])

        # 정의어 수집(전역 사전 + 청크 메타)
        art_defs = extract_definitions(a)
        definitions.extend(art_defs)
        defined_terms = [d["term"] for d in art_defs]

        chunks.append({
            "chunk_id": f"{law}_{a['article']}",
            "text": text,
            "context_header": context_header,
            "metadata": {
                "law_name": law,
                "reg_type": meta["reg_type"],
                "article": a["article"],
                "chapter": chapter,
                "effective_date": a["effective_date"] or meta["effective_date"],
                "is_current": True,  # fetch_law.py가 현행(시행일 기준) 본문을 받았음
                "applies_to": [],     # 본법은 일반 적용 — 하위 고시에서 품목·등급 채움
                "source_url": f"https://www.law.go.kr/법령/{law}/{a['article']}",
                "cross_refs": cross_refs,
                "defined_terms": defined_terms,
            },
        })

    return chunks, definitions


def main() -> None:
    parser = argparse.ArgumentParser(description="구조화 JSON → 최종 청크+메타데이터")
    parser.add_argument("json", help="입력 구조화 JSON (예: processed/의료기기법_structured.json)")
    parser.add_argument("--out-dir", default="samples", help="출력 폴더 (기본: samples)")
    args = parser.parse_args()

    in_path = Path(args.json)
    if not in_path.exists():
        sys.exit(f"[오류] 파일 없음: {in_path}")

    data = json.loads(in_path.read_text(encoding="utf-8"))
    if "meta" not in data or "articles" not in data:
        sys.exit("[오류] structure.py 산출 형식이 아닙니다(meta/articles 필요).")

    chunks, definitions = make_chunks(data)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    law = data["meta"]["law_name"]
    out_path = out_dir / f"{law}_processed.json"

    out_path.write_text(
        json.dumps(
            {"meta": data["meta"], "chunks": chunks, "definitions": definitions},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 요약(검증용)
    n_refs = sum(1 for c in chunks if c["metadata"]["cross_refs"])
    uniq_terms = sorted({d["term"] for d in definitions})
    print(f"[완료] {out_path}")
    print(f"  - 청크: {len(chunks)}개 (조 단위)")
    print(f"  - 교차참조 있는 청크: {n_refs}개")
    print(f"  - 정의어: {len(uniq_terms)}개 → {', '.join(uniq_terms[:8])}{' ...' if len(uniq_terms) > 8 else ''}")
    print("\n다음 단계: embed.py (Supabase pgvector 적재) → search.py (하이브리드 검색)")


if __name__ == "__main__":
    main()
