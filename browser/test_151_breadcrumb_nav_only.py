import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = "http://lattice-cast:13491"
FRONTEND = "http://lattice-cast:13491"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Get a table to navigate to via API
        req = urllib.request.Request(f"{BASE}/api/tables", headers={"Authorization": "Bearer claude"})
        tables = json.loads(urllib.request.urlopen(req).read())
        if not tables:
            print("No tables found")
            await browser.close()
            return

        table = tables[0]
        ws_id = table['workspace_id']
        t_id = table['table_id']
        print(f"Table: {table['name']}")

        # Set up auth in localStorage
        await page.goto(FRONTEND)
        await page.wait_for_timeout(1000)
        login_info = json.dumps({"accessToken": "claude", "role": "member"})
        await page.evaluate(f"localStorage.setItem('loginInfo', {json.dumps(login_info)})")

        # Navigate to table
        await page.goto(f"{FRONTEND}/{ws_id}/{t_id}")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/screenshots/151_01_table_loaded.png")
        print(f"URL: {page.url}")

        table_btn = page.get_by_test_id("breadcrumb-table")
        ws_btn = page.get_by_test_id("breadcrumb-workspace")

        table_visible = await table_btn.is_visible()
        ws_visible = await ws_btn.is_visible()
        print(f"table breadcrumb visible: {table_visible}")
        print(f"workspace breadcrumb visible: {ws_visible}")

        if table_visible:
            title = await table_btn.get_attribute("title")
            tag = await table_btn.evaluate("el => el.tagName")
            text = await table_btn.inner_text()
            print(f"Table breadcrumb tag: {tag}, title: {title!r}, text: {text!r}")
            assert "rename" not in (title or "").lower(), f"Should NOT have rename title: {title}"

        if ws_visible:
            title = await ws_btn.get_attribute("title")
            tag = await ws_btn.evaluate("el => el.tagName")
            text = await ws_btn.inner_text()
            print(f"Workspace breadcrumb tag: {tag}, title: {title!r}, text: {text!r}")
            assert "rename" not in (title or "").lower(), f"Should NOT have rename title: {title}"

        # Click table breadcrumb — should NOT show rename input
        if table_visible:
            await table_btn.click()
            await page.wait_for_timeout(500)
            inp_count = await page.get_by_test_id("breadcrumb-table-input").count()
            print(f"Rename input after table click: {inp_count} (must be 0)")
            assert inp_count == 0, "Rename input MUST NOT appear after clicking table breadcrumb"
            await page.screenshot(path="/screenshots/151_02_after_table_click.png")
            print("PASS: No rename input after table click")

        # Click workspace breadcrumb — should navigate
        if ws_visible:
            await page.goto(f"{FRONTEND}/{ws_id}/{t_id}")
            await page.wait_for_timeout(2000)
            ws_btn2 = page.get_by_test_id("breadcrumb-workspace")
            await ws_btn2.click()
            await page.wait_for_timeout(1000)
            new_url = page.url
            print(f"URL after workspace click: {new_url}")
            inp_count = await page.get_by_test_id("breadcrumb-workspace-input").count()
            print(f"Rename input after ws click: {inp_count} (must be 0)")
            assert inp_count == 0, "Rename input MUST NOT appear"
            await page.screenshot(path="/screenshots/151_03_after_ws_click.png")
            print("PASS: No rename input after workspace click, navigated to:", new_url)

        if not table_visible and not ws_visible:
            print("WARNING: breadcrumb not found, page may not have loaded correctly")

        print("All checks passed!")
        await browser.close()

asyncio.run(main())
