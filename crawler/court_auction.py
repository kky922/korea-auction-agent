"""
법원경매정보 크롤러 (대구/경북 특화)
대상: https://www.courtauction.go.kr

필터: 아파트/연립/다세대/오피스텔, 유찰 2~4회, 최저가/감정가 ≤70%
출력: data/raw/daegu_cases.json (파이프라인 호환 형식)
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "data" / "raw" / "daegu_cases.json"

TARGET_REGIONS = [
    ("대구", "대구광역시"),
    ("경북", "경상북도"),
]

ALLOWED_TYPES = {"아파트", "연립", "다세대", "오피스텔"}
MIN_FAILED = 2
MAX_FAILED = 4
MAX_BID_RATIO = 0.70

# 비고란 위험 키워드 → rights_clear=False
RIGHTS_RISK_KEYWORDS = {
    "유치권", "법정지상권", "분묘기지권", "지분매각", "토지별도등기",
    "선순위임차인", "대항력있는임차인", "가처분", "가등기",
}
# 비고란 명도 난이도 상향 키워드
EVICTION_HIGH_KEYWORDS = {"유치권", "점유", "임차인", "불법점유"}
EVICTION_LOW_KEYWORDS  = {"공가", "빈집", "명도완료", "인도명령"}

COURT_ID_MAP = {
    "대구지방법원": "DAEGU",
    "대구지방법원 서부지원": "DAEGU-W",
    "대구지방법원 경산지원": "GYEONGSAN",
    "대구지방법원 경주지원": "GYEONGJU",
    "대구지방법원 포항지원": "POHANG",
    "대구지방법원 김천지원": "GIMCHEON",
    "대구지방법원 안동지원": "ANDONG",
    "대구지방법원 구미지원": "GUMI",
    "대구지방법원 의성지원": "UISEONG",
    "대구지방법원 영덕지원": "YEONGDEOK",
    "대구지방법원 상주지원": "SANGJU",
}

TYPE_MAP = {
    "아파트": "apartment",
    "연립": "villa",
    "다세대": "villa",
    "오피스텔": "officetel",
}

# rowspan carry-forward 방식으로 메인행(8칸)+서브행(3칸) 파싱
PARSE_JS = """() => {
    const tbody = document.querySelectorAll("table tbody")[1];
    if (!tbody) return [];
    const trs = Array.from(tbody.querySelectorAll("tr"));
    const rows = [];
    for (let i = 0; i < trs.length; i++) {
        const tds = Array.from(trs[i].querySelectorAll("td"));
        rows.push({
            count: tds.length,
            cells: tds.map(function(td) { return td.innerText.trim(); })
        });
    }
    return rows;
}"""


def parse_rows(raw_rows: list) -> list:
    results = []
    last = {
        "사건번호": "", "법원명": "", "용도": "",
        "최저매각가격": "", "진행상태": "", "감정가": "",
        "매각기일": "", "비고": "",
    }

    i = 0
    while i < len(raw_rows):
        main = raw_rows[i]
        i += 1
        if main["count"] != 8:
            continue

        c = main["cells"]
        case_raw = c[1]

        # 법원명: 첫 줄 (타경 없는 줄)
        all_lines = [l.strip() for l in case_raw.split("\n") if l.strip()]
        court_name = next((l for l in all_lines if "타경" not in l and "중복" not in l), last["법원명"])

        case_lines = [l for l in all_lines if "타경" in l]
        case_num = " / ".join(case_lines) if case_lines else last["사건번호"]

        sojaej = c[3].replace("[지도]", "").strip()
        bigo = c[5] if c[5] else last["비고"]
        appraised = c[6] if c[6] else last["감정가"]
        sale_date = c[7].split("\n")[-1].strip() if c[7] else last["매각기일"]

        yongdo = min_price = status = ""
        if i < len(raw_rows) and raw_rows[i]["count"] == 3:
            s = raw_rows[i]["cells"]
            yongdo = s[0] if s[0] else last["용도"]
            min_price = s[1] if s[1] else last["최저매각가격"]
            status = s[2] if s[2] else last["진행상태"]
            i += 1

        if court_name: last["법원명"] = court_name
        if case_num:   last["사건번호"] = case_num
        if bigo:       last["비고"] = bigo
        if appraised:  last["감정가"] = appraised
        if sale_date:  last["매각기일"] = sale_date
        if yongdo:     last["용도"] = yongdo
        if min_price:  last["최저매각가격"] = min_price
        if status:     last["진행상태"] = status

        if not sojaej or "소재지" in sojaej or "총 물건수" in sojaej:
            continue

        results.append({
            "사건번호": case_num,
            "법원명": court_name,
            "소재지": sojaej,
            "비고": bigo,
            "감정가": appraised,
            "최저매각가격": min_price,
            "매각기일": sale_date,
            "용도": yongdo,
            "진행상태": status,
        })

    return results


def parse_price(text: str) -> int:
    line = text.split("\n")[0]
    cleaned = re.sub(r"[^\d]", "", line)
    return int(cleaned) if cleaned else 0


def parse_bid_ratio(text: str) -> float:
    """'18,094,647,000\n(51%)' → 0.51"""
    match = re.search(r"\((\d+)%\)", text)
    if match:
        return int(match.group(1)) / 100
    return 1.0


def parse_failed_count(status: str) -> int:
    match = re.search(r"유찰\s*(\d+)회", status)
    return int(match.group(1)) if match else 0


HARD_EXCLUDE_KEYWORDS = {"유치권", "법정지상권", "분묘기지권", "지분매각"}


def passes_filter(item: dict) -> bool:
    yongdo = item.get("용도", "")
    status = item.get("진행상태", "")
    min_price_text = item.get("최저매각가격", "")
    bigo = item.get("비고", "")

    if not any(t in yongdo for t in ALLOWED_TYPES):
        return False

    failed = parse_failed_count(status)
    if not (MIN_FAILED <= failed <= MAX_FAILED):
        return False

    ratio = parse_bid_ratio(min_price_text)
    if ratio > MAX_BID_RATIO:
        return False

    # 비고란 하드 제외 (유치권·법정지상권 등 법적 리스크 큰 물건)
    if any(kw in bigo for kw in HARD_EXCLUDE_KEYWORDS):
        return False

    return True


def make_case_id(court_name: str, case_num: str) -> str:
    prefix = COURT_ID_MAP.get(court_name, "DAEGU")
    match = re.search(r"(\d{4})타경(\d+)", case_num)
    if match:
        return f"{prefix}-{match.group(1)}-{match.group(2)}"
    safe = re.sub(r"[^A-Za-z0-9]", "-", case_num)[:20]
    return f"{prefix}-{safe}"


def analyze_bigo(bigo: str) -> dict:
    """비고란 텍스트로 권리관계·명도 난이도 자동 판별"""
    rights_clear = True
    eviction_level = "MEDIUM"
    risk_flags = []

    for kw in RIGHTS_RISK_KEYWORDS:
        if kw in bigo:
            rights_clear = False
            risk_flags.append(kw)

    if any(kw in bigo for kw in EVICTION_HIGH_KEYWORDS):
        eviction_level = "HIGH"
    elif any(kw in bigo for kw in EVICTION_LOW_KEYWORDS):
        eviction_level = "LOW"

    return {
        "rights_clear": rights_clear,
        "eviction_risk_level": eviction_level,
        "risk_flags": risk_flags,
    }


def to_pipeline_format(item: dict) -> dict:
    court_name = item.get("법원명", "대구지방법원")
    case_num = item.get("사건번호", "")
    address = " ".join(item.get("소재지", "").split())
    yongdo = item.get("용도", "")
    appraised = parse_price(item.get("감정가", "0"))
    min_bid = parse_price(item.get("최저매각가격", "0"))
    sale_date = item.get("매각기일", "").replace(".", "-")

    prop_type = "apartment"
    for k, v in TYPE_MAP.items():
        if k in yongdo:
            prop_type = v
            break

    # 예상 매각가: 감정가 85% (보수적 시세 추정, 실사 후 수정 필요)
    expected_resale = int(appraised * 0.85) if appraised > 0 else int(min_bid * 1.3)

    bigo = item.get("비고", "")
    rights_info = analyze_bigo(bigo)
    risk_note = f" | 위험요소: {', '.join(rights_info['risk_flags'])}" if rights_info["risk_flags"] else ""

    return {
        "case_id": make_case_id(court_name, case_num),
        "court_name": court_name,
        "court_info_url": "https://www.courtauction.go.kr/",
        "sale_date": sale_date,
        "address": address,
        "property_type": prop_type,
        "minimum_bid_price": str(min_bid),
        "estimated_sale_price_reason": f"크롤러 자동수집 | 감정가 {appraised:,}원 | 유찰 {item.get('진행상태', '')}",
        "expected_resale_price": str(expected_resale),
        "repair_cost": "1200000",
        "repair_cost_reason": "기본 수리비 추정 (임장 전 기본값)",
        "acquisition_cost": "1300000",
        "acquisition_cost_reason": "취득세+등기+법무 기본 추정",
        "other_cost": "500000",
        "other_cost_reason": "명도비/관리비/잡비 기본 추정",
        "reserve_cash": "3000000",
        "photo_urls": [],
        "photo_note": "크롤러 자동수집 | 사진 미연동",
        "map_url": f"https://map.naver.com/p/search/{address}",
        "latitude": 0.0,
        "longitude": 0.0,
        "rights_clear": rights_info["rights_clear"],
        "eviction_risk_level": rights_info["eviction_risk_level"],
        "bigo": bigo,
        "rights_note": f"비고 자동분석{risk_note}" if bigo else "비고 없음",
        "site_visit_done": False,
        "documents_ready": False,
        "funding_plan_ready": False,
    }


async def scrape_region(page, region_label: str, max_pages: int = 5) -> list:
    results = []
    try:
        await page.goto("https://www.courtauction.go.kr", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        await page.click("#mf_btn_rletRpdt")
        await page.wait_for_timeout(1500)

        await page.select_option("#mf_sbx_rletRpdtSdLst", label=region_label)
        await page.wait_for_timeout(1500)

        await page.click("#mf_btn_quickSearchGds")
        await page.wait_for_timeout(5000)

        for page_num in range(1, max_pages + 1):
            print(f"  [{region_label}] 페이지 {page_num}...")

            raw_rows = await page.evaluate(PARSE_JS)
            items = parse_rows(raw_rows)
            passed = [item for item in items if passes_filter(item)]
            excluded_bigo = [
                item for item in items
                if not passes_filter(item) and any(kw in item.get("비고", "") for kw in HARD_EXCLUDE_KEYWORDS)
            ]
            results.extend(passed)
            print(f"    → {len(items)}건 중 {len(passed)}건 통과"
                  + (f" | 비고 제외 {len(excluded_bigo)}건" if excluded_bigo else ""))

            if page_num < max_pages:
                next_btn = page.locator("a:has-text('다음'), button:has-text('다음')").first
                if await next_btn.count() > 0 and await next_btn.is_enabled():
                    await next_btn.click()
                    await page.wait_for_timeout(2500)
                else:
                    print(f"  [{region_label}] 마지막 페이지")
                    break

    except Exception as e:
        print(f"[{region_label}] 오류: {e}")
        try:
            await page.screenshot(path=str(ROOT / "crawler" / f"debug_{region_label}.png"))
        except Exception:
            pass

    return results


async def run() -> list:
    all_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        for _, label in TARGET_REGIONS:
            print(f"\n=== {label} 크롤링 ===")
            items = await scrape_region(page, label, max_pages=5)
            all_items.extend(items)
            await page.wait_for_timeout(3000)

        await browser.close()

    return all_items


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 크롤링 시작")
    print(f"필터: {ALLOWED_TYPES} | 유찰 {MIN_FAILED}~{MAX_FAILED}회 | 비율 ≤{int(MAX_BID_RATIO*100)}%")

    items = asyncio.run(run())

    if not items:
        print("조건에 맞는 물건 없음")
        # 빈 파일 유지 (파이프라인이 빈 리스트로 돌아가게)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text("[]", encoding="utf-8")
        return

    pipeline_items = [to_pipeline_format(item) for item in items]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(pipeline_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n저장: {OUTPUT_PATH} ({len(pipeline_items)}건)")
    for item in items[:3]:
        print(f"  • {item['사건번호']} | {item['소재지'][:30]} | {item['진행상태']}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 완료")


if __name__ == "__main__":
    main()
