import json
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List

try:
    from realtor_api import get_market_price
    _HAS_REALTOR_API = True
except ImportError:
    _HAS_REALTOR_API = False

ROOT = Path(__file__).resolve().parent.parent
_CRAWLER_OUTPUT = ROOT / "data" / "raw" / "daegu_cases.json"
_SAMPLE_DATA = ROOT / "data" / "raw" / "sample_raw_cases.json"
NORMALIZED_OUTPUT_PATH = ROOT / "data" / "candidates" / "latest_candidates.json"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    cleaned = str(value).replace(",", "").strip()
    if not cleaned:
        return default
    return int(float(cleaned))


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return float(value)
    cleaned = str(value).replace(",", "").strip()
    if not cleaned:
        return default
    return float(cleaned)


def map_eviction_level(source: str) -> str:
    level = (source or "").upper()
    if level in {"LOW", "MEDIUM", "HIGH"}:
        return level
    if level in {"L", "1"}:
        return "LOW"
    if level in {"M", "2"}:
        return "MEDIUM"
    if level in {"H", "3"}:
        return "HIGH"
    return "HIGH"


def build_quick_links(item: Dict[str, Any]) -> Dict[str, str]:
    address = str(item.get("address", "")).strip()
    court_info_url = str(item.get("court_info_url", "")).strip()

    # 네이버 검색은 주소만 넣어 정확도를 높인다.
    query = quote(address) if address else ""

    return {
        "court_detail_url": court_info_url,
        "court_search_url": f"https://www.courtauction.go.kr/",
        "naver_search_url": f"https://search.naver.com/search.naver?query={query}",
    }


def _fetch_resale_from_market(address: str, min_bid: int) -> int:
    """실거래가 API로 예상매각가 추정. 실패 시 감정가의 85% 추정."""
    if not _HAS_REALTOR_API:
        return int(min_bid * 1.2)
    result = get_market_price(address)
    avg_만원 = result.get("avg_price_만원", 0)
    if avg_만원 > 0:
        return avg_만원 * 10000
    return int(min_bid * 1.2)


def adapt_one_case(item: Dict[str, Any]) -> Dict[str, Any]:
    min_bid = safe_int(item.get("minimum_bid_price"))
    expected_resale = safe_int(item.get("expected_resale_price"))
    repair_cost = safe_int(item.get("repair_cost"), default=1200000)
    acquisition_cost = safe_int(item.get("acquisition_cost"), default=1300000)
    other_cost = safe_int(item.get("other_cost"), default=500000)
    reserve_cash = safe_int(item.get("reserve_cash"), default=3000000)

    # 예상매각가가 없으면 실거래가 API로 추정
    if expected_resale == 0 and min_bid > 0:
        address = str(item.get("address", ""))
        expected_resale = _fetch_resale_from_market(address, min_bid)

    return {
        "candidate_id": item.get("case_id", "UNKNOWN"),
        "court_name": item.get("court_name", ""),
        "court_info_url": item.get("court_info_url", ""),
        "quick_links": build_quick_links(item),
        "sale_date": item.get("sale_date", ""),
        "location": item.get("address", ""),
        "property_type": item.get("property_type", "apartment"),
        "estimated_sale_price": min_bid,
        "estimated_sale_price_reason": item.get("estimated_sale_price_reason", ""),
        "expected_resale_price": expected_resale,
        "repair_cost": repair_cost,
        "repair_cost_reason": item.get("repair_cost_reason", ""),
        "acquisition_cost": acquisition_cost,
        "acquisition_cost_reason": item.get("acquisition_cost_reason", ""),
        "other_cost": other_cost,
        "other_cost_reason": item.get("other_cost_reason", ""),
        "reserve_cash": reserve_cash,
        "photo_urls": item.get("photo_urls", []),
        "photo_note": item.get("photo_note", ""),
        "map_url": item.get("map_url", ""),
        "latitude": safe_float(item.get("latitude"), default=0.0),
        "longitude": safe_float(item.get("longitude"), default=0.0),
        "rights_clarity": "CLEAR" if item.get("rights_clear") else "UNCLEAR",
        "eviction_difficulty": map_eviction_level(item.get("eviction_risk_level", "HIGH")),
        "site_visit_done": bool(item.get("site_visit_done", False)),
        "documents_ready": bool(item.get("documents_ready", False)),
        "funding_plan_ready": bool(item.get("funding_plan_ready", False)),
    }


def adapt_cases(raw_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [adapt_one_case(case) for case in raw_cases]


def main() -> None:
    raw_cases: List[Dict[str, Any]] = []
    # 크롤러 출력이 존재하면 그것만 사용 (더미 데이터 제외)
    if _CRAWLER_OUTPUT.exists():
        raw_cases = load_json(_CRAWLER_OUTPUT)
    elif _SAMPLE_DATA.exists():
        raw_cases = load_json(_SAMPLE_DATA)
    normalized = adapt_cases(raw_cases)

    ensure_parent(NORMALIZED_OUTPUT_PATH)
    with NORMALIZED_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"Saved: {NORMALIZED_OUTPUT_PATH}")
    print(f"Adapted cases: {len(normalized)}")


if __name__ == "__main__":
    main()
