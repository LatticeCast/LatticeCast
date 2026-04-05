import os
from playwright.sync_api import sync_playwright

os.makedirs('.browser', exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    
    page.goto('http://frontend:5173')
    page.wait_for_timeout(2000)
    page.screenshot(path='.browser/148_home_topbar.png')
    print("Screenshot saved")
    
    # Check top bar has home icon
    home_btn = page.query_selector('[data-testid="nav-home"]')
    print(f"Home button in top bar: {'FOUND' if home_btn else 'NOT FOUND'}")
    
    # Open sidebar and take another screenshot
    toggle = page.query_selector('[data-testid="menu-toggle"]')
    if toggle:
        toggle.click()
        page.wait_for_timeout(500)
        page.screenshot(path='.browser/148_home_topbar_sidebar_open.png')
        print("Sidebar open screenshot saved")
    
    browser.close()
