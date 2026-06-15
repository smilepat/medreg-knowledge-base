"""
fetch_law.py — 국가법령정보 Open API(DRF)로 법령 전문(全文)을 받아온다.

왜 이 방식인가:
  law.go.kr 웹페이지는 본문을 JS로 가려 스크립트 수집이 막힌다. 공식 Open API는
  type=XML 로 받으면 '법령 위계(조/항/호)'가 이미 구조화된 형태로 와서, 우리
  파이프라인(법령 위계 보존)에 가장 깨끗하게 맞는다. (PDF 추출은 API에 없는
  외부 문서용 — docs/pipeline-architecture.md 참조.)

사전 준비(1회):
  1) https://open.law.go.kr 에서 OPEN API 활용신청 → OC 키 발급 + 사용 PC의 IP 등록
  2) 발급받은 OC 키를 환경변수로 두거나(--oc 로 직접 전달):
       (PowerShell)  $env:LAW_OC = "발급키"
       (bash)        export LAW_OC=발급키

사용법:
  python scripts/fetch_law.py "의료기기법"
  python scripts/fetch_law.py "의료기기법" --oc 발급키 --out-dir raw

산출물:
  raw/<법령명>.xml   (구조화 원문 — structure.py 입력)
  + 콘솔에 법령명/시행일/공포번호/조문 수 요약
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DRF = "https://www.law.go.kr/DRF"
UA = "Mozilla/5.0 (medreg-knowledge-base fetch_law.py)"


def _load_dotenv() -> None:
    """프로젝트 루트의 .env를 읽어 환경변수에 주입한다(외부 라이브러리 없이).

    이미 설정된 환경변수는 덮어쓰지 않는다.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def _get(url: str, timeout: int = 40) -> bytes:
    """URL을 GET 하여 바이트를 반환한다(에러 시 원인 노출)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        sys.exit(f"[오류] 요청 실패: {url}\n  → {e}")


def _check_auth(raw: bytes) -> None:
    """OC 키 미등록 등 인증 실패 응답을 조기에 잡아낸다."""
    head = raw[:400].decode("utf-8", "replace")
    if "사용자 정보 검증에 실패" in head or "등록되지 않은" in head:
        sys.exit(
            "[오류] Open API 인증 실패 — OC 키 또는 IP 등록을 확인하세요.\n"
            "  https://open.law.go.kr 에서 OC 발급 + 현재 PC IP 등록 필요."
        )


def search_law(oc: str, query: str) -> tuple[str, str]:
    """법령명으로 검색해 (법령일련번호 MST, 법령명) 을 반환한다.

    정확히 일치하는 현행 법령을 우선 선택한다.
    """
    q = urllib.parse.quote(query)
    url = f"{DRF}/lawSearch.do?OC={oc}&target=law&type=XML&display=20&query={q}"
    raw = _get(url)
    _check_auth(raw)

    root = ET.fromstring(raw)
    laws = root.findall("law")
    if not laws:
        sys.exit(f"[오류] 검색 결과 없음: {query}")

    # 정확히 일치하는 법령명 우선, 없으면 첫 결과
    def name_of(el):
        n = el.findtext("법령명한글") or ""
        return n.strip()

    exact = [el for el in laws if name_of(el) == query]
    chosen = exact[0] if exact else laws[0]

    mst = (chosen.findtext("법령일련번호") or "").strip()
    name = name_of(chosen)
    if not mst:
        sys.exit("[오류] 법령일련번호(MST)를 찾지 못했습니다.")
    return mst, name


def fetch_body(oc: str, mst: str) -> bytes:
    """법령 본문(구조화 XML)을 받아온다."""
    url = f"{DRF}/lawService.do?OC={oc}&target=law&MST={mst}&type=XML"
    raw = _get(url)
    _check_auth(raw)
    return raw


def summarize(raw: bytes) -> dict:
    """본문 XML에서 핵심 메타와 조문 수를 뽑아 요약한다."""
    info = {"법령명": "?", "시행일자": "?", "공포번호": "?", "조문수": 0}
    try:
        root = ET.fromstring(raw)
        basic = root.find("기본정보")
        if basic is not None:
            info["법령명"] = (basic.findtext("법령명_한글") or basic.findtext("법령명한글") or "?").strip()
            info["시행일자"] = (basic.findtext("시행일자") or "?").strip()
            info["공포번호"] = (basic.findtext("공포번호") or "?").strip()
        # 조문단위 개수
        info["조문수"] = len(root.findall(".//조문단위"))
    except ET.ParseError:
        pass
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description="국가법령정보 Open API로 법령 전문 수집")
    parser.add_argument("query", help="법령명 (예: 의료기기법)")
    parser.add_argument("--oc", default=None, help="OC 키 (기본: .env 또는 환경변수 LAW_OC)")
    parser.add_argument("--out-dir", default="raw", help="저장 폴더 (기본: raw)")
    args = parser.parse_args()

    # .env 로드 후 OC 결정 (인자 > 환경변수/.env)
    _load_dotenv()
    if not args.oc:
        args.oc = os.environ.get("LAW_OC")

    if not args.oc:
        sys.exit(
            "[오류] OC 키 없음 — --oc 로 전달하거나 환경변수 LAW_OC 설정.\n"
            "  발급: https://open.law.go.kr (OPEN API 활용신청)"
        )

    print(f"[1/3] 검색: {args.query}")
    mst, name = search_law(args.oc, args.query)
    print(f"      → 매칭: {name} (MST={mst})")

    print("[2/3] 본문 수신 (구조화 XML)")
    raw = fetch_body(args.oc, mst)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.xml"
    out_path.write_bytes(raw)

    print("[3/3] 저장 완료")
    info = summarize(raw)
    print(f"      파일: {out_path}")
    print(f"      법령명: {info['법령명']}")
    print(f"      시행일자: {info['시행일자']} / 공포번호: {info['공포번호']}")
    print(f"      조문 수: {info['조문수']}개")
    print("\n다음 단계: structure.py 로 조/항/호 위계 파싱 → 청킹")


if __name__ == "__main__":
    main()
