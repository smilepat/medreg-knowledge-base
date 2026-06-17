# SETUP — 다른 PC에서 작업 시작하기

> 멀티 PC 원칙: **GitHub = 정본(SSOT)**. 시작 시 `git pull`, 종료 시 `commit` + `push`.
> 지식베이스(법령 584청크)는 **Supabase에 있음** → 다른 PC는 클론 후 키만 넣으면 바로 검색·점검 가능(로컬 재적재 불필요).

---

## 1. 전제

- Git, **Python 3.13**
- 키(아래) — 회사 공용 자격증명. 채팅·git에 올리지 말 것.

## 2. 설치 (4단계)

```bash
# 1) 클론
git clone https://github.com/smilepat/medreg-knowledge-base.git
cd medreg-knowledge-base

# 2) 파이썬 의존성
python -m pip install -r requirements.txt

# 3) .env 생성 (예시 복사 후 값 채우기 — .env 는 git 제외됨)
cp .env.example .env
#   LAW_OC=smilepat
#   SUPABASE_DB_URL=postgresql://postgres.rpxvlskmlrhivbiamicb:<비번>@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require
#   GEMINI_API_KEY=<키>

# 4) 점검 (❌ 없으면 준비 완료)
python scripts/setup_check.py
```

> Windows 콘솔 한글 깨짐 시: PowerShell `$env:PYTHONIOENCODING="utf-8"` (bash `export PYTHONIOENCODING=utf-8`).

## 3. 바로 사용 가능 (IP 등록 불필요)

지식베이스가 Supabase에 있으므로 **클론한 어느 PC에서도** 즉시 동작:

```bash
python scripts/report.py "의료기기 제조업 허가는 누구에게 받나?"        # 근거 인용 답변
python scripts/check.py examples/sample-report-draft.md                  # 내 문서 정합성 점검
python scripts/bid_matrix.py examples/sample-bid-notice.md \
       --company examples/company-profile.sample.md                      # 입찰 매트릭스
python scripts/search_pg.py "의료기기 등급분류 기준"                     # 의미검색
```

## 4. 새 법령·고시 추가할 때만 — IP 등록 필요

`fetch_law.py`(국가법령정보 Open API)는 **호출 PC의 공인 IP가 OC 계정에 등록**돼야 동작:

1. `python scripts/setup_check.py` 출력의 `[4]`에서 이 PC 공인 IP 확인
2. **open.law.go.kr → 마이페이지 → OPEN API** 에서 OC(`smilepat`)에 그 IP 추가
3. 그 후:
   ```bash
   python scripts/fetch_law.py "<법령명>"                 # 법·시행령·시행규칙
   python scripts/fetch_law.py "<고시명>" --target admrul  # 식약처 고시 등 행정규칙
   python scripts/structure.py "raw/<법령명>.xml"
   python scripts/chunk.py "processed/<법령명>_structured.json"
   python scripts/embed.py                                 # Supabase에 적재(공유 반영)
   ```

## 5. 현재 적재된 지식베이스 (Supabase, 7법령 584청크)

| 영역 | 법령 |
|------|------|
| 인허가 | 의료기기법 · 시행령 · 시행규칙 |
| 품질 | 의료기기 제조 및 품질관리 기준(GMP 고시) |
| 보험 | 국민건강보험법 |
| 조달 | 국가를 당사자로 하는 계약에 관한 법률 · 시행령 |

## 6. 자주 겪는 이슈

- **`SUPABASE_DB_URL` 연결 실패**: `?sslmode=require` 포함, **session pooler(5432)** 호스트인지 확인.
- **`fetch_law` 인증 실패(IP)**: 위 4번 — 새 PC IP 미등록. KT 가정용 IP는 바뀔 수 있어 재등록 필요할 수 있음.
- **한글 깨짐**: `PYTHONIOENCODING=utf-8`.
- **로컬만으로 검색**(Supabase 없이): `samples/*.json`이 git에 있어 `python scripts/search.py "질의"` (키워드) 가능.

---

자세한 구조·전략은 [docs/overview.md](docs/overview.md) · [README.md](README.md) · [docs/handoff-2026-06-15.md](docs/handoff-2026-06-15.md).
