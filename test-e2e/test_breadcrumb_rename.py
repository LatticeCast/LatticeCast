import asyncio, json, urllib.request
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Get a table to navigate to
        req = urllib.request.Request("http://nginx/api/tables", headers={"Authorization": "Bearer claude"})
        resp = urllib.request.urlopen(req)
        tables = json.loads(resp.read())

        if not tables:
            print("No tables found")
            await browser.close()
            return

        table = tables[0]
        ws_id = table['workspace_id']
        t_id = table['table_id']
        print(f"Table: {table['name']}, ws: {ws_id}")

        # Dev login to set auth in localStorage
        await page.goto(f"http://nginx/api/login/dev?user_name=claude&redirect=/{ws_id}/{t_id}", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        await page.screenshot(path="/screenshots/breadcrumb_01_loaded.png")
        print("Screenshot 01: page loaded")

        # Check breadcrumb
        table_btn = page.get_by_test_id("breadcrumb-table")
        ws_btn = page.get_by_test_id("breadcrumb-workspace")
        
        table_visible = await table_btn.is_visible()
        ws_visible = await ws_btn.is_visible()
        print(f"table btn visible: {table_visible}, workspace btn visible: {ws_visible}")

        if table_visible:
            text = await table_btn.inner_text()
            print(f"Table breadcrumb text: '{text}'")
            await table_btn.click()
            await page.wait_for_timeout(400)
            await page.screenshot(path="/screenshots/breadcrumb_02_table_rename_input.png")
            print("Screenshot 02: after clicking table breadcrumb")

            inp = page.get_by_test_id("breadcrumb-table-input")
            if await inp.is_visible():
                print("Rename input appeared!")
                await inp.fill("Test Renamed Table")
                await page.screenshot(path="/screenshots/breadcrumb_03_typing.png")
                print("Screenshot 03: typing new name")
                await inp.press("Escape")
                await page.wait_for_timeout(300)
                await page.screenshot(path="/screenshots/breadcrumb_04_after_cancel.png")
                print("Screenshot 04: after cancel")
            else:
                print("Input NOT visible after click")

        if ws_visible:
            await ws_btn.click()
            await page.wait_for_timeout(400)
            await page.screenshot(path="/screenshots/breadcrumb_05_workspace_rename.png")
            print("Screenshot 05: workspace rename input")

        await browser.close()
        print("Done")

asyncio.run(main())
