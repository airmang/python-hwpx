import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1800, height: 1200 } });
  await page.goto('http://127.0.0.1:3098/editor', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    const first = document.querySelector('[data-page] [contenteditable="true"]');
    first?.focus();
  });
  await page.locator('button[title="표 삽입"]').click();
  await page.getByRole('button', { name: '삽입' }).first().click();
  await page.locator('td[data-hwpx-cell="1"]').first().waitFor({ timeout: 8000 });

  await page.evaluate(() => window.__HWPX_TEST_BRIDGE?.setTableSelectionRange({
    sectionIndex: 0,
    paragraphIndex: 0,
    tableIndex: 0,
    row: 0,
    col: 0,
    endRow: 0,
    endCol: 0,
  }));

  await page.getByText('표').first().waitFor({timeout:5000}).catch(()=>{});
  await page.waitForTimeout(500);

  const sidebar = page.locator('div.w-72.min-h-0.border-l.border-gray-200.bg-white.flex.flex-col.overflow-hidden.flex-shrink-0');
  await sidebar.waitFor({ state: 'visible', timeout: 5000 });
  const all = await sidebar.locator('button').allTextContents();
  console.log('buttons', all);
  const txts = await page.evaluate(() => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    return {
      sidebarOpen: bridge?.getStateSnapshot().sidebarOpen,
      sidebarTab: bridge?.getStateSnapshot().sidebarTab,
      uiState: bridge ? { tab: bridge.getStateSnapshot().sidebarTab } : null,
      sidebar: bridge?.getStateSnapshot(),
    };
  });
  console.log('snapshot', txts.sidebar);

  const tableTab = sidebar.getByRole('button', { name: '표', exact: true });
  const cellTab = sidebar.getByRole('button', { name: '셀', exact: true });
  console.log('tableTab count', await tableTab.count(), 'cellTab count', await cellTab.count());

  if (await cellTab.count()) {
    await cellTab.first().click();
    await page.waitForTimeout(250);
    console.log('after click cell all', await sidebar.locator('button').allTextContents());
    console.log('headers', await sidebar.locator('.border-b button').allTextContents());
  }

  await browser.close();
})();
