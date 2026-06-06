import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent.parent
INBOX_PATH = ROOT / "results" / "decision_inbox" / "latest_actions.json"
DECISIONS_PATH = ROOT / "data" / "decisions" / "pending_decisions.json"
REPORT_PATH = ROOT / "data" / "reports" / "latest_run_report.json"
ANALYSIS_SUMMARY_PATH = ROOT / "results" / "analysis_cards" / "latest_analysis_summary.json"
FOLLOWUP_PATH = ROOT / "results" / "followups" / "latest_followup.md"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def run_script(script_name: str) -> subprocess.CompletedProcess:
    script_path = ROOT / "src" / script_name
    return subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def decision_map(decisions: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {row["candidate_id"]: row for row in decisions.get("decisions", [])}


def analysis_map(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {row["candidate_id"]: row for row in summary.get("items", [])}


st.set_page_config(page_title="Auction Study Dashboard", layout="wide")
st.title("한국 법원경매 자동운영 대시보드")

col_a, col_b = st.columns(2)
if col_a.button("전체 자동 실행", use_container_width=True):
    completed = run_script("auto_run.py")
    if completed.returncode == 0:
        st.success("auto_run.py 실행 완료")
    else:
        st.error(f"실행 실패: {completed.stderr}")

if col_b.button("결정 반영 후 Follow-up 갱신", use_container_width=True):
    completed = run_script("decision_engine.py")
    if completed.returncode == 0:
        st.success("decision_engine.py 실행 완료")
    else:
        st.error(f"실행 실패: {completed.stderr}")

inbox = load_json(INBOX_PATH, {"shortlist": []})
decisions = load_json(DECISIONS_PATH, {"decisions": [], "allowed_decisions": ["APPROVE", "PASS", "PENDING"]})
report = load_json(REPORT_PATH, {"summary": {"by_status": {"APPROVED": 0, "HOLD": 0, "REJECT": 0}}})
analysis_summary = load_json(ANALYSIS_SUMMARY_PATH, {"items": []})
analysis_by_id = analysis_map(analysis_summary)
decision_by_id = decision_map(decisions)

sum_col1, sum_col2, sum_col3 = st.columns(3)
sum_col1.metric("APPROVED", report["summary"]["by_status"].get("APPROVED", 0))
sum_col2.metric("HOLD", report["summary"]["by_status"].get("HOLD", 0))
sum_col3.metric("REJECT", report["summary"]["by_status"].get("REJECT", 0))

st.subheader("오늘 검토 후보")
shortlist: List[Dict[str, Any]] = inbox.get("shortlist", [])
preferred_shortage = int(inbox.get("preferred_shortage", 0))
if preferred_shortage > 0:
    st.warning(
        "대구/인근 후보 공급이 부족합니다. "
        f"(목표 최소 {inbox.get('min_preferred_slots', 0)}개, 현재 공급 {inbox.get('preferred_supply_total', 0)}개)"
    )
if not shortlist:
    st.info("shortlist가 비어 있습니다. auto_run.py를 먼저 실행하세요.")
else:
    preview_rows = []
    for item in shortlist:
        card = analysis_by_id.get(item["candidate_id"], {})
        preview_rows.append(
            {
                "후보ID": item["candidate_id"],
                "상태": item.get("status", ""),
                "권역우선도": item.get("region_priority", ""),
                "법원": item.get("court_name", ""),
                "법원정보링크": item.get("court_info_url", ""),
                "물건바로보기": (
                    (item.get("quick_links") or {}).get("court_detail_url")
                    or (item.get("quick_links") or {}).get("naver_search_url")
                    or ""
                ),
                "매각기일": item.get("sale_date", ""),
                "주소": item.get("location", ""),
                "추천점수": item.get("recommendation_score", 0),
                "분석점수": card.get("total_analysis_score", "-"),
                "리스크등급": card.get("risk_level", "-"),
                "체크리스트충족률(%)": item.get("checklist_completion", 0),
                "예상수익률": item.get("expected_margin_rate", 0),
                "최대입찰가": item.get("max_bid", 0),
                "반복노출": "예" if item.get("is_repeat", False) else "아니오",
            }
        )
    st.dataframe(preview_rows, use_container_width=True)
    st.caption("상단 표에서 후보를 1차 비교하고, 아래 카드에서 상세 확인 후 결정하세요.")

    for item in shortlist:
        cid = item["candidate_id"]
        decision_row = decision_by_id.get(cid, {"decision": "PENDING", "comment": ""})
        card_info = analysis_by_id.get(cid, {})
        with st.expander(f"{cid} | {item.get('location', '')} | score {item.get('recommendation_score', 0)}"):
            st.write(
                f"상태: **{item.get('status', 'UNKNOWN')}** | "
                f"권역: **{item.get('region_priority', 'OTHER')}** | "
                f"기대수익률: **{item.get('expected_margin_rate', 0):.4f}**"
            )
            st.write(
                f"법원: **{item.get('court_name', '-')}** | "
                f"매각기일: **{item.get('sale_date', '-')}** | "
                f"체크리스트: **{item.get('checklist_completion', 0)}%**"
            )
            if item.get("court_info_url"):
                st.markdown(f"[법원 제공 정보 확인]({item.get('court_info_url')})")
            quick_links = item.get("quick_links") or {}
            if quick_links.get("court_detail_url"):
                st.markdown(f"[물건 바로보기(상세링크)]({quick_links.get('court_detail_url')})")
            if quick_links.get("naver_search_url"):
                st.markdown(f"[물건 바로보기(사건/주소 검색)]({quick_links.get('naver_search_url')})")
            st.write(f"최대입찰가: `{item.get('max_bid', 0):,}원`")
            if item.get("reasons"):
                st.write(f"게이트 사유: `{', '.join(item['reasons'])}`")

            st.write(
                f"분석점수: **{card_info.get('total_analysis_score', '-') }** / "
                f"리스크: **{card_info.get('risk_level', '-') }**"
            )
            card_path = card_info.get("card_path")
            if card_path and Path(card_path).exists():
                if st.button(f"{cid} 분석카드 보기", key=f"card_btn_{cid}"):
                    with Path(card_path).open("r", encoding="utf-8") as f:
                        st.code(f.read(), language="markdown")

            photo_urls = item.get("photo_urls", [])
            if photo_urls:
                st.write("물건 사진")
                st.image(photo_urls, use_container_width=True)
            else:
                st.info(item.get("photo_note", "실매물 사진이 아직 연결되지 않았습니다."))

            map_url = item.get("map_url", "")
            latitude = float(item.get("latitude", 0) or 0)
            longitude = float(item.get("longitude", 0) or 0)
            if latitude and longitude:
                st.write("위치 지도")
                st.map(pd.DataFrame([{"lat": latitude, "lon": longitude}]))
            if map_url:
                st.markdown(f"[지도 링크 열기]({map_url})")

            select_key = f"decision_{cid}"
            comment_key = f"comment_{cid}"
            new_decision = st.selectbox(
                "결정",
                options=decisions.get("allowed_decisions", ["APPROVE", "PASS", "PENDING"]),
                index=decisions.get("allowed_decisions", ["APPROVE", "PASS", "PENDING"]).index(
                    decision_row.get("decision", "PENDING")
                ),
                key=select_key,
            )
            new_comment = st.text_input("메모", value=decision_row.get("comment", ""), key=comment_key)

            if st.button(f"{cid} 결정 저장", key=f"save_btn_{cid}"):
                decision_by_id[cid] = {"candidate_id": cid, "decision": new_decision, "comment": new_comment}
                merged = {
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "allowed_decisions": decisions.get("allowed_decisions", ["APPROVE", "PASS", "PENDING"]),
                    "decisions": list(decision_by_id.values()),
                }
                save_json(DECISIONS_PATH, merged)
                st.success(f"{cid} 결정 저장 완료")

st.subheader("최신 Follow-up")
if FOLLOWUP_PATH.exists():
    st.markdown(FOLLOWUP_PATH.read_text(encoding="utf-8"))
else:
    st.info("follow-up 파일이 아직 없습니다.")
