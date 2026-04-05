"""
Test: sidebar toggle — ☰ opens, « closes, smooth CSS transition
Ticket row 115
"""
import asyncio
import base64
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
        await page.goto(f"{BASE}/tables")
        await page.wait_for_load_state("networkidle")

        # Screenshot 1: initial state — ☰ visible, sidebar closed
        await page.screenshot(path=f"{OUT}/115_1_initial_hamburger.png", full_page=False)
        print("Screenshot 1: initial state (☰ visible, sidebar closed)")

        # Verify ☰ is visible and « is not via opacity
        menu_toggle = page.locator('[data-testid="menu-toggle"]')
        aria_label = await menu_toggle.get_attribute("aria-label")
        print(f"  aria-label: {aria_label}")
        assert aria_label == "Open menu", f"Expected 'Open menu', got '{aria_label}'"

        # Click toggle — should OPEN sidebar
        await menu_toggle.click()
        await page.wait_for_timeout(400)  # wait for transition

        # Screenshot 2: sidebar open — « visible
        await page.screenshot(path=f"{OUT}/115_2_sidebar_open.png", full_page=False)
        print("Screenshot 2: sidebar open (« visible)")

        aria_label = await menu_toggle.get_attribute("aria-label")
        print(f"  aria-label: {aria_label}")
        assert aria_label == "Close menu", f"Expected 'Close menu', got '{aria_label}'"

        # Verify nav is visible
        nav = page.locator('[data-testid="menu-nav"]')
        assert await nav.is_visible(), "Nav should be visible when sidebar is open"

        # Click toggle — should CLOSE sidebar
        await menu_toggle.click()
        await page.wait_for_timeout(400)  # wait for transition

        # Screenshot 3: sidebar closed again — ☰ visible
        await page.screenshot(path=f"{OUT}/115_3_sidebar_closed.png", full_page=False)
        print("Screenshot 3: sidebar closed again (☰ visible)")

        aria_label = await menu_toggle.get_attribute("aria-label")
        print(f"  aria-label: {aria_label}")
        assert aria_label == "Open menu", f"Expected 'Open menu', got '{aria_label}'"

        # Verify clicking ☰ does NOT navigate (URL stays the same)
        url_before = page.url
        await menu_toggle.click()
        await page.wait_for_timeout(400)
        url_after = page.url
        assert url_before == url_after, f"URL changed after clicking toggle: {url_before} → {url_after}"
        print(f"  URL unchanged after open: {url_after}")

        # Verify clicking « does NOT navigate
        url_before = page.url
        await menu_toggle.click()
        await page.wait_for_timeout(400)
        url_after = page.url
        assert url_before == url_after, f"URL changed after clicking close: {url_before} → {url_after}"
        print(f"  URL unchanged after close: {url_after}")

        # Screenshot 4: mid-transition (click and screenshot quickly)
        await menu_toggle.click()
        await page.wait_for_timeout(150)  # mid-transition
        await page.screenshot(path=f"{OUT}/115_4_mid_transition.png", full_page=False)
        print("Screenshot 4: mid-transition")
        await page.wait_for_timeout(300)  # finish transition

        await browser.close()
        print("\nAll assertions passed!")

asyncio.run(main())
