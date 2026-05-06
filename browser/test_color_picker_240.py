#!/usr/bin/env python3
"""Test color picker in ManageOptionsModal (ticket 240)"""
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "http://localhost:13491"
OUT = "/output"
WORKSPACE_ID = "31aab3c7-8c50-43b3-b855-db27b8676aa4"
TABLE_ID = "latticecast"

LOGIN_INFO = {
    "provider": "none",
    "accessToken": "claude",
    "userInfo": {"sub": "claude", "email": "claude", "name": "Claude"},
    "role": "user",
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script(
        f"localStorage.setItem('loginInfo', JSON.stringify({json.dumps(LOGIN_INFO)}));"
    )

    page = ctx.new_page()

    table_url = f"{BASE_URL}/{WORKSPACE_ID}/{TABLE_ID}"
    try:
        page.goto(table_url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        page.screenshot(path=f"{OUT}/240_timeout.png")
        print("Timeout loading page")
        browser.close()
        exit(1)

    page.wait_for_timeout(2000)

    # Click the "Table" view tab using its data-testid
    tab = page.query_selector('[data-testid="view-tab-Table"]')
    if tab:
        tab.evaluate("el => el.click()")
        page.wait_for_timeout(1000)
        print("Switched to Table view via data-testid")
    else:
        print("Table tab not found — staying on current view")

    page.screenshot(path=f"{OUT}/240_table.png", full_page=False)
    print("URL:", page.url)

    # Find column headers with select type
    header_buttons = page.query_selector_all("th button")
    print(f"Found {len(header_buttons)} header buttons")
    for btn in header_buttons:
        print(f"  Header: {btn.inner_text().strip()!r}")

    found_manage = False
    for btn in header_buttons:
        text = btn.inner_text().strip()
        if any(kw in text for kw in ["Status", "Priority", "Type"]):
            print(f"Clicking header: {text!r}")
            btn.evaluate("el => el.click()")
            page.wait_for_timeout(500)
            manage_btn = page.query_selector('button:has-text("Manage Options")')
            if manage_btn:
                manage_btn.evaluate("el => el.click()")
                page.wait_for_timeout(500)
                page.screenshot(path=f"{OUT}/240_manage_options_modal.png", full_page=False)
                print("Manage Options modal opened!")
                found_manage = True

                color_btn = page.query_selector('[data-testid="choice-color-btn-0"]')
                if color_btn:
                    color_btn.evaluate("el => el.click()")
                    page.wait_for_timeout(300)
                    page.screenshot(path=f"{OUT}/240_color_palette.png", full_page=False)
                    print("Color palette opened!")
                else:
                    print("WARNING: choice-color-btn-0 not found")
                break
            else:
                page.evaluate("document.querySelector('body').click()")

    if not found_manage:
        print("Could not open Manage Options modal")
        page.screenshot(path=f"{OUT}/240_no_modal.png")

    browser.close()
    print("Done")
