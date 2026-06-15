"""
extract.py — 파이프라인 1단계: 원문(PDF) → 텍스트 + 표 추출

목적:
  의료기기 규정 PDF에서 본문 텍스트와 '표'를 추출하되, 표 구조를 Markdown 표로
  보존한다. (일반 텍스트 추출은 표를 줄글로 뭉개므로, 표는 따로 떠서 보존한다.)

사용법:
  python scripts/extract.py raw/<파일>.pdf
  → processed/<파일>_raw.md 생성 + 추출 요약 출력

설계 메모:
  - PoC 1번 대상은 의료기기법(본법) — 표가 적어 배관(파이프라인) 검증용으로 적합.
  - HWP(한글) 파일은 별도 변환 경로 필요(이 스크립트는 PDF 전용). docs/extraction-tools.md 참조.
  - 표와 본문의 '읽기 순서' 정밀 결합은 다음 단계(structure.py)에서 다룬다.
    여기서는 페이지별로 본문 → 표 순으로 보존하는 것을 목표로 한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import pdfplumber  # PDF 텍스트·표 추출 (표 구조 보존에 강함)
except ImportError:
    sys.exit("[오류] pdfplumber 미설치 → 실행: python -m pip install pdfplumber")


def table_to_markdown(table: list[list]) -> str:
    """추출한 표(2차원 리스트)를 Markdown 표 문자열로 변환한다.

    - 첫 행을 헤더로 사용한다.
    - None 셀은 빈 칸으로, 셀 안 줄바꿈은 공백으로 정리한다.
    - '|'는 Markdown 표 구분자와 충돌하므로 escape 처리한다.
    """
    if not table or not table[0]:
        return ""

    def clean(cell) -> str:
        # 셀 정제: None→'', 줄바꿈 제거, 파이프 escape
        text = "" if cell is None else str(cell)
        return text.replace("\n", " ").replace("|", "\\|").strip()

    header = table[0]
    col_count = len(header)

    lines = []
    lines.append("| " + " | ".join(clean(c) for c in header) + " |")
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in table[1:]:
        # 열 개수가 헤더와 다를 수 있어 맞춰준다(부족분 채움/초과분 절단).
        cells = list(row) + [None] * (col_count - len(row))
        lines.append("| " + " | ".join(clean(c) for c in cells[:col_count]) + " |")

    return "\n".join(lines)


def extract_pdf(pdf_path: Path) -> tuple[str, dict]:
    """PDF에서 페이지별 본문 텍스트 + 표(Markdown)를 추출한다.

    반환: (마크다운 전문, 통계 딕셔너리)
    """
    md_parts: list[str] = []
    stats = {"pages": 0, "tables": 0, "empty_pages": 0}

    with pdfplumber.open(pdf_path) as pdf:
        stats["pages"] = len(pdf.pages)

        for page_no, page in enumerate(pdf.pages, start=1):
            md_parts.append(f"\n\n<!-- ===== p.{page_no} ===== -->\n")

            # 1) 본문 텍스트
            text = page.extract_text() or ""
            if text.strip():
                md_parts.append(text.strip())
            else:
                stats["empty_pages"] += 1
                # 본문이 비면 스캔본(이미지 PDF)일 가능성 → OCR 필요 신호
                md_parts.append("> ⚠️ [본문 텍스트 없음 — 스캔본(이미지 PDF)일 수 있음, OCR 필요]")

            # 2) 표 (있으면 Markdown으로 보존)
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables, start=1):
                md = table_to_markdown(table)
                if md:
                    stats["tables"] += 1
                    md_parts.append(f"\n**[표 p.{page_no}-{t_idx}]**\n\n{md}")

    return "\n".join(md_parts), stats


def main() -> None:
    parser = argparse.ArgumentParser(description="규정 PDF → 텍스트+표 추출 (Markdown)")
    parser.add_argument("pdf", help="입력 PDF 경로 (예: raw/의료기기법.pdf)")
    parser.add_argument(
        "-o", "--out", help="출력 경로 (기본: processed/<파일명>_raw.md)"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f"[오류] 파일 없음: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        sys.exit(
            f"[오류] PDF만 지원합니다(입력: {pdf_path.suffix}). "
            "HWP는 별도 변환 필요 — docs/extraction-tools.md 참조."
        )

    # 출력 경로 결정
    out_path = (
        Path(args.out)
        if args.out
        else Path("processed") / f"{pdf_path.stem}_raw.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        markdown, stats = extract_pdf(pdf_path)
    except Exception as e:  # 추출 실패는 파일 손상/암호화 등 다양 → 원인 노출
        sys.exit(f"[오류] 추출 실패: {e}")

    header = (
        f"# 추출 결과: {pdf_path.name}\n\n"
        f"> 원문: `{pdf_path}` / 페이지 {stats['pages']} / "
        f"표 {stats['tables']}개 / 빈 페이지 {stats['empty_pages']}개\n"
        f"> ⚠️ 이 파일은 '추출 직후' 원시본입니다. 정제·구조화는 다음 단계.\n"
    )
    out_path.write_text(header + markdown, encoding="utf-8")

    # 추출 요약(검증용)
    print(f"[완료] {out_path}")
    print(f"  - 페이지: {stats['pages']}")
    print(f"  - 표: {stats['tables']}개  (표 보존 여부를 출력 파일에서 직접 확인)")
    print(f"  - 빈 페이지: {stats['empty_pages']}개  (>0 이면 스캔본 의심 → OCR)")


if __name__ == "__main__":
    main()
