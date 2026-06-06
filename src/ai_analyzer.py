"""
DeepSeek API 기반 경매 물건 AI 권리분석 (Phase 4)
API 키: .env 파일의 DEEPSEEK_API_KEY
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

import requests

_API_URL = "https://api.deepseek.com/v1/chat/completions"
_MODEL = "deepseek-chat"


def _load_api_key() -> Optional[str]:
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def analyze(candidate: Dict[str, Any], market: Optional[Dict[str, Any]] = None) -> str:
    """
    DeepSeek으로 경매 물건 권리분석 텍스트 생성.

    Returns:
        분석 텍스트. API 키 없거나 오류 시 빈 문자열.
    """
    api_key = _load_api_key()
    if not api_key:
        return ""

    market = market or {}
    avg_만원 = market.get("avg_price_만원", 0)
    avg_won = avg_만원 * 10000
    trade_cnt = market.get("trade_count", 0)

    bid_price = candidate.get("estimated_sale_price", 0)
    resale = candidate.get("expected_resale_price", 0)
    repair = candidate.get("repair_cost", 0)
    acq = candidate.get("acquisition_cost", 0) + candidate.get("other_cost", 0)
    total_cost = bid_price + repair + acq
    margin = resale - total_cost
    margin_pct = round(margin / total_cost * 100, 1) if total_cost else 0

    market_section = (
        f"- 주변 실거래 평균가: {avg_won:,}원 ({avg_만원}만원, {trade_cnt}건)"
        if avg_만원 > 0
        else "- 주변 실거래가: 데이터 없음"
    )

    prompt = f"""경매 물건을 간결하게 분석해주세요.

## 물건 정보
- ID: {candidate.get('candidate_id', 'N/A')}
- 소재지: {candidate.get('location', 'N/A')}
- 법원: {candidate.get('court_name', 'N/A')}  매각일: {candidate.get('sale_date', 'N/A')}
- 종류: {candidate.get('property_type', 'N/A')}
- 권리관계: {candidate.get('rights_clarity', 'N/A')}  명도난이도: {candidate.get('eviction_difficulty', 'N/A')}
- 예상낙찰가: {bid_price:,}원  수리비: {repair:,}원  취득비: {acq:,}원
- 총투자금: {total_cost:,}원  예상매각가: {resale:,}원
- 기대수익: {margin:,}원 ({margin_pct}%)
{market_section}

## 요청 (각 항목 1~2문장)
1. 핵심 리스크
2. 수익 가능성
3. 임장 시 반드시 확인할 것

⚠️ 참고용 분석. 고액 물건은 법무사 확인 필수.
"""

    try:
        resp = requests.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _MODEL,
                "messages": [
                    {"role": "system", "content": "부동산 경매 권리분석 전문가"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"AI 분석 오류: {e}"


if __name__ == "__main__":
    sample = {
        "candidate_id": "TEST-001",
        "location": "대구 수성구 범어동",
        "court_name": "대구지방법원",
        "sale_date": "2026-06-10",
        "property_type": "apartment",
        "rights_clarity": "CLEAR",
        "eviction_difficulty": "LOW",
        "estimated_sale_price": 150000000,
        "repair_cost": 5000000,
        "acquisition_cost": 5000000,
        "other_cost": 1000000,
        "expected_resale_price": 200000000,
    }
    market = {"avg_price_만원": 18000, "trade_count": 12}
    print(analyze(sample, market))
