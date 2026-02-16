import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:3098';
const OUT = '/Users/jskang/nomadlab/output/playwright';
const email = `pw-save-${Date.now()}@example.com`;
const password = 'Test1234!';

async function exists(locator) {
  return (await locator.count()) > 0;
}

async function waitForEditor(page) {
  await page.goto(`${BASE}/editor`, { waitUntil: 'domcontentloaded' });
  await page.locator('[data-hwpx-editor-root="true"]').first().waitFor({ timeout: 30000 });
}

async function openSaveDialog(page) {
  await page.getByRole('button', { name: '저장' }).first().click();
  await page.getByRole('heading', { name: '다른 이름으로 저장' }).waitFor({ timeout: 10000 });
}

async function clickServerSaveAndWaitResponse(page) {
  const button = page.getByRole('button', { name: /서버 저장|서버 덮어쓰기/ }).first();
  const visible = await button.isVisible().catch(() => false);
  if (!visible) return null;

  const responsePromise = page
    .waitForResponse((res) => res.url().includes('/api/hwpx-documents') && res.request().method() === 'POST', {
      timeout: 15000,
    })
    .catch(() => null);

  await button.click();
  return await responsePromise;
}

async function signupAndReturn(page) {
  await page.waitForURL(/\/login\?callbackUrl=%2Feditor/, { timeout: 15000 });
  await page.getByRole('button', { name: '회원가입' }).first().click();

  await page.getByRole('textbox', { name: '이름' }).fill('Playwright User');
  await page.getByRole('textbox', { name: '이메일' }).fill(email);
  await page.getByRole('textbox', { name: '비밀번호' }).fill(password);

  await page.getByRole('button', { name: '회원가입', exact: true }).click();

  await page.waitForURL(/\/editor/, { timeout: 20000 });
  await page.locator('[data-hwpx-editor-root="true"]').first().waitFor({ timeout: 20000 });
}

async function main() {
  await fs.mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  const hwpxResponses = [];
  page.on('response', async (res) => {
    if (!res.url().includes('/api/hwpx-documents')) return;
    let body = '';
    try {
      body = (await res.text()).slice(0, 500);
    } catch {}
    hwpxResponses.push({
      url: res.url(),
      status: res.status(),
      method: res.request().method(),
      body,
    });
  });

  const result = {
    base: BASE,
    email,
    firstAttempt: null,
    finalAttempt: null,
    finalUrl: null,
    hwpxResponses,
    success: false,
    note: '',
  };

  try {
    await waitForEditor(page);
    await openSaveDialog(page);
    const firstRes = await clickServerSaveAndWaitResponse(page);

    if (firstRes) {
      let body = '';
      try { body = await firstRes.text(); } catch {}
      result.firstAttempt = { status: firstRes.status(), body: body.slice(0, 500) };
    } else {
      result.firstAttempt = { status: null, body: null };
    }

    await page.waitForTimeout(1800);
    const onLoginPage =
      page.url().includes('/login?callbackUrl=%2Feditor') ||
      (await exists(page.getByRole('button', { name: '회원가입' }).first()));

    if (onLoginPage) {
      await signupAndReturn(page);
      await openSaveDialog(page);
    }

    const finalRes = await clickServerSaveAndWaitResponse(page);
    await page.waitForTimeout(1500);
    if (finalRes) {
      let body = '';
      try { body = await finalRes.text(); } catch {}
      result.finalAttempt = { status: finalRes.status(), body: body.slice(0, 500) };
    } else {
      result.finalAttempt = { status: null, body: null };
    }

    result.finalUrl = page.url();

    const hasErrorBanner = await exists(page.getByText('서버 저장에 실패했습니다'));
    const okStatus = result.finalAttempt?.status === 200 || result.finalAttempt?.status === 201;
    result.success = Boolean(okStatus && !hasErrorBanner && !page.url().includes('/login'));
    result.note = hasErrorBanner ? 'error-banner-visible' : 'ok';

    await page.screenshot({ path: `${OUT}/editor-save-server-check-final.png`, fullPage: true });
    await fs.writeFile(`${OUT}/editor-save-server-check-result.json`, JSON.stringify(result, null, 2), 'utf8');

    console.log(JSON.stringify(result, null, 2));

    if (!result.success) {
      process.exitCode = 2;
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
