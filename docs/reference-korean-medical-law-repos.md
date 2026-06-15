# 참고: 대한민국 의료법령 관련 공개 GitHub 레포 분석 (2026-06-15)

> 우리 medreg 프로젝트와 유사하거나 데이터·설계를 차용할 수 있는 공개 레포를 조사·분석한 기록.
> ⚠️ 코드 내부·데이터 정확성은 표면 분석 수준이며, **실제 차용 전 라이선스·정확도 재검증 필수**.
> 원칙: [새 외부 서비스/의존성 자제] — 코드 통째 차용보다 **설계 참고** 우선.

---

## 0. 한눈에 보기

| 레포 | 유형 | 접근법 | 라이선스 | 우리에게 가치 |
|------|------|--------|----------|----------------|
| **legalize-kr** / admrule-kr | **법령 데이터셋** | md+frontmatter+git, 거의 매일 갱신 | 텍스트=공공저작물 | ★★★ 데이터 소스 후보 |
| RadiationSafetyNM/radsafety-laws | 데이터 레이어 | legalize-kr raw fetch + 주간 CI | 스크립트 MIT | ★★★ 배치·버전관리 모델 |
| jeongsuho-lawyer/legalcheck | 룰 기반 린터 | YAML 룰 정적분석 | **Apache-2.0** | ★★ LLM 한계 실측 근거 |
| fullth/medical-law-checkeer | 프롬프트 검토 | FastAPI + 크롬확장 | 없음 | ★★ 검토항목↔법령 매핑 |
| HaileysArchives/medical_law_search_chatbot | RAG 기본형 | LangChain+Chroma | 없음 | ★ RAG 베이스라인 비교 |
| 32squared/medical-compliance-tester | 멀티에이전트 RAG | Claude Code agents | 없음 | ★ RAG 평가(batch_eval) |

---

## 1. legalize-kr / admrule-kr — ★ 데이터 소스 후보 (가장 중요한 발견)

- **무엇:** 대한민국 법령(legalize-kr)·행정규칙 고시(admrule-kr)를 **Markdown + frontmatter + git**으로
  관리하는 오픈 데이터셋. law.go.kr OpenAPI를 1차 출처로 가공, **거의 매일 개정을 추적·커밋**.
- **우리 관점 핵심:**
  - **raw fetch 라 IP·OC 키가 필요 없다** → 우리 `fetch_law.py`의 약점(OC+고정 IP 등록 의존, 가정용 IP 변동)을 보완.
  - **의료기기법·의료법·의료기사법·진단용방사선규칙·특수의료장비규칙**이 이미 포함(법률+시행령+시행규칙 세트).
  - 갱신을 git history로 추적 → 우리 **버전관리(시행일/현행)** 와 궁합.
- **주의:** 가공본이므로 *정확한 조문·최신 개정은 law.go.kr 원본 대조 필요*(그쪽 README 명시) — 우리 환각방지 원칙과 동일.
- **검토 가치:** M2 배치 단계에서 `fetch_law.py`(공식 API, 권위 있음) + legalize-kr(무IP, 폭넓음)를 **이중 소스**로 쓰는 안 고려.

## 2. RadiationSafetyNM/radsafety-laws — ★ 배치·버전관리 모델

- **무엇:** legalize-kr에서 *필요한 법령만* raw fetch해 vendoring + **GitHub Actions 주간 cron 자동 갱신**.
  앱(`radsafety-web`) ↔ 데이터(`radsafety-laws`) 분리.
- **구조:** `data/laws`(법률·시행령·시행규칙) / `data/admin-rules`(고시·예규) / `data/attachments`(별표 PDF, law.go.kr flDownload).
- **우리 관점:**
  - **"데이터 레포 분리 + CI 주간 갱신 + 별표 PDF 자동수집"** 패턴이 우리 M2 목표(배치 파이프라인 + 버전관리)와 거의 동일 → **설계 청사진으로 직접 참고**.
  - 별표/서식을 `flDownload`로 자동 수집하는 방식은 우리 `extract.py`(표/별표) 경로와 연결.
  - 라이선스: 법령 텍스트=공공저작물(자유), 가공 스크립트=MIT(차용 가능).

## 3. jeongsuho-lawyer/legalcheck — ★ 우리 안전장치 설계의 실측 근거

