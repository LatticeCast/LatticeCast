"""Verify RLS fix — login as test246 and visit /tables/ta and /tables/promotion."""
import asyncio
from playwright.async_api import async_playwright

URL = "http://localhost:13491"
WS = "73ec8b8a-a3fa-4522-be8b-b9b0354091f2"
USER = {"provider": "none", "user_id": "test246", "accessToken": "test246"}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(URL)
        # inject auth
        import json
        await page.evaluate(f"localStorage.setItem('auth', '{json.dumps(USER)}')")

        for table in ["ta", "promotion", "articles", "production"]:
            await page.goto(f"{URL}/{WS}/{table}")
            await page.wait_for_timeout(1500)
            body = await page.content()
            ok = "Failed to fetch" not in body and "Not Found" not in body
            await page.screenshot(path=f"/output/rls_{table}.png")
            print(f"{table}: {'OK' if ok else 'FAIL'}")

        await browser.close()


asyncio.run(main())
