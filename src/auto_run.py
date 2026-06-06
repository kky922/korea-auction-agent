import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent

# .env 파일 자동 로딩
_env_path = ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from telegram_notifier import is_configured, send_lines, send_message
RUN_LOG = ROOT / "logs" / "auto_run.log"
DAILY_STATE_PATH = ROOT / "logs" / "telegram_daily_state.json"
FOLLOWUP_PATH = ROOT / "results" / "followups" / "latest_followup.md"
ANALYSIS_SUMMARY_PATH = ROOT / "results" / "analysis_cards" / "latest_analysis_summary.json"
DECISION_INBOX_PATH = ROOT / "results" / "decision_inbox" / "latest_actions.json"
WEEKLY_REVIEW_PATH = ROOT / "results" / "weekly_reviews" / "latest_review.md"
REPORT_PATH = ROOT / "data" / "reports" / "latest_run_report.json"
WATCH_FILES: List[Path] = [
    FOLLOWUP_PATH,
    ANALYSIS_SUMMARY_PATH,
    DECISION_INBOX_PATH,
    WEEKLY_REVIEW_PATH,
]
SCRIPTS: List[Path] = [
    ROOT / "crawler" / "court_auction.py",   # 1. 크롤링 → data/raw/daegu_cases.json
    ROOT / "src" / "input_adapter.py",        # 2. 정규화 → data/candidates/latest_candidates.json
    ROOT / "src" / "pipeline.py",             # 3. 게이트 평가
    ROOT / "src" / "feedback_loop.py",        # 4. 피드백
    ROOT / "src" / "property_analysis.py",    # 5. 분석 카드
    ROOT / "src" / "decision_engine.py",      # 6. 결정 inbox
]

