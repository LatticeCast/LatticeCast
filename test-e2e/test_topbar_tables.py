import os
from playwright.sync_api import sync_playwright

os.makedirs('.browser', exist_ok=True)

BASE_URL = 'http://lattice-cast:13491'

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    
    page.goto(BASE_URL)
    page.wait_for_timeout(2000)
    page.screenshot(path='.browser/149_topbar_tables_home.png')
    print("Screenshot 1: home page saved")
    
    # Check Tables button in top bar
    topbar_tables = page.query_selector('[data-testid="nav-tables-topbar"]')
    print(f"Tables button in top bar: {'PASS - FOUND' if topbar_tables else 'FAIL - NOT FOUND'}")
    
    # Check sidebar Tables button is gone
    sidebar_tables = page.query_selector('[data-testid="nav-tables"]')
    print(f"Tables button in sidebar (should be gone): {'FAIL - still present' if sidebar_tables else 'PASS - removed'}")
    
    # Open sidebar
    toggle = page.query_selector('[data-testid="menu-toggle"]')
    if toggle:
        toggle.click()
        page.wait_for_timeout(400)
        page.screenshot(path='.browser/149_topbar_tables_sidebar_open.png')
        print("Screenshot 2: sidebar open saved")
        
        topbar_tables2 = page.query_selector('[data-testid="nav-tables-topbar"]')
        print(f"Tables button visible with sidebar open: {'PASS - FOUND' if topbar_tables2 else 'FAIL - NOT FOUND'}")
    
    browser.close()
    print("Done")
