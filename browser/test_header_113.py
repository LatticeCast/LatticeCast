#!/usr/bin/env python3
"""Test ticket 113: verify single blue header bar with table breadcrumb"""
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://lattice-cast:13491"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        
        # Go to home page (dev mode auto-logs in)
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.screenshot(path="/output/header_home.png")
        print("Home screenshot saved")
        
        # Navigate to tables list
        await page.goto(f"{BASE_URL}/tables", wait_until="networkidle")
        await page.screenshot(path="/output/header_tables.png")
        print("Tables screenshot saved")
        
        # Find a table link and click it
        links = await page.locator("a[href*='/']").all()
        table_url = None
        for link in links:
            href = await link.get_attribute("href")
            if href and href.count('/') >= 2 and 'table' not in href and 'login' not in href and 'callback' not in href:
                table_url = href
                break
        
        # Try clicking first table row
        rows = await page.locator("tr").all()
        print(f"Found {len(rows)} table rows")
        
        # Navigate directly to a known table 
        await page.goto(f"{BASE_URL}", wait_until="networkidle")
        # Click on Tables nav
        await page.click("text=Tables")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="/output/header_after_tables_nav.png")
        
        # Try to find a table to click
        table_links = page.locator("a").filter(has_text="")
        count = await table_links.count()
        print(f"Found {count} links")
        
        # Get all links
        all_links = await page.locator("a").all()
        for link in all_links:
            href = await link.get_attribute("href") or ""
            text = await link.inner_text()
            print(f"Link: {href!r} text={text!r}")
        
        await browser.close()

asyncio.run(main())
