import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "data" / "reports" / "latest_run_report.json"
PREFERENCE_PATH = ROOT / "config" / "user_preferences.json"
ANALYSIS_SUMMARY_PATH = ROOT / "results" / "analysis_cards" / "latest_analysis_summary.json"
DECISION_INPUT_PATH = ROOT / "data" / "decisions" / "pending_decisions.json"
DECISION_INBOX_PATH = ROOT / "results" / "decision_inbox" / "latest_actions.json"
FOLLOWUP_PATH = ROOT / "results" / "followups" / "latest_followup.md"
EXPOSURE_HISTORY_PATH = ROOT / "data" / "decisions" / "exposure_history.json"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: Any) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_exposure_history() -> Dict[str, Any]:
    if not EXPOSURE_HISTORY_PATH.exists():
        return {"items": {}}
    return load_json(EXPOSURE_HISTORY_PATH)


def save_exposure_history(history: Dict[str, Any]) -> None:
    history["updated_at"] = datetime.now().isoformat(timespec="seconds")
    dump_json(EXPOSURE_HISTORY_PATH, history)


def _is_recently_shown(last_shown_at: str, cooldown_days: int) -> bool:
    if not last_shown_at:
        return False
    try:
        shown_at = datetime.fromisoformat(last_shown_at)
    except ValueError:
        return False
    return datetime.now() - shown_at < timedelta(days=cooldown_days)


def build_decision_inbox(
    report: Dict[str, Any],
    preferences: Dict[str, Any],
    exposure_history: Dict[str, Any],
) -> Dict[str, Any]:
    target_status = set(preferences.get("target_status_for_review", ["APPROVED", "HOLD"]))
    max_items = int(preferences.get("max_daily_review_count", 10))
    min_preferred_slots = int(preferences.get("min_preferred_slots", 0))
    cooldown_days = int(preferences.get("review_cooldown_days", 2))
    history_items = exposure_history.get("items", {})

    candidates = [r for r in report["results"] if r["status"] in target_status]
    candidates.sort(key=lambda r: r.get("recommendation_score", 0), reverse=True)

    fresh: List[Dict[str, Any]] = []
    repeat: List[Dict[str, Any]] = []
    for row in candidates:
        prev = history_items.get(row["candidate_id"], {})
        status_changed = prev.get("last_status") != row.get("status")
        recently_shown = _is_recently_shown(prev.get("last_shown_at", ""), cooldown_days)
        if (not recently_shown) or status_changed:
            fresh.append({**row, "is_repeat": False})
        else:
            repeat.append({**row, "is_repeat": True})

    preferred_fresh = [row for row in fresh if row.get("region_priority") == "PREFERRED"]
    non_preferred_fresh = [row for row in fresh if row.get("region_priority") != "PREFERRED"]
    preferred_repeat = [row for row in repeat if row.get("region_priority") == "PREFERRED"]
    non_preferred_repeat = [row for row in repeat if row.get("region_priority") != "PREFERRED"]

    shortlisted: List[Dict[str, Any]] = []
    shortlisted.extend(preferred_fresh[:min_preferred_slots])
    if len(shortlisted) < min_preferred_slots:
        need = min_preferred_slots - len(shortlisted)
        shortlisted.extend(preferred_repeat[:need])

    remaining_pool = [*non_preferred_fresh, *preferred_fresh[min_preferred_slots:], *non_preferred_repeat, *preferred_repeat]
    for row in remaining_pool:
        if len(shortlisted) >= max_items:
            break
        if row["candidate_id"] not in {x["candidate_id"] for x in shortlisted}:
            shortlisted.append(row)

    preferred_supply_total = len([r for r in candidates if r.get("region_priority") == "PREFERRED"])
    preferred_in_shortlist = len([r for r in shortlisted if r.get("region_priority") == "PREFERRED"])
    preferred_shortage = max(0, min_preferred_slots - preferred_supply_total)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_guide": "각 후보를 보고 APPROVE 또는 PASS를 입력하세요. APPROVE 시 후속 액션이 생성됩니다.",
        "cooldown_days": cooldown_days,
        "min_preferred_slots": min_preferred_slots,
        "preferred_supply_total": preferred_supply_total,
        "preferred_in_shortlist": preferred_in_shortlist,
        "preferred_shortage": preferred_shortage,
        "shortlist": shortlisted,
    }


def update_exposure_history(shortlist: List[Dict[str, Any]], history: Dict[str, Any]) -> Dict[str, Any]:
    items = history.get("items", {})
    now = datetime.now().isoformat(timespec="seconds")
    for row in shortlist:
        cid = row["candidate_id"]
        prev = items.get(cid, {})
        items[cid] = {
            "candidate_id": cid,
            "last_shown_at": now,
            "last_status": row.get("status", "UNKNOWN"),
            "shown_count": int(prev.get("shown_count", 0)) + 1,
        }
    history["items"] = items
    return history


