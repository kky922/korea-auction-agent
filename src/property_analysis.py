import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    from ai_analyzer import analyze as ai_analyze
    _HAS_AI = True
except ImportError:
    _HAS_AI = False

try:
    from realtor_api import get_market_price
    _HAS_REALTOR = True
except ImportError:
    _HAS_REALTOR = False

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "data" / "reports" / "latest_run_report.json"
CANDIDATE_PATH = ROOT / "data" / "candidates" / "latest_candidates.json"
PREFERENCE_PATH = ROOT / "config" / "user_preferences.json"
CARD_DIR = ROOT / "results" / "analysis_cards"
SUMMARY_PATH = CARD_DIR / "latest_analysis_summary.json"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def rights_score(item: Dict[str, Any]) -> float:
    score = 85.0 if item.get("rights_clarity") == "CLEAR" else 35.0
    difficulty = item.get("eviction_difficulty", "HIGH")
    score += {"LOW": 10.0, "MEDIUM": 0.0, "HIGH": -25.0}.get(difficulty, -20.0)
    return round(clamp(score), 1)


def location_score(report_row: Dict[str, Any], preferences: Dict[str, Any]) -> float:
    location_base = (
        preferences.get("analysis_scoring", {})
        .get("location_base", {})
    )
    default_base = {"PREFERRED": 88.0, "MONITOR": 76.0, "OTHER": 62.0}
    merged = {**default_base, **location_base}
    base = merged.get(report_row.get("region_priority", "OTHER"), 60.0)
    return round(clamp(base), 1)


def repair_score(item: Dict[str, Any]) -> float:
    total_price = float(item.get("estimated_sale_price", 1))
    repair_ratio = float(item.get("repair_cost", 0)) / total_price if total_price else 1.0
    score = 90.0 - (repair_ratio * 200)
    return round(clamp(score), 1)


def liquidity_score(item: Dict[str, Any], report_row: Dict[str, Any]) -> float:
    margin_rate = float(report_row.get("expected_margin_rate", 0.0))
    property_type = item.get("property_type", "")
    type_bonus = {"apartment": 8.0, "villa": 3.0, "officetel": -2.0}.get(property_type, 0.0)
    score = 65.0 + (margin_rate * 40) + type_bonus
    return round(clamp(score), 1)


def risk_level(total_score: float) -> str:
    if total_score >= 80:
        return "LOW"
    if total_score >= 60:
        return "MEDIUM"
    return "HIGH"


def reason_explanation(reason_code: str) -> str:
    mapping = {
        "BUDGET_EXCEEDED": "총투자비가 예산 상한을 초과했습니다.",
        "RESERVE_TOO_LOW": "예비비가 부족해 돌발비용 대응이 어렵습니다.",
        "RIGHTS_UNCLEAR": "권리관계가 불명확해 법적 리스크가 큽니다.",
        "EVICTION_RISK_HIGH": "명도 난이도가 높아 실행 리스크가 큽니다.",
        "MARGIN_TOO_LOW": "보수적 기준 수익률을 충족하지 못했습니다.",
        "MAX_BID_MISSING": "최대입찰가 산출값이 유효하지 않습니다.",
        "SITE_VISIT_MISSING": "현장조사가 완료되지 않았습니다.",
        "DOCUMENTS_MISSING": "필수 서류 점검이 완료되지 않았습니다.",
        "FUNDING_PLAN_MISSING": "자금조달 계획이 확정되지 않았습니다.",
    }
    return mapping.get(reason_code, "사유 코드 설명이 정의되지 않았습니다.")