# 크롤러는 Playwright가 설치된 venv에서 실행
CRAWLER_PYTHON = Path(os.environ.get("CRAWLER_PYTHON", sys.executable))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_log(message: str) -> None:
    ensure_parent(RUN_LOG)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def _probe_chromium_executable() -> Optional[Path]:
    if not CRAWLER_PYTHON.exists():
        return None
    probe = [
        str(CRAWLER_PYTHON),
        "-c",
        (
            "from pathlib import Path; "
            "from playwright.sync_api import sync_playwright; "
            "p = sync_playwright().start(); "
            "print(Path(p.chromium.executable_path)); "
            "p.stop()"
        ),
    ]
    completed = subprocess.run(probe, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        return None
    executable = Path(completed.stdout.strip().splitlines()[-1])
    return executable if executable.exists() else None


def ensure_crawler_browser() -> bool:
    if _probe_chromium_executable() is not None:
        return True

    append_log("Chromium missing for court_auction.py: running playwright install chromium")
    install_cmd = [str(CRAWLER_PYTHON), "-m", "playwright", "install", "chromium"]
    try:
        completed = subprocess.run(install_cmd, capture_output=True, text=True, check=True, timeout=1800)
    except subprocess.CalledProcessError as exc:
        append_log("Chromium install failed")
        if exc.stdout:
            append_log(exc.stdout.strip())
        if exc.stderr:
            append_log(exc.stderr.strip())
        return False

    if completed.stdout.strip():
        append_log(completed.stdout.strip())
    if completed.stderr.strip():
        append_log(completed.stderr.strip())

    executable = _probe_chromium_executable()
    if executable is None:
        append_log("Chromium install finished, but the executable is still missing")
        return False

    append_log(f"Chromium ready: {executable}")
    return True


def run_script(script_path: Path) -> bool:
    is_crawler = script_path.name == "court_auction.py"
    interpreter = str(CRAWLER_PYTHON) if is_crawler and CRAWLER_PYTHON.exists() else sys.executable
    cmd = [interpreter, str(script_path)]

    if is_crawler and not ensure_crawler_browser():
        append_log(f"[{datetime.now().isoformat(timespec='seconds')}] FAIL {script_path.name}")
        if is_configured():
            send_message(
                "[auction_study] court_auction.py 실패\nChromium/Playwright 브라우저 확인 또는 설치에 실패했습니다.",
                code_block=True,
            )
        return False

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        append_log(f"[{datetime.now().isoformat(timespec='seconds')}] FAIL {script_path.name}")
        if exc.stdout:
            append_log(exc.stdout.strip())
        if exc.stderr:
            append_log(exc.stderr.strip())
        if is_configured():
            preview = (exc.stderr or exc.stdout or "").strip().splitlines()
            detail = preview[-1] if preview else "unknown error"
            send_message(
                f"[auction_study] {script_path.name} 실패\n{detail}",
                code_block=True,
            )
        return False

    append_log(f"[{datetime.now().isoformat(timespec='seconds')}] OK {script_path.name}")
    if completed.stdout.strip():
        append_log(completed.stdout.strip())
    if completed.stderr.strip():
        append_log(completed.stderr.strip())
    return True


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def get_mtimes(paths: List[Path]) -> Dict[Path, float]:
    out: Dict[Path, float] = {}
    for p in paths:
        if p.exists():
            try:
                out[p] = p.stat().st_mtime
            except OSError:
                pass
    return out


def build_run_summary_lines(updated_paths: List[Path]) -> List[str]:
    report = read_json(REPORT_PATH, {})
    by_status = ((report.get("summary") or {}).get("by_status") or {}) if isinstance(report, dict) else {}
    hold = int(by_status.get("HOLD", 0) or 0)
    reject = int(by_status.get("REJECT", 0) or 0)

    now = datetime.now().strftime("%m/%d %H:%M")
    lines = [
        f"[{now}] 파이프라인 완료",
        f"HOLD {hold}건  |  REJECT {reject}건",
    ]
    if hold > 0:
        lines.append("→ 09:00 분석카드 발송 예정")
    return lines


def _shortlist_preview(shortlist: List[dict], limit: int = 3) -> List[str]:
    preview_lines: List[str] = []
    for item in shortlist[:limit]:
        cid = item.get("candidate_id", "-")
        loc = item.get("location", "-")
        score = item.get("recommendation_score", 0)
        preview_lines.append(f"  • {cid} | {loc} | score {score}")
    return preview_lines


def build_dashboard_snapshot_lines() -> List[str]:
    report = read_json(REPORT_PATH, {})
    by_status = ((report.get("summary") or {}).get("by_status") or {}) if isinstance(report, dict) else {}
    approved = int(by_status.get("APPROVED", 0) or 0)
    hold = int(by_status.get("HOLD", 0) or 0)
    reject = int(by_status.get("REJECT", 0) or 0)

    inbox = read_json(DECISION_INBOX_PATH, {})
    shortlist = inbox.get("shortlist", []) if isinstance(inbox, dict) else []
    preferred_shortage = int(inbox.get("preferred_shortage", 0) or 0) if isinstance(inbox, dict) else 0
    preferred_supply_total = int(inbox.get("preferred_supply_total", 0) or 0) if isinstance(inbox, dict) else 0
    min_preferred_slots = int(inbox.get("min_preferred_slots", 0) or 0) if isinstance(inbox, dict) else 0
    actions = inbox.get("actions", []) if isinstance(inbox, dict) else []

    lines = [
        f"- 상태 집계: APPROVED {approved} | HOLD {hold} | REJECT {reject}",
        f"- 오늘 검토 후보(shortlist): {len(shortlist) if isinstance(shortlist, list) else 0}",
        f"- 추천 액션 수: {len(actions) if isinstance(actions, list) else 0}",
    ]
    if preferred_shortage > 0:
        lines.append(
            f"- 권역 공급 부족: 목표 {min_preferred_slots} / 공급 {preferred_supply_total} (부족 {preferred_shortage})"
        )
    if isinstance(shortlist, list) and shortlist:
        lines.append("- shortlist 상위:")
        lines.extend(_shortlist_preview(shortlist))
    return lines


def _pick_top_analysis_cards(limit: int = 4) -> List[dict]:
    summary = read_json(ANALYSIS_SUMMARY_PATH, {})
    items = summary.get("items", []) if isinstance(summary, dict) else []
    if not isinstance(items, list):
        return []
    sorted_items = sorted(
        [i for i in items if isinstance(i, dict)],
        key=lambda x: float(x.get("total_analysis_score", 0) or 0),
        reverse=True,
    )
    return sorted_items[:limit]


def _candidate_context_by_id(candidate_id: str) -> dict:
    inbox = read_json(DECISION_INBOX_PATH, {})
    shortlist = inbox.get("shortlist", []) if isinstance(inbox, dict) else []
    if not isinstance(shortlist, list):
        return {}
    for item in shortlist:
        if isinstance(item, dict) and item.get("candidate_id") == candidate_id:
            return item
    return {}


def _load_card_text(card_path: str, fallback: dict) -> str:
    cid = fallback.get("candidate_id", "-")
    try:
        p = Path(card_path)
        if p.exists():
            body = p.read_text(encoding="utf-8").strip()
            if len(body) > 3800:
                body = body[:3800] + "\n... (생략)"
            return body
    except Exception:
        pass
    return f"🏠 {cid} — 카드 파일을 읽을 수 없습니다."


def maybe_send_run_update_alert(before: Dict[Path, float]) -> None:
    if not is_configured():
        append_log("Telegram not configured: skip run-update alert")
        return

    after = get_mtimes(WATCH_FILES)
    updated: List[Path] = []
    for p in WATCH_FILES:
        b = before.get(p)
        a = after.get(p)
        if a is None:
            continue
        if b is None or a > b:
            updated.append(p)

    sent = send_lines("[auction_study] 결과 갱신 알림", build_run_summary_lines(updated))
    append_log(f"Telegram run-update alert: {'sent' if sent else 'failed'}")


def _today_kst() -> str:
    from datetime import timezone, timedelta

    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")


def maybe_send_daily_summary(force: bool = False) -> None:
    if not is_configured():
        append_log("Telegram not configured: skip daily summary")
        return

    state = read_json(DAILY_STATE_PATH, {})
    today = _today_kst()
    last_sent = state.get("last_daily_summary_date", "")
    if (last_sent == today) and not force:
        append_log("Daily summary already sent today: skip")
        return

    top_cards = [c for c in _pick_top_analysis_cards(limit=4) if c.get("status") in ("HOLD", "APPROVED")]
    if not top_cards:
        append_log("Telegram daily cards: HOLD 물건 없음, 발송 생략")
        sent = True
    else:
        now_str = datetime.now().strftime("%m/%d %H:%M")
        header = (
            f"📋 경매봇 일일 리포트 ({now_str})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"예산: 2억 이하  |  지역: 대구·경북\n"
            f"물건: 아파트·연립·다세대·오피스텔\n"
            f"조건: 유찰 2~4회, 최저가 ≤70%\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"HOLD {len(top_cards)}건 발송"
        )
        send_message(header, code_block=True)
        sent = True
        candidates = read_json(ROOT / "data" / "candidates" / "latest_candidates.json", [])
        cand_map = {c["candidate_id"]: c for c in candidates if isinstance(c, dict)}
        for idx, card in enumerate(top_cards, start=1):
            card_text = _load_card_text(str(card.get("card_path", "")), card)
            ok = send_message(f"🏠 경매봇 분석카드 {idx}/{len(top_cards)}\n{card_text}", code_block=True)
            # 네이버 지도 링크를 코드블록 밖 별도 메시지로 발송
            cid = card.get("candidate_id", "")
            cand = cand_map.get(cid, {})
            naver_url = (cand.get("quick_links") or {}).get("naver_search_url", "")
            location = cand.get("location", cid)
            # 주소에서 괄호 이후 불필요한 부분 제거
            short_loc = location.split("[")[0].strip() if "[" in location else location
            if naver_url:
                send_message(f'🗺️ <a href="{naver_url}">{short_loc}</a>', html=True)
            append_log(f"Telegram daily card {idx}/{len(top_cards)}: {'sent' if ok else 'failed'}")
            sent = sent and ok
        append_log(f"Telegram daily cards(overall): {'sent' if sent else 'failed'}")
    if sent:
        ensure_parent(DAILY_STATE_PATH)
        state["last_daily_summary_date"] = today
        DAILY_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main(send_daily_summary: bool = False, force_daily_summary: bool = False) -> None:
    append_log(f"[{datetime.now().isoformat(timespec='seconds')}] AUTO RUN START")
    success = True
    for script in SCRIPTS:
        if not run_script(script):
            success = False
            break
    append_log(f"[{datetime.now().isoformat(timespec='seconds')}] AUTO RUN END")
    if send_daily_summary and success:
        maybe_send_daily_summary(force=force_daily_summary)
    elif send_daily_summary and not success:
        append_log("Daily summary skipped because upstream script failed")
    print("Auto run completed" if success else "Auto run completed with errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-summary", action="store_true")
    parser.add_argument("--force-daily-summary", action="store_true")
    args = parser.parse_args()
    main(send_daily_summary=args.daily_summary, force_daily_summary=args.force_daily_summary)
