#!/usr/bin/env node
/**
 * UI proof: open /customer/cart, click "Подтвердить заказ", capture POST to /api/v12/cart/checkout.
 * No secrets in stdout.
 * Run from repo root:
 *   1. frontend/.env: REACT_APP_DEV_AUTH_BYPASS=1, restart frontend (yarn start).
 *   2. python3 scripts/dev/seed_cart_for_ui_proof.py
 *   3. PLAYWRIGHT_BROWSERS_PATH=<repo>/.playwright-browsers node scripts/dev/ui_checkout_click_proof_v1.js
 * Requires: npm install (root), npx playwright install chromium (or set PLAYWRIGHT_BROWSERS_PATH).
 */
const path = require('path');
const root = path.resolve(__dirname, '../..');
if (!process.env.PLAYWRIGHT_BROWSERS_PATH) {
  process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(root, '.playwright-browsers');
}
let playwright;
try {
  playwright = require('playwright');
} catch (e) {
  const frontendModules = path.join(root, 'frontend', 'node_modules');
  require('module')._nodeModulePaths.push(frontendModules);
  try {
    playwright = require('playwright');
  } catch (e2) {
    console.error('UI_CLICK_PROOF_FAIL: playwright not found. Run: (cd ' + root + ' && npm install && npx playwright install chromium)');
    process.exit(1);
  }
}

const BASE_URL = process.env.UI_PROOF_BASE || 'http://localhost:3000';
const CHECKOUT_PATH = '/customer/cart';

async function main() {
  let browser;
  try {
    browser = await playwright.chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    });
    const context = await browser.newContext();
    let postStatus = null;
    let postUrl = null;
    let postBody = null;

    await context.route('**/api/v12/cart/checkout**', async (route) => {
      const request = route.request();
      if (request.method() === 'POST') {
        postUrl = request.url();
        postBody = request.postData();
        await route.continue();
      } else {
        await route.continue();
      }
    });

    const page = await context.newPage();

    const responsePromise = page.waitForResponse(
      (res) => res.url().includes('/api/v12/cart/checkout') && res.request().method() === 'POST',
      { timeout: 25000 }
    ).catch(() => null);

    await page.goto(BASE_URL + '/auth', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(1000);
    const devCustomerBtn = page.locator('[data-testid="dev-login-customer-btn"]').first;
    try {
      await devCustomerBtn.waitFor({ state: 'visible', timeout: 5000 });
      await devCustomerBtn.click();
      await page.waitForTimeout(3000);
    } catch (_) {}

    await page.goto(BASE_URL + CHECKOUT_PATH, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForResponse((r) => r.url().includes('/api/v12/cart/intents'), { timeout: 10000 }).catch(() => null);
    await page.waitForTimeout(3000);

    const confirmSel = '[data-testid="confirm-checkout-btn"], button:has-text("Подтвердить заказ")';
    let btn = page.locator(confirmSel).first;
    try {
      await btn.waitFor({ state: 'visible', timeout: 4000 });
    } catch (_) {
      const orderBtn = page.locator('[data-testid="checkout-btn"], button:has-text("Оформить заказ")').first;
      try {
        await orderBtn.waitFor({ state: 'visible', timeout: 8000 });
        await orderBtn.click();
        await page.waitForResponse((r) => r.url().includes('/api/v12/cart/plan'), { timeout: 20000 }).catch(() => null);
        await page.waitForTimeout(4000);
        btn = page.locator(confirmSel).first;
        await btn.waitFor({ state: 'visible', timeout: 12000 });
      } catch (__) {
        console.log('UI_CLICK_PROOF_FAIL status=0 body=confirm button not found (no plan or not on cart)');
        await browser.close();
        process.exit(1);
      }
    }

    const disabled = await btn.getAttribute('disabled').catch(() => null);
    if (disabled !== null && disabled !== 'false') {
      console.log('UI_CLICK_PROOF_FAIL status=0 body=button disabled');
      await browser.close();
      process.exit(1);
    }

    await btn.click();
    const res = await responsePromise;
    let responseBody = '';
    if (res) {
      postStatus = res.status();
      postUrl = postUrl || res.url();
      try {
        const json = await res.json().catch(() => ({}));
        responseBody = typeof json === 'string' ? json : JSON.stringify(json);
      } catch (_) {}
    }

    await page.waitForTimeout(2000);

    if (postStatus !== null && postStatus !== undefined) {
      const bodyPreview = (responseBody || postBody || '').toString().slice(0, 200);
      if (postStatus === 200) {
        console.log('UI_CLICK_PROOF_OK status=' + postStatus + ' url=' + (postUrl || ''));
      } else {
        console.log('UI_CLICK_PROOF_FAIL status=' + postStatus + ' body=' + bodyPreview);
        process.exit(1);
      }
    } else {
      console.log('UI_CLICK_PROOF_FAIL status=0 body=no POST request captured');
      process.exit(1);
    }
  } catch (err) {
    const msg = (err && err.message) ? String(err.message).slice(0, 200) : String(err).slice(0, 200);
    console.log('UI_CLICK_PROOF_FAIL status=0 body=' + msg.replace(/\s+/g, ' '));
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
}

main();
