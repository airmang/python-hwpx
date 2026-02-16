import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const BASE_URL = process.env.EDITOR_URL || 'http://127.0.0.1:3098/editor';
const outDir = '/Users/jskang/nomadlab/output/playwright/editor-3098-qa';
const SIDEBAR_SELECTOR = 'div.w-72.min-h-0.border-l.border-gray-200.bg-white.flex.flex-col.overflow-hidden.flex-shrink-0';
const TOP_MENU_DROPDOWN_SELECTOR = 'div.absolute.left-0.top-full.bg-white.border.border-gray-200.shadow-lg.rounded-b.min-w-\\[220px\\].py-1';

const steps = [];

async function runStep(page, name, fn) {
  const started = Date.now();
  try {
    const result = await fn();
    const file = path.join(outDir, `${name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    steps.push({
      name,
      status: 'passed',
      durationMs: Date.now() - started,
      screenshot: file,
      result,
      error: null,
    });
    return { ok: true, result };
  } catch (error) {
    const file = path.join(outDir, `${name}-error.png`);
    await page.screenshot({ path: file, fullPage: true }).catch(() => null);
    steps.push({
      name,
      status: 'failed',
      durationMs: Date.now() - started,
      screenshot: file,
      result: null,
      error: String(error),
    });
    return { ok: false, error: String(error) };
  }
}

async function findTopMenuButton(page, label) {
  const handles = await page.$$('button');
  const candidates = [];
  for (const handle of handles) {
    const info = await handle.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        text: (el.textContent || '').trim(),
        x: rect.x,
        y: rect.y,
        w: rect.width,
        h: rect.height,
      };
    });
    if (
      info.text === label &&
      info.w > 0 &&
      info.h > 0 &&
      info.y <= 150 &&
      info.x > 0
    ) {
      candidates.push({ handle, y: info.y, x: info.x, text: info.text });
    }
  }
  if (candidates.length === 0) {
    throw new Error(`top menu not found: ${label}`);
  }
  candidates.sort((a, b) => (a.y - b.y) || (a.x - b.x));
  return candidates[0].handle;
}

async function clickTopMenu(page, label) {
  const btn = await findTopMenuButton(page, label);
  await btn.click();
  return btn;
}

async function clickTableMenuItem(page, itemName) {
  await page.keyboard.press('Escape').catch(() => {});
  await clickTopMenu(page, '표');
  const clicked = await page.evaluate(({ label, selector }) => {
    const menus = Array.from(document.querySelectorAll(selector));
    const menu = menus.find((m) => !!m.offsetParent);
    if (!menu) return false;
    const button = Array.from(menu.querySelectorAll('button')).find(
      (b) => b.textContent?.trim() === label,
    );
    if (!button) return false;
    button.click();
    return true;
  }, { label: itemName, selector: TOP_MENU_DROPDOWN_SELECTOR });
  if (!clicked) {
    throw new Error(`menu item not found: ${itemName}`);
  }
  await page.waitForTimeout(120);
}

async function clickTopMenuItem(page, menuLabel, itemName) {
  await page.keyboard.press('Escape').catch(() => {});
  await clickTopMenu(page, menuLabel);
  const clicked = await page.evaluate(({ label, selector }) => {
    const menus = Array.from(document.querySelectorAll(selector));
    const menu = menus.find((m) => !!m.offsetParent);
    if (!menu) return false;
    const button = Array.from(menu.querySelectorAll('button')).find((btn) => {
      const text = (btn.textContent || '').trim();
      return text === label || text.startsWith(`${label}`);
    });
    if (!button) return false;
    button.click();
    return true;
  }, { label: itemName, selector: TOP_MENU_DROPDOWN_SELECTOR });
  if (!clicked) {
    throw new Error(`menu item not found: ${itemName} in ${menuLabel}`);
  }
  await page.waitForTimeout(150);
}

function defaultTableSelection() {
  return {
    sectionIndex: 0,
    paragraphIndex: 0,
    tableIndex: 0,
    row: 0,
    col: 0,
    endRow: 0,
    endCol: 0,
  };
}

async function getStateSnapshot(page) {
  return getDebug(page, 'getStateSnapshot');
}

async function openInsertTable(page) {
  const tableButton = page.locator('button[title="표 삽입"]');
  await tableButton.waitFor({ timeout: 5000 });
  await tableButton.click();
  const insertBtn = page.getByRole('button', { name: '삽입' }).first();
  await insertBtn.click();
  await page.locator('table').first().waitFor({ timeout: 8000 });
}

async function ensureTableExists(page, minimum = 1) {
  const current = await page.locator('td').count();
  if (current >= minimum) return;
  await openInsertTable(page);
  await page.waitForTimeout(250);
}

async function ensureTableSelection(page, range = defaultTableSelection()) {
  await page.evaluate((r) => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge?.setTableSelectionRange) return;
    bridge.setTableSelectionRange(r);
  }, range);
  await page.waitForTimeout(80);
  const snapshot = await getStateSnapshot(page);
  if (!snapshot.selection || snapshot.selection.type !== 'cell') {
    throw new Error('table selection not applied');
  }
  if (snapshot.selection.tableIndex !== range.tableIndex) {
    throw new Error('unexpected table index after selection');
  }
  return snapshot;
}

function getFormatSidebar(page) {
  return page.locator(SIDEBAR_SELECTOR);
}

async function ensureSidebarOpen(page) {
  const sidebar = getFormatSidebar(page);
  const snapshot = await getStateSnapshot(page);
  if (!snapshot.sidebarOpen) {
    let openBtn = page.locator('button[aria-label="서식 사이드바 열기"][class*="absolute"]').first();
    if (await openBtn.count() === 0) {
      openBtn = page.locator('button[aria-label="서식 사이드바 열기"]').first();
    }
    if (await openBtn.count() === 0) {
      throw new Error('sidebar open control missing');
    }
    await openBtn.click();
    await sidebar.waitFor({ state: 'visible', timeout: 5000 });
  }
  if (await sidebar.isVisible().catch(() => false)) return sidebar;
  if (!(await sidebar.isVisible().catch(() => false))) {
    await page.waitForTimeout(80);
  }
  return sidebar;
}

async function ensureTablePropertiesPanel(page) {
  await ensureTableExists(page, 1);
  await ensureTableSelection(page);
  const sidebar = await ensureSidebarOpen(page);

  await clickTableMenuItem(page, '표 속성…');
  await page.waitForTimeout(150);

  const tableTab = sidebar.getByRole('button', { name: '표', exact: true }).first();
  if (await tableTab.isVisible().catch(() => false)) {
    await tableTab.click();
  }
  await sidebar.getByRole('button', { name: '표 크기', exact: true }).waitFor({ timeout: 5000 });
  return sidebar;
}

async function ensureCellPropertiesPanel(page) {
  await ensureTableSelection(page);
  const sidebar = await ensureSidebarOpen(page);
  const cellTab = sidebar.getByRole('button', { name: '셀', exact: true }).first();
  if (await cellTab.count() > 0) {
    await cellTab.click();
    await page.waitForTimeout(120);
  }
  return sidebar;
}

async function getSection(sidebar, title, exact = false) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matcher = exact
    ? new RegExp(`^${escaped}$`)
    : new RegExp(`^${escaped}`);
  const btn = sidebar.getByRole('button', { name: matcher }).first();
  await btn.waitFor({ timeout: 5000 });
  const root = btn.locator('xpath=ancestor::*[contains(@class, "border-b")]').first();
  let content = root.locator('div.px-3.pb-3').first();
  if (!(await content.isVisible().catch(() => false))) {
    await btn.click();
    content = root.locator('div.px-3.pb-3').first();
    await content.waitFor({ state: 'visible', timeout: 5000 });
  }
  return { button: btn, root, content };
}

async function getDebug(page, key) {
  return page.evaluate((k) => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge || !bridge[k]) throw new Error('bridge unavailable');
    return bridge[k]();
  }, key);
}

async function ensureFirstParagraphFocused(page) {
  await page.evaluate(() => {
    const el = document.querySelector('[data-page] [contenteditable="true"]');
    if (el) {
      el.focus();
      const sel = window.getSelection();
      if (sel) {
        sel.selectAllChildren(el);
        sel.collapseToStart();
      }
    }
  });
}

(async () => {
  await fs.mkdir(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1200 } });
  const page = await context.newPage();

  const adResponses = [];
  const consoleErrors = [];
  let lastApiError = null;

  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/ads')) {
      adResponses.push({ url, status: res.status() });
      if (res.status() >= 400) {
        lastApiError = { url, status: res.status() };
      }
    }
  });

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(900);

  await runStep(page, '01-landing', async () => {
    await page.locator('[data-hwpx-editor-root="true"]').waitFor({ timeout: 30000 });
    return {
      title: await page.title(),
      url: page.url(),
      consoleErrors: consoleErrors.length,
      adCalls: adResponses.length,
    };
  });

  await runStep(page, '02-first-paragraph-focus', async () => {
    await ensureFirstParagraphFocused(page);
    return await page.evaluate(() => {
      const el = document.activeElement;
      return {
        isEditable: !!el?.isContentEditable,
        inPage: !!el?.closest?.('[data-page]'),
        tag: el?.tagName ?? null,
      };
    });
  });

  await runStep(page, '03-quick-controls', async () => {
    const quickControls = ['뒤로가기', '홈', '대시', '내 드라이브', '광고 관리'];
    const values = {};
    for (const label of quickControls) {
      const count = await page.getByRole('button', { name: label }).count();
      const countLink = await page.getByRole('link', { name: label }).count();
      values[label] = { buttons: count, links: countLink };
      if (count + countLink === 0) {
        throw new Error(`quick control missing: ${label}`);
      }
    }
    return values;
  });

  await runStep(page, '04-ad-rails-notice', async () => {
    const leftAside = page.locator('aside').nth(0);
    const rightAside = page.locator('aside').nth(1);
    const notice = page.locator('text=맞춤 광고');
    const customConsent = page.locator('text=문서 내용을 기기에서만').first();
    const leftAds = await leftAside.count();
    const rightAds = await rightAside.count();
    return {
      leftAsideVisible: await leftAside.isVisible(),
      rightAsideVisible: await rightAside.isVisible(),
      leftAsideCount: leftAds,
      rightAsideCount: rightAds,
      noticeCount: await notice.count(),
      consentCount: await customConsent.count(),
      adApiCalls: adResponses.length,
      adApiLast: adResponses.at(-1) ?? null,
    };
  });

  await runStep(page, '05-table-insert', async () => {
    await openInsertTable(page);
    await page.waitForSelector('td[data-hwpx-cell="1"]', { timeout: 5000 });
    const tdCount = await page.locator('td[data-hwpx-cell="1"]').count();
    const debug = await getDebug(page, 'getTableDebug');
    return {
      tdCount,
      rowCount: debug.rowCount,
      colCount: debug.colCount,
    };
  });

  await runStep(page, '06-table-width-adjust', async () => {
    const sidebar = await ensureTablePropertiesPanel(page);
    const section = await getSection(sidebar, '표 크기');
    const first = section.content.locator('input[type="number"]').nth(0);
    const before = Number(await first.inputValue());
    const target = before + 10;
    await first.fill(String(target));
    await first.press('Enter');
    await page.waitForTimeout(250);
    const after = Number(await first.inputValue());
    const debug = await getDebug(page, 'getTableDebug');
    return { before, after, rowWidthMm: Number((debug.widthHwp / 100).toFixed(2)) };
  });

  await runStep(page, '07-table-fill-page', async () => {
    const sidebar = await ensureTablePropertiesPanel(page);
    const section = await getSection(sidebar, '표 크기');
    const fullBtn = section.content.getByRole('button', { name: '종이 폭 꽉 채우기' }).first();
    const before = await getDebug(page, 'getTableDebug');
    await fullBtn.click();
    await page.waitForTimeout(250);
    const after = await getDebug(page, 'getTableDebug');
    const pageDebug = await getDebug(page, 'getPageDebug');
    const pagePixelDiff = Math.abs(after.widthHwp - (pageDebug.pageWidthPx - pageDebug.marginLeftPx - pageDebug.marginRightPx));
    return {
      beforeMm: Number((before.widthHwp / 100).toFixed(2)),
      afterMm: Number((after.widthHwp / 100).toFixed(2)),
      pageAreaMmApprox: Number(((pageDebug.pageWidthPx - pageDebug.marginLeftPx - pageDebug.marginRightPx) / 100).toFixed(2)),
      pagePixelDiff,
    };
  });

  await runStep(page, '08-table-out-margins', async () => {
    const sidebar = await ensureTablePropertiesPanel(page);
    const section = await getSection(sidebar, '바깥 여백');
    const topInput = section.content.locator('input[type="number"]').nth(0);
    const rightInput = section.content.locator('input[type="number"]').nth(3);
    const before = await getDebug(page, 'getTableDebug');
    await topInput.fill('4.2');
    await topInput.press('Enter');
    await rightInput.fill('9.2');
    await rightInput.press('Enter');
    await page.waitForTimeout(240);
    const after = await getDebug(page, 'getTableDebug');
    return {
      beforeTop: before.outMargin?.top,
      beforeRight: before.outMargin?.right,
      afterTop: after.outMargin?.top,
      afterRight: after.outMargin?.right,
    };
  });

  await runStep(page, '09-table-in-margins', async () => {
    const sidebar = await ensureTablePropertiesPanel(page);
    const section = await getSection(sidebar, '안쪽 여백');
    const topInput = section.content.locator('input[type="number"]').nth(0);
    const rightInput = section.content.locator('input[type="number"]').nth(1);
    await topInput.fill('2.0');
    await topInput.press('Enter');
    await rightInput.fill('3.0');
    await rightInput.press('Enter');
    await page.waitForTimeout(200);
    const after = await getDebug(page, 'getTableDebug');
    return {
      topMm: after.inMargin?.top,
      rightMm: after.inMargin?.right,
    };
  });

  await runStep(page, '10-table-single-side-border', async () => {
    const sidebar = await ensureCellPropertiesPanel(page);
    const section = await getSection(sidebar, '테두리', true);
    const presetBtn = section.content.getByRole('button', { name: '없음', exact: true }).first();
    await presetBtn.click();
    const leftBtn = section.content.getByRole('button', { name: 'L', exact: true }).first();
    await leftBtn.click();
    const selects = section.content.locator('select');
    await selects.first().selectOption('DASH');
    await selects.nth(1).selectOption('0.5 mm');
    const styleInputs = section.content.locator('button[title="색상"]');
    if (await styleInputs.count() > 0) {
      await styleInputs.first().click();
    }
    await page.waitForTimeout(120);
    const style = await getDebug(page, 'getTableDebug');
    return {
      selectedCellBorderLeft: style.selectedCellStyle?.borderLeftType,
      selectedCellBorderRight: style.selectedCellStyle?.borderRightType,
    };
  });

  await runStep(page, '11-table-merge-split', async () => {
    await ensureTableExists(page, 2);
    await ensureTableSelection(page, {
      sectionIndex: 0,
      paragraphIndex: 0,
      tableIndex: 0,
      row: 0,
      col: 0,
      endRow: 0,
      endCol: 1,
    });
    const before = await getDebug(page, 'getTableDebug');
    await clickTableMenuItem(page, '셀 합치기');
    await page.waitForTimeout(250);
    const merged = await getDebug(page, 'getTableDebug');
    await ensureTableSelection(page, {
      sectionIndex: 0,
      paragraphIndex: 0,
      tableIndex: 0,
      row: 0,
      col: 0,
      endRow: 0,
      endCol: 0,
    });
    await clickTableMenuItem(page, '셀 나누기');
    await page.waitForTimeout(250);
    const split = await getDebug(page, 'getTableDebug');
    return {
      beforeAnchor: before.anchorCellCount,
      afterMergeAnchor: merged.anchorCellCount,
      afterSplitAnchor: split.anchorCellCount,
    };
  });

  await runStep(page, '12-table-row-col-delete', async () => {
    const before = await getDebug(page, 'getTableDebug');
    await clickTableMenuItem(page, '줄 삽입 (아래)');
    await page.waitForTimeout(200);
    const afterInsert = await getDebug(page, 'getTableDebug');
    await clickTableMenuItem(page, '줄 삭제');
    await page.waitForTimeout(200);
    const afterDelete = await getDebug(page, 'getTableDebug');
    await clickTableMenuItem(page, '칸 삽입 (오른쪽)');
    await page.waitForTimeout(200);
    const afterInsertCol = await getDebug(page, 'getTableDebug');
    await clickTableMenuItem(page, '칸 삭제');
    await page.waitForTimeout(200);
    const afterDeleteCol = await getDebug(page, 'getTableDebug');
    return {
      before: { rows: before.rowCount, cols: before.colCount },
      afterInsert: { rows: afterInsert.rowCount, cols: afterInsert.colCount },
      afterDelete: { rows: afterDelete.rowCount, cols: afterDelete.colCount },
      afterInsertCol: { rows: afterInsertCol.rowCount, cols: afterInsertCol.colCount },
      afterDeleteCol: { rows: afterDeleteCol.rowCount, cols: afterDeleteCol.colCount },
    };
  });

  await runStep(page, '13-formatting-actions', async () => {
    await ensureFirstParagraphFocused(page);
    const editable = page.locator('[data-page] [contenteditable="true"]').first();
    await editable.click();
    await page.keyboard.type('테스트');
    await page.getByTitle('굵게 (Ctrl+B)').click();
    await page.getByTitle('기울임 (Ctrl+I)').click();
    await page.getByTitle('밑줄 (Ctrl+U)').click();
    await page.getByTitle('취소선 (Ctrl+D)').click();
    const text = await editable.innerText();
    return { textLength: text.length };
  });

  await runStep(page, '14-font-family-via-ribbon', async () => {
    await ensureTableExists(page, 1);
    const firstCell = page.locator('td').first();
    await firstCell.click();
    await page.keyboard.press('Meta+A');
    const fontDropdown = page.locator('div[title="글꼴"]').first();
    await fontDropdown.locator('> button').click();
    const optionButtons = fontDropdown.locator('div.absolute button');
    const count = await optionButtons.count();
    if (count < 2) throw new Error('font options unavailable');
    await optionButtons.nth(1).click();
    await page.waitForTimeout(180);
    const debug = await getDebug(page, 'getTableDebug');
    if (!debug.selectedCellTextStyle?.fontFamily) {
      throw new Error('selectedCellTextStyle.fontFamily is empty');
    }
    return { selectedFont: debug.selectedCellTextStyle.fontFamily };
  });

  await runStep(page, '15-sidebar-toggle', async () => {
    const closeBtn = page.getByRole('button', { name: '사이드바 닫기' }).first();
    if (await closeBtn.count() > 0) {
      await closeBtn.click();
      await getFormatSidebar(page).waitFor({ state: 'hidden', timeout: 3000 }).catch(() => {});
    }
    let openBtn = page.locator('button[aria-label="서식 사이드바 열기"][class*="absolute"]').first();
    if (await openBtn.count() === 0) {
      openBtn = page.locator('button[aria-label="서식 사이드바 열기"]').first();
    }
    const openFound = await openBtn.waitFor({ state: 'visible', timeout: 3000 }).then(() => true).catch(() => false);
    if (!openFound) {
      throw new Error('sidebar open button not visible');
    }
    await openBtn.click();
    await getFormatSidebar(page).waitFor({ state: 'visible', timeout: 3000 });
    return { toggled: true };
  });

  await runStep(page, '16-table-cell-drag-select', async () => {
    await ensureTableSelection(page);
    const sidebar = await getFormatSidebar(page);
    if (await sidebar.isVisible().catch(() => false)) {
      const tableTab = sidebar.getByRole('button', { name: '셀', exact: true }).first();
      if (await tableTab.isVisible().catch(() => false)) {
        await tableTab.click();
      }
    }
    const firstCell = page.locator('td[data-hwpx-cell="1"]').first();
    const secondCell = page.locator('td[data-hwpx-cell="1"]').nth(4);
    const firstBox = await firstCell.boundingBox();
    const secondBox = await secondCell.boundingBox();
    if (!firstBox || !secondBox) {
      throw new Error('table cells not measurable for drag select');
    }
    await page.mouse.move(firstBox.x + firstBox.width / 2, firstBox.y + firstBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(secondBox.x + secondBox.width / 2, secondBox.y + secondBox.height / 2);
    await page.mouse.up();
    const snapshot = await getStateSnapshot(page);
    const selection = snapshot.selection;
    if (!selection?.endRow && !selection?.endCol) {
      throw new Error('drag selection not applied');
    }
    return {
      start: { row: selection.row, col: selection.col },
      end: { row: selection.endRow, col: selection.endCol },
    };
  });

  await runStep(page, '17-footnote-endnote-safe-zone', async () => {
    await clickTopMenuItem(page, '입력', '각주');
    await clickTopMenuItem(page, '입력', '미주');
    await page.waitForTimeout(220);
    const pageDebug = await getDebug(page, 'getPageDebug');
    const zones = await page.evaluate((d) => {
      const page = document.querySelector('[data-page]');
      const foot = document.querySelector('[data-note-content="footnotes"]');
      const end = document.querySelector('[data-note-content="endnotes"]');
      if (!page || !foot || !end) return null;
      const p = page.getBoundingClientRect();
      const f = foot.getBoundingClientRect();
      const e = end.getBoundingClientRect();
      const minX = p.left + d.marginLeftPx;
      const maxX = p.right - d.marginRightPx;
      return {
        footSafe: f.left >= minX - 1.5 && f.right <= maxX + 1.5,
        endSafe: e.left >= minX - 1.5 && e.right <= maxX + 1.5,
        footLeft: f.left,
        footRight: f.right,
        endLeft: e.left,
        endRight: e.right,
      };
    }, pageDebug);
    if (!zones?.footSafe || !zones?.endSafe) {
      throw new Error(`note zone check failed: ${JSON.stringify(zones)}`);
    }
    return zones;
  });

  await runStep(page, '18-ctrl-r-align-shortcut', async () => {
    const editable = page.locator('[data-page] [contenteditable="true"]').first();
    await editable.click();
    await page.keyboard.press('Meta+A');
    await page.keyboard.down('Control');
    await page.keyboard.press('R');
    await page.keyboard.up('Control');
    return { alignShortcutExecuted: true };
  });

  await runStep(page, '19-ad-api-health', async () => {
    const health = {
      total: adResponses.length,
      failed: adResponses.filter((r) => r.status >= 400).length,
      last: adResponses.at(-1) ?? null,
      consoleErrors,
      consentVisible: await page.locator('text=맞춤 광고').count(),
      adEndpointError: lastApiError,
    };
    if (!health.last) {
      throw new Error('ads api did not respond');
    }
    return health;
  });

  const summary = {
    generatedAt: new Date().toISOString(),
    baseUrl: BASE_URL,
    total: steps.length,
    passCount: steps.filter((s) => s.status === 'passed').length,
    failCount: steps.filter((s) => s.status === 'failed').length,
    steps,
    consoleErrors,
    adResponses,
  };

  const reportPath = path.join(outDir, 'editor-3098-qa-report.json');
  await fs.writeFile(reportPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
  console.log('SUMMARY', JSON.stringify({ outDir, total: summary.total, pass: summary.passCount, fail: summary.failCount }));

  await context.close();
  await browser.close();
  if (summary.failCount > 0) {
    process.exitCode = 1;
  }
})();
