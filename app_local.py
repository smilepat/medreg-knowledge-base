"""
app_local.py — 의료기기 규정 지식베이스 로컬 웹앱 (키 불필요 / Streamlit)

app.py 와 같은 3개 기능을 제공하되, Supabase·Gemini 없이 로컬 samples/(584조항) +
scripts/search.py 의 키워드+글자유사도 검색만으로 동작한다. (= ask.py 의 웹 버전)

차이(정직):
  - 의미검색(임베딩)·LLM 의미판정(지지/모순/충족) 미사용 → 키워드 근접도 기반 1차 점검.
  - "충돌(모순)" 자동 판정 불가(LLM 필요). 근거 유무/조문 존재 확인 중심.
  - 완전한 의미판정·임베딩 검색이 필요하면 app.py + .env(SUPABASE_DB_URL/GEMINI_API_KEY).

실행:
  python -m streamlit run app_local.py
  → 브라우저 자동 열림(보통 http://localhost:8501)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

import streamlit as st  # noqa: E402
import search  # scripts/search.py (순수 로컬, 네트워크/키 불필요)  # noqa: E402

SAMPLES = ROOT / "samples"

# ── 로컬 검색 헬퍼 ─────────────────────────────────────────────
TYPES_KW = {
    "자격요건": ["허가", "등록", "신고", "자격", "면허", "제조업", "수입업", "판매업"],
    "품질·인증": ["gmp", "GMP", "인증", "적합", "품질", "ISO", "iso", "시험성적", "kc", "KC"],
    "규격·성능": ["규격", "성능", "사양", "사이즈", "출력", "정밀", "해상도", "용량", "재질"],
    "실적·납품": ["실적", "납품", "공급", "계약실적", "거래", "이력"],
    "가격·계약": ["가격", "단가", "계약", "예산", "입찰가", "보증", "지체상금"],
    "서류제출": ["제출", "서류", "서식", "증명서", "사본", "별지", "양식", "첨부"],
}


@st.cache_data(show_spinner=False)
def load_chunks() -> list[dict]:
    return search.load_chunks(SAMPLES)


def local_search(chunks: list[dict], query: str, top_k: int, current_only: bool) -> list[tuple]:
    """(score, reasons, chunk) 리스트를 점수 내림차순으로 반환."""
    pool = [c for c in chunks if c["metadata"].get("is_current")] if current_only else chunks
    tokens = search.tokenize(query)
    q_articles = search.RE_ARTICLE.findall(query)
    scored = []
    for c in pool:
        s, why = search.score_chunk(query, tokens, q_articles, c)
        if s > 0:
            scored.append((s, why, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def find_article_local(chunks: list[dict], article: str, law: str | None) -> dict | None:
    for c in chunks:
        m = c["metadata"]
        if m.get("article") == article and (law is None or m.get("law_name") == law):
            return c
    return None


def split_lines(text: str) -> list[str]:
    """문서를 한 줄=한 항목으로 분해(불릿/번호/빈줄/헤더 제외)."""
    out = []
    for line in text.splitlines():
        s = line.strip().lstrip("-*0123456789. )").strip()
        if len(s) < 8 or s.startswith("#"):
            continue
        out.append(s)
    return out


def detect_law(claim: str, laws: list[str]) -> str | None:
    for law in sorted(laws, key=len, reverse=True):
        if law in claim:
            return law
    return None


def classify_local(req: str) -> str:
    low = req
    for t, kws in TYPES_KW.items():
        if any(kw in low for kw in kws):
            return t
    return "기타"


# 키워드 점수 임계값(임베딩 sim이 아니라 가산 점수라 상대적 기준)
SCORE_OK = 4.0    # 이상이면 근거있음(키워드 강매칭)
SCORE_LOW = 2.0   # 이 값~OK 는 저신뢰

# ── UI ────────────────────────────────────────────────────────
st.set_page_config(page_title="의료기기 규정 비서 (로컬)", page_icon="⚖️", layout="wide")
st.title("⚖️ 의료기기 규정 지식베이스 — 로컬판(키 불필요)")
st.caption("⚠️ 결과는 **초안**입니다 — 최종 판단·책임은 담당자(HITL). 인용 출처를 반드시 확인하세요.")

chunks = load_chunks()
LAWS = sorted({c["metadata"]["law_name"] for c in chunks})

st.info(
    "🔌 **로컬 키워드 검색 모드** — Supabase/Gemini 없이 `samples/`(584조항)로 동작합니다. "
    "의미검색(임베딩)·LLM 의미판정(지지/모순/충족)은 미사용 → **키워드 근접도 기반 1차 점검**입니다. "
    "완전한 의미판정이 필요하면 키를 채우고 `app.py`를 쓰세요."
)

with st.sidebar:
    st.subheader("📚 적재된 규정")
    for law in LAWS:
        st.write("- " + law)
    st.caption(f"총 {len(chunks)}개 조항")
    st.divider()
    current_only = st.checkbox("현행 규정만 사용", value=True)

tab1, tab2, tab3 = st.tabs(["📖 규정 근거찾기", "✅ 문서 점검", "📋 입찰 매트릭스"])

# ── 탭1: 규정 근거찾기 ────────────────────────────────────────
with tab1:
    st.markdown("질문하면 관련 **조항을 출처·시행일과 함께** 찾아줍니다. 근거 없으면 '확인 불가'.")
    q = st.text_input("질문", placeholder="예: 의료기기 제조업 허가는 누구에게 받나?")
    if st.button("근거 찾기", type="primary", key="b1") and q.strip():
        res = local_search(chunks, q, top_k=3, current_only=current_only)
        if not res or res[0][0] < SCORE_LOW:
            st.warning("⚠️ 확인 불가 — 보유 규정에서 충분한 근거를 찾지 못했습니다. (법령 용어로 다시 시도)")
        else:
            if res[0][0] < SCORE_OK:
                st.info("키워드 일치도가 다소 낮습니다 — 적합성을 신중히 확인하세요.")
            for s, why, c in res:
                m = c["metadata"]
                with st.expander(
                    f"[{m['law_name']} {m['article']} · 시행 {m['effective_date']}] (점수 {s:.1f})",
                    expanded=True,
                ):
                    body = c["text"].split("\n", 1)[-1]
                    st.write(body)
                    if why:
                        st.caption("매칭 근거: " + why)
                    if m.get("cross_refs"):
                        st.caption("함께 볼 참조: " + ", ".join(m["cross_refs"][:5]))
                    st.caption("출처: " + m["source_url"])

# ── 탭2: 문서 점검 ────────────────────────────────────────────
with tab2:
    st.markdown("내 문서를 **한 줄에 한 주장씩** 붙여넣으면, 규정 근거가 있는지 항목별로 점검합니다.")
    st.caption("※ 로컬판은 '모순(충돌)' 자동 판정은 못 합니다(LLM 필요). 근거 유무·조문 존재 확인 중심입니다.")
    doc = st.text_area(
        "점검할 문장들", height=160,
        placeholder="의료기기 제조업 허가는 식품의약품안전처장에게 받는다.\n우리 제품은 의료기기법 제15조에 따라 제조허가를 받았다.",
    )
    if st.button("점검하기", type="primary", key="b2") and doc.strip():
        claims = split_lines(doc)
        rows = []
        prog = st.progress(0.0)
        for i, claim in enumerate(claims, 1):
            q_articles = search.RE_ARTICLE.findall(claim)
            named = detect_law(claim, LAWS)
            if q_articles:
                prov = find_article_local(chunks, q_articles[0], named)
                if prov is None:
                    verdict, basis = "⚠️ 근거없음", f"{(named + ' ') if named else ''}{q_articles[0]} — KB에 없음(오인용/미적재 가능)"
                else:
                    m = prov["metadata"]
                    tag = f"{m['law_name']} {m['article']} (시행 {m['effective_date']})"
                    if not m.get("is_current", True):
                        verdict, basis = "⚠️ 시행예정/구버전", tag + " — 현행 아님"
                    else:
                        verdict, basis = "✅ 조문 존재", tag
            else:
                hit = local_search(chunks, claim, top_k=1, current_only=current_only)
                if not hit or hit[0][0] < SCORE_LOW:
                    verdict, basis = "⚠️ 근거없음", "키워드 근거 부족 → 확인 필요"
                else:
                    s, _why, c = hit[0]
                    m = c["metadata"]
                    tag = f"{m['law_name']} {m['article']} (점수 {s:.1f})"
                    verdict = "✅ 근거있음(키워드)" if s >= SCORE_OK else "⚠️ 저신뢰"
                    basis = tag
            rows.append({"항목": claim, "판정": verdict, "근거": basis})
            prog.progress(i / len(claims))
        prog.empty()
        st.dataframe(rows, use_container_width=True, hide_index=True)
        flags = sum(1 for r in rows if r["판정"].startswith("⚠️"))
        st.info(f"확인 필요(⚠️) {flags}건 — 담당자 검토 권장.")

# ── 탭3: 입찰 매트릭스 ────────────────────────────────────────
with tab3:
    st.markdown("입찰 요구사항을 **유형·규정근거**로 정리합니다. (회사 프로필 충족판정은 LLM 필요 → 로컬은 키워드 대조)")
    col1, col2 = st.columns(2)
    with col1:
        notice = st.text_area(
            "입찰 요구사항(한 줄에 하나)", height=200,
            placeholder="의료기기 제조업 허가를 보유한 제조업체일 것\nGMP 적합인정서를 제출할 것",
        )
    with col2:
        company = st.text_area(
            "회사 역량 프로필(선택 — 키워드 대조)", height=200,
            placeholder="제조업 허가 보유 / GMP 적합인정서 보유 / 초음파 수술기 품목허가 …",
        )
    if st.button("매트릭스 생성", type="primary", key="b3") and notice.strip():
        reqs = split_lines(notice)
        rows = []
        prog = st.progress(0.0)
        for i, req in enumerate(reqs, 1):
            rtype = classify_local(req)
            hit = local_search(chunks, req, top_k=1, current_only=current_only)
            s = hit[0][0] if hit else 0.0
            if s >= SCORE_OK:
                m = hit[0][2]["metadata"]; basis = f"{m['law_name']} {m['article']} (점수 {s:.1f})"
            elif s >= SCORE_LOW:
                m = hit[0][2]["metadata"]; basis = f"참고(저신뢰): {m['law_name']} {m['article']} ({s:.1f})"
            else:
                basis = "규정 외(조달·실적 요건)"
            row = {"요구사항": req, "유형": rtype, "규정 근거": basis}
            if company.strip():
                toks = [t for t in search.tokenize(req) if t not in ("일 것", "제출", "보유")]
                overlap = [t for t in toks if t in company]
                if overlap:
                    row["충족(키워드)"] = f"◐ 추정충족 — 일치: {', '.join(overlap[:4])}"
                else:
                    row["충족(키워드)"] = "⚠️ 확인필요 — 프로필에 단서 없음"
            rows.append(row)
            prog.progress(i / len(reqs))
        prog.empty()
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("⚠️ 유형분류·충족판정은 키워드 기반 1차 결과 — 정밀 판정은 LLM(app.py) 또는 담당자(HITL).")
