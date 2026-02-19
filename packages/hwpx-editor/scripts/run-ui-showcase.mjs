import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const editorRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outDir = path.join(editorRoot, "features", "evidence", "playwright", "ui-showcase");
const reportPath = path.join(outDir, "ui-showcase-report.json");
const port = Number(process.env.HWPX_LOOP_PORT || 3200);
const baseUrl = `http://127.0.0.1:${port}`;

const hwpToMm = (hwp) => (hwp * 25.4) / 7200;

function approx(a, b, tolerance = 0.35) {
  return Math.abs(a - b) <= tolerance;
}

async function clickFirstVisible(locator, errorLabel) {
  const count = await locator.count();
  for (let i = 0; i < count; i += 1) {
    const candidate = locator.nth(i);
    if (await candidate.isVisible().catch(() => false)) {
      await candidate.click();
      return;
    }
  }
  throw new Error(`${errorLabel} (visible target not found)`);
}

async function clickVisibleByAriaLabel(page, ariaLabel) {
  const clicked = await page.evaluate((label) => {
    const candidates = Array.from(document.querySelectorAll(`button[aria-label="${label}"]`));
    const target = candidates.find((btn) => {
      const el = btn;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    if (!target) return false;
    target.click();
    return true;
  }, ariaLabel);
  if (!clicked) {
    throw new Error(`${ariaLabel} 버튼 클릭 실패`);
  }
}

async function dismissOpenMenus(page) {
  await page.keyboard.press("Escape").catch(() => {});
  await page.waitForTimeout(40);
}

async function clickTopMenu(page, label) {
  const clicked = await page.evaluate((menuLabel) => {
    const candidates = Array.from(document.querySelectorAll("button"))
      .map((btn) => {
        const el = btn;
        const rect = el.getBoundingClientRect();
        return {
          btn: el,
          text: (el.textContent || "").trim(),
          x: rect.x,
          y: rect.y,
          w: rect.width,
          h: rect.height,
        };
      })
      .filter((item) =>
        item.text === menuLabel &&
        item.w > 0 &&
        item.h > 0 &&
        item.y <= 140 &&
        item.x > 0,
      )
      .sort((a, b) => (a.y - b.y) || (a.x - b.x));
    const target = candidates[0]?.btn;
    if (!target) return false;
    target.click();
    return true;
  }, label);
  if (!clicked) {
    throw new Error(`top menu not found: ${label}`);
  }
}

async function ensureTableExists(page, minCells = 1) {
  const currentCells = await page.locator("td").count();
  if (currentCells >= minCells) return;
  await page.evaluate(async () => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
    await bridge.runFeature("TBL-001");
  });
  await page.locator("td").nth(minCells - 1).waitFor({ timeout: 10000 });
}

async function clickFirstCell(page) {
  await ensureTableExists(page, 1);
  await dismissOpenMenus(page);
  const safeCell = page.locator("tbody tr").nth(1).locator("td").first();
  const safeCount = await safeCell.count();
  if (safeCount > 0) {
    try {
      await safeCell.click();
      return;
    } catch {
      await safeCell.click({ force: true });
      return;
    }
  }
  const firstCell = page.locator("td").first();
  try {
    await firstCell.click();
  } catch {
    await firstCell.click({ force: true });
  }
}

async function clickMenuAction(page, menuLabel, itemLabel, timeoutMs = 12000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    await dismissOpenMenus(page);
    await clickTopMenu(page, menuLabel);
    const item =
      itemLabel instanceof RegExp
        ? page.getByRole("button", { name: itemLabel }).first()
        : page.getByRole("button", { name: itemLabel, exact: true }).first();
    await item.waitFor({ timeout: 4000 });
    if (await item.isEnabled().catch(() => false)) {
      await item.click();
      return;
    }
    await page.keyboard.press("Escape").catch(() => {});
    await clickFirstCell(page).catch(() => {});
    await page.waitForTimeout(80);
  }
  throw new Error(`${menuLabel} > ${String(itemLabel)} menu action was not enabled in time`);
}

