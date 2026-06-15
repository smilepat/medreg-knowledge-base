# medreg-knowledge-base

> 의료기기 정부규정 → **LLM 친화 구조화 지식베이스** → 보고서·입찰제안서 규정 준수 자동 지원

수백 페이지의 의료기기 정부규정(법·시행령·시행규칙·식약처 고시 + 조달/입찰 규정)을
**한 번 잘 가공해 재사용 가능한 지식 자산**으로 바꾸고, RAG(검색증강생성) 기반으로
보고서·입찰제안서 작성 시 규정 준수를 지원하는 시스템입니다.

> 핵심 철학: "PDF를 LLM에 통째로 던지기"가 아니라, **조항 하나하나를 색인 카드(index card)로
> 잘라 라벨을 붙여 캐비닛에 정리**하는 작업. 가공(Phase 1)에 가치의 90%가 있습니다.

---

## 현재 확정 사항 (2026-06-15)

| 항목 | 결정 |
|------|------|
| 첫 타깃 | **보고서용 Q&A 검색** (입찰 컴플라이언스 매칭은 다음 단계) |
| 벡터 DB | **Supabase pgvector 재사용** (ai-english-platform과 동일 인스턴스, 별 스키마) |
| 공개 범위 | Private |
| 현재 단계 | **Phase 1 PoC** — 문서 1건으로 파이프라인 전체(추출→구조화→검색→인용) 끝까지 통과 |

---

## 4단계 파이프라인

```
Phase 0  범위 정의      어떤 규정 / 무슨 산출물          → docs/roadmap.md
Phase 1  원문 → 구조화  ★가치의 90% (조/항/호/목 보존)   → docs/pipeline-architecture.md
Phase 2  저장 + 검색    pgvector + 하이브리드 검색       → docs/pipeline-architecture.md
Phase 3  활용           보고서 인용 / 입찰 매칭          → docs/pipeline-architecture.md
```

**문제 정의부터 가공까지 한눈에:** [docs/overview.md](docs/overview.md) (① 문제 정의 → ② 기존 데이터 검색 → ③ 법령 가져오기 → ④ 처리·저장·가공)

전체 전략은 [STRATEGY.md](STRATEGY.md), 단계별 실행 계획은 [docs/roadmap.md](docs/roadmap.md) 참조.

## 3대 안전장치 (전 단계 관통)

1. **환각 방지** — 규정 주장은 검색된 원문이 있을 때만. 근거 없으면 "확인 불가". 인용엔 `법령명+조항+시행일` 의무.
2. **버전 관리** — 시행일 기준 "현행" 추적. 폐지 조항 인용 사고 방지.
3. **HITL(사람 검토)** — 최종본은 담당자가 인용 출처 직접 확인. LLM은 초안 작성자이지 결재자 아님.

---

## 폴더 구조

```
/raw          원문 (HWP/PDF/스캔본) — gitignore (용량·저작권)
/processed    가공 결과 (구조화 Markdown + JSON 메타데이터)
/scripts      파이썬 파이프라인 스크립트 (extract / clean / structure / chunk / embed)
/samples      PoC 샘플 산출물 (검증용 1건)
/docs         설계 문서 (전략·로드맵·아키텍처·메타데이터 스키마)
```

## 기술 스택

- **언어:** Python (파이프라인), TypeScript (검색/활용 UI는 후순위)
- **벡터 DB:** Supabase PostgreSQL + pgvector
- **추출 도구:** 미정 — Upstage Document Parse / LlamaParse / Docling 비교 평가 예정
- **임베딩/생성:** 추후 확정 (한국어 규정 특성 고려)
- **개발:** Claude Code (한 파일씩 단계적)

## 빠른 시작 (M1 PoC — 의료기기법 기준)

사전: `.env`에 `LAW_OC=<발급키>` (국가법령정보 Open API, open.law.go.kr에서 발급 + IP 등록)

```bash
# 1) 원문 수집 (Open API → 구조화 XML)
python scripts/fetch_law.py "의료기기법"

# 2) 구조화 (XML → 위계 트리 JSON/MD)
python scripts/structure.py "raw/의료기기법.xml"

# 3) 청킹 + 메타데이터 (→ samples/의료기기법_processed.json)
python scripts/chunk.py "processed/의료기기법_structured.json"

# 4) 검색 (로컬: 키워드+글자유사도, 메타필터)
python scripts/search.py "의료기기 등급분류 기준" --top 3

# 5) 인용 답변 초안 (환각 방지 + 출처 인용 + HITL)
python scripts/report.py "의료기기 제조업 허가는 누구에게 받나?"
```

> Windows 콘솔에서 한글이 깨지면 `set PYTHONIOENCODING=utf-8` (PowerShell: `$env:PYTHONIOENCODING="utf-8"`) 후 실행.
> 외부 PDF(입찰공고·회사자료)는 `python scripts/extract.py raw/<파일>.pdf` (표 Markdown 보존).

## 파이프라인 스크립트

| 스크립트 | 역할 |
|----------|------|
| `fetch_law.py` | 국가법령정보 Open API로 법령 전문(구조화 XML) 수집 |
| `extract.py` | 외부 PDF 텍스트+표 추출 (표 Markdown 보존) |
| `structure.py` | 법령 XML → 위계 트리(조/항/호) JSON + 사람용 MD |
| `chunk.py` | 조 단위 contextual 청킹 + 메타데이터 + 정의어/교차참조 |
| `search.py` | 로컬 검색(키워드+글자유사도) + 메타데이터 필터 |
| `report.py` | 근거 인용 답변 초안 (환각 방지 / 버전 / HITL) |
