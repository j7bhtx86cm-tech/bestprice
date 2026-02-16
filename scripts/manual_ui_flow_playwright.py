#!/usr/bin/env python3
"""
Automate manual UI flow: register supplier, restaurant, upload doc, accept contract.
Takes 4 screenshots. Requires: backend on 8001, frontend on 3000.
"""
import asyncio
import os
import sys
from pathlib import Path

# Use user's Playwright browsers on macOS (avoids sandbox cache path)
if sys.platform == "darwin" and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    user_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    if user_cache.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(user_cache)

ROOT = Path(__file__).resolve().parents[1]
SCREEN_DIR = ROOT / "evidence" / "screens" / "manual_ui_flow"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8001"

SUP_EMAIL = "manual_supplier@example.com"
SUP_PW = "TestPass123!"
REST_EMAIL = "manual_restaurant@example.com"
REST_PW = "TestPass123!"


async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: pip install playwright && playwright install chromium")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. Ports ok
            await page.goto(BASE, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
            page2 = await context.new_page()
            await page2.goto(f"{API}/docs", wait_until="networkidle", timeout=15000)
            await page2.wait_for_timeout(500)
            await page.screenshot(path=SCREEN_DIR / "01_ports_ok.png", full_page=True)
            await page2.close()

            # 2. Register supplier
            await page.goto(f"{BASE}/supplier/auth", wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(3000)
            switch_btn = page.locator("button:has-text('Зарегистрироваться')").first
            await switch_btn.click(timeout=10000)
            await page.wait_for_selector("[data-testid=supplier-register-form]", timeout=5000)
            await page.fill("[data-testid=register-email-input]", SUP_EMAIL)
            await page.fill("[data-testid=register-password-input]", SUP_PW)
            await page.fill("#inn", "7707083893")
            await page.fill("input[id='companyName'], input[name='companyName']", "ООО Ручной Поставщик", timeout=2000)
            await page.fill("input[id='legalAddress'], input[name='legalAddress']", "Москва", timeout=2000)
            await page.fill("input[id='ogrn'], input[name='ogrn']", "1027700132195", timeout=2000)
            await page.fill("input[id='actualAddress'], input[name='actualAddress']", "Москва", timeout=2000)
            await page.fill("input[id='phone'], input[name='phone']", "+79001234567", timeout=2000)
            await page.fill("input[id='companyEmail'], input[name='companyEmail']", "info@manual.example.com", timeout=2000)
            await page.fill("input[id='contactPersonName'], input[name='contactPersonName']", "Иванов", timeout=2000)
            await page.fill("input[id='contactPersonPosition'], input[name='contactPersonPosition']", "Директор", timeout=2000)
            await page.fill("input[id='contactPersonPhone'], input[name='contactPersonPhone']", "+79001234567", timeout=2000)
            await page.check("input[type='checkbox']", timeout=2000)
            await page.click("button[type='submit']")
            await page.wait_for_url("**/supplier/**", timeout=10000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=SCREEN_DIR / "02_supplier_registered.png", full_page=True)

            # 3. Register restaurant (new context to logout)
            await context.clear_cookies()
            await page.goto(f"{BASE}/customer/auth", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1500)
            await page.locator("[data-testid=switch-to-register-btn]").click(timeout=8000)
            await page.wait_for_selector("[data-testid=supplier-register-form]", timeout=5000)
            await page.fill("#email", REST_EMAIL)
            await page.fill("#password", REST_PW)
            await page.fill("#inn", "7701234567")
            await page.fill("#companyName", "ООО Ручной Ресторан")
            await page.fill("#ogrn", "1027701234567")
            await page.fill("#legalAddress", "Москва")
            await page.fill("#actualAddress", "Москва")
            await page.fill("#phone", "+79001234568")
            await page.fill("#companyEmail", "rest@manual.example.com")
            await page.fill("#contactPersonName", "Петров")
            await page.fill("#contactPersonPosition", "Директор")
            await page.fill("#contactPersonPhone", "+79001234568")
            await page.fill("input[placeholder='Адрес доставки']", "Москва, ул. Тестовая 1")
            await page.check("input[type='checkbox']")
            await page.click("[data-testid=register-submit-btn]")
            await page.wait_for_url("**/customer/**", timeout=10000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=SCREEN_DIR / "03_restaurant_registered.png", full_page=True)

            # 4. Upload document
            await page.goto(f"{BASE}/customer/documents", wait_until="networkidle", timeout=15000)
            pdf_path = ROOT / "backend" / "uploads" / "_manual_sample.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4 Manual flow\n")
            await page.select_option("#documentType", "Договор аренды", timeout=3000)
            await page.fill("#edo", "EDO-001")
            await page.fill("#guid", "manual-flow-guid-001")
            await page.set_input_files("#files", str(pdf_path))
            await page.click("[data-testid=submit-moderation-btn]")
            await page.wait_for_timeout(3000)
            await page.screenshot(path=SCREEN_DIR / "04_restaurant_uploaded_doc.png", full_page=True)

            # 5. Login as supplier, accept contract
            await context.clear_cookies()
            await page.goto(f"{BASE}/supplier/auth", wait_until="networkidle", timeout=15000)
            await page.fill("[data-testid=login-email-input]", SUP_EMAIL)
            await page.fill("[data-testid=login-password-input]", SUP_PW)
            await page.click("[data-testid=login-submit-btn]")
            await page.wait_for_url("**/supplier/**", timeout=10000)
            await page.goto(f"{BASE}/supplier/documents", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            btn = page.locator("button:has-text('Принять договор')")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(2000)
            # Restaurant and doc should be visible now

        except Exception as e:
            print(f"FAIL: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await browser.close()

    print("Manual UI flow: 4 screenshots saved to evidence/screens/manual_ui_flow/")


if __name__ == "__main__":
    asyncio.run(main())
