#!/usr/bin/env python3
"""
Capture screenshots after API-created data. Uses login (not registration).
Credentials: e2e_supplier@example.com, e2e_restaurant@example.com, TestPass123!
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN_DIR = ROOT / "evidence" / "screens" / "manual_ui_flow"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

if sys.platform == "darwin" and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    user_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    if user_cache.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(user_cache)

BASE = "http://127.0.0.1:3000"

SUP_EMAIL = "e2e_supplier@example.com"
SUP_PW = "TestPass123!"
REST_EMAIL = "e2e_restaurant@example.com"
REST_PW = "TestPass123!"


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        try:
            # 1. Ports
            await page.goto(BASE, wait_until="commit", timeout=20000)
            await page.wait_for_timeout(2000)
            await page.screenshot(path=SCREEN_DIR / "01_ports_ok.png", full_page=True)

            page2 = await context.new_page()
            await page2.goto("http://127.0.0.1:8001/docs", wait_until="commit", timeout=15000)
            await page2.wait_for_timeout(1000)
            await page2.screenshot(path=SCREEN_DIR / "01_ports_api.png")
            await page2.close()

            # 2. Supplier dashboard: start from home, click "Я поставщик"
            await page.goto(BASE, wait_until="commit", timeout=20000)
            await page.wait_for_timeout(3000)
            await page.click("[data-testid=hero-supplier-btn]", timeout=10000)
            await page.wait_for_url("**/supplier/auth**", timeout=10000)
            await page.wait_for_timeout(3000)
            await page.wait_for_selector("[data-testid=login-email-input], input[type=email], form", timeout=15000)
            await page.fill("[data-testid=login-email-input]", SUP_EMAIL)
            await page.fill("[data-testid=login-password-input]", SUP_PW)
            await page.click("[data-testid=login-submit-btn]")
            await page.wait_for_url("**/supplier/**", timeout=15000)
            await page.wait_for_timeout(2000)
            await page.goto(f"{BASE}/supplier/profile", wait_until="commit", timeout=15000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=SCREEN_DIR / "02_supplier_registered.png", full_page=True)

            # 3. Restaurant dashboard (logout, login)
            await context.clear_cookies()
            await page.goto(f"{BASE}/customer/auth", wait_until="commit", timeout=20000)
            await page.wait_for_timeout(2000)
            await page.fill("input[type='email']", REST_EMAIL)
            await page.fill("input[type='password']", REST_PW)
            await page.click("button[type='submit']")
            await page.wait_for_url("**/customer/**", timeout=15000)
            await page.wait_for_timeout(2000)
            await page.goto(f"{BASE}/customer/profile", wait_until="commit", timeout=15000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=SCREEN_DIR / "03_restaurant_registered.png", full_page=True)

            # 4. Documents
            await page.goto(f"{BASE}/customer/documents", wait_until="commit", timeout=15000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=SCREEN_DIR / "04_restaurant_uploaded_doc.png", full_page=True)

        except Exception as e:
            print(f"FAIL: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await browser.close()

    print("Screenshots saved to evidence/screens/manual_ui_flow/")


if __name__ == "__main__":
    asyncio.run(main())
