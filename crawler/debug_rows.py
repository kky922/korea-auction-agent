import asyncio
from playwright.async_api import async_playwright

JS = """() => {
    const tbody = document.querySelectorAll("table tbody")[1];
    if (!tbody) return [];
    const trs = tbody.querySelectorAll("tr");
    const result = [];
    for (let i=0; i<trs.length; i++) {
        const tds = trs[i].querySelectorAll("td");
        const cols = [];
        for (let j=0; j<tds.length; j++) {
            const t = tds[j].innerText.trim().replace(/\\s+/g, " ").substring(0, 60);
            cols.push(tds[j].rowSpan + ":" + t);
        }
        result.push(cols);
    }
    return result;
}"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        await page.goto("https://www.courtauction.go.kr", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(4000)
        await page.click("#mf_btn_rletRpdt")
        await page.wait_for_timeout(1500)
        await page.select_option("#mf_sbx_rletRpdtSdLst", label="서울특별시")
        await page.wait_for_timeout(1500)
        await page.click("#mf_btn_quickSearchGds")
        await page.wait_for_timeout(6000)

        rows = await page.evaluate(JS)
        for i, row in enumerate(rows):
            print(f"Row{i:02d}({len(row)}cols)", row)

        await browser.close()

asyncio.run(main())
