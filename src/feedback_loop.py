import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "data" / "reports" / "latest_run_report.json"
POLICY_PATCH_PATH = ROOT / "policy" / "strategy_patch_latest.json"
WEEKLY_REVIEW_PATH = ROOT / "results" / "weekly_reviews" / "latest_review.md"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_report() -> Dict[str, Any]:
    with REPORT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def aggregate_reasons(results: List[Dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for item in results:
        for reason in item.get("reasons", []):
            counter[reason] += 1
    return counter


def build_strategy_patch(reason_counter: Counter) -> Dict[str, Any]:
    patch = {
        "profile": "small_capital_conservative",
        "changes": [],
        "learning_topics": [],
    }

    if reason_counter["RESERVE_TOO_LOW"] >= 1:
        patch["changes"].append(
            {
                "target": "capital_plan",
                "action": "increase_reserve_cash",
                "note": "예비비 부족 사례가 발생해 최소 예비비 점검 빈도를 늘린다."
            }
        )

    if reason_counter["RIGHTS_UNCLEAR"] >= 1:
        patch["learning_topics"].append("말소기준권리와 대항력 사례 복습")

    if reason_counter["MARGIN_TOO_LOW"] >= 1:
        patch["changes"].append(
            {
                "target": "valuation",
                "action": "tighten_cost_buffer",
                "note": "수익률 부족 사례가 있어 비용 버퍼를 5% 상향 점검한다."
            }
        )

    if not patch["changes"]:
        patch["changes"].append(
            {
                "target": "operation",
                "action": "keep_current_policy",
                "note": "정책 변경 없이 현행 규칙을 유지한다."
            }
        )

    if not patch["learning_topics"]:
        patch["learning_topics"].append("실전 체크리스트 반복 훈련")

    return patch


def write_weekly_review(report: Dict[str, Any], reason_counter: Counter, patch: Dict[str, Any]) -> None:
    lines = [
        "# 주간 복기 리포트",
        "",
        "## 실행 요약",
        f"- 총 후보 수: {report['summary']['total']}",
        f"- 승인: {report['summary']['by_status'].get('APPROVED', 0)}",
        f"- 보류: {report['summary']['by_status'].get('HOLD', 0)}",
        f"- 탈락: {report['summary']['by_status'].get('REJECT', 0)}",
        "",
        "## 주요 실패 사유",
    ]

    if reason_counter:
        for reason, count in reason_counter.most_common():
            lines.append(f"- {reason}: {count}건")
    else:
        lines.append("- 실패 사유 없음")

    lines.extend(
        [
            "",
            "## 다음 주 전략 패치",
        ]
    )
    for change in patch["changes"]:
        lines.append(f"- {change['target']} / {change['action']}: {change['note']}")

    lines.extend(
        [
            "",
            "## 학습 강화 주제",
        ]
    )
    for topic in patch["learning_topics"]:
        lines.append(f"- {topic}")

    ensure_parent(WEEKLY_REVIEW_PATH)
    WEEKLY_REVIEW_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = load_report()
    reasons = aggregate_reasons(report["results"])
    patch = build_strategy_patch(reasons)

    ensure_parent(POLICY_PATCH_PATH)
    with POLICY_PATCH_PATH.open("w", encoding="utf-8") as f:
        json.dump(patch, f, ensure_ascii=False, indent=2)

    write_weekly_review(report, reasons, patch)
    print(f"Saved: {POLICY_PATCH_PATH}")
    print(f"Saved: {WEEKLY_REVIEW_PATH}")


if __name__ == "__main__":
    main()
