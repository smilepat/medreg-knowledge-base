# 사용 가이드 — 의료기기 규정 지식베이스

> 비개발자도 따라 할 수 있게 정리한 실사용 가이드. 명령은 그대로 복사해 쓰면 됩니다.
> (개발 셋업은 [SETUP.md](../SETUP.md), 전체 그림은 [overview.md](overview.md) 참조)

---

## 1. 이게 뭐예요? (3줄 요약)

- 의료기기 사업 관련 **정부 규정 7개 법령(584개 조항)**을 검색·인용 가능한 지식베이스로 만들었습니다.
- 질문하면 **"어느 법 몇 조에 그렇게 적혀 있다"를 출처·시행일과 함께** 답합니다.
- 핵심 3가지: **① 보고서 근거 찾기 ② 내 문서 규정 점검 ③ 입찰 요구사항 대조**.

세 가지 안전장치가 코드에 박혀 있습니다:
- **환각 방지**: 근거가 없으면 지어내지 않고 "확인 불가"라고 답함
- **버전 관리**: 모든 인용에 시행일 표기(폐지·예정 조항 구분)
- **사람 검토(HITL)**: 결과는 "초안" — 최종은 담당자가 출처 확인

## 2. 지금 담겨 있는 규정 (7법령 584조항)

| 영역 | 법령 |
|------|------|
| 인허가 | 의료기기법 · 시행령 · 시행규칙 |
| 품질 | 의료기기 제조 및 품질관리 기준(GMP 고시) |
| 보험 | 국민건강보험법 |
| 조달 | 국가를 당사자로 하는 계약에 관한 법률 · 시행령 |

---

## 3. 사용 전 준비 (한 번만)

```bash
cd medreg-knowledge-base
python scripts/setup_check.py        # ✅만 나오면 준비 끝
```
한글이 깨지면 먼저 실행: PowerShell `$env:PYTHONIOENCODING="utf-8"`

---

## 4. 세 가지 사용법

### ① 보고서 근거 찾기 — `report.py`
보고서 쓰다가 "이거 근거 조항이 뭐지?" 할 때.

```bash
python scripts/report.py "의료기기 제조업 허가는 누구에게 받나?"
```
→ **[의료기기법 제6조 (시행 2025-08-01)]** 조문 + 출처 URL을 줍니다. 그대로 보고서에 인용.
- 근거가 없으면 **"⚠️ 확인 불가"** (지어내지 않음)
- 현행만 보려면 뒤에 `--current-only`

### ② 내 문서 규정 점검 — `check.py`
이미 쓴 보고서가 규정과 어긋나지 않는지 항목별로 점검.

```bash
python scripts/check.py 내문서.md --out 점검표.md
```
→ 각 문장을 **✅근거있음 / ⚠️충돌(모순) / ⚠️근거없음 / ⚠️확인필요**로 표시한 표 생성.
- 예: "제15조에 따라 제조허가" → ⚠️충돌 (제15조는 수입허가지 제조허가 아님)
- 예: 근거 없는 주장 → ⚠️근거없음
- `내문서.md`는 한 줄에 한 주장씩 적힌 텍스트/마크다운 파일

### ③ 입찰 요구사항 대조 — `bid_matrix.py`
입찰 공고문 요구사항을 규정·회사역량과 대조.

```bash
# 규정 근거만 매핑
python scripts/bid_matrix.py 공고문.md --out 매트릭스.md

# 회사 프로필과 대조해 충족 여부까지
python scripts/bid_matrix.py 공고문.md --company 회사프로필.md --out 매트릭스.md
```
→ 요구사항별로 **유형 · 규정 근거 · 충족(✅/❌/⚠️)** 표.
- 회사 프로필 양식: `examples/company-profile.sample.md` 복사 → `examples/company-profile.md`로 자사 정보 입력(이 파일은 git 제외).

---

## 5. 시나리오별 추천 흐름

**보고서 작성 중**
1. 단락 쓰기 → 근거 필요하면 `report.py "질문"` → 인용 붙여넣기
2. 다 쓴 뒤 `check.py 보고서.md` 로 전체 점검 → ⚠️ 항목 직접 확인

**입찰 준비**
1. 공고문을 텍스트로 저장 → `bid_matrix.py 공고문.md --company 회사프로필.md`
2. ⚠️ 확인필요·❌ 미충족 항목을 담당자가 보완

**규정 빠르게 찾기**
- `python scripts/search_pg.py "키워드나 질문"` — 관련 조항 상위 5개(유사도순)

---

## 6. 새 규정 추가하기 (선택, 개발 작업)

새 법령·고시를 지식베이스에 넣으려면 (이 PC 공인 IP를 open.law.go.kr에 등록 후):

```bash
python scripts/fetch_law.py "법령명"                  # 법·시행령·시행규칙
python scripts/fetch_law.py "고시명" --target admrul   # 식약처 고시 등
python scripts/structure.py "raw/법령명.xml"
python scripts/chunk.py "processed/법령명_structured.json"
python scripts/embed.py                                # Supabase에 적재
```

---

## 7. 꼭 기억할 점

- **결과는 "초안"입니다.** 법적 책임이 걸린 사안은 **반드시 출처 원문을 직접 확인**(HITL).
- 답변 못 찾으면 **"확인 불가"가 정상** — 지어내지 않도록 만든 것입니다.
- 검색·LLM 판정이 **인접 주제를 가깝게 잡을 수 있음**(예: 책임보험↔건강보험) → 판정 근거(조항)를 꼭 눈으로 확인.
- 회사 자료·입찰 기밀은 **git에 올리지 마세요**(`.gitignore`로 막혀 있지만 파일명 주의).

## 8. 막힐 때

| 증상 | 해결 |
|------|------|
| 한글 깨짐 | `$env:PYTHONIOENCODING="utf-8"` (PowerShell) |
| 연결 실패 | `python scripts/setup_check.py` 로 .env·키 확인 |
| `fetch_law` 인증 실패 | 이 PC 공인 IP를 open.law.go.kr OC(smilepat)에 등록 |
| 결과가 이상함 | 항상 출처 조항 원문을 직접 확인(HITL) |
