"""
setup_check.py — 다른 PC에서 클론 후 '작업 가능 상태'인지 점검한다.

확인 항목(값은 출력하지 않음 — 보안):
  1) .env 키 존재(LAW_OC / SUPABASE_DB_URL|PASSWORD / GEMINI_API_KEY)
  2) Supabase 연결 + 지식베이스(medreg.chunks) 적재 현황
  3) Gemini 임베딩 호출 가능 여부
  4) 이 PC의 공인 IP (fetch_law 사용 시 open.law.go.kr 에 등록 필요)

사용법: python scripts/setup_check.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

OK, NO, WARN = "✅", "❌", "⚠️"


def load_env() -> dict:
    env = {}
    p = Path(__file__).resolve().parent.parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, _, v = s.partition("=")
                env[k.strip()] = v.strip()
    return env


def main() -> None:
    print("=== medreg 셋업 점검 ===")
    env = load_env()

    # 1) .env 키
    print("\n[1] .env 키")
    law = bool(env.get("LAW_OC"))
    supa = bool(env.get("SUPABASE_DB_URL") or env.get("SUPABASE_DB_PASSWORD"))
    gem = bool(env.get("GEMINI_API_KEY"))
    print(f"  {OK if law else WARN} LAW_OC (법령 수집용, fetch_law)")
    print(f"  {OK if supa else NO} SUPABASE_DB_URL/PASSWORD (검색·점검 필수)")
    print(f"  {OK if gem else NO} GEMINI_API_KEY (임베딩·LLM 판정 필수)")

    # 2) Supabase + KB
    print("\n[2] Supabase 지식베이스")
    dsn = env.get("SUPABASE_DB_URL", "")
    if dsn.startswith("postgresql://"):
        try:
            import psycopg2
            c = psycopg2.connect(dsn, connect_timeout=15)
            cur = c.cursor()
            cur.execute("select count(*), count(distinct law_name) from medreg.chunks")
            n, nl = cur.fetchone()
            print(f"  {OK} 연결 성공 — medreg.chunks {n}청크 / {nl}법령")
            if n == 0:
                print(f"     {WARN} 비어있음 → python scripts/embed.py --recreate 로 적재")
            c.close()
        except Exception as e:
            print(f"  {NO} 연결/조회 실패: {str(e)[:70]}")
    else:
        print(f"  {NO} SUPABASE_DB_URL(postgresql://...) 미설정")

    # 3) Gemini
    print("\n[3] Gemini")
    if gem:
        try:
            from google import genai
            from google.genai import types
            cli = genai.Client(api_key=env["GEMINI_API_KEY"])
            r = cli.models.embed_content(
                model="gemini-embedding-001", contents="테스트",
                config=types.EmbedContentConfig(output_dimensionality=1536, task_type="RETRIEVAL_QUERY"),
            )
            print(f"  {OK} 임베딩 호출 성공 ({len(r.embeddings[0].values)}차원)")
        except Exception as e:
            print(f"  {NO} 호출 실패: {str(e)[:70]}")
    else:
        print(f"  {NO} GEMINI_API_KEY 없음")

    # 4) 공인 IP (fetch_law 사용 시 등록 필요)
    print("\n[4] 이 PC 공인 IP (fetch_law로 새 법령 수집 시 필요)")
    try:
        ip = urllib.request.urlopen("https://api.ipify.org", timeout=10).read().decode()
        print(f"  ℹ️ {ip} — 새 법령을 받으려면 open.law.go.kr 에서 OC(smilepat)에 이 IP 등록")
        print("     (검색·점검·입찰매칭은 IP 등록 없이 Supabase로 바로 동작)")
    except Exception:
        print(f"  {WARN} IP 확인 실패(네트워크)")

    print("\n점검 완료. ❌가 없으면 검색·점검·입찰매칭 바로 사용 가능.")


if __name__ == "__main__":
    main()
