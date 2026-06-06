import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent.parent
RULE_PATH = ROOT / "policy" / "decision_gates.json"
PREFERENCE_PATH = ROOT / "config" / "user_preferences.json"
DEFAULT_INPUT_PATH = ROOT / "data" / "candidates" / "latest_candidates.json"
LEGACY_INPUT_PATH = ROOT / "data" / "candidates" / "sample_candidates.json"
REPORT_PATH = ROOT / "data" / "reports" / "latest_run_report.json"


@dataclass
class CandidateResult:
    candidate_id: str
    total_cost: int
    max_bid: int
    expected_margin: int
    expected_margin_rate: float
    status: str
    reasons: List[str]
    court_name: str = ""
    court_info_url: str = ""
    quick_links: Dict[str, str] = None
    sale_date: str = ""
    location: str = ""
    region_priority: str = "OTHER"
    recommendation_score: float = 0.0
    checklist_completion: float = 0.0
    estimated_sale_price_reason: str = ""
    repair_cost_reason: str = ""
    acquisition_cost_reason: str = ""
    other_cost_reason: str = ""
    photo_urls: List[str] = None
    photo_note: str = ""
    map_url: str = ""
    latitude: float = 0.0
    longitude: float = 0.0


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def conservative_valuation(item: Dict[str, Any]) -> Dict[str, Any]:
    total_cost = (
        item["estimated_sale_price"]
        + item["repair_cost"]
        + item["acquisition_cost"]
        + item["other_cost"]
    )
    expected_margin = item["expected_resale_price"] - total_cost
    expected_margin_rate = expected_margin / total_cost if total_cost else 0.0

    # 보수형 기준: 목표 수익률(12%)을 역산해 최대 입찰가를 계산한다.
    target_margin_rate = 0.12
    fixed_cost = item["repair_cost"] + item["acquisition_cost"] + item["other_cost"]
    max_bid = int(item["expected_resale_price"] / (1 + target_margin_rate) - fixed_cost)
    if max_bid < 0:
        max_bid = 0

    return {
        "total_cost": total_cost,
        "expected_margin": expected_margin,
        "expected_margin_rate": expected_margin_rate,
        "max_bid": max_bid,
    }


def evaluate_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> Tuple[bool, str]:
    field = rule["field"]
    operator = rule["operator"]
    expected = rule["value"]
    reason = rule["reason_code"]
    actual = data.get(field)

    passed = False
    if operator == "<=":
        passed = actual <= expected
    elif operator == ">=":
        passed = actual >= expected
    elif operator == ">":
        passed = actual > expected
    elif operator == "==":
        passed = actual == expected
    elif operator == "in":
        passed = actual in expected
    else:
        raise ValueError(f"Unsupported operator: {operator}")

    return passed, reason


def run_gates(gate_rules: Dict[str, Any], features: Dict[str, Any]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    status = "APPROVED"

    for gate in gate_rules["gates"]:
        gate_failed = False
        for rule in gate["rules"]:
            passed, reason = evaluate_rule(rule, features)
            if not passed:
                gate_failed = True
                reasons.append(reason)

        if gate_failed:
            if gate["type"] == "hard_reject":
                return "REJECT", reasons
            if gate["type"] == "hold":
                status = "HOLD"

    return status, reasons


def process_candidates(candidates: List[Dict[str, Any]], gate_rules: Dict[str, Any]) -> List[CandidateResult]:
    results: List[CandidateResult] = []
    for item in candidates:
        valuation = conservative_valuation(item)
        features = {**item, **valuation}
        status, reasons = run_gates(gate_rules, features)
        results.append(
            CandidateResult(
                candidate_id=item["candidate_id"],
                total_cost=valuation["total_cost"],
                max_bid=valuation["max_bid"],
                expected_margin=valuation["expected_margin"],
                expected_margin_rate=round(valuation["expected_margin_rate"], 4),
                status=status,
                reasons=reasons,
            )
        )
    return results


def summarize(results: List[CandidateResult]) -> Dict[str, Any]:
    by_status = {"APPROVED": 0, "HOLD": 0, "REJECT": 0}
    for row in results:
        by_status[row.status] = by_status.get(row.status, 0) + 1
    return {"total": len(results), "by_status": by_status}


def detect_region_priority(location: str, preferences: Dict[str, Any]) -> str:
    preferred = preferences.get("preferred_regions", [])
    monitor = preferences.get("monitor_regions", [])
    if any(token in location for token in preferred):
        return "PREFERRED"
    if any(token in location for token in monitor):
        return "MONITOR"
    return "OTHER"


def recommendation_score(status: str, margin_rate: float, region_priority: str) -> float:
    base = {"APPROVED": 70.0, "HOLD": 45.0, "REJECT": 10.0}.get(status, 0.0)
    margin_bonus = max(min(margin_rate * 100, 30), -30)
    region_bonus = {"PREFERRED": 15.0, "MONITOR": 7.0, "OTHER": 0.0}.get(region_priority, 0.0)
    return round(base + margin_bonus + region_bonus, 2)


def main() -> None:
    gate_rules = load_json(RULE_PATH)
    preferences = load_json(PREFERENCE_PATH) if PREFERENCE_PATH.exists() else {}
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_PATH
    if not input_path.exists():
        input_path = LEGACY_INPUT_PATH
    candidates = load_json(input_path)
    raw_results = process_candidates(candidates, gate_rules)

    enriched_results: List[CandidateResult] = []
    for row, item in zip(raw_results, candidates):
        region = detect_region_priority(item.get("location", ""), preferences)
        score = recommendation_score(row.status, row.expected_margin_rate, region)
        checklist_done = [
            bool(item.get("site_visit_done", False)),
            bool(item.get("documents_ready", False)),
            bool(item.get("funding_plan_ready", False)),
        ]
        checklist_completion = round((sum(1 for v in checklist_done if v) / len(checklist_done)) * 100, 1)
        enriched_results.append(
            CandidateResult(
                candidate_id=row.candidate_id,
                location=item.get("location", ""),
                court_name=item.get("court_name", ""),
                court_info_url=item.get("court_info_url", ""),
                quick_links=item.get("quick_links", {}),
                sale_date=item.get("sale_date", ""),
                region_priority=region,
                total_cost=row.total_cost,
                max_bid=row.max_bid,
                expected_margin=row.expected_margin,
                expected_margin_rate=row.expected_margin_rate,
                recommendation_score=score,
                status=row.status,
                reasons=row.reasons,
                checklist_completion=checklist_completion,
                estimated_sale_price_reason=item.get("estimated_sale_price_reason", ""),
                repair_cost_reason=item.get("repair_cost_reason", ""),
                acquisition_cost_reason=item.get("acquisition_cost_reason", ""),
                other_cost_reason=item.get("other_cost_reason", ""),
                photo_urls=item.get("photo_urls", []),
                photo_note=item.get("photo_note", ""),
                map_url=item.get("map_url", ""),
                latitude=float(item.get("latitude", 0) or 0),
                longitude=float(item.get("longitude", 0) or 0),
            )
        )

    report = {
        "profile": gate_rules["profile"],
        "summary": summarize(enriched_results),
        "results": [asdict(r) for r in enriched_results],
    }

    ensure_parent(REPORT_PATH)
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    report["input_path"] = str(input_path)
    print(f"Saved: {REPORT_PATH}")
    print(f"Input: {input_path}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
