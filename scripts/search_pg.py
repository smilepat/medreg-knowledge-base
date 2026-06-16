"""
search_pg.py — 의미검색(임베딩) 기반 검색: Supabase pgvector

로컬 search.py(키워드+글자유사도)의 한계(약한 매칭 오탐)를 의미검색으로 보완한다.
질의를 Gemini 임베딩(RETRIEVAL_QUERY)으로 벡터화 → pgvector 코사인 유사도 상위 K.
코사인 유사도(0~1)는 의미적 관련도라, '관련 없음'을 임계값으로 솔직히 가려낼 수 있다.

사전: .env 의 SUPABASE_DB_URL + GEMINI_API_KEY, embed.py로 medreg.chunks 적재됨.

사용법:
  python scripts/search_pg.py "의료기기 등급분류 기준"
  python scripts/search_pg.py "임플란트 건강보험 수가" --top 3 --current-only
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import psycopg2
from google import genai
from google.genai import types

DIM = 1536
MODEL = "gemini-embedding-001"


def load_env() -> dict:
    env = {}
    p = Path(__file__).resolve().parent.parent / ".env"
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            env[k.strip()] = v.strip()
    return env


def embed_query(client, q: str) -> list[float]:
    r = client.models.embed_content(
        model=MODEL, contents=q,
        config=types.EmbedContentConfig(output_dimensionality=DIM, task_type="RETRIEVAL_QUERY"),
    )
    v = r.embeddings[0].values
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def main() -> None:
    ap = argparse.ArgumentParser(description="의미검색(pgvector) — 코사인 유사도")
    ap.add_argument("query")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--current-only", action="store_true")
    args = ap.parse_args()

    env = load_env()
    client = genai.Client(api_key=env["GEMINI_API_KEY"])
    qvec = "[" + ",".join(f"{x:.6f}" for x in embed_query(client, args.query)) + "]"

    where = "where is_current" if args.current_only else ""
    sql = f"""
        select law_name, article, context_header, effective_date, source_url,
               1 - (embedding <=> %s::vector) as sim
        from medreg.chunks
        {where}
        order by embedding <=> %s::vector
        limit %s
    """
    conn = psycopg2.connect(env["SUPABASE_DB_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute(sql, (qvec, qvec, args.top))
    rows = cur.fetchall()
    conn.close()

    print(f"질의: {args.query!r}  (의미검색, 코사인 유사도)\n")
    for i, (law, art, hdr, eff, url, sim) in enumerate(rows, 1):
        flag = "  ← 관련 낮음(참고)" if sim < 0.55 else ""
        print(f"#{i} [{sim:.3f}] {hdr}{flag}")
        print(f"     시행 {eff} / {url}\n")
    if rows and rows[0][5] < 0.55:
        print("⚠️ 최상위도 유사도 낮음 → 보유 규정과 의미적으로 거리가 멂(범위 밖 가능).")


if __name__ == "__main__":
    main()