def axis_reasons(item: Dict[str, Any], report_row: Dict[str, Any]) -> Dict[str, str]:
    rights = "권리관계가 명확" if item.get("rights_clarity") == "CLEAR" else "권리관계 불명확"
    eviction = {
        "LOW": "명도 난이도 낮음",
        "MEDIUM": "명도 난이도 보통",
        "HIGH": "명도 난이도 높음",
    }.get(item.get("eviction_difficulty", "HIGH"), "명도 정보 부족")

    location_reason = {
        "PREFERRED": "대구/인근 우선권역이라 가점",
        "MONITOR": "서울 모니터 권역으로 중간 가점",
        "OTHER": "우선권역 외 지역",
    }.get(report_row.get("region_priority", "OTHER"), "권역 정보 부족")

    sale_price = float(item.get("estimated_sale_price", 1) or 1)
    repair_ratio = (float(item.get("repair_cost", 0) or 0) / sale_price) * 100 if sale_price else 0.0
    repair_reason = f"수리비가 낙찰가 대비 {repair_ratio:.1f}% 수준"

    margin_rate = float(report_row.get("expected_margin_rate", 0.0)) * 100
    liquidity_reason = (
        f"예상수익률 {margin_rate:.1f}% 기준 출구전략 여력 "
        + ("양호" if margin_rate >= 12 else "부족")
    )

    return {
        "rights": f"{rights}, {eviction}",
        "location": location_reason,
        "repair": repair_reason,
        "liquidity": liquidity_reason,
    }


def status_emoji(status: str) -> str:
    return {"APPROVED": "✅", "HOLD": "⚠️", "REJECT": "❌"}.get(status, "❓")


def risk_emoji(level: str) -> str:
    return {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(level, "⚪")


def card_markdown(
    item: Dict[str, Any],
    report_row: Dict[str, Any],
    scores: Dict[str, float],
    total_score: float,
    weighted: Dict[str, float],
) -> str:
    cid = item["candidate_id"]
    status = report_row.get("status", "UNKNOWN")
    rlevel = risk_level(total_score)
    margin_rate = report_row.get("expected_margin_rate", 0.0)
    margin_won = report_row.get("expected_margin", 0)
    total_cost = report_row.get("total_cost", 0)
    max_bid = report_row.get("max_bid", 0)
    resale = item.get("expected_resale_price", 0)
    bid = item.get("estimated_sale_price", 0)
    repair = item.get("repair_cost", 0)
    acq = item.get("acquisition_cost", 0) + item.get("other_cost", 0)
    region = report_row.get("region_priority", "OTHER")
    checklist = report_row.get("checklist_completion", 0)
    naver_url = (report_row.get("quick_links") or {}).get("naver_search_url", "")
    reasons = report_row.get("reasons", [])

    lines = [
        f"🏠 {cid}  {status_emoji(status)} {status}",
        "",
        f"📍 {item.get('location', '-')}",
        f"🏛 {item.get('court_name', '-')}  |  📅 매각일 {item.get('sale_date', '-')}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "💰 수익 분석",
        f"  낙찰예상가    {bid:>15,}원",
        f"  수리비        {repair:>15,}원",
        f"  취득/부대비   {acq:>15,}원",
        f"  ───────────────────",
        f"  총 투자금     {total_cost:>15,}원",
        f"  예상매각가    {resale:>15,}원",
        f"  기대수익    {'+' if margin_won >= 0 else ''}{margin_won:>14,}원  ({margin_rate*100:.1f}%)",
        f"  최대입찰가    {max_bid:>15,}원",
        "",
        "━━━━━━━━━━━━━━━━━━",
        f"📊 종합점수 {total_score}  {risk_emoji(rlevel)} {rlevel}리스크",
        f"  ⚖️ 권리/명도  {scores['rights']:>5.1f}    🏙 입지     {scores['location']:>5.1f}",
        f"  🔧 수리비용  {scores['repair']:>5.1f}    💧 유동성   {scores['liquidity']:>5.1f}",
        "",
    ]

    # 게이트 실패사유 중 실행 체크리스트 제외한 것만 표시
    exec_reasons = {"SITE_VISIT_MISSING", "DOCUMENTS_MISSING", "FUNDING_PLAN_MISSING"}
    hard_reasons = [r for r in reasons if r not in exec_reasons]
    if hard_reasons:
        lines.append(f"⛔ 실패사유: {', '.join(hard_reasons)}")

    # 네이버 링크는 코드블록 밖에서 별도 발송 — 여기선 제외

    visit_done = item.get("site_visit_done", False)
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📋 임장 체크리스트",
        f"  1. 임장(현장방문)       : {'✅ 완료' if visit_done else '❌ 미완료'}",
        f"     → 외관·주차·관리상태·주변시세 직접 확인",
        f"  2. 서류확인(등기부등본) : https://www.iros.go.kr/",
        f"     → 말소기준권리·임차인·가압류 확인 (700원)",
        f"  3. 자금조달계획         : 직접확인 필요",
        f"     → 현금/대출 비율, 명도비 여유자금 확보",
    ]

    return "\n".join(lines) + "\n"