- **무엇:** AI 앱 출시 전 14개 전문자격사법(의료법·약사법 등) 위반을 **YAML 룰로 정적 분석**하는 린터. RAG 아님. Claude Code Skill(`SKILL.md`) 제공. **유일하게 Apache-2.0**.
- **우리 관점 핵심 — LLM 한계 실측(30개 프로젝트, Opus 4.6/Sonnet 4.6):**
  - LLM이 **일부 직역(손해사정·행정사법 등)을 놓침**.
  - LLM이 **판례를 잘못 인용**(실존하나 무관한 사건). 3회 반복 시 매번 다른 판례번호.
  - → 이는 우리 medreg의 **환각 방지 + 원문 인용 의무(법령명+조항+시행일) + 버전관리** 설계가 옳다는 외부 실증. STRATEGY 근거로 인용 가능.
  - `rules/_law_status.json`(법령 상태 추적), `rules/*.yaml`(룰 구조)은 M3 입찰 컴플라이언스 룰셋 설계에 참고.

## 4. fullth/medical-law-checkeer — 검토항목↔법령 매핑(요구사항 매트릭스 원형)

- **무엇:** 네이버 블로그의 **의료광고 위반**을 검토하는 크롬 확장 + FastAPI 백엔드. **프롬프트 기반(RAG 아님)**, `prompts/medical_law.py`.
- **우리 관점:** README의 **"위반 유형 ↔ 근거 법령" 매핑표**(예: 과장광고→의료법 제56조②1호, 미인증 의료기기→의료기기법 제36조)가 우리 **M3 입찰 requirement matrix**(요구사항↔근거조항 대조)의 좋은 원형.
- 주의: 라이선스 없음 → 코드 재사용 불가, 개념만 참고.

## 5. HaileysArchives/medical_law_search_chatbot — RAG 베이스라인(대조군)

- **무엇:** LangChain + Chroma + **Upstage `solar-pro` 임베딩** + `RecursiveCharacterTextSplitter`, 데이터=단일 `medical.docx`, Streamlit.
- **우리 관점:** 전형적 "기본형 RAG". **글자수 분할**이라 우리의 **법령 위계 청킹(조/항/호) + 메타데이터 + 버전관리**가 왜 더 나은지 보여주는 대조군. 한국어 임베딩으로 Upstage solar-pro가 후보가 될 수 있음(우리 임베딩 모델 선택 시 참고).
- 주의: 라이선스 없음.

## 6. 32squared/medical-compliance-tester — 멀티에이전트 RAG 평가

- **무엇:** Claude Code **멀티에이전트**(`.claude/agents/medical-expert.md` 등) + `batch_eval_rag.py`(RAG 평가) + Docker/GCP. 건강상담 Modular RAG.
- **우리 관점:** `batch_eval_rag.py`식 **RAG 품질 자동 평가** 방식은 우리 검색 품질 검증(M1-4 "테스트 질문 3~5개") 확장에 참고. 다만 규모 크고 라이선스 없음 → 개념 참고만.

---

## 7. 종합 — medreg에 적용할 점

1. **데이터 소스 보강(우선 검토):** `legalize-kr`/`admrule-kr`는 **IP·키 없이** 의료기기법 포함 법령을
   markdown으로 제공 → 우리 `fetch_law.py`(공식 API)의 IP 의존 약점을 보완하는 **2차 소스** 후보.
   단, 공식 API가 권위·정확도에서 우위 → **공식 API를 정본, legalize-kr를 폭넓은 보조**로 이중화 검토.
2. **배치·버전관리 청사진:** `radsafety-laws`의 *데이터 레포 분리 + 주간 CI cron + 별표 PDF 자동수집*을
   우리 M2 설계에 차용(스크립트 MIT라 참고/이식 가능).
3. **안전장치 정당성:** `legalcheck`의 *LLM 직역 누락·판례 오인용 실측*은 우리 환각방지/원문인용/버전관리
   설계의 외부 근거. STRATEGY.md 보강에 인용 가능.
4. **입찰 매트릭스 원형(M3):** `medical-law-checkeer`의 검토항목↔법령 매핑, `legalcheck`의 YAML 룰 구조.
5. **임베딩 후보:** 한국어 법령엔 Upstage `solar-pro`(Haileys 사례) / gemini-embedding-001 비교.

### 라이선스 요약(차용 시 주의)
- 법령 **텍스트 자체** = 공공저작물(자유 이용).
- 코드: legalcheck=**Apache-2.0**, radsafety 스크립트=**MIT** → 차용 가능. 나머지(검토 4개 중 3개)=**라이선스 없음** → 코드 재사용 불가, **개념만 참고**.

> 다음 행동(선택): legalize-kr에서 의료기기법 markdown을 받아 우리 `의료기기법.xml`(공식 API)과
> **조문 일치도 대조** → 2차 소스 신뢰도 평가. (원하시면 진행)
