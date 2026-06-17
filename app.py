"""
app.py — 의료기기 규정 지식베이스 로컬 웹앱 (Streamlit)

터미널 없이 브라우저에서 3대 기능을 쓴다: 규정 근거찾기 · 문서 점검 · 입찰 매트릭스.
기존 스크립트 로직(retriever/judge/check/bid_matrix)을 그대로 재사용한다.

실행:
  python -m pip install -r requirements.txt
  streamlit run app.py
  → 브라우저가 자동으로 열림(보통 http://localhost:8501)

사전: .env 에 SUPABASE_DB_URL + GEMINI_API_KEY (setup_check.py 로 확인).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

import streamlit as st  # noqa: E402
import retriever  # noqa: E402
import check as check_mod  # noqa: E402
import bid_matrix as bm  # noqa: E402

st.set_page_config(page_title="의료기기 규정 비서", page_icon="⚖️", layout="wide")

st.title("⚖️ 의료기기 규정 지식베이스")
st.caption("⚠️ 결과는 **초안**입니다 — 최종 판단·책임은 담당자(HITL). 인용 출처를 반드시 확인하세요.")

# 키 점검
env = retriever._load_env()
missing = [k for k in ("SUPABASE_DB_URL", "GEMINI_API_KEY") if not env.get(k)]
if missing:
    st.error(f"키 {', '.join(missing)} 가 없습니다. (로컬은 .env, 클라우드는 Secrets) `setup_check.py` 참고.")
    st.stop()


# 접속 보호: APP_PASSWORD 가 설정돼 있으면 로그인 요구(미설정 시 게이트 없음=로컬 편의)
def _gate() -> bool:
    pw_required = env.get("APP_PASSWORD")
    if not pw_required:
        return True
    if st.session_state.get("authed"):
        return True
    st.subheader("🔒 접속 비밀번호")
    pw = st.text_input("비밀번호", type="password", label_visibility="collapsed")
    if st.button("입장"):
        if pw == pw_required:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    return False


if not _gate():
    st.stop()


@st.cache_data(ttl=600)
def get_laws() -> list[str]:
    return retriever.all_law_names()


with st.sidebar:
    st.subheader("📚 적재된 규정")
    for law in sorted(get_laws()):
        st.write("- " + law)
    st.divider()
    current_only = st.checkbox("현행 규정만 사용", value=True)

tab1, tab2, tab3 = st.tabs(["📖 규정 근거찾기", "✅ 문서 점검", "📋 입찰 매트릭스"])

# ── 탭1: 규정 근거찾기 (report) ──────────────────────────────
with tab1:
    st.markdown("질문하면 관련 **조항을 출처·시행일과 함께** 찾아줍니다. 근거 없으면 '확인 불가'.")
    q = st.text_input("질문", placeholder="예: 의료기기 제조업 허가는 누구에게 받나?")
    if st.button("근거 찾기", type="primary", key="b1") and q.strip():
        with st.spinner("검색 중…"):
            res = retriever.hybrid_search(q, top_k=3, current_only=current_only)
        if not res or res[0]["sim"] < 0.50:
            st.warning("⚠️ 확인 불가 — 보유 규정에서 충분한 근거를 찾지 못했습니다.")
        else:
            if res[0]["sim"] < 0.65:
                st.info(f"유사도 {res[0]['sim']:.2f}로 다소 낮습니다 — 적합성을 신중히 확인하세요.")
            for c in res:
                m = c["metadata"]
                with st.expander(f"[{m['law_name']} {m['article']} · 시행 {m['effective_date']}] "
                                 f"(유사도 {c['sim']:.2f})", expanded=True):
                    body = c["text"].split("\n", 1)[-1]
                    st.write(body)
                    if m.get("cross_refs"):
                        st.caption("함께 볼 참조: " + ", ".join(m["cross_refs"][:5]))
                    st.caption("출처: " + m["source_url"])

# ── 탭2: 문서 점검 (check) ──────────────────────────────────
with tab2:
    st.markdown("내 문서를 **한 줄에 한 주장씩** 붙여넣으면, 규정과 맞는지 항목별로 점검합니다.")
    use_llm = st.checkbox("LLM 판정 사용(조항이 주장을 실제 뒷받침하는지)", value=True, key="llm2")
    doc = st.text_area("점검할 문장들", height=160,
                       placeholder="의료기기 제조업 허가는 식품의약품안전처장에게 받는다.\n우리 제품은 의료기기법 제15조에 따라 제조허가를 받았다.")
    if st.button("점검하기", type="primary", key="b2") and doc.strip():
        claims = check_mod.split_claims(doc)
        laws = get_laws()
        rows = []
        prog = st.progress(0.0)
        for i, claim in enumerate(claims, 1):
            r = check_mod.assess(claim, laws, current_only, use_llm)
            rows.append({"항목": claim, "판정": r["verdict"], "근거": r["basis"]})
            prog.progress(i / len(claims))
        prog.empty()
        st.dataframe(rows, use_container_width=True, hide_index=True)
        flags = sum(1 for r in rows if r["판정"].startswith("⚠️"))
        st.info(f"확인 필요(⚠️) {flags}건 — 담당자 검토 권장.")

# ── 탭3: 입찰 매트릭스 (bid_matrix) ─────────────────────────
with tab3:
    st.markdown("입찰 공고문 요구사항을 **유형·규정근거**로 정리하고, 회사 프로필을 주면 **충족 여부**까지 봅니다.")
    col1, col2 = st.columns(2)
    with col1:
        notice = st.text_area("입찰 요구사항(한 줄에 하나)", height=200,
                              placeholder="의료기기 제조업 허가를 보유한 제조업체일 것\nGMP 적합인정서를 제출할 것")
    with col2:
        company = st.text_area("회사 역량 프로필(선택 — 넣으면 충족판정)", height=200,
                               placeholder="제조업 허가 보유 / GMP 적합인정서 보유 / 초음파 수술기 품목허가 …")
    if st.button("매트릭스 생성", type="primary", key="b3") and notice.strip():
        reqs = bm.split_reqs(notice)
        rows = []
        prog = st.progress(0.0)
        for i, req in enumerate(reqs, 1):
            rtype = bm.classify(req)
            hits = retriever.hybrid_search(req, top_k=1)
            sim = hits[0]["sim"] if hits else 0.0
            ref = ""
            if sim >= 0.68:
                m = hits[0]["metadata"]; ref = f"{m['law_name']} {m['article']}"
                basis = f"{ref} (유사도 {sim:.2f})"
            elif sim >= 0.60:
                m = hits[0]["metadata"]; ref = f"{m['law_name']} {m['article']}"
                basis = f"참고(저신뢰): {ref} ({sim:.2f})"
            else:
                basis = "규정 외(조달·실적 요건)"
            row = {"요구사항": req, "유형": rtype, "규정 근거": basis}
            if company.strip():
                fj = bm.judge_fulfillment(req, ref or "(미확인)", company)
                row["충족"] = f"{fj['status']} — {fj['reason']}"
            rows.append(row)
            prog.progress(i / len(reqs))
        prog.empty()
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("⚠️ 충족 판정은 프로필 텍스트 기반 1차 판단 — 최종 증빙은 담당자 확인(HITL).")
