"""
embed.py — 파이프라인 4단계(인프라판): 청크 → 임베딩 → Supabase pgvector 적재

목적:
  samples/*_processed.json 청크를 Gemini 임베딩으로 벡터화해 Supabase(pgvector)에 적재한다.
  이후 search.py가 '의미검색(임베딩) + 키워드'를 합쳐 하이브리드로 동작 → check.py 오탐 감소.

사전:
  .env 에 SUPABASE_DB_URL(접속문자열) + GEMINI_API_KEY 필요. (둘 다 git 제외)

스키마: medreg.chunks (vector(1536), hnsw 코사인 인덱스 + 키워드 GIN + 메타 인덱스)

사용법:
  python scripts/embed.py                 # 적재(있으면 upsert)
  python scripts/embed.py --recreate      # 테이블 재생성 후 적재
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    sys.exit("[오류] psycopg2 미설치 → python -m pip install psycopg2-binary")
try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("[오류] google-genai 미설치 → python -m pip install google-genai")

DIM = 1536
MODEL = "gemini-embedding-001"
BATCH = 50


def load_env() -> dict:
    """.env 를 읽어 dict 로 반환(외부 라이브러리 없이)."""
    env = {}
    p = Path(__file__).resolve().parent.parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, _, v = s.partition("=")
                env[k.strip()] = v.strip()
    return env


def load_chunks(samples_dir: Path) -> list[dict]:
    files = sorted(samples_dir.glob("*_processed.json"))
    if not files:
        sys.exit(f"[오류] 청크 없음: {samples_dir}/*_processed.json")
    chunks = []
    for f in files:
        chunks.extend(json.loads(f.read_text(encoding="utf-8")).get("chunks", []))
    return chunks


def embed_texts(client, texts: list[str]) -> list[list[float]]:
    """문서용 임베딩 생성(차원 truncation 후 단위벡터 정규화)."""
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        r = client.models.embed_content(
            model=MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                output_dimensionality=DIM, task_type="RETRIEVAL_DOCUMENT"
            ),
        )
        for e in r.embeddings:
            v = e.values
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])  # 코사인용 단위벡터
        print(f"  임베딩 {min(i + BATCH, len(texts))}/{len(texts)}")
    return out


def ensure_schema(cur, recreate: bool) -> None:
    cur.execute("create extension if not exists vector")
    cur.execute("create schema if not exists medreg")
    if recreate:
        cur.execute("drop table if exists medreg.chunks")
    cur.execute(f"""
        create table if not exists medreg.chunks (
            chunk_id        text primary key,
            law_name        text,
            reg_type        text,
            article         text,
            chapter         text,
            effective_date  date,
            is_current      boolean,
            status          text,
            source_url      text,
            context_header  text,
            text            text,
            cross_refs      text[],
            defined_terms   text[],
            embedding       vector({DIM})
        )
    """)
    cur.execute("create index if not exists chunks_embedding_idx on medreg.chunks "
                "using hnsw (embedding vector_cosine_ops)")
    cur.execute("create index if not exists chunks_text_idx on medreg.chunks "
                "using gin (to_tsvector('simple', text))")
    cur.execute("create index if not exists chunks_meta_idx on medreg.chunks "
                "(is_current, reg_type)")


def to_vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def nz(s):
    return s if s else None


def main() -> None:
    parser = argparse.ArgumentParser(description="청크 → Gemini 임베딩 → Supabase pgvector")
    parser.add_argument("--samples-dir", default="samples")
    parser.add_argument("--recreate", action="store_true", help="테이블 재생성 후 적재")
    args = parser.parse_args()

    env = load_env()
    dsn = env.get("SUPABASE_DB_URL")
    key = env.get("GEMINI_API_KEY")
    if not dsn or not dsn.startswith("postgresql://"):
        sys.exit("[오류] .env의 SUPABASE_DB_URL(postgresql://...) 없음")
    if not key:
        sys.exit("[오류] .env의 GEMINI_API_KEY 없음")

    chunks = load_chunks(Path(args.samples_dir))
    print(f"[1/3] 청크 {len(chunks)}개 로드")

    client = genai.Client(api_key=key)
    print(f"[2/3] 임베딩 생성 ({MODEL}, {DIM}차원)")
    vecs = embed_texts(client, [c["text"] for c in chunks])

    print("[3/3] Supabase 적재")
    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        ensure_schema(cur, args.recreate)
        rows = []
        for c, v in zip(chunks, vecs):
            m = c["metadata"]
            rows.append((
                c["chunk_id"], m["law_name"], m["reg_type"], m["article"], nz(m.get("chapter")),
                nz(m.get("effective_date")), m.get("is_current"), m.get("status"),
                m.get("source_url"), c["context_header"], c["text"],
                m.get("cross_refs") or [], m.get("defined_terms") or [], to_vec(v),
            ))
        execute_values(cur, """
            insert into medreg.chunks
              (chunk_id, law_name, reg_type, article, chapter, effective_date, is_current,
               status, source_url, context_header, text, cross_refs, defined_terms, embedding)
            values %s
            on conflict (chunk_id) do update set
              law_name=excluded.law_name, reg_type=excluded.reg_type, article=excluded.article,
              chapter=excluded.chapter, effective_date=excluded.effective_date,
              is_current=excluded.is_current, status=excluded.status, source_url=excluded.source_url,
              context_header=excluded.context_header, text=excluded.text,
              cross_refs=excluded.cross_refs, defined_terms=excluded.defined_terms,
              embedding=excluded.embedding
        """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)")
        conn.commit()
        cur.execute("select count(*), count(distinct law_name) from medreg.chunks")
        n, nl = cur.fetchone()
        print(f"[완료] medreg.chunks 적재: {n}행 / 법령 {nl}종")
    except Exception as e:
        conn.rollback()
        sys.exit(f"[오류] 적재 실패(롤백): {e}")
    finally:
        conn.close()

    print("\n다음: search.py에 의미검색(쿼리 임베딩) 합산 → 하이브리드 완성")


if __name__ == "__main__":
    main()
