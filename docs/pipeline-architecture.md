# 파이프라인 아키텍처

> 데이터 흐름과 각 스크립트의 책임 범위. 스크립트는 `/scripts`에 한 개씩 추가.

---

## 전체 데이터 흐름

```
raw/*.{pdf,hwp}
   │  extract.py        ┌─ 표 보존 (Markdown 표)
   ▼                    └─ 스캔본은 OCR
processed/*_raw.md
   │  clean.py          ┌─ 머리말/꼬리말/페이지번호 제거
   ▼
processed/*_clean.md
   │  structure.py      ┌─ 법령 위계(조/항/호/목) 파싱
   ▼                    └─ Markdown(계층) + JSON 메타데이터
processed/*_structured.json
   │  chunk.py          ┌─ 조항 1개 = 청크 1개
   ▼                    └─ contextual (상위 맥락 포함) + 메타 6필드
samples/*_processed.json   ← ★ PoC 핵심 검증물
   │  embed.py          ┌─ 임베딩 생성
   ▼                    └─ Supabase pgvector 적재
[ pgvector: medreg.chunks ]
   │  search.py         ┌─ 하이브리드(의미+키워드) + 메타 필터
   ▼
검색 결과 (청크 + 출처)
   │  report.py         ┌─ 출처 인용 초안 (환각 방지)
   ▼
보고서 초안 → HITL 검토
```

---

## 스크립트별 책임

| 스크립트 | 입력 | 출력 | 핵심 책임 |
|----------|------|------|----------|
| `extract.py` | raw PDF/HWP | `*_raw.md` | 텍스트+표 추출, **표 보존**, OCR |
| `clean.py` | `*_raw.md` | `*_clean.md` | 노이즈 제거 |
| `structure.py` | `*_clean.md` | `*_structured.json` | 위계 파싱, 이중 출력 |
| `chunk.py` | `*_structured.json` | `*_processed.json` | 조항 청킹 + 메타 태깅 |
| `embed.py` | `*_processed.json` | pgvector 적재 | 임베딩 + 저장 |
| `search.py` | 질문 | 청크+출처 | 하이브리드 검색 + 필터 |
| `report.py` | 검색결과 | 보고서 초안 | 출처 인용, 환각 방지 |

---

## Phase 2 검색 상세 (하이브리드)

```
질문
 ├─ (1) 메타데이터 필터:  is_current=true AND reg_type IN (...) AND applies_to @> (...)
 ├─ (2) 의미 검색:        embedding <=> query_embedding   (벡터 유사도)
 ├─ (3) 키워드 검색:      to_tsvector @@ to_tsquery('제15조', 'GMP')
 └─ (4) 결합/재정렬(RRF 등) → 상위 K개 청크
```

법령은 정확한 조항 번호·용어가 중요 → **키워드 매칭 필수** (의미 검색만으로 부족).

## Phase 3 활용 상세

### 보고서 (첫 타깃)
```
질문 → search.py → 상위 청크 → report.py
   프롬프트 규칙: "검색된 청크에 근거가 있을 때만 단정.
   없으면 '확인 불가'. 모든 인용에 [법령명 조항 (시행일)] 표기."
```

### 입찰 매칭 (후순위)
```
공고문 → requirement matrix(항목별 요구사항) → 각 항목별 search.py 대조
       → 충족 / 미충족 / 확인필요 + 근거 인용 → HITL
```

---

## 안전장치 구현 위치

| 안전장치 | 구현 지점 |
|----------|----------|
| 환각 방지 | `report.py` 프롬프트 + 인용 강제 / 검색 0건 시 "확인 불가" |
| 버전 관리 | `metadata.effective_date` + `is_current` / 검색 필터 기본값 `is_current=true` |
| HITL | 최종 출력에 "⚠️ 담당자 인용 확인 필요" 워터마크 + 출처 링크 노출 |
