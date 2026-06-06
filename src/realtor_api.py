"""
국토교통부 아파트 매매 실거래가 API (Phase 2)
Endpoint: https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests

SIGUNGU_CODES: Dict[str, str] = {
    "대구 중구": "27110",
    "대구 동구": "27140",
    "대구 서구": "27170",
    "대구 남구": "27200",
    "대구 북구": "27230",
    "대구 수성구": "27260",
    "대구 달서구": "27290",
    "대구 달성군": "27710",
    "경북 포항시 남구": "47111",
    "경북 포항시 북구": "47113",
    "경북 경주시": "47130",
    "경북 김천시": "47150",
    "경북 안동시": "47170",
    "경북 구미시": "47190",
    "경북 영주시": "47210",
    "경북 영천시": "47230",
    "경북 상주시": "47250",
    "경북 문경시": "47280",
    "경북 경산시": "47290",
    "경남 창원시 성산구": "48121",
    "경남 창원시 의창구": "48113",
    "서울 강남구": "11680",
    "서울 강북구": "11305",
    "서울 서초구": "11650",
    "서울 송파구": "11710",
    "서울 마포구": "11440",
    "서울 영등포구": "11560",
    "경기 부천시": "41190",
    "경기 성남시 분당구": "41135",
    "경기 수원시 영통구": "41117",
    "경기 고양시 덕양구": "41281",
    "인천 남동구": "28200",
    "인천 부평구": "28237",
}

_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"


def _load_api_key() -> Optional[str]:
    key = os.getenv("PUBLIC_DATA_API_KEY")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("PUBLIC_DATA_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def address_to_lawd_cd(address: str) -> Optional[str]:
    """주소 문자열에서 법정동 코드(앞 5자리) 추출"""
    for name, code in SIGUNGU_CODES.items():
        parts = name.split()
        if all(p in address for p in parts):
            return code
    # 부분 매칭 (시군구 2단어 이상)
    for name, code in SIGUNGU_CODES.items():
        parts = name.split()
        if sum(1 for p in parts if p in address) >= min(2, len(parts)):
            return code
    return None


def _fetch_trades_xml(lawd_cd: str, deal_ymd: str, api_key: str) -> List[Dict]:
    params = {
        "serviceKey": api_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": 1,
        "numOfRows": 100,
    }
    try:
        resp = requests.get(_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        result = []
        for item in root.findall(".//item"):
            def g(tag: str) -> str:
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else ""

            amount_str = g("dealAmount").replace(",", "")
            area_str = g("excluUseAr")
            if not amount_str:
                continue
            result.append({
                "apt_name": g("aptNm"),
                "area": float(area_str) if area_str else 0.0,
                "floor": g("floor"),
                "deal_amount_만원": int(amount_str),
                "year": g("dealYear"),
                "month": g("dealMonth"),
                "dong": g("umdNm"),
            })
        return result
    except Exception:
        return []


def get_market_price(
    address: str,
    area_m2: Optional[float] = None,
    months_back: int = 6,
) -> Dict:
    """
    주소 기반 주변 아파트 시세 조회.

    Returns dict:
        avg_price_만원, min_price_만원, max_price_만원, trade_count, source
    """
    api_key = _load_api_key()
    if not api_key:
        return {"avg_price_만원": 0, "trade_count": 0, "source": "no_api_key"}

    lawd_cd = address_to_lawd_cd(address)
    if not lawd_cd:
        return {"avg_price_만원": 0, "trade_count": 0, "source": "unknown_address"}

    all_trades: List[Dict] = []
    now = datetime.now()
    for i in range(months_back):
        ym = (now - timedelta(days=30 * i)).strftime("%Y%m")
        all_trades.extend(_fetch_trades_xml(lawd_cd, ym, api_key))

    if not all_trades:
        return {"avg_price_만원": 0, "trade_count": 0, "source": "no_data", "lawd_cd": lawd_cd}

    if area_m2 and area_m2 > 0:
        filtered = [t for t in all_trades if t["area"] > 0 and abs(t["area"] - area_m2) <= 10]
        if not filtered:
            filtered = all_trades
    else:
        filtered = all_trades

    prices = [t["deal_amount_만원"] for t in filtered if t["deal_amount_만원"] > 0]
    if not prices:
        return {"avg_price_만원": 0, "trade_count": 0, "source": "no_valid_prices"}

    return {
        "avg_price_만원": int(sum(prices) / len(prices)),
        "min_price_만원": min(prices),
        "max_price_만원": max(prices),
        "trade_count": len(prices),
        "source": "실거래가API",
        "lawd_cd": lawd_cd,
    }


if __name__ == "__main__":
    import json
    test_addr = "대구 수성구 범어동"
    result = get_market_price(test_addr, area_m2=84)
    print(f"주소: {test_addr}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
