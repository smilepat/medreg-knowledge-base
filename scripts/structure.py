"""
structure.py — 파이프라인 2단계: 법령 XML → 위계 트리(JSON) + 사람용 Markdown

입력:  raw/<법령명>.xml          (fetch_law.py가 받은 국가법령정보 Open API XML)
출력:  processed/<법령명>_structured.json   (기계용 — chunk.py 입력)
       processed/<법령명>_structured.md     (사람용 — 검수용)

설계 핵심(왜 이렇게 하나):
  - 한국 법령 XML은 '조문여부'로 장/절 헤더(전문)와 실제 조문을 구분한다.
    → 장(章) 헤더를 만나면 '현재 장'으로 기억해, 뒤따르는 조문에 맥락으로 붙인다.
      (contextual chunking의 토대 — "이 조가 어느 장 소속인지"를 청크가 알게 함)
  - '조문가지번호'는 제5조의2 같은 가지조(추가된 조)를 표현 → 조번호 표기에 합친다.
  - 항(①②) → 호(1.2.) 중첩을 그대로 트리로 보존한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# 법종구분(XML) → 우리 규정유형(reg_type) 매핑
REG_TYPE_MAP = {
    "법률": "법",
    "대통령령": "시행령",
    "총리령": "시행규칙",
    "부령": "시행규칙",
}


def txt(el, tag: str) -> str:
    """자식 태그의 텍스트를 안전하게 추출(없으면 빈 문자열)."""
    v = el.findtext(tag)
    return v.strip() if v else ""


def parse_basic(root: ET.Element) -> dict:
    """기본정보 → 법령 단위 메타데이터."""
    b = root.find("기본정보")
    if b is None:
        sys.exit("[오류] 기본정보 없음 — 올바른 법령 XML이 아닙니다.")
    law_type = txt(b, "법종구분")
    return {
        "law_name": txt(b, "법령명_한글"),
        "law_id": txt(b, "법령ID"),
        "reg_type": REG_TYPE_MAP.get(law_type, law_type),  # 매핑 없으면 원문 유지
        "law_type_raw": law_type,
        "effective_date": _fmt_date(txt(b, "시행일자")),
        "promulgation_no": txt(b, "공포번호"),
        "promulgation_date": _fmt_date(txt(b, "공포일자")),
        "ministry": txt(b, "소관부처"),
        "amend_type": txt(b, "제개정구분"),
    }


def _fmt_date(yyyymmdd: str) -> str:
    """'20250801' → '2025-08-01' (형식 불명이면 원문 유지)."""
    if re.fullmatch(r"\d{8}", yyyymmdd):
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd


def article_label(no: str, branch: str) -> str:
    """조번호+가지번호 → '제5조의2' 형태 라벨."""
    if branch and branch != "0":
        return f"제{no}조의{branch}"
    return f"제{no}조"


def parse_hang(hang_el: ET.Element) -> dict:
    """항 → {번호, 내용, 호[]}."""
    return {
        "no": txt(hang_el, "항번호"),
        "text": txt(hang_el, "항내용"),
        "ho": [
            {"no": txt(h, "호번호"), "text": txt(h, "호내용")}
            for h in hang_el.findall("호")
        ],
    }


def parse_articles(root: ET.Element) -> list[dict]:
    """조문단위들을 순회하며 장(章) 맥락을 부여한 조문 리스트를 만든다."""
    jomun = root.find("조문")
    if jomun is None:
        sys.exit("[오류] 조문 컨테이너 없음.")

    articles: list[dict] = []
    current_chapter = ""  # 현재 장(章) 제목 — 전문 헤더를 만나면 갱신

    for u in jomun.findall("조문단위"):
        kind = txt(u, "조문여부")  # '조문' | '전문'
        content = txt(u, "조문내용")

        if kind == "전문":
            # 장/절/관 헤더 — '제N장 ...' 형태면 현재 장으로 기억
            if re.match(r"제\d+장", content):
                current_chapter = content
            # 전문 헤더 자체는 조문이 아니므로 청크 대상에서 제외(맥락으로만 사용)
            continue

        no = txt(u, "조문번호")
        branch = txt(u, "조문가지번호")
        label = article_label(no, branch)

        articles.append({
            "article": label,                 # 제2조 / 제5조의2
            "title": txt(u, "조문제목"),       # 정의
            "chapter": current_chapter,        # 제1장 총칙
            "effective_date": _fmt_date(txt(u, "조문시행일자")),
            "head": content,                   # '제2조(정의)' (항이 있으면 헤더만)
            "hang": [parse_hang(h) for h in u.findall("항")],
            "ref_material": txt(u, "조문참고자료"),
        })

    return articles


def to_markdown(meta: dict, articles: list[dict]) -> str:
    """사람 검수용 Markdown(계층 헤더)."""
    lines = [
        f"# {meta['law_name']} (구조화)",
        "",
        f"> {meta['reg_type']} / 시행 {meta['effective_date']} / "
        f"공포 제{meta['promulgation_no']}호 / {meta['ministry']}",
        f"> 조문 {len(articles)}개",
        "",
    ]
    last_chapter = None
    for a in articles:
        if a["chapter"] and a["chapter"] != last_chapter:
            lines.append(f"\n## {a['chapter']}\n")
            last_chapter = a["chapter"]
        title = f" ({a['title']})" if a["title"] else ""
        lines.append(f"### {a['article']}{title}")
        # 항이 없으면 head가 전체 본문
        # (항내용/호내용에는 번호(①, 1.)가 이미 포함돼 있어 따로 붙이지 않는다)
        if not a["hang"]:
            lines.append(a["head"])
        else:
            for h in a["hang"]:
                lines.append(f"- {h['text']}")
                for ho in h["ho"]:
                    lines.append(f"  - {ho['text']}")
        lines.append("")
    return "\n".join(lines)


# ── 행정규칙(고시·훈령·예규) 분기 ──────────────────────────────
# 행정규칙 XML은 법령과 다름: root <AdmRulService>, <행정규칙기본정보>,
# 조문은 <조문내용>(평탄 텍스트, 항/호 inline). → 조문내용 1개 = 조 1개로 본다.

def parse_basic_admrul(root: ET.Element) -> dict:
    b = root.find("행정규칙기본정보")
    if b is None:
        sys.exit("[오류] 행정규칙기본정보 없음 — 올바른 행정규칙 XML이 아닙니다.")
    return {
        "law_name": txt(b, "행정규칙명"),
        "law_id": txt(b, "행정규칙ID"),
        "reg_type": txt(b, "행정규칙종류") or "고시",  # 고시/훈령/예규
        "law_type_raw": txt(b, "행정규칙종류"),
        "effective_date": _fmt_date(txt(b, "시행일자")),
        "promulgation_no": txt(b, "발령번호"),
        "promulgation_date": _fmt_date(txt(b, "발령일자")),
        "ministry": txt(b, "소관부처명"),
        "amend_type": "",
    }


def parse_articles_admrul(root: ET.Element) -> list[dict]:
    """<조문내용> 평탄 텍스트를 조 단위 조문으로 파싱(장 헤더 분리)."""
    articles: list[dict] = []
    current_chapter = ""
    for j in root.findall("조문내용"):
        text = (j.text or "").strip()
        if not text:
            continue
        first = text.split("\n", 1)[0].strip()
        art_m = re.match(r"^(제\d+조(?:의\d+)?)", first)
        chap_m = re.match(r"^(제\d+장)\s*(.*)$", first)
        if chap_m and not art_m:
            current_chapter = first  # 장 헤더
            continue
        if not art_m:
            continue  # 조 번호 없는 블록(서문 등)은 건너뜀
        title_m = re.match(r"^제\d+조(?:의\d+)?\s*\(([^)]*)\)", first)
        articles.append({
            "article": art_m.group(1),
            "title": title_m.group(1).strip() if title_m else "",
            "chapter": current_chapter,
            "effective_date": "",  # 행정규칙은 조별 시행일 없음 → meta 시행일 사용
            "head": text,          # 항/호가 inline → 본문 전체
            "hang": [],
            "ref_material": "",
        })
    return articles


def main() -> None:
    parser = argparse.ArgumentParser(description="법령/행정규칙 XML → 위계 트리 JSON + Markdown")
    parser.add_argument("xml", help="입력 XML (예: raw/의료기기법.xml)")
    parser.add_argument("--out-dir", default="processed", help="출력 폴더 (기본: processed)")
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.exists():
        sys.exit(f"[오류] 파일 없음: {xml_path}")

    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        sys.exit(f"[오류] XML 파싱 실패: {e}")

    # 법령(<법령>) vs 행정규칙(<AdmRulService>) 분기
    if root.tag == "AdmRulService" or root.find("행정규칙기본정보") is not None:
        meta = parse_basic_admrul(root)
        articles = parse_articles_admrul(root)
    else:
        meta = parse_basic(root)
        articles = parse_articles(root)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = meta["law_name"] or xml_path.stem

    json_path = out_dir / f"{stem}_structured.json"
    md_path = out_dir / f"{stem}_structured.md"

    json_path.write_text(
        json.dumps({"meta": meta, "articles": articles}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(to_markdown(meta, articles), encoding="utf-8")

    # 요약(검증용)
    n_hang = sum(len(a["hang"]) for a in articles)
    n_ho = sum(len(h["ho"]) for a in articles for h in a["hang"])
    chapters = sorted({a["chapter"] for a in articles if a["chapter"]})
    print(f"[완료] {json_path}")
    print(f"       {md_path}")
    print(f"  - 법령: {meta['law_name']} / {meta['reg_type']} / 시행 {meta['effective_date']}")
    print(f"  - 조문: {len(articles)}개 / 항: {n_hang}개 / 호: {n_ho}개")
    print(f"  - 장(章): {len(chapters)}개 → {', '.join(chapters[:6])}{' ...' if len(chapters) > 6 else ''}")
    print("\n다음 단계: chunk.py 로 조항 단위 contextual 청킹 + 메타데이터 태깅")


if __name__ == "__main__":
    main()
