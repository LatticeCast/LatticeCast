"""
Test: top bar breadcrumb — Home / workspace_name / table_name, each clickable
Ticket row 126
"""
import asyncio
import os
from playwright.async_api import async_playwright

BASE = "http://lattice-cast:13491"
OUT = "/output"


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        # Bypass login
        await page.goto(f"{BASE}/login")
        await page.evaluate("""() => {
            localStorage.setItem('auth', JSON.stringify({
                accessToken: 'claude',
                role: 'admin',
                provider: 'dev',
                userInfo: { name: 'Claude Bot', email: 'claude@test.com' }
            }));
        }""")

        # Navigate to tables list to get a table URL
        await page.goto(f"{BASE}/tables")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(500)

        # Screenshot 1: tables page — only Home breadcrumb shown (no table selected)
        await page.screenshot(path=f"{OUT}/126_1_tables_home_breadcrumb.png", full_page=False)
        print("Screenshot 1: tables page — should show 'Home / Tables' or just 'Home'")

        # Verify Home breadcrumb button exists
        home_btn = page.locator('[data-testid="breadcrumb-home"]')
        assert await home_btn.is_visible(), "Home breadcrumb button should be visible"
        home_text = await home_btn.inner_text()
        assert home_text.strip() == "Home", f"Expected 'Home', got '{home_text}'"
        print(f"  Home breadcrumb text: '{home_text.strip()}' ✓")

        # Navigate to a specific table
        # Get table links from the page
        table_links = page.locator('a[href*="/"], button').filter(has_text="SA")
        count = await table_links.count()
        print(f"  Found {count} potential table links")

        # Try to find and click a table via the API
        import json
        tables_response = await page.evaluate("""async () => {
            const r = await fetch('/api/tables', { headers: { Authorization: 'Bearer claude' } });
            return r.json();
        }""")
        print(f"  Tables from API: {[t['name'] for t in tables_response[:3]]}")

        if tables_response:
            table = tables_response[0]
            ws_id = table['workspace_id']
            tbl_id = table['table_id']
            tbl_name = table['name']

            # Get workspace info
            ws_response = await page.evaluate("""async () => {
                const r = await fetch('/api/workspaces', { headers: { Authorization: 'Bearer claude' } });
                return r.json();
            }""")
            ws = next((w for w in ws_response if w['workspace_id'] == ws_id), None)
            ws_name = ws['name'] if ws else 'unknown'
            print(f"  Navigating to table: {tbl_name} in workspace: {ws_name}")

            await page.goto(f"{BASE}/{ws_id}/{tbl_id}")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(800)

            # Screenshot 2: table page — full breadcrumb: Home / workspace / table
            await page.screenshot(path=f"{OUT}/126_2_table_breadcrumb.png", full_page=False)
            print("Screenshot 2: table page — full breadcrumb")

            # Verify all three breadcrumb segments
            home_btn = page.locator('[data-testid="breadcrumb-home"]')
            assert await home_btn.is_visible(), "Home breadcrumb should be visible"

            ws_btn = page.locator('[data-testid="breadcrumb-workspace"]')
            assert await ws_btn.is_visible(), "Workspace breadcrumb should be visible"
            ws_text = await ws_btn.inner_text()
            assert ws_text.strip() == ws_name, f"Expected '{ws_name}', got '{ws_text}'"
            print(f"  Workspace breadcrumb: '{ws_text.strip()}' ✓")

            tbl_btn = page.locator('[data-testid="breadcrumb-table"]')
            assert await tbl_btn.is_visible(), "Table breadcrumb should be visible"
            tbl_text = await tbl_btn.inner_text()
            assert tbl_text.strip() == tbl_name, f"Expected '{tbl_name}', got '{tbl_text}'"
            print(f"  Table breadcrumb: '{tbl_text.strip()}' ✓")

            # Test clicking Home breadcrumb — should navigate to /
            await home_btn.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(400)
            current_url = page.url
            print(f"  After clicking Home: {current_url}")
            assert current_url.endswith('/') or '/#' in current_url or current_url.endswith('/tables') or '/' == current_url.split(BASE)[-1], \
                f"Home should navigate to root, got: {current_url}"

            # Screenshot 3: after clicking Home
            await page.screenshot(path=f"{OUT}/126_3_after_home_click.png", full_page=False)
            print("Screenshot 3: after clicking Home breadcrumb")

            # Go back to table and test workspace breadcrumb click
            await page.goto(f"{BASE}/{ws_id}/{tbl_id}")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(800)

            ws_btn = page.locator('[data-testid="breadcrumb-workspace"]')
            await ws_btn.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(400)
            current_url = page.url
            print(f"  After clicking workspace: {current_url}")
            assert '/tables' in current_url, f"Workspace should navigate to /tables, got: {current_url}"

            # Screenshot 4: after clicking workspace breadcrumb
            await page.screenshot(path=f"{OUT}/126_4_after_workspace_click.png", full_page=False)
            print("Screenshot 4: after clicking workspace breadcrumb")

        print("\nAll assertions passed ✓")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