def _build_market_info(item: Dict[str, Any]) -> Dict:
    if not _HAS_REALTOR:
        return {}
    location = item.get("location", "")
    if not location:
        return {}
    return get_market_price(location)


def _append_ai_section(card_text: str, item: Dict[str, Any], market: Dict) -> str:
    if not _HAS_AI:
        return card_text
    ai_text = ai_analyze(item, market)
    if not ai_text:
        return card_text
    section = (
        "\n━━━━━━━━━━━━━━━━━━\n"
        "🤖 AI 권리분석 (DeepSeek) ⚠️ 참고용\n"
        + ai_text
        + "\n"
    )
    return card_text + section


def main() -> None:
    report = load_json(REPORT_PATH)
    candidates = load_json(CANDIDATE_PATH)
    preferences = load_json(PREFERENCE_PATH) if PREFERENCE_PATH.exists() else {}
    weights = (
        preferences.get("analysis_scoring", {})
        .get("weights", {})
    )
    w_rights = float(weights.get("rights", 0.30))
    w_location = float(weights.get("location", 0.25))
    w_repair = float(weights.get("repair", 0.20))
    w_liquidity = float(weights.get("liquidity", 0.25))
    weight_sum = w_rights + w_location + w_repair + w_liquidity
    if weight_sum <= 0:
        w_rights, w_location, w_repair, w_liquidity = 0.30, 0.25, 0.20, 0.25
        weight_sum = 1.0

    w_rights /= weight_sum
    w_location /= weight_sum
    w_repair /= weight_sum
    w_liquidity /= weight_sum
    candidate_map = {row["candidate_id"]: row for row in candidates}

    summaries: List[Dict[str, Any]] = []
    ensure_parent(SUMMARY_PATH)
    CARD_DIR.mkdir(parents=True, exist_ok=True)

    for row in report.get("results", []):
        cid = row["candidate_id"]
        item = candidate_map.get(cid, {"candidate_id": cid})

        scores = {
            "rights": rights_score(item),
            "location": location_score(row, preferences),
            "repair": repair_score(item),
            "liquidity": liquidity_score(item, row),
        }
        weighted = {
            "rights": round(scores["rights"] * w_rights, 2),
            "location": round(scores["location"] * w_location, 2),
            "repair": round(scores["repair"] * w_repair, 2),
            "liquidity": round(scores["liquidity"] * w_liquidity, 2),
        }
        total_score = round(sum(weighted.values()), 1)

        card_path = CARD_DIR / f"{cid}.md"
        card_text = card_markdown(item, row, scores, total_score, weighted)
        market = _build_market_info(item)
        card_text = _append_ai_section(card_text, item, market)
        # 실거래가 데이터가 있으면 summary에도 기록
        if market.get("avg_price_만원", 0) > 0:
            row["market_avg_price_만원"] = market["avg_price_만원"]
            row["market_trade_count"] = market["trade_count"]
        card_path.write_text(card_text, encoding="utf-8")

        summaries.append(
            {
                "candidate_id": cid,
                "status": row.get("status"),
                "location": row.get("location", ""),
                "court_name": row.get("court_name", ""),
                "sale_date": row.get("sale_date", ""),
                "checklist_completion": row.get("checklist_completion", 0),
                "total_analysis_score": total_score,
                "risk_level": risk_level(total_score),
                "weight_profile": {
                    "rights": round(w_rights, 3),
                    "location": round(w_location, 3),
                    "repair": round(w_repair, 3),
                    "liquidity": round(w_liquidity, 3),
                },
                "card_path": str(card_path),
            }
        )

    summary_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(summaries),
        "items": summaries,
    }

    with SUMMARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary_payload, f, ensure_ascii=False, indent=2)

    print(f"Saved: {SUMMARY_PATH}")
    print(f"Saved cards: {len(summaries)}")


if __name__ == "__main__":
    main()
