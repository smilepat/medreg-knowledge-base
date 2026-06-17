# DEPLOY — 클라우드 배포 가이드 (외부 접속)

> 로컬 웹앱(`streamlit run app.py`)을 **외부에서 접속 가능**하게 올리는 방법.
> ⚠️ 회사·입찰 **기밀 자료**를 다루므로, 공개 배포 전 아래 보안 항목을 반드시 충족할 것.
> 실제 퍼블리시는 **호스트 선택 + 보안 확인 후** 진행(이 문서는 준비 완료 상태 기준).

---

## 0. 배포 전 필수 보안 체크리스트

- [ ] **APP_PASSWORD 설정** — 앱 로그인 보호(미설정 시 누구나 접속). `app.py`가 자동 적용.
- [ ] **비밀키는 호스트 Secrets(환경변수)로만** — `SUPABASE_DB_URL` / `GEMINI_API_KEY` / `APP_PASSWORD`.
      절대 git·프론트에 노출 금지. (코드는 `.env` 없이 OS 환경변수에서 읽도록 되어 있음)
- [ ] **가능하면 비공개(Private) 호스팅** 또는 회사 IP 제한.
- [ ] **HITL 고지 유지** — 결과는 "초안"(앱 상단에 이미 표시).
- [ ] Gemini/Supabase **비용·사용량 한도** 확인.

> 코드는 이미 클라우드 대응 완료: `retriever._load_env()`가 환경변수(Secrets)와 `.env`를 병합.

## 1. 옵션 A — Hugging Face Spaces (Streamlit SDK)

가장 빠름. (단, HF = 새 외부 서비스 → 회사 정책 확인 후)

1. https://huggingface.co → **New Space** → SDK: **Streamlit**, 가시성: **Private** 권장
2. 이 저장소 파일을 Space에 올림 (`app.py`, `scripts/`, `requirements.txt`, `samples/`)
3. Space **Settings → Variables and secrets** 에 추가:
   - `SUPABASE_DB_URL` = `postgresql://...pooler...:5432/postgres?sslmode=require`
   - `GEMINI_API_KEY` = `...`
   - `APP_PASSWORD` = `<공유 비밀번호>`
4. Space가 자동 빌드 → URL 접속 → 비밀번호 입력 후 사용

> `samples/`는 git에 포함돼 있어 함께 올라감. 지식베이스 검색은 Supabase로 동작.

## 2. 옵션 B — Docker (사내 서버 / 클라우드 VM)

`Dockerfile` 예시:
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
```
실행 시 환경변수 주입:
```bash
docker build -t medreg-app .
docker run -p 8501:8501 \
  -e SUPABASE_DB_URL="..." -e GEMINI_API_KEY="..." -e APP_PASSWORD="..." \
  medreg-app
```

## 3. 옵션 C — 사내망 공유(배포 없이)

같은 사무실 네트워크면 호스팅 없이 충분할 수 있음:
```bash
python -m streamlit run app.py --server.address 0.0.0.0
```
→ 실행 PC의 `Network URL`(예: http://172.30.1.81:8501)을 같은 망의 동료가 접속.
(이 PC가 켜져 있어야 하고, 외부 인터넷에선 접속 불가 → 기밀 측면에서 안전한 편)

## 4. 배포 후 운영 메모

- **새 법령 추가**(`fetch_law`)는 클라우드에서 불가(IP 등록 필요) → **관리자가 로컬에서** 받아 `embed.py`로 Supabase에 반영하면, 배포된 앱에도 **자동 반영**(같은 DB 참조).
- 비밀번호·키 교체 시 호스트 Secrets만 갱신.

---

## 진행 결정 필요 (현재 상태)

코드·보안 장치(로그인, 환경변수 대응)·가이드는 **준비 완료**. 실제 외부 공개는 다음을 정한 뒤 진행:
1. **호스트**: HF Spaces(A) / 사내 서버 Docker(B) / 사내망 공유(C)
2. **공개 범위**: 비공개 권장 (기밀 자료)
3. APP_PASSWORD 값 결정
