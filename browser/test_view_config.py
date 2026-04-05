from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    
    # Go to the app
    page.goto("http://nginx:80")
    page.wait_for_timeout(2000)
    page.screenshot(path="/app/.browser/view_config_01_home.png")
    
    # Try to find a table view
    page.goto("http://nginx:80/claude/7e6821be-3de8-4e54-b0b6-05db91e5f797")
    page.wait_for_timeout(3000)
    page.screenshot(path="/app/.browser/view_config_02_table.png")
    
    # Check view switcher is visible
    body = page.locator("body").inner_text()
    print("Page loaded, body length:", len(body))
    
    # Check if view tabs exist
    tabs = page.locator("button").all()
    tab_texts = [t.inner_text() for t in tabs[:20]]
    print(f"First 20 buttons: {tab_texts}")
    
    browser.close()
    print("Done")
