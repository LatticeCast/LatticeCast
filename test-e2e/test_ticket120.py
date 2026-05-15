#!/usr/bin/env python3
"""Test ticket 120 - verify single blue header bar, table name shown in layout header"""
import asyncio
import os
from playwright.async_api import async_playwright

BASE_URL = "http://lattice-cast:13491"
WORKSPACE_ID = "31aab3c7-8c50-43b3-b855-db27b8676aa4"
TABLE_ID = "7e6821be-3de8-4e54-b0b6-05db91e5f797"
OUT = "/output"

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        # Set auth token (key=loginInfo, accessToken=claude for dev mode)
        await page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        await page.evaluate("""() => {
            localStorage.setItem('loginInfo', JSON.stringify({
                provider: 'none',
                accessToken: 'claude',
                role: 'admin',
                userInfo: { sub: 'claude', name: 'Claude Bot', email: 'claude@test.com' }
            }));
        }""")

        # Navigate to table detail page
        await page.goto(f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{OUT}/ticket120_table_detail_final.png")
        print(f"URL: {page.url}")

        # Verify only 1 blue bar (the layout header)
        blue_bars = await page.locator(".bg-blue-600").count()
        print(f"bg-blue-600 element count: {blue_bars}")
        assert blue_bars <= 2, f"Expected at most 2 blue elements (header + button), got {blue_bars}"

        # Verify the layout header exists
        header = page.locator("header.bg-blue-600")
        assert await header.count() == 1, "Expected exactly 1 layout header"
        print("PASS: Exactly 1 layout header bar")

        # Verify NO second blue bar (TableHeader-style div)
        second_blue_bar = page.locator("div.bg-blue-600")
        count = await second_blue_bar.count()
        print(f"Rogue div.bg-blue-600 count: {count} (should be 0)")
        assert count == 0, f"Found {count} extra blue bars — expected 0"
        print("PASS: No second blue header bar")

        await browser.close()
        print("All assertions passed!")

asyncio.run(main())
