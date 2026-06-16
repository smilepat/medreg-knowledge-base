"""
judge.py — LLM 판정 계층: "이 조항이 주장을 실제로 뒷받침하는가?"

검색(retriever)은 '의미적으로 가까운 조항'을 줄 뿐, 주장이 사실인지는 모른다.
judge는 Gemini에게 **제공된 조항 텍스트만** 근거로(외부지식 금지) 주장과의 관계를 판정시킨다.
→ 자기참조 오주장(예: "건강보험 수가는 의료기기법에서 정한다") 같은 substance 오류를 거른다.

환각 방지: 프롬프트가 "조항에 없는 내용은 추측 금지, 외부지식 금지"를 강제.
모델: gemini-2.5-flash (기본 — 빠르고 저렴).
"""

from __future__ import annotations

import json

from retriever import _client_  # .env 기반 Gemini 클라이언트 재사용
from google.genai import types

MODEL = "gemini-2.5-flash"

_PROMPT = """너는 한국 법령 준수 검토 보조자다. 아래 [조항] 텍스트만을 근거로 [주장]을 판정하라.
규칙: 조항에 적혀있지 않은 내용은 절대 추측하지 말 것. 외부지식·일반상식 사용 금지.
조항이 주장의 주제 자체와 무관하면 '무관'이다(다른 법 소관이면 무관).

[주장]
{claim}

[조항] {cite}
{provision}

판정 기준:
- 지지: 조항이 주장을 직접 뒷받침함
- 부분지지: 일부만/조건부로 뒷받침함
- 무관: 조항이 주장의 내용과 관련이 없음(주제가 다름)
- 모순: 조항이 주장과 반대되거나 충돌함
- 불충분: 이 조항만으로는 판단 근거가 부족함

반드시 JSON만 출력: {{"verdict":"지지|부분지지|무관|모순|불충분","reason":"한국어 한 문장 근거"}}"""

_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "verdict": types.Schema(type=types.Type.STRING,
                                enum=["지지", "부분지지", "무관", "모순", "불충분"]),
        "reason": types.Schema(type=types.Type.STRING),
    },
    required=["verdict", "reason"],
)


def judge(claim: str, provision: str, cite: str) -> dict:
    """주장 vs 조항 판정 → {'verdict':..., 'reason':...}. 실패 시 verdict='불충분'."""
    prompt = _PROMPT.format(claim=claim, cite=cite, provision=provision[:4000])
    try:
        resp = _client_().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_SCHEMA,
                temperature=0,
            ),
        )
        data = json.loads(resp.text)
        return {"verdict": data.get("verdict", "불충분"),
                "reason": (data.get("reason") or "").strip()}
    except Exception as e:
        return {"verdict": "불충분", "reason": f"판정 실패: {str(e)[:60]}"}
