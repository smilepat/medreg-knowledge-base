# 메타데이터 스키마 (청크 단위)

> 모든 청크는 아래 필드를 갖는다. 이 라벨이 검색 정확도(메타데이터 필터링)와
> 인용 신뢰도(환각 방지)의 핵심이다.

---

## 1. 청크 JSON 구조 (제안)

```json
{
  "chunk_id": "의료기기법_제15조_제2항",
  "text": "○○법 제15조(제조업의 허가 등) 제2항 — [조항 본문 ...]",
  "context_header": "의료기기법 > 제3장 제조·수입 > 제15조 제조업의 허가 등",

  "metadata": {
    "law_name": "의료기기법",
    "reg_type": "법",
    "article": "제15조",
    "clause": "제2항",
    "item": null,
    "subitem": null,
    "effective_date": "2025-01-01",
    "is_current": true,
    "applies_to": ["2등급 의료기기", "제조업"],
    "source_page": 12,
    "source_url": "https://www.law.go.kr/...",
    "cross_refs": ["의료기기법 제20조", "의료기기법 시행규칙 제9조"],
    "defined_terms": ["제조업", "의료기기"]
  }
}
```

## 2. 필드 정의

| 필드 | 필수 | 타입 | 설명 |
|------|:---:|------|------|
| `chunk_id` | ✅ | string | 고유 ID. `법령명_조_항` 규칙 |
| `text` | ✅ | string | 청크 본문 (contextual — 상위 맥락 포함) |
| `context_header` | ✅ | string | 사람이 읽는 계층 경로 (법령>장>조 제목) |
| `law_name` | ✅ | string | 법령명 |
| `reg_type` | ✅ | enum | `법` / `시행령` / `시행규칙` / `고시` / `공고` / `입찰규정` |
| `article` | ✅ | string | 조 (제15조) |
| `clause` | ⬜ | string | 항 (제2항) |
| `item` | ⬜ | string | 호 (제1호) |
| `subitem` | ⬜ | string | 목 (가목) |
| `effective_date` | ✅ | date | 시행일 (YYYY-MM-DD) |
| `is_current` | ✅ | bool | 현행 여부 (버전 관리) |
| `applies_to` | ⬜ | string[] | 적용대상 (품목·등급·업종) |
| `source_page` | ✅ | int | 원문 페이지 |
| `source_url` | ⬜ | string | 원문 링크 |
| `cross_refs` | ⬜ | string[] | 교차 참조 조항 |
| `defined_terms` | ⬜ | string[] | 이 청크가 정의/사용하는 용어 |

## 3. 별도 테이블

### 정의어 사전 (definitions)
| 컬럼 | 설명 |
|------|------|
| `term` | 용어 (예: "제조업") |
| `definition` | 정의 본문 |
| `law_name` / `article` | 정의 출처 조항 |

### 교차참조 그래프 (cross_references)
| 컬럼 | 설명 |
|------|------|
| `from_chunk` | 참조하는 청크 |
| `to_chunk` | 참조되는 청크 |
| `relation` | 관계 유형 (따른다 / 준용 / 예외 등) |

---

## 4. pgvector 테이블 (제안)

```sql
-- 청크 + 임베딩 (Supabase, 별 스키마 medreg)
create table medreg.chunks (
  chunk_id      text primary key,
  text          text not null,
  context_header text,
  embedding     vector(1536),        -- 임베딩 차원은 모델 확정 후 조정
  law_name      text,
  reg_type      text,
  article       text,
  clause        text,
  effective_date date,
  is_current    boolean default true,
  applies_to    text[],
  source_page   int,
  source_url    text,
  cross_refs    text[],
  metadata      jsonb                 -- 나머지 필드 유연 저장
);

-- 하이브리드 검색용 인덱스
create index on medreg.chunks using ivfflat (embedding vector_cosine_ops);
create index on medreg.chunks using gin (to_tsvector('simple', text));  -- 키워드
create index on medreg.chunks (is_current, reg_type);                    -- 메타 필터
```

> ⚠️ 임베딩 차원(`vector(1536)`)은 임베딩 모델 확정 후 조정. 한국어 법령 특성 고려해 선택.