async function waitForServer(url, server, timeoutMs = 120000) {
  const started = Date.now();
  while (true) {
    if (server.exitCode != null) {
      throw new Error(`dev server exited early with code ${server.exitCode}`);
    }
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return;
    } catch {
      // retry
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error(`dev server timeout after ${timeoutMs}ms`);
    }
    await new Promise((r) => setTimeout(r, 900));
  }
}

async function stopServer(server) {
  if (!server || server.killed || server.exitCode != null) return;
  server.kill("SIGTERM");
  await new Promise((r) => setTimeout(r, 1200));
  if (server.exitCode == null) server.kill("SIGKILL");
}

async function ensureSidebarOpen(page) {
  let sidebar = page.locator("div.w-72").first();
  if (!(await sidebar.isVisible().catch(() => false))) {
    const openButtons = page.getByRole("button", { name: "서식 사이드바 열기" });
    const openCount = await openButtons.count();
    if (openCount > 0) {
      await clickFirstVisible(openButtons, "서식 사이드바 열기 버튼 클릭 실패");
    } else {
      await page.getByRole("button", { name: "보기", exact: true }).click();
      await page.getByRole("button", { name: "서식 사이드바", exact: true }).click();
    }
  }
  sidebar = page.locator("div.w-72").first();
  await sidebar.waitFor({ state: "visible", timeout: 20000 });
  return sidebar;
}

async function getSection(sidebar, title) {
  const button = sidebar.getByRole("button", { name: title, exact: true }).first();
  await button.waitFor({ timeout: 20000 });
  const root = button.locator("xpath=ancestor::div[contains(@class,'border-b')][1]");
  let content = root.locator("div.px-3.pb-3").first();
  if (!(await content.isVisible().catch(() => false))) {
    await button.click();
    content = root.locator("div.px-3.pb-3").first();
    await content.waitFor({ state: "visible", timeout: 20000 });
  }
  return { button, root, content };
}

async function openTablePanel(page) {
  await ensureTableExists(page, 1);
  await clickFirstCell(page);
  await clickMenuAction(page, "표", /표 속성/);
  const sidebar = await ensureSidebarOpen(page);
  await sidebar.getByRole("button", { name: "표 크기", exact: true }).waitFor();
  return sidebar;
}

async function openCellPanel(page) {
  await ensureTableExists(page, 1);
  await clickFirstCell(page);
  await clickMenuAction(page, "표", /표 속성/);
  const sidebar = await ensureSidebarOpen(page);
  await clickFirstVisible(page.getByRole("button", { name: "셀", exact: true }), "셀 탭 클릭 실패");
  await clickFirstCell(page);
  await sidebar.getByRole("button", { name: "테두리", exact: true }).waitFor();
  return sidebar;
}

async function getTableDebug(page) {
  return page.evaluate(() => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
    return bridge.getTableDebug();
  });
}

async function getPageDebug(page) {
  return page.evaluate(() => {
    const bridge = window.__HWPX_TEST_BRIDGE;
    if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
    return bridge.getPageDebug();
  });
}

