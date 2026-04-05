import os
from playwright.sync_api import sync_playwright

os.makedirs('/app/.browser', exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    
    page.goto('http://frontend:5173')
    page.wait_for_timeout(2000)
    page.screenshot(path='/app/.browser/148_home_topbar.png')
    print("Screenshot 1 saved")
    
    # Check top bar has home icon button with data-testid=nav-home
    home_btn = page.query_selector('[data-testid="nav-home"]')
    print(f"Home button in top bar: {'FOUND' if home_btn else 'NOT FOUND'}")
    
    # sidebar should not have nav-home directly (it's been moved out)
    sidebar_nav = page.query_selector('[data-testid="menu-nav"]')
    if sidebar_nav:
        sidebar_home = sidebar_nav.query_selector('[data-testid="nav-home"]')
        print(f"Home button in sidebar: {'FOUND (bad)' if sidebar_home else 'NOT FOUND (good)'}")
    
    # Open sidebar and verify home icon still visible in top bar
    toggle = page.query_selector('[data-testid="menu-toggle"]')
    if toggle:
        toggle.click()
        page.wait_for_timeout(500)
        home_btn2 = page.query_selector('[data-testid="nav-home"]')
        print(f"Home button visible with sidebar open: {'YES' if home_btn2 else 'NO'}")
        page.screenshot(path='/app/.browser/148_sidebar_open.png')
        print("Screenshot 2 saved")
    
    browser.close()
    print("DONE")
