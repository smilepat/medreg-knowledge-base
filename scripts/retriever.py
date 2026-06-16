"""
retriever.py — 공용 검색 모듈 (Supabase pgvector 하이브리드)

report.py / check.py 가 공통으로 쓴다. 의미검색(임베딩 코사인) + 조문번호 직격 부스트 +
메타데이터(현행) 필터. 반환 형식은 로컬 청크(samples/*.json)와 동일한 dict 구조라
기존 도구가 그대로 소비할 수 있다(+ sim 점수 추가).

사전: .env 의 SUPABASE_DB_URL + GEMINI_API_KEY, embed.py 로 medreg.chunks 적재됨.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

try:
    import psycopg2
    from google import genai
    from google.genai import types
except ImportError as e:
    sys.exit(f"[오류] 의존성 미설치({e}) → python -m pip install -r requirements.txt")

DIM = 1536
MODEL = "gemini-embedding-001"
RE_ARTICLE = re.compile(r"제\d+조(?:의\d+)?")

_env = None
_client = None
_conn = None


def _load_env() -> dict:
    global _env
    if _env is None:
        _env = {}
        p = Path(__file__).resolve().parent.parent / ".env"
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, _, v = s.partition("=")
                _env[k.strip()] = v.strip()
    return _env


def _conn_():
    global _conn
    if _conn is None or _conn.closed:
        dsn = _load_env().get("SUPABASE_DB_URL")
        if not dsn:
            sys.exit("[오류] .env SUPABASE_DB_URL 없음")
        _conn = psycopg2.connect(dsn, connect_timeout=15)
    return _conn


def _client_():
    global _client
    if _client is None:
        _client = genai.Client(api_key=_load_env()["GEMINI_API_KEY"])
    return _client


def embed_query(q: str) -> str:
    """질의 임베딩(정규화) → pgvector 리터럴 문자열."""
    r = _client_().models.embed_content(
        model=MODEL, contents=q,
        config=types.EmbedContentConfig(output_dimensionality=DIM, task_type="RETRIEVAL_QUERY"),
    )
    v = r.embeddings[0].values
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return "[" + ",".join(f"{x / n:.6f}" for x in v) + "]"


def _row_to_chunk(row, sim: float) -> dict:
    """DB 행 → 로컬 청크와 동일 구조 dict (+ sim)."""
    (cid, law, reg, art, chap, eff, cur, st, url, hdr, text, xrefs, terms) = row
    return {
        "chunk_id": cid,
        "text": text,
        "context_header": hdr,
        "sim": sim,
        "metadata": {
            "law_name": law, "reg_type": reg, "article": art, "chapter": chap,
            "effective_date": eff.isoformat() if eff else "",
            "is_current": cur, "status": st, "source_url": url,
            "cross_refs": xrefs or [], "defined_terms": terms or [],
        },
    }


_COLS = ("chunk_id, law_name, reg_type, article, chapter, effective_date, is_current, "
         "status, source_url, context_header, text, cross_refs, defined_terms")


def hybrid_search(query: str, top_k: int = 5, current_only: bool = False) -> list[dict]:
    """의미검색 + 조문 직격 부스트. 반환: 청크 dict 리스트(sim 내림차순)."""
    qvec = embed_query(query)
    q_articles = RE_ARTICLE.findall(query)
    where = "where is_current" if current_only else ""
    # 점수 = 코사인유사도 + (질의에 든 조번호와 일치 시 0.5 부스트)
    sql = f"""
        select {_COLS}, 1 - (embedding <=> %s::vector) as sim
        from medreg.chunks {where}
        order by (1 - (embedding <=> %s::vector))
                 + (case when article = any(%s) then 0.5 else 0 end) desc
        limit %s
    """
    cur = _conn_().cursor()
    cur.execute(sql, (qvec, qvec, q_articles, top_k))
    rows = cur.fetchall()
    return [_row_to_chunk(r[:-1], float(r[-1])) for r in rows]


def find_article(article: str, law: str | None = None) -> dict | None:
    """(법령, 조) 로 단일 청크 조회(인용 검증용). 임베딩 불필요."""
    sql = f"select {_COLS}, 0 from medreg.chunks where article = %s"
    params = [article]
    if law:
        sql += " and law_name = %s"
        params.append(law)
    sql += " limit 1"
    cur = _conn_().cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    return _row_to_chunk(row[:-1], 0.0) if row else None


def all_law_names() -> list[str]:
    cur = _conn_().cursor()
    cur.execute("select distinct law_name from medreg.chunks")
    return [r[0] for r in cur.fetchall()]