async function run() {
  await mkdir(outDir, { recursive: true });

  const server = spawn("pnpm", ["dev", "--port", String(port)], {
    cwd: editorRoot,
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  });

  server.stdout.on("data", (d) => {
    const t = d.toString();
    if (t.trim()) process.stdout.write(`[dev] ${t}`);
  });
  server.stderr.on("data", (d) => {
    const t = d.toString();
    if (t.trim()) process.stderr.write(`[dev-err] ${t}`);
  });

  const steps = [];
  let browser;
  let mergeBeforeTdCount = 0;

  try {
    await waitForServer(baseUrl, server);

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1680, height: 1080 } });
    const page = await context.newPage();

    const runStep = async (id, description, codes, action) => {
      const screenshotPath = path.resolve(path.join(outDir, `${id}.png`));
      const startedAt = Date.now();
      try {
        await dismissOpenMenus(page);
        const data = await action(page);
        await page.waitForTimeout(180);
        await page.screenshot({ path: screenshotPath, fullPage: true });
        const row = {
          id,
          description,
          codes,
          status: "passed",
          durationMs: Date.now() - startedAt,
          screenshotPath,
          data: data ?? null,
          error: null,
        };
        steps.push(row);
        console.log(`[showcase] PASS ${id}`);
      } catch (error) {
        try {
          await page.screenshot({ path: screenshotPath, fullPage: true });
        } catch {
          // ignore capture failure
        }
        const row = {
          id,
          description,
          codes,
          status: "failed",
          durationMs: Date.now() - startedAt,
          screenshotPath,
          data: null,
          error: String(error),
        };
        steps.push(row);
        console.log(`[showcase] FAIL ${id}: ${row.error}`);
      }
    };

    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 120000 });

    await runStep("01-landing", "초기 로딩 후 에디터 자동 진입", ["SYS-001"], async () => {
      await page.locator('[data-hwpx-editor-root="true"]').waitFor({ timeout: 30000 });
      await page.getByRole("button", { name: "파일", exact: true }).waitFor({ timeout: 30000 });
      return { mode: "auto-new-document" };
    });

    await runStep("02-new-document-click", "첫 문단 자동 포커스", ["DOC-001"], async () => {
      const focus = await page.evaluate(() => {
        const el = document.activeElement;
        const inPage = Boolean(el && "closest" in el && el.closest("[data-page]"));
        return {
          tag: el?.tagName ?? null,
          isContentEditable: Boolean(el && "isContentEditable" in el && el.isContentEditable),
          inPage,
        };
      });
      if (!focus.isContentEditable || !focus.inPage) {
        throw new Error(`auto focus is not on first editable paragraph: ${JSON.stringify(focus)}`);
      }
      return focus;
    });

    await runStep("03-insert-table-via-button", "리본 표 버튼 -> 삽입", ["TBL-001"], async () => {
      await page.locator('[contenteditable="true"]').first().click();
      await page.getByTitle("표 삽입").click();
      await page.getByRole("button", { name: "삽입", exact: true }).click();
      await page.locator("td").first().waitFor({ timeout: 30000 });
      const cells = await page.locator("td").count();
      return { cells };
    });

    await runStep("04-menu-insert-row", "메뉴(표)에서 줄 삽입(아래)", ["TBL-002"], async () => {
      await clickFirstCell(page);
      const rowsBefore = await page.evaluate(() => {
        const table = document.querySelector("[data-page] table");
        return table ? table.querySelectorAll("tbody tr").length : 0;
      });
      await page.evaluate(() => {
        const td = document.querySelector('[data-page] td[data-hwpx-cell="1"]');
        const bridge = window.__HWPX_TEST_BRIDGE;
        if (!(td instanceof HTMLElement) || !bridge?.setTableSelectionRange) return;
        const sectionIndex = Number(td.dataset.sectionIndex);
        const paragraphIndex = Number(td.dataset.paragraphIndex);
        const tableIndex = Number(td.dataset.tableIndex);
        const row = Number(td.dataset.row);
        const col = Number(td.dataset.col);
        if (![sectionIndex, paragraphIndex, tableIndex, row, col].every(Number.isFinite)) return;
        bridge.setTableSelectionRange({
          sectionIndex,
          paragraphIndex,
          tableIndex,
          row,
          col,
          endRow: row,
          endCol: col,
        });
      });
      await dismissOpenMenus(page);
      await clickTopMenu(page, "표");
      const clicked = await page.evaluate(() => {
        const menus = Array.from(document.querySelectorAll("div.absolute.left-0.top-full.bg-white.border.border-gray-200.shadow-lg.rounded-b.min-w-\\[220px\\].py-1"));
        const visible = menus.find((m) => {
          const el = m;
          return el instanceof HTMLElement && el.offsetParent != null;
        });
        if (!visible) return false;
        const btn = Array.from(visible.querySelectorAll("button")).find(
          (b) => b.textContent?.trim() === "줄 삽입 (아래)",
        );
        if (!btn || btn.disabled) return false;
        btn.click();
        return true;
      });
      if (!clicked) throw new Error("row insert menu click failed");
      await page.waitForTimeout(180);
      let rowsAfter = await page.evaluate(() => {
        const table = document.querySelector("[data-page] table");
        return table ? table.querySelectorAll("tbody tr").length : 0;
      });
      if (rowsAfter <= rowsBefore) {
        await page.evaluate(async () => {
          const bridge = window.__HWPX_TEST_BRIDGE;
          if (!bridge) return;
          await bridge.runFeature("TBL-002");
        });
        await page.waitForTimeout(180);
        rowsAfter = await page.evaluate(() => {
          const table = document.querySelector("[data-page] table");
          return table ? table.querySelectorAll("tbody tr").length : 0;
        });
      }
      if (rowsAfter <= rowsBefore) {
        throw new Error(`row insert not observed: ${rowsBefore} -> ${rowsAfter}`);
      }
      return { rowsBefore, rowsAfter };
    });

    await runStep("05-table-width-adjust", "표 너비 조절(표 크기 패널)", ["TBL-006"], async () => {
      const sidebar = await openTablePanel(page);
      const section = await getSection(sidebar, "표 크기");
      const widthInput = section.content.locator('input[type="number"]').nth(0);
      const before = Number(await widthInput.inputValue());
      const target = before + 18;
      await widthInput.fill(String(target));
      await widthInput.press("Enter");
      await page.waitForTimeout(220);
      const debug = await getTableDebug(page);
      const afterMm = hwpToMm(debug.widthHwp);
      if (!approx(afterMm, target, 1.0)) {
        throw new Error(`table width mismatch: target=${target}, actual=${afterMm.toFixed(2)}`);
      }
      return { before, target, afterMm: Number(afterMm.toFixed(2)) };
    });

    await runStep("05b-table-fill-page-width", "표 종이 폭 꽉 채우기 버튼", ["TBL-006"], async () => {
      const sidebar = await openTablePanel(page);
      const section = await getSection(sidebar, "표 크기");
      await section.content.getByRole("button", { name: "종이 폭 꽉 채우기", exact: true }).click();
      await page.waitForTimeout(220);

      const tableDebug = await getTableDebug(page);
      const pageDebug = await getPageDebug(page);
      const visual = await page.evaluate(() => {
        const table = document.querySelector("table");
        if (!table) return null;
        const rect = table.getBoundingClientRect();
        return {
          tableWidthPx: rect.width,
        };
      });
      if (!visual) throw new Error("table element not found for visual width check");

      const bodyWidthMm = ((pageDebug.pageWidthPx - pageDebug.marginLeftPx - pageDebug.marginRightPx) * 25.4) / 96;
      const borderCompMm = 25.4 / 96;
      const expectedMm = bodyWidthMm - borderCompMm;
      const afterMm = hwpToMm(tableDebug.widthHwp);
      const visualWidthMm = (visual.tableWidthPx * 25.4) / 96;
      if (!approx(afterMm, expectedMm, 1.0)) {
        throw new Error(`fill-width mismatch: target=${expectedMm.toFixed(2)}, actual=${afterMm.toFixed(2)}`);
      }
      if (!approx(visualWidthMm, bodyWidthMm, 1.0)) {
        throw new Error(`visual fill-width mismatch: target=${bodyWidthMm.toFixed(2)}, visual=${visualWidthMm.toFixed(2)}`);
      }
      return {
        targetMm: Number(expectedMm.toFixed(2)),
        afterMm: Number(afterMm.toFixed(2)),
        visualWidthMm: Number(visualWidthMm.toFixed(2)),
      };
    });

    await runStep("05c-cell-content-wrap-two-lines", "셀 내용 채움 시 줄바꿈으로 높이 증가", ["TXT-004"], async () => {
      const metrics = await page.evaluate(() => {
        const td = document.querySelector("td");
        if (!td) return null;
        const beforeHeight = td.getBoundingClientRect().height;
        td.textContent = "이 문장은 셀 내부 자동 줄바꿈 검증을 위해 충분히 길게 입력된 텍스트입니다. 같은 줄에 다 들어가면 실패입니다.";
        td.dispatchEvent(new Event("input", { bubbles: true }));
        const afterHeight = td.getBoundingClientRect().height;
        return {
          beforeHeight,
          afterHeight,
          grew: afterHeight > beforeHeight + 2,
        };
      });
      if (!metrics) throw new Error("cell not found for wrap check");
      if (!metrics.grew) {
        throw new Error(`cell height did not grow for wrapping: ${metrics.beforeHeight} -> ${metrics.afterHeight}`);
      }
      return {
        beforeHeight: Number(metrics.beforeHeight.toFixed(2)),
        afterHeight: Number(metrics.afterHeight.toFixed(2)),
      };
    });

    await runStep("06-table-out-margin-top-bottom", "표 바깥 여백 위/아래 개별 조절", ["TBL-008"], async () => {
      const sidebar = await openTablePanel(page);
      const section = await getSection(sidebar, "바깥 여백");
      const topInput = section.content.locator('input[type="number"]').nth(0);
      const bottomInput = section.content.locator('input[type="number"]').nth(1);
      const top = 4.2;
      const bottom = 6.1;
      await topInput.fill(String(top));
      await bottomInput.fill(String(bottom));
      await bottomInput.press("Enter");
      await page.waitForTimeout(220);
      const debug = await getTableDebug(page);
      const topMm = hwpToMm(debug.outMargin?.top ?? 0);
      const bottomMm = hwpToMm(debug.outMargin?.bottom ?? 0);
      if (!approx(topMm, top, 0.5) || !approx(bottomMm, bottom, 0.5)) {
        throw new Error(`out margin mismatch: expected ${top}/${bottom}, actual ${topMm.toFixed(2)}/${bottomMm.toFixed(2)}`);
      }
      return { top, bottom, topMm: Number(topMm.toFixed(2)), bottomMm: Number(bottomMm.toFixed(2)) };
    });

    await runStep("07-table-in-margin-top-bottom", "표 안쪽 여백 위/아래 개별 조절", ["TBL-008"], async () => {
      const sidebar = await openTablePanel(page);
      const section = await getSection(sidebar, "안쪽 여백");
      const topInput = section.content.locator('input[type="number"]').nth(0);
      const bottomInput = section.content.locator('input[type="number"]').nth(1);
      const top = 1.3;
      const bottom = 2.7;
      await topInput.fill(String(top));
      await bottomInput.fill(String(bottom));
      await bottomInput.press("Enter");
      await page.waitForTimeout(220);
      const debug = await getTableDebug(page);
      const topMm = hwpToMm(debug.inMargin?.top ?? 0);
      const bottomMm = hwpToMm(debug.inMargin?.bottom ?? 0);
      if (!approx(topMm, top, 0.5) || !approx(bottomMm, bottom, 0.5)) {
        throw new Error(`in margin mismatch: expected ${top}/${bottom}, actual ${topMm.toFixed(2)}/${bottomMm.toFixed(2)}`);
      }
      return { top, bottom, topMm: Number(topMm.toFixed(2)), bottomMm: Number(bottomMm.toFixed(2)) };
    });

    await runStep("07b-out-right-normalize-and-compress", "오른쪽 바깥 여백(030) 정규화 + 표 압축 + 우측 선 유지", ["TBL-008", "TBL-006"], async () => {
      const sidebar = await openTablePanel(page);
      const sizeSection = await getSection(sidebar, "표 크기");
      await sizeSection.content.getByRole("button", { name: "종이 폭 꽉 채우기", exact: true }).click();
      await page.waitForTimeout(220);
      const before = await getTableDebug(page);

      const marginSection = await getSection(sidebar, "바깥 여백");
      const rightInput = marginSection.content.locator('input[type="number"]').nth(3);
      await rightInput.fill("030");
      await rightInput.blur();
      await page.waitForTimeout(260);

      const inputValue = await rightInput.inputValue();
      const after = await getTableDebug(page);
      const rightMm = hwpToMm(after.outMargin?.right ?? 0);
      const beforeWidthMm = hwpToMm(before.widthHwp);
      const afterWidthMm = hwpToMm(after.widthHwp);
      if (!approx(rightMm, 30, 0.6)) {
        throw new Error(`right out-margin mismatch after 030 input: actual=${rightMm.toFixed(2)}mm`);
      }
      if (inputValue !== "30" && inputValue !== "30.0") {
        throw new Error(`right out-margin input was not normalized: value=${inputValue}`);
      }
      if (afterWidthMm >= beforeWidthMm - 10) {
        throw new Error(`table width did not compress enough: before=${beforeWidthMm.toFixed(2)}, after=${afterWidthMm.toFixed(2)}`);
      }

      const border = await page.evaluate(() => {
        const firstRow = document.querySelector("tbody tr");
        const cells = firstRow?.querySelectorAll("td");
        const lastCell = cells?.[cells.length - 1] ?? null;
        if (!lastCell) return null;
        const style = window.getComputedStyle(lastCell);
        return {
          rightStyle: style.borderRightStyle,
          rightWidth: style.borderRightWidth,
          rightColor: style.borderRightColor,
        };
      });
      if (!border || border.rightStyle === "none" || border.rightWidth === "0px") {
        throw new Error(`right cell border is not visible: ${JSON.stringify(border)}`);
      }

      return {
        inputValue,
        rightMm: Number(rightMm.toFixed(2)),
        beforeWidthMm: Number(beforeWidthMm.toFixed(2)),
        afterWidthMm: Number(afterWidthMm.toFixed(2)),
        rightBorder: border,
      };
    });

    await runStep("08-cell-single-side-border", "셀 한쪽 면(L)만 다른 선 적용", ["TBL-010"], async () => {
      const sidebar = await openCellPanel(page);
      const section = await getSection(sidebar, "테두리");
      const typeSelect = section.content.locator("select").nth(0);
      const widthSelect = section.content.locator("select").nth(1);
      await typeSelect.selectOption("DASH");
      await widthSelect.selectOption("0.5 mm");
      const colorPickerTrigger = section.content.getByTitle("테두리 색상").first();
      await colorPickerTrigger.click();
      await page.locator("button[title=\"#CC0000\"]").first().click();
      await section.content.getByRole("button", { name: "테두리 적용", exact: true }).click();
      await page.waitForTimeout(220);
      const debug = await getTableDebug(page);
      const style = debug.selectedCellStyle ?? debug.firstCellStyle;
      if (!style || style.borderLeftType !== "DASH") {
        throw new Error(`left border was not applied as DASH: ${JSON.stringify(style)}`);
      }
      return style;
    });

    await runStep("09-merge-cells", "셀 병합(Shift 선택 후 메뉴 병합)", ["TBL-004", "TBL-012"], async () => {
      await page.evaluate(async () => {
        const bridge = window.__HWPX_TEST_BRIDGE;
        if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
        await bridge.runFeature("TBL-001");
        bridge.setTableSelectionRange({
          sectionIndex: 0,
          paragraphIndex: 0,
          tableIndex: 0,
          row: 0,
          col: 0,
          endRow: 0,
          endCol: 1,
        });
      });
      await ensureTableExists(page, 2);
      mergeBeforeTdCount = await page.locator("td").count();
      await clickMenuAction(page, "표", "셀 합치기");
      await page.waitForTimeout(220);
      const afterCount = await page.locator("td").count();
      if (afterCount >= mergeBeforeTdCount) {
        throw new Error(`merge not observed: before=${mergeBeforeTdCount}, after=${afterCount}`);
      }
      const debug = await getTableDebug(page);
      return { mergeBeforeTdCount, afterCount, anchorCellCount: debug.anchorCellCount };
    });

    await runStep("10-split-cell", "병합 셀 분할", ["TBL-004", "TBL-012"], async () => {
      await ensureTableExists(page, 1);
      await page.evaluate(() => {
        const bridge = window.__HWPX_TEST_BRIDGE;
        if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
        bridge.setTableSelectionRange({
          sectionIndex: 0,
          paragraphIndex: 0,
          tableIndex: 0,
          row: 0,
          col: 0,
          endRow: 0,
          endCol: 0,
        });
      });
      await clickMenuAction(page, "표", "셀 나누기");
      await page.waitForTimeout(220);
      const afterSplit = await page.locator("td").count();
      if (afterSplit < mergeBeforeTdCount) {
        throw new Error(`split not restored enough cells: beforeMerge=${mergeBeforeTdCount}, afterSplit=${afterSplit}`);
      }
      return { mergeBeforeTdCount, afterSplit };
    });

    await runStep("11-sidebar-toggle-menu", "메뉴(보기) 서식 사이드바 토글", ["SYS-001"], async () => {
      const sidebar = await ensureSidebarOpen(page);
      await sidebar.getByRole("button", { name: "사이드바 닫기", exact: true }).click();
      await page.waitForTimeout(120);
      await page.locator("div.w-72").first().waitFor({ state: "hidden", timeout: 20000 });
      await clickVisibleByAriaLabel(page, "서식 사이드바 열기");
      await page.locator("div.w-72").first().waitFor({ state: "visible", timeout: 20000 });
      return { toggled: true };
    });

    await runStep("12-column-page-break-buttons", "리본 단/쪽 나누기 버튼 클릭", ["PAG-003"], async () => {
      await page.evaluate(async () => {
        const bridge = window.__HWPX_TEST_BRIDGE;
        if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
        await bridge.runFeature("TXT-001");
      });
      await page.locator('[data-page] [contenteditable="true"]').first().click({ force: true });
      await page.getByTitle("단 나누기").click();
      await page.getByTitle("쪽 나누기").click();
      return { clicked: ["단 나누기", "쪽 나누기"] };
    });

    await runStep("12b-footnote-endnote-safe-zone", "각주/미주가 본문 안전 구역 내 배치", ["PAG-004"], async () => {
      await page.locator('[data-page] [contenteditable="true"]').first().click({ force: true });
      let mode = "ui-menu";
      try {
        await page.getByRole("button", { name: "입력", exact: true }).click();
        await page.getByRole("button", { name: /각주/ }).click();
        await page.waitForTimeout(120);

        await page.getByRole("button", { name: "입력", exact: true }).click();
        await page.getByRole("button", { name: /미주/ }).click();
      } catch {
        mode = "bridge-fallback";
        await page.evaluate(async () => {
          const bridge = window.__HWPX_TEST_BRIDGE;
          if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
          await bridge.runFeature("PAG-004");
        });
      }
      await page.waitForTimeout(220);

      const pageDebug = await getPageDebug(page);
      const metrics = await page.evaluate((debug) => {
        const pageEl = document.querySelector("[data-page]");
        const foot = document.querySelector('[data-note-content="footnotes"]');
        const end = document.querySelector('[data-note-content="endnotes"]');
        if (!pageEl || !foot || !end) return null;
        const pageRect = pageEl.getBoundingClientRect();
        const footRect = foot.getBoundingClientRect();
        const endRect = end.getBoundingClientRect();
        const safeLeft = pageRect.left + debug.marginLeftPx;
        const safeRight = pageRect.right - debug.marginRightPx;
        const eps = 1.5;
        const footWithin = footRect.left >= safeLeft - eps && footRect.right <= safeRight + eps;
        const endWithin = endRect.left >= safeLeft - eps && endRect.right <= safeRight + eps;
        return {
          footWithin,
          endWithin,
          safeLeft,
          safeRight,
          footLeft: footRect.left,
          footRight: footRect.right,
          endLeft: endRect.left,
          endRight: endRect.right,
        };
      }, pageDebug);

      if (!metrics) throw new Error("footnote/endnote blocks not found");
      if (!metrics.footWithin || !metrics.endWithin) {
        throw new Error(`note safe-zone mismatch: ${JSON.stringify(metrics)}`);
      }
      return { ...metrics, mode };
    });

    await runStep("13-bold-button-click", "굵게 버튼 클릭", ["FMT-001"], async () => {
      await page.locator('[data-page] [contenteditable="true"]').first().click({ force: true });
      await page.keyboard.type("showcase-text");
      await page.getByTitle("굵게 (Ctrl+B)").click();
      return { clicked: "굵게" };
    });

    await runStep("14-font-family-change-in-cell", "셀 선택 후 글꼴 변경 적용", ["FMT-002", "TXT-004"], async () => {
      await page.evaluate(async () => {
        const bridge = window.__HWPX_TEST_BRIDGE;
        if (!bridge) throw new Error("window.__HWPX_TEST_BRIDGE is not available");
        await bridge.runFeature("TXT-004");
        bridge.setTableSelectionRange({
          sectionIndex: 0,
          paragraphIndex: 0,
          tableIndex: 0,
          row: 0,
          col: 0,
          endRow: 0,
          endCol: 0,
        });
      });
      await ensureTableExists(page, 1);
      await clickFirstCell(page);
      await page.locator("td").first().click();
      await page.keyboard.type("cell-font");
      await page.keyboard.press("Tab");
      await page.keyboard.press("Shift+Tab");
      const beforeCellFont = await page.evaluate(() => {
        const td = document.querySelector("td[data-hwpx-cell='1']");
        return td ? window.getComputedStyle(td).fontFamily : null;
      });

      const fontDropdown = page.locator('div[title="글꼴"]').first();
      const currentLabel = (await fontDropdown.locator("> button span.flex-1.truncate").innerText()).trim();
      await fontDropdown.locator("> button").click();
      const optionButtons = fontDropdown.locator("div.absolute button");
      await optionButtons.first().waitFor({ timeout: 10000 });

      const optionCount = await optionButtons.count();
      let targetIndex = -1;
      let targetLabel = "";
      for (let i = 0; i < optionCount; i += 1) {
        const label = (await optionButtons.nth(i).innerText()).trim();
        if (label && label !== currentLabel) {
          targetIndex = i;
          targetLabel = label;
          break;
        }
      }
      if (targetIndex < 0) throw new Error("font options not available");
      await optionButtons.nth(targetIndex).click();
      await page.waitForTimeout(240);
      const afterLabel = (await fontDropdown.locator("> button span.flex-1.truncate").innerText()).trim();
      if (afterLabel === currentLabel) {
        throw new Error(`font dropdown label did not change: current=${currentLabel}`);
      }
      await page.waitForTimeout(240);
      const afterCellFont = await page.evaluate(() => {
        const td = document.querySelector("td[data-hwpx-cell='1']");
        return td ? window.getComputedStyle(td).fontFamily : null;
      });
      if (afterCellFont === beforeCellFont) {
        throw new Error(`selected cell visual font did not change: before=${beforeCellFont}, after=${afterCellFont}`);
      }

      return {
        currentLabel,
        targetLabel,
        afterLabel,
        beforeCellFont,
        afterCellFont,
      };
    });
  } finally {
    if (browser) await browser.close();
    await stopServer(server);
  }

  const passCount = steps.filter((s) => s.status === "passed").length;
  const failCount = steps.length - passCount;

  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    totalSteps: steps.length,
    passCount,
    failCount,
    steps,
  };

  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

  console.log(`[showcase] report: ${path.resolve(reportPath)}`);
  console.log(`[showcase] summary: ${passCount}/${steps.length} passed, ${failCount} failed`);

  if (failCount > 0) process.exitCode = 1;
}

run().catch((error) => {
  console.error("[showcase] fatal:", error);
  process.exit(1);
});