def load_analysis_map() -> Dict[str, Dict[str, Any]]:
    if not ANALYSIS_SUMMARY_PATH.exists():
        return {}
    summary = load_json(ANALYSIS_SUMMARY_PATH)
    return {row["candidate_id"]: row for row in summary.get("items", [])}


def parse_decision_map(decision_input: Dict[str, Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for row in decision_input.get("decisions", []):
        mapping[row.get("candidate_id", "")] = row.get("decision", "PENDING")
    return mapping


def sync_decision_input(shortlist: List[Dict[str, Any]], existing_input: Dict[str, Any]) -> Dict[str, Any]:
    old_map = {
        row.get("candidate_id"): row
        for row in existing_input.get("decisions", [])
        if row.get("candidate_id")
    }
    merged: List[Dict[str, str]] = []
    for item in shortlist:
        cid = item["candidate_id"]
        prev = old_map.get(cid, {})
        merged.append(
            {
                "candidate_id": cid,
                "decision": prev.get("decision", "PENDING"),
                "comment": prev.get("comment", ""),
            }
        )

    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "decisions": merged,
        "allowed_decisions": ["APPROVE", "PASS", "PENDING"],
    }


def write_followup(
    shortlist: List[Dict[str, Any]],
    decision_map: Dict[str, str],
    preferred_shortage: int = 0,
) -> None:
    analysis_map = load_analysis_map()
    lines = [
        "# 자동 후속 조치",
        "",
        f"생성시각: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]

    if preferred_shortage > 0:
        lines.extend(
            [
                "## 데이터 수집 보강 필요",
                "",
                f"- 대구/인근 우선 후보가 최소 슬롯 대비 {preferred_shortage}개 부족합니다.",
                "- 다음 실행 전 대구/경산/구미 신규 물건을 원본 데이터에 추가하세요.",
                "",
            ]
        )

    approved = [item for item in shortlist if decision_map.get(item["candidate_id"]) == "APPROVE"]
    passed = [item for item in shortlist if decision_map.get(item["candidate_id"]) == "PASS"]
    pending = [item for item in shortlist if decision_map.get(item["candidate_id"], "PENDING") == "PENDING"]

    lines.extend(["## APPROVE", ""])
    if not approved:
        lines.append("- 승인된 후보 없음")
    else:
        for item in approved:
            lines.extend(
                [
                    f"- {item['candidate_id']} ({item['location']})",
                    "  - 24시간 이내 현장조사 일정 확정",
                    "  - 등기/임차/배당 체크리스트 재검증",
                    f"  - 최대입찰가 상한 확인: {item['max_bid']:,}원",
                    f"  - 분석카드: {analysis_map.get(item['candidate_id'], {}).get('card_path', '없음')}",
                ]
            )

    lines.extend(["", "## PASS", ""])
    if not passed:
        lines.append("- PASS 없음")
    else:
        for item in passed:
            lines.append(f"- {item['candidate_id']}: 사유 기록 후 후보군에서 제외")

    lines.extend(["", "## PENDING", ""])
    if not pending:
        lines.append("- PENDING 없음")
    else:
        for item in pending:
            lines.append(
                f"- {item['candidate_id']}: 의사결정 대기 (분석카드: "
                f"{analysis_map.get(item['candidate_id'], {}).get('card_path', '없음')})"
            )

    ensure_parent(FOLLOWUP_PATH)
    FOLLOWUP_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    report = load_json(REPORT_PATH)
    preferences = load_json(PREFERENCE_PATH)
    exposure_history = load_exposure_history()
    inbox = build_decision_inbox(report, preferences, exposure_history)
    dump_json(DECISION_INBOX_PATH, inbox)
    save_exposure_history(update_exposure_history(inbox["shortlist"], exposure_history))

    decision_input = load_json(DECISION_INPUT_PATH) if DECISION_INPUT_PATH.exists() else {"decisions": []}
    synced_input = sync_decision_input(inbox["shortlist"], decision_input)
    dump_json(DECISION_INPUT_PATH, synced_input)
    decision_map = parse_decision_map(synced_input)
    write_followup(inbox["shortlist"], decision_map, int(inbox.get("preferred_shortage", 0)))

    print(f"Saved: {DECISION_INBOX_PATH}")
    print(f"Saved: {DECISION_INPUT_PATH}")
    print(f"Saved: {FOLLOWUP_PATH}")
    print(f"Saved: {EXPOSURE_HISTORY_PATH}")


if __name__ == "__main__":
    main()
